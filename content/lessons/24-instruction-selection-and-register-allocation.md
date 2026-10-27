---
title: "Instruction selection and register allocation"
slug: 24-instruction-selection-and-register-allocation
part: "Part 5 — The back end and performance"
summary: Compute liveness, build an interference graph, color it with K registers and spills, and emit x86-64 you can run.
minutes: 75
gpu: false
objectives:
  - Compute which variables are live at each instruction, including across a loop.
  - Build an interference graph and explain what an edge means.
  - Color the graph with K colors, and spill a variable to the stack when K is too few.
  - Emit x86-64 for a small IR with variables in registers and stack slots, and run it.
prereqs:
  - 23-generating-llvm-ir
exercise: 24-instruction-selection-and-register-allocation
---

# Instruction selection and register allocation

IR has as many values as the program needs: `%t0`, `%t1`, `%t2`, thousands of them. An x86-64 CPU has 16 general-purpose registers, and two of them (`rsp` and often `rbp`) are spoken for. Somewhere between IR and machine code, a part of the compiler called the **back end** has to decide which value goes in which register, and where the rest go.

The back end has two jobs. **Instruction selection** picks machine instructions that do what each IR operation says. **Register allocation** decides where each value lives: in a register, or in memory when no register is free. Both are choices among correct answers, and the quality of the choices decides how fast the program runs.

This lesson builds a small back end. You compute which values are alive when, turn that into a graph, color the graph so no two values that are alive together share a register, and emit real x86-64 that you run from Python.

## What you already know

- A register is a small, fast storage slot inside the CPU, and x86-64 has 16 general-purpose ones.
- An instruction like `add rax, rcx` reads and writes registers; with a bracket operand it reads or writes memory.
- The System V calling convention passes the first two integer arguments in `rdi` and `rsi` and returns in `rax`.
- A loop is a backward jump, and its variables are updated on every trip.
- `cputools.assemble` turns Intel-syntax assembly text into a library you call with `ctypes`.

## A small IR with variables

The IR here is the three-address code from lesson 22 with two changes. It has jumps and labels, so a program can loop. And a name may be assigned more than once: it is not SSA. That keeps register allocation easy to see, because a variable is a named location.

| Instruction | Meaning |
|---|---|
| `d = const n` | set `d` to the integer `n` |
| `d = copy a` | `d` gets the value of `a` |
| `d = add a b`, `sub`, `mul` | arithmetic on two names |
| `L:` | a label |
| `jmp L` | jump to `L` |
| `jnz a L` | jump to `L` if `a` is not zero, else continue |
| `ret a` | return `a` |

Here is a function that sums `n + (n-1) + ... + 1`:

```text
sum_to(n):
  0: s = const 0
  1: top:
  2: s = add s n
  3: one = const 1
  4: n = sub n one
  5: jnz n top
  6: ret s
```

It has three variables: `n`, `s`, and `one`. Do they all need their own register?

## Liveness

A variable is **live** at a point in the program if some path from that point reads it before writing it again. Think of a variable as a note you keep on your desk. It is live from the moment you write it until the last time you read it. In between, the note occupies desk space. After the last read, you can throw it away and reuse the space.

Two sets describe each instruction `i`:

- `live_in[i]` holds the variables live just before it runs.
- `live_out[i]` holds the variables live just after it runs.

The rules follow from the definition:

```text
live_in[i]  = uses(i)  ∪  (live_out[i] − defs(i))
live_out[i] = union of live_in[j] for every successor j of i
```

The first rule says: whatever instruction `i` reads is live before it. Whatever is live after it stays live before it, unless `i` just wrote it, because the old value is then dead. The second says that a variable is live after `i` if any instruction that can run next needs it. A **successor** is an instruction that can run right after `i`. For most instructions that is the next one. For `jmp` it is the label's position, and for `jnz` it is both the next instruction and the label.

Start with straight-line code, with no jumps. This function has parameters `a` and `b`:

```text
0: t1 = add a b
1: t2 = mul t1 a
2: t3 = sub t2 b
3: ret t3
```

Work backward from the end. `ret t3` reads `t3`, so `live_in[3] = {t3}` and `live_out[3] = {}`. Each step up applies the two rules:

