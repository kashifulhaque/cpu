---
title: "Memory in IR: alloca, load, store, and mem2reg"
slug: 21-memory-in-ir
part: "Part 4 — Compilers and LLVM IR"
summary: Read and write LLVM IR that uses stack slots, pointers, arrays, and structs, and watch mem2reg turn slots back into SSA values.
minutes: 60
gpu: false
objectives:
  - Explain why clang at -O0 gives every variable an `alloca` and reads it with `load` and `store`.
  - Compute the address of an array element or a struct field with `getelementptr`.
  - Run `mem2reg` with `cputools.run_opt` and count the memory instructions that disappear.
  - Write IR that sums an array passed from Python and reads a field of a struct.
prereqs:
  - 20-control-flow-and-ssa
exercise: 21-memory-in-ir
---

# Memory in IR: alloca, load, store, and mem2reg

In lessons 19 and 20 you wrote IR where every value had a name and was assigned exactly once. That is SSA, and it is wonderful for a compiler: to know what `%x` holds, look at the one line that defines it. But a C program says `int y = x + 1; y = y * 2;` and assigns `y` twice. Programs also read arrays and structs that live in memory, not in a named value.

This lesson fills the gap. LLVM IR has a small set of instructions for memory: `alloca` to reserve a slot on the stack, `load` and `store` to read and write an address, and `getelementptr` to compute the address of an array element or a struct field. With them a front end (the part of a compiler that reads the source language) can translate any variable without worrying about SSA at all. A later pass called `mem2reg` then promotes most of those slots back into SSA values.

You will see the whole story on real clang output, then write memory-using IR yourself and call it from Python.

## What you already know

- A function in IR has basic blocks, each ending in a terminator such as `br` or `ret`.
- SSA means every `%name` is assigned once, and a `phi` picks a value based on the block you came from.
- `cputools.verify_ir`, `run_opt`, and `ir_to_lib` check IR, transform it, and load it for calls from Python.
- A pointer is an address, and in x86-64 a `mov` with brackets reads or writes memory at it.
- `ctypes` can pass pointers and arrays from Python to compiled code.

## The problem: variables that change

Take this C function.

```c
int f(int x) {
    int y = x + 1;
    return y * 2;
}
```

If a front end tried to produce pure SSA for it, it would have to track every assignment to every variable. For a loop that means working out where to put `phi` nodes, which is a real algorithm. Front ends avoid that work with a trick: give every variable a **stack slot**, a place in memory owned by the function. Writing the variable becomes a `store` to the slot. Reading it becomes a `load` from the slot. The slot is the same address all the time, so no SSA bookkeeping is needed.

This is exactly what clang does at `-O0` (no optimization). Here is the real IR, with the attribute and metadata lines at the end left out:

```llvm
define dso_local i32 @f(i32 noundef %x) #0 {
entry:
  %x.addr = alloca i32, align 4
  %y = alloca i32, align 4
  store i32 %x, ptr %x.addr, align 4
  %0 = load i32, ptr %x.addr, align 4
  %add = add nsw i32 %0, 1
  store i32 %add, ptr %y, align 4
  %1 = load i32, ptr %y, align 4
  %mul = mul nsw i32 %1, 2
  ret i32 %mul
}
```

Read it line by line:

- `%x.addr = alloca i32, align 4` reserves 4 bytes on the stack and names the **address** `%x.addr`. The result of `alloca` is a pointer, type `ptr`. The `align 4` says the address is a multiple of 4.
- `store i32 %x, ptr %x.addr, align 4` writes the parameter into its slot. Even parameters get slots, so that C code can assign to them.
- `%0 = load i32, ptr %x.addr, align 4` reads 4 bytes from that address as an `i32`.
- The arithmetic is ordinary SSA on the loaded values.

Two things to notice. First, the type on `load` and `store` says how many bytes to move and how to read them. The pointer itself carries no type: since LLVM 15 every pointer is just `ptr`. Second, `alloca` appears in the `entry` block. Clang puts every slot there, so each runs once and the frame size is fixed.

> [!KEY]
> A front end can ignore SSA by giving every variable an `alloca` slot and using `store` to assign and `load` to read. An optimization pass turns the slots back into SSA values.

## Stack slots on the real machine

An `alloca` is a stack allocation. In machine code it becomes a move of the stack pointer, or a fixed offset from it, and the `store` and `load` become `mov` instructions with a bracket address. You met this in lesson 16: clang `-O0` assembly is full of `mov DWORD PTR [rbp-4], edi`. That line is the machine-code form of `store i32 %x, ptr %x.addr`.

This is why `-O0` code is slow. Every variable access goes through the stack. The L1 cache hides much of the cost, but each access still needs a load or store instruction, and the CPU must track the dependence between a store and the load that reads it back.

## The mem2reg pass

`mem2reg` is the pass that undoes the trick. For each `alloca` whose address is only used by direct `load` and `store` instructions, it removes the slot and replaces the memory traffic with SSA values. Where two assignments can reach the same read, it inserts a `phi`.

Run it on the function above with `cputools.run_opt(ir, "mem2reg")`. The real result:

```llvm
define dso_local i32 @f(i32 noundef %x) #0 {
entry:
  %add = add nsw i32 %x, 1
  %mul = mul nsw i32 %add, 2
  ret i32 %mul
}
```

Both allocas, both stores, and both loads are gone. `%0` became `%x`, and `%1` became `%add`. The tally before and after:

| Opcode | Before | After |
|---|---|---|
| `alloca` | 2 | 0 |
| `store` | 2 | 0 |
| `load` | 2 | 0 |

A loop shows the `phi` appearing. Here is the C for a sum, and the part of the IR clang produces at `-O0` that matters:

```c
int sum(int *a, int n) {
    int s = 0;
    for (int i = 0; i < n; i++) s += a[i];
    return s;
}
```

```llvm
entry:
  %a.addr = alloca ptr, align 8
  %n.addr = alloca i32, align 4
  %s = alloca i32, align 4
  %i = alloca i32, align 4
  store ptr %a, ptr %a.addr, align 8
  store i32 %n, ptr %n.addr, align 4
  store i32 0, ptr %s, align 4
  store i32 0, ptr %i, align 4
  br label %for.cond
```

The loop body reads and writes `%s` and `%i` on every trip. After `mem2reg`, the loop header looks like this (real output, trimmed to the instructions that matter):

```llvm
for.cond:                                         ; preds = %for.inc, %entry
  %s.0 = phi i32 [ 0, %entry ], [ %add, %for.inc ]
  %i.0 = phi i32 [ 0, %entry ], [ %inc, %for.inc ]
  %cmp = icmp slt i32 %i.0, %n
  br i1 %cmp, label %for.body, label %for.end
```

The two variables `s` and `i` became two phi nodes: `0` on entry, the updated value from the back edge. All four allocas are gone. One `load` is left, the read of `a[i]`, because that reads the caller's array, not a local slot.

> [!KEY]
> `mem2reg` promotes a local variable's slot to SSA values, and it inserts a `phi` wherever control flow merges two different values of the variable. Memory that other code can see, such as the caller's array, is never promoted.

Not every `alloca` can be promoted. If the address escapes (it is passed to another function, or stored somewhere), other code may read or write the slot behind the compiler's back, and `mem2reg` leaves it alone.

## Pointers and getelementptr

Arrays and structs live in memory, and the way IR reaches inside them is `getelementptr`, often written **GEP**. It computes an address. It never touches memory itself.

The simplest form takes an element type, a base pointer, and an index:

```llvm
%p = getelementptr inbounds i32, ptr %a, i64 %i
```

Read it as "the address `%a + %i * sizeof(i32)`". For an `i32` the size is 4, so for `%i = 3` the address is `%a + 12`. The index is counted in elements of the type you named, not in bytes. That is the same rule as C pointer arithmetic: `a + 3` for an `int *a` moves 12 bytes.

The index must be an integer, and for 64-bit pointers it is normally `i64`. That is why clang's loop above has `%idxprom = sext i32 %i to i64` right before the GEP: C's `int i` is 32 bits, so it must be widened first. The word `inbounds` promises the address stays inside the object. It lets the optimizer assume more, and it makes the behavior undefined if the promise is false.