| i | Instruction | live_out | live_in |
|---|---|---|---|
| 3 | `ret t3` | {} | {t3} |
| 2 | `t3 = sub t2 b` | {t3} | {t2, b} |
| 1 | `t2 = mul t1 a` | {b, t2} | {t1, a, b} |
| 0 | `t1 = add a b` | {a, b, t1} | {a, b} |

At instruction 1, three values are live before it: `t1`, `a`, and `b`. So three registers are needed at that moment. Variable `a` is live from the start through instruction 1, then dies. `b` lives to instruction 2.

### Loops

A loop makes the second rule circular. The `jnz` at the end of `sum_to` jumps back to `top`, so what is live at `top` depends on what is live after the `jnz`, which depends on `top`. You cannot compute it in one backward pass.

The fix is to repeat. Start with every set empty. Apply both rules to every instruction. If any set changed, do it again. Stop when a whole pass changes nothing. This is a **fixed point**, like the one in lesson 22. Sets only grow, and there are finitely many variables, so it always stops.

For `sum_to`, the fixed point is:

| i | Instruction | live_in | live_out |
|---|---|---|---|
| 0 | `s = const 0` | {n} | {n, s} |
| 1 | `top:` | {n, s} | {n, s} |
| 2 | `s = add s n` | {n, s} | {n, s} |
| 3 | `one = const 1` | {n, s} | {n, s, one} |
| 4 | `n = sub n one` | {n, s, one} | {n, s} |
| 5 | `jnz n top` | {n, s} | {n, s} |
| 6 | `ret s` | {s} | {} |

Notice that `n` is live through the whole loop. It is read at instruction 2 and 4 on this trip, and the back edge brings it to the next trip. A single pass in program order would miss that.

> [!KEY]
> A variable is live from a write to the last read that can follow it on any path. Loops make that a circular definition, so the compiler repeats the computation until nothing changes.

## The interference graph

Two variables **interfere** if they are alive at the same time: they need different registers. Capture that in a graph. Each variable is a **node**. An **edge** between two nodes means they interfere.

The rule: for each instruction that writes a variable `d`, draw an edge from `d` to every other variable in `live_out`. Writing `d` must not overwrite something still needed after the instruction. Also, the parameters arrive together, so they all interfere with each other.

For the straight-line function:

```text
a ---- b ---- t2
 \    /
  \  /
   t1             t3 (no edges)
```

Instruction 0 writes `t1`, and `a` and `b` are in `live_out`: edges `t1–a`, `t1–b`. Instruction 1 writes `t2` while `b` is live: edge `t2–b`. Instruction 2 writes `t3`, and only `t3` is live after it: no edge. The parameters give `a–b`.

For `sum_to`, the loop makes `n`, `s`, and `one` all interfere: a triangle. Three variables, each alive when the other two are, need three registers. That is the minimum for this code.

## Coloring the graph

Now give each node a register so that neighbors differ. This is **graph coloring**: assign each node one of K colors so that no edge joins two nodes of the same color. Each color is a register. Coloring with the fewest colors is NP-complete, which means no fast method is known for all graphs. Compilers use a heuristic that is fast and usually good.

The heuristic has two phases.

**Simplify.** A node with fewer than K neighbors is easy: whatever colors its neighbors take, one of the K colors is free for it. So remove it from the graph and push it on a stack. Removing it lowers its neighbors' degrees, which may make them easy. Keep going.

**Select.** When the graph is empty, pop the stack. Each node is added back, in reverse order. Give it the lowest color that none of its already-colored neighbors uses.

If at some point every remaining node has K or more neighbors, you are stuck. Pick a node anyway, the one with the most neighbors, and push it. It may still get a color in the select phase, because its neighbors might not use all K colors. If it does not, there is no color for it. That node is a **spill**: it lives in memory instead.

Here is `K4`, four nodes that all interfere, with K = 3:

```text
a --- b       Simplify: every node has 3 neighbors, not fewer than 3.
| \ / |       Stuck. Push the node with the most neighbors (tie: smallest name): a.
| / \ |       Then b, c, d have 2 neighbors each: easy. Push b, c, d.
c --- d       Select: pop d -> color 0, c -> color 1, b -> color 2, a -> none free: spill.
```

Four values that are all alive together cannot fit in three registers, so one must go to memory. The heuristic found the minimum: one spill. This version, which pushes the stuck node and hopes, is **optimistic coloring**. The 1981 original by Gregory Chaitin spilled the stuck node at once. Preston Briggs and others later showed that trying first, as above, often saves a spill.

> [!KEY]
> Register allocation is graph coloring: nodes are variables, edges mean "alive together", and colors are registers. A node with fewer than K neighbors is always colorable, so remove those first.

## Spilling

A **spilled** variable lives in a stack slot instead of a register. Every read and write of it becomes a memory access. The CPU can read a memory operand directly in many instructions, so a spill costs an extra load or store, usually an L1 hit of 4 to 5 cycles of latency, not a disaster, but not free.

Real compilers choose spills carefully: a variable used in an inner loop is a bad one to spill, and one used once is a good one. Your allocator uses a simple rule, the node with the most neighbors, and a simple scheme: a spilled variable stays in memory for its whole life.

## Instruction selection

With every variable placed, the back end writes x86-64. Each IR operation maps to one or a few instructions:

| IR | x86-64 (Intel syntax) |
|---|---|
| `d = const n` | `mov d, n` |
| `d = add a b` | `mov rax, a` then `add rax, b` then `mov d, rax` |
| `d = mul a b` | the same, with `imul rax, b` |
| `d = sub a b` | the same, with `sub rax, b` |
| `jnz a L` | `cmp a, 0` then `jne .LL` |
| `L:` | `.LL:` |
| `ret a` | `mov rax, a` then `ret` |

Why `rax` in the middle? On x86-64, an instruction cannot have two memory operands. If `a` and `d` are both spilled, `add d, a` has no encoding. Routing everything through `rax` makes every case valid: `rax` is a **scratch register** that the allocator never gives out. Parameters arrive in `rdi` and `rsi`, so the allocator may use only the registers `REGS = rcx, r8, r9, r10, r11`. None of them is a parameter register, which means moving the parameters to their homes cannot overwrite a parameter that has not been moved yet.

A spilled variable is `qword ptr [rsp + 8*slot]`. The function reserves space with `sub rsp, 8*nslots` at the start, and gives it back with `add rsp, 8*nslots` before each `ret`. `qword` means 8 bytes, and `ptr` marks the bracket as a memory operand.

Here is the reference solution's real output for `sum_to` with K = 3. Nothing spills:

```asm
sum_to:
  mov r9, rdi          # n lives in r9
  mov rcx, 0           # s lives in rcx
.Ltop:
  mov rax, rcx
  add rax, r9          # s = s + n, through rax
  mov rcx, rax
  mov r8, 1            # one lives in r8
  mov rax, r9
  sub rax, r8          # n = n - one
  mov r9, rax
  cmp r9, 0
  jne .Ltop
  mov rax, rcx
  ret
```

Every operation has an extra `mov` through `rax`. A real instruction selector avoids them. Compare what clang does at `-O2` for `long f(long a, long b) { return (a + b) * a - b; }`:

```asm
f:
  lea rax, [rsi + rdi]    # a + b, in one instruction, into a fresh register
  imul rax, rdi           # * a
  sub rax, rsi            # - b
  ret
```

Four instructions. It uses `lea`, which computes `rsi + rdi` without changing either register, and does the whole computation in `rax`. At `-O0`, clang does what your generator does: it stores `rdi` and `rsi` into the stack at `[rbp - 8]` and `[rbp - 16]` and reads them back. The difference between `-O0` and `-O2` is largely register allocation.

Real instruction selection is **pattern matching on a graph of IR operations**. LLVM's selector knows that an add can often be a `lea`, and that a multiply by a constant can be a shift. Your selector maps each IR instruction on its own and does no such matching.

## Try it on your own machine

Each command works on Linux with clang installed. On macOS the assembly differs.

1. Write the `f` function above as `f.c`, then run `clang -S -O0 -masm=intel f.c -o -` and `clang -S -O2 -masm=intel f.c -o -`. Compare how many instructions touch memory.
2. Write a C function that keeps 20 values alive at once, for example by loading 20 array elements and adding them in a different order. Compile it with `-O2` and count the `[rsp + ...]` accesses: those are spills.
3. Run `objdump -d -M intel a.out` on a compiled program and look for `push` and `pop` of callee-saved registers at the start and end of a function: the calling convention forces those saves.