To read an element, you `load` from the address the GEP made:

```llvm
%idx = sext i32 %i to i64
%p   = getelementptr inbounds i32, ptr %a, i64 %idx
%v   = load i32, ptr %p
```

Three lines: widen the index, compute the address, read four bytes from it.

### Structs

A struct type in IR is a list of field types. For a C struct with an `int` and a `long`:

```c
struct P { int a; long b; };
```

clang emits `%struct.P = type { i32, i64 }`. To reach field `b`, GEP takes two indices after the base pointer:

```llvm
%b = getelementptr inbounds %struct.P, ptr %0, i32 0, i32 1
```

The first index (`0`) steps over whole structs: `0` means "this struct, not the next one in an array". The second index (`1`) picks the field. The values are field numbers, not byte offsets. The compiler computes the byte offset from the **data layout**, a line at the top of every module that describes sizes and alignments. On x86-64 an `i64` must start at a multiple of 8, so there are 4 bytes of padding after the `i32`, and field 1 is at byte 8. You can check this against Python: `ctypes.Structure` with an `int32` and an `int64` field puts the second at offset 8.

### Arrays in alloca

An `alloca` can also reserve many elements. A local array `int v[4]` is `%v = alloca [4 x i32]`, and its element `2` is:

```llvm
%e = getelementptr inbounds [4 x i32], ptr %v, i64 0, i64 2
```

The first index again steps over whole `[4 x i32]` objects, and the second picks the element. The address is `%v + 8`.

> [!TIP]
> To read the address a GEP computes, multiply the last index by the size of the type, then add the earlier steps. When the layout puzzles you, ask clang: write the C struct and look at `cputools.c_to_ir`.

## Try it on your own machine

Each command runs on Linux or macOS with clang installed.

1. Write a file `f.c` with the `f` function from this lesson, then run `clang -S -emit-llvm -O0 -Xclang -disable-O0-optnone -fno-discard-value-names f.c -o f.ll`. Open `f.ll` and find the `alloca`, `store`, and `load` lines. The extra `-Xclang` flag keeps `opt` from skipping the function.
2. Run `opt -S -passes=mem2reg f.ll`. The memory instructions disappear. Compare the line counts with `wc -l` on both files.
3. Run `llc -O0 f.ll -o - --x86-asm-syntax=intel`. Find the `mov` instructions that touch `[rbp - 4]`: they are the stores and loads of your slots.
4. Write a C function that takes `struct P *p` and returns `p->b`, compile it with `-S -emit-llvm`, and find the `getelementptr` with two indices.
5. Take the address of a local, for example pass `&y` to a function you declare but do not define, then run `mem2reg`. The `alloca` for `y` stays, because its address escapes.

> [!RECAP]
> - `alloca` reserves a stack slot and returns its address; `store` writes through an address and `load` reads through one.
> - Clang at `-O0` gives every variable a slot, and `mem2reg` turns the slots back into SSA values with `phi` nodes.
> - `getelementptr` computes an address from a base pointer and indices, and never touches memory.
> - A struct GEP takes `i32 0, i32 N`: the first index steps over whole structs and the second picks the field.

## Build it step by step

You write six functions in `starter.py`. The first two are Python tools over IR text. The last four are IR that you hand-write as strings returned from `def xxx_ir() -> str:`.

1. `count_opcodes(ir)` takes IR text and returns a dict from opcode to count, over the instructions inside function bodies. Walk the lines. Track whether you are inside a `define ... {` ... `}` pair. Skip blank lines, comments (everything after `;`), and labels. Take the first word after `%name = `, or the first word when there is no assignment. The common mistake is counting a label like `entry:` or a `declare` line as an instruction.

2. `mem2reg_report(c_source)` compiles the C with `cputools.c_to_ir(src, opt="-O0")`, runs `cputools.run_opt(ir, "mem2reg")`, and returns `{"before": ..., "after": ...}`, each holding the counts of `alloca`, `load`, `store`, and `phi` with zero for an absent opcode. The common mistake is leaving out `-O0`: at `-O1` and above clang has already promoted the slots, so "before" would already be clean.

3. `swap_ir()` returns a module with `@swap(ptr %a, ptr %b)` that exchanges two `i32` values. Load both values first, then store them crosswise. Storing one before loading the other overwrites a value you still need.

4. `sum_array_ir()` returns `@sum_array(ptr %a, i32 %n)` that returns the sum of `n` ints. Use a loop with `phi` nodes or with allocas, as you like, and `getelementptr` to reach each element. The common mistake is passing an `i32` index to the GEP without `sext` to `i64`, which the verifier rejects or which gives wrong addresses for large indices.

5. `get_b_ir()` returns a module with `%Point = type { i32, i64 }`, a function `@get_b` that returns field 1, and `@set_a` that stores into field 0. Use the struct type in both GEPs. The common mistake is giving only one index: a struct GEP needs `i32 0, i32 N`.

6. `local_sum_ir()` returns `@local_sum(i32 %n)` that sums `1..n` the way clang `-O0` would: variables in `alloca` slots, no `phi` at all. Put the `alloca` instructions in the `entry` block and store the starting values before the loop. The checks run `mem2reg` on your IR and expect the allocas to vanish and phis to appear.

When a function raises `ToolError`, read the message: it is the verifier's or clang's own text, with the line and column.

## Where this breaks

- **Escaping addresses block promotion.** If you pass the address of a local to a function, or store it in a global, `mem2reg` cannot promote the slot. Real compilers first inline small callees so the address stops escaping, then promote.
- **Structs and arrays are not promoted by `mem2reg`.** It only promotes scalar slots. A different pass, SROA (scalar replacement of aggregates), splits a struct slot into one slot per field and then lets `mem2reg` finish the work. In real clang pipelines SROA runs first, and its output looks much like `mem2reg`'s.
- **Aliasing limits what the optimizer can assume.** Two pointers might point to the same memory, so a store through one may change a load through the other. Without proof, the optimizer must keep both memory operations in order. C's `restrict` keyword and IR's `noalias` attribute give the proof.
- **`inbounds` is a promise, not a check.** An out-of-range `inbounds` GEP produces a poison value, and using it is undefined behavior. LLVM will not add a bounds check for you.
- **Memory is slow when it is real.** After `mem2reg` an SSA value can live in a register. A value in memory stays in memory, and each access can cost a cache miss. Lesson 24 shows how the back end decides which values get registers.

## Further reading

- [LLVM Language Reference: memory access and addressing](https://llvm.org/docs/LangRef.html#memory-access-and-addressing-operations) — the exact meaning of `alloca`, `load`, `store`, and `getelementptr`.
- [The Often Misunderstood GEP Instruction](https://llvm.org/docs/GetElementPtr.html) — why GEP only computes an address and what the two-index struct form means.
- [LLVM Passes: mem2reg](https://llvm.org/docs/Passes.html#mem2reg-promote-memory-to-register) — the pass's own description, with its conditions for promotion.
- [Kaleidoscope tutorial, chapter 7: mutable variables](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/LangImpl07.html) — the same alloca trick, used by a real front end, in the chapter that comes just before the code you write in lesson 23.
- [Compiler Explorer](https://godbolt.org) — type C and pick "LLVM IR" output to see `alloca`, `load`, and `store` for any function.

## The exercise

In `starter.py` you write `count_opcodes`, `mem2reg_report`, `swap_ir`, `sum_array_ir`, `get_b_ir`, and `local_sum_ir`. The checks verify your IR with `cputools.verify_ir`, compile it with `cputools.ir_to_lib`, and call it from Python through `ctypes` with real arrays and structs. The compiled code runs in a child process, so a wrong address fails the check and does not stop the run.

The checks compare `mem2reg_report` with the counts for the two C functions in this lesson, require your `sum_array_ir` text to use `getelementptr`, and require `local_sum_ir` to hold at least two allocas and no `phi` before `mem2reg` and no alloca after it.