> [!RECAP]
> - A variable is live from a write to its last possible read, and loops need a repeat-until-stable computation.
> - Two variables interfere when one is written while the other is live; that is an edge in the interference graph.
> - Coloring the graph with K colors assigns K registers, and a node that cannot be colored spills to a stack slot.
> - Instruction selection maps each IR operation to x86-64, using `rax` as scratch so memory operands work.

## Build it step by step

The starter holds the IR, `parse_program`, and three helpers: `uses`, `defs`, and `successors`. You write five functions.

1. `liveness(prog)` returns `(live_in, live_out)`, two lists with one set per instruction, labels included. Loop until nothing changes. The common mistake is one backward pass: it gets straight-line code right and loops wrong.

2. `interference_graph(prog)` returns a dict from each variable to the set of its neighbors. Every variable is a key, even one with no edges. Add an edge between each defined name and every other name in `live_out`, and between every pair of parameters. The common mistake is adding an edge only one way. The graph must be symmetric.

3. `color_graph(graph, k)` returns `(colors, spilled)`. Simplify with a working copy of the graph, then select against the original graph. Ties go to the smallest name, so the checks can predict your result. The common mistake is checking neighbors in the working copy during select. Removed nodes must count.

4. `allocate(prog, k)` calls the two functions above, maps color `c` to `REGS[c]`, and gives spilled variables the slot numbers 0, 1, 2 in name order. It returns an `Allocation` with a `reg` dict and a `slot` dict.

5. `emit_x86(prog, alloc)` returns assembly text. Define a helper `loc(name)` that gives the register or the `qword ptr [rsp + ...]` operand, then walk the instructions, using `rax` as the scratch register. The common mistake is forgetting `add rsp, ...` before `ret`, which returns to a garbage address and crashes. The checks run your code in a child process, so that shows up as a failed check, not a dead run.


## Where this breaks

- **Coloring is only a heuristic.** Finding the best allocation is NP-complete. LLVM's default, the greedy allocator, does something quite different, with priority queues, live-range splitting, and eviction. The graph-coloring method here is the classic textbook one and is used in some production compilers.
- **Real registers are not interchangeable.** Division needs `rax` and `rdx`. Shifts by a variable need `cl`. Calls clobber some registers and preserve others, so a value alive across a call prefers a callee-saved register. Allocators handle these as constraints on the graph.
- **Spill code costs.** A bad spill in an inner loop can slow a program a lot. That is why allocators weigh each variable by how often it executes.
- **Your selector is naive.** Every operation takes at least two instructions. Real selectors use `lea`, memory operands, and instruction patterns specific to the CPU. For a C version of `sum_to`, clang `-O2` emits no loop at all: it works out the closed-form answer with a few multiplications.

## Further reading

- [LLVM Code Generator documentation](https://llvm.org/docs/CodeGenerator.html) — how LLVM selects instructions and allocates registers, with the stages named.
- [Compiler Explorer](https://godbolt.org) — compile the same C at `-O0` and `-O2` and watch the stack traffic disappear.
- [Felix Cloutier's x86 reference](https://www.felixcloutier.com/x86/) — every instruction this lesson emits, including `imul`, `cmp`, `lea`, and the conditional jumps.
- [Agner Fog's optimization manuals](https://www.agner.org/optimize/) — instruction latencies and throughput for real CPUs, which are what instruction selection is trying to minimize.

## The exercise

In `starter.py` you write `liveness`, `interference_graph`, `color_graph`, `allocate`, and `emit_x86`. The checks compare liveness sets and interference graphs with hand-computed answers for a straight-line function and a loop. They check that `color_graph` colors random graphs validly, with the right number of spills on small cases like `K4`. They then assemble your output with `cputools.assemble` and run it in a child process, so a wrong jump or a broken stack is a failed check and not a crash of the whole run.

The generated code is compared with a Python interpreter on many inputs: straight-line and looping programs, including random ones from a seeded generator, with 5, 3, 2, and 1 registers, so spilled and unspilled paths both run. Two checks read your assembly text: when nothing spills, it must not touch `rsp`, and it must not use registers outside the first `K` of `REGS`.
