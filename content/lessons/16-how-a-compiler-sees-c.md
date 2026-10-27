---
title: "How a compiler turns C into assembly"
slug: 16-how-a-compiler-sees-c
part: "Part 3 — From C to machine code"
summary: Read clang's assembly at -O0 and -O2, write predicates over it, and hand-write a function that matches a C one.
minutes: 60
gpu: false
objectives:
  - Explain why clang at -O0 keeps every variable in memory and clang at -O2 keeps them in registers.
  - Read an assembly listing and ignore the directives, labels, and comments that are not instructions.
  - Spot a loop in assembly as a jump to an earlier label, and say when the optimizer removes it.
  - Recognize `lea` used as a multiply, and write one by hand.
prereqs:
  - 15-c-for-the-curious
exercise: 16-how-a-compiler-sees-c
---

# How a compiler turns C into assembly

You can write x86-64 assembly by hand, and you can write small C functions. The two are connected by a program: the compiler. A **compiler** is a program that reads source code in one language and writes an equivalent program in another. Here, clang reads C and writes assembly.

This lesson looks at what clang writes. The answer depends heavily on one flag, the **optimization level**. At `-O0` clang translates each line of C almost word for word. At `-O2` it rewrites your code, and sometimes the result looks nothing like what you wrote. Learning to read both is the first skill of anyone who tunes code or debugs a crash with no source in sight.

You will not use a debugger or a profiler yet. You will read text. By the end you will write small Python functions that ask questions about assembly, such as "does this code still have a loop?", and you will beat clang at `-O0` by hand.

## What you already know

- A function receives its first integer arguments in `edi` and `esi` and returns in `eax` (the System V convention).
- `lea` computes an address, such as `[rdi + 4*rdi]`, without reading memory.
- `cmp` plus a conditional jump makes an `if` or a loop.
- The stack holds local variables at addresses like `[rbp - 4]`.
- `cputools.c_to_asm` turns C text into assembly text, and `cputools.assemble` turns assembly text into a function you can call.

## The same function at two levels

Start with the smallest function that shows the difference. The C source is one line.

```c
int f(int x) { return x * 5; }
```

Here is what `cputools.c_to_asm(src, opt="-O0")` prints for it, with the bookkeeping lines removed. The comments are the compiler's own.

```asm
f:
    push rbp                       # save the caller's frame pointer
    mov  rbp, rsp                  # rbp marks this function's frame
    mov  dword ptr [rbp - 4], edi  # store the argument x on the stack
    imul eax, dword ptr [rbp - 4], 5   # load x, multiply by 5, put the result in eax
    pop  rbp                       # restore the caller's frame pointer
    ret
```

This is a literal translation. The argument arrives in `edi`, and the compiler immediately copies it into a stack slot, `[rbp - 4]`, because a C variable has a home in memory. The multiply reads it back out. There are six instructions, and one of them writes memory and one reads it.

Next, the same function at `-O2`.

```asm
f:
    lea eax, [rdi + 4*rdi]         # eax = x + 4x = 5x
    ret
```

Two instructions and no memory. The optimizer saw that `x` is only used once, so it never needed a stack slot. It also saw that multiplying by 5 is `x + 4*x`, and `lea` can compute that in one step because its address arithmetic allows a scale of 1, 2, 4, or 8.

The sequence of steps that turned the first listing into the second is an **optimization pass**. You will write some in lesson 22.

> [!KEY]
> At `-O0` every C variable lives in memory, so every use is a load and every assignment is a store. At `-O2` the compiler keeps values in registers and rewrites arithmetic into cheaper instructions.

### Why `-O0` still exists

`-O0` is slow, so why use it? Because it is predictable. Each C statement maps to a block of instructions, and a debugger can stop at any line and show every variable, because every variable is in memory. Optimized code has no such promise: a variable may live in a register for three instructions and then vanish.

The table below summarizes the levels that clang accepts.

| Flag | What it does |
|---|---|
| `-O0` | No optimization. Fast to compile, easy to debug. Clang's default. |
| `-O1` | Cheap passes: keep variables in registers, fold constants, remove dead code. |
| `-O2` | Everything in `-O1` plus inlining and loop rewrites. The usual choice for release builds. |
| `-O3` | `-O2` plus more aggressive loop and vector transforms. |
| `-Os` | Like `-O2`, but prefers smaller code. |

For `x * 5`, `-O1` and `-O2` produce the same two instructions. The levels differ most on loops.

## Reading a listing

A real listing has more lines than instructions. Clang prints this, trimmed to the function `f`:

```asm
    .text
    .intel_syntax noprefix
    .globl  f                       # -- Begin function f
    .p2align 4, 0x90
    .type   f,@function
f:                                  # @f
# %bb.0:
    lea eax, [rdi + 4*rdi]
    ret
.Lfunc_end0:
    .size   f, .Lfunc_end0-f
```

Four kinds of line appear. The table sorts them.

| Kind | How to spot it | Example |
|---|---|---|
| Directive | Starts with a dot. It instructs the assembler and is not run. | `.globl f`, `.p2align 4, 0x90` |
| Label | Ends with a colon. It names an address. | `f:`, `.LBB0_1:` |
| Comment | Starts with `#`. | `# %bb.0:` |
| Instruction | Anything else. This is what the CPU runs. | `lea eax, [rdi + 4*rdi]` |

A label that starts with `.L` is local to the file: clang uses `.LBB0_1` for "function 0, basic block 1". Labels without the dot, such as `f`, are function names. In Part 4 you will meet the idea behind "basic block"; for now, read it as "a stretch of code with no jumps in or out except at its ends".

The first skill the exercise asks for is to turn this text into a clean list of instructions. In Python, that is a loop over `asm.splitlines()` that cuts off the comment, strips the margins, and skips blanks, labels, and directives.

## Loops are backward jumps

Assembly has no `for` or `while`. A loop is a conditional jump to a label that appears earlier in the text. A jump to a label later in the text is an `if`.

Here is `-O0` code for summing 1 through `n`.

```c
int sum(int n) { int s = 0; for (int i = 1; i <= n; i++) s += i; return s; }
```

```asm
sum:
    push rbp
    mov  rbp, rsp
    mov  dword ptr [rbp - 4], edi    # n
    mov  dword ptr [rbp - 8], 0      # s = 0
    mov  dword ptr [rbp - 12], 1     # i = 1
.LBB0_1:
    mov  eax, dword ptr [rbp - 12]   # eax = i
    cmp  eax, dword ptr [rbp - 4]    # compare i with n
    jg   .LBB0_4                     # i > n: leave the loop (forward jump)
    mov  eax, dword ptr [rbp - 12]
    add  eax, dword ptr [rbp - 8]
    mov  dword ptr [rbp - 8], eax    # s += i
    mov  eax, dword ptr [rbp - 12]
    add  eax, 1
    mov  dword ptr [rbp - 12], eax   # i++
    jmp  .LBB0_1                     # back to the top (backward jump)
.LBB0_4:
    mov  eax, dword ptr [rbp - 8]
    pop  rbp
    ret
```

The picture below shows the jumps. The arrow that points up is the loop.

```text
  sum:
     setup
  .LBB0_1:  <------------------+
     compare i, n              |
     jg .LBB0_4 --------+      |   forward jump: leaves the loop
     s += i              |     |
     i++                 |     |
     jmp .LBB0_1 --------|-----+   backward jump: the loop
  .LBB0_4:  <-----------+
     return s
```

A predicate `has_loop(asm)` can find this without understanding any instruction. Scan the lines top to bottom, remember each label you have seen, and for every jump check whether its target is in that set. If so, the jump goes backward.

Compile the same C at `-O2`.

```asm
sum:
    test edi, edi
    jle  .LBB0_1                 # n <= 0: return 0
    lea  eax, [rdi - 1]          # eax = n - 1
    lea  ecx, [rdi - 2]          # ecx = n - 2
    imul rcx, rax                # rcx = (n - 1) * (n - 2), in 64 bits
    shr  rcx                     # rcx = rcx / 2
    lea  eax, [rcx + 2*rdi]      # eax = rcx + 2n
    dec  eax                     # eax = rcx + 2n - 1
    ret
.LBB0_1:
    xor  eax, eax                # return 0
    ret
```

The loop is gone. Clang 19 recognized the pattern "add each integer from 1 to n" and replaced it with a formula. Check it for `n = 4`: `(3 * 2) / 2 = 3`, then `3 + 2*4 - 1 = 10`, which is `1 + 2 + 3 + 4`. Every jump in this listing goes forward, so `has_loop` is false.

This is the result of one specific compiler version. A different version, or a loop with a slightly different body, may keep the loop. The next example shows a loop the optimizer cannot remove.

```c
long total(const long *a, int n) { long s = 0; for (int i = 0; i < n; i++) s += a[i]; return s; }
```

The compiler cannot guess what is in memory, so it must read every element. At `-O2` it keeps the loop and goes further: it adds two 64-bit numbers at a time with the SSE2 instruction `paddq` on `xmm` registers.

```asm
.LBB0_5:
    movdqu xmm2, xmmword ptr [rdi + rsi]        # load two longs
    paddq  xmm0, xmm2                           # add two at once
    movdqu xmm2, xmmword ptr [rdi + rsi + 16]   # load the next two
    paddq  xmm1, xmm2
    add    rsi, 32                              # 4 longs = 32 bytes
    cmp    rax, rsi
    jne    .LBB0_5                              # backward jump
```

A second, scalar loop follows it to handle the last few elements when `n` is not a multiple of four. That is **vectorization**, and lesson 25 covers it. For now, notice that `has_loop` is still true.

> [!KEY]
> A loop is a jump to an earlier label. The optimizer can delete a loop only when it can prove the result without running it.

## `lea` as arithmetic

`lea` stands for "load effective address", but clang uses it as a three-operand adder with a built-in multiply. The form `[base + scale*index + disp]` can compute `base + index*scale + disp` for scale 1, 2, 4, or 8, and it writes the result to any register without touching the flags.

| C expression | One instruction |
|---|---|
| `x * 5` | `lea eax, [rdi + 4*rdi]` |
| `x * 9 + 1` | `lea eax, [rdi + 8*rdi + 1]` |
| `x * 3` | `lea eax, [rdi + 2*rdi]` |
| `a + b` | `lea eax, [rdi + rsi]` |
| `x - 7` | `lea eax, [rdi - 7]` |

Write the destination as a 32-bit register (`eax`) and the result wraps like a C `int`. Name the 64-bit address registers on the right (`rdi`), because addresses are 64 bits wide.

Multiplying by 5 with `lea` takes one instruction and about one cycle. `imul` takes about three. That difference is why `-O2` prefers it.

## Writing assembly that matches C

You have seen enough of clang's style to match it. Your task has three parts. Take a C function, read what clang does at `-O0` and `-O2`, and write assembly that returns the same values for every input, including ones that overflow. Use the stack only when you must. A function of two integers and a few additions needs no memory at all.

Always check the wrap-around behavior. C's `int` arithmetic is 32-bit: `2147483647 + 1` stored in an `int` becomes `-2147483648` when it wraps. Writing to `eax` gives the same result in assembly. Writing to `rax` does not, because the upper half keeps its bits.

## Try it on your own machine

1. Compile a function to assembly and compare levels. Look for the line count to fall and the `[rbp - ...]` lines to disappear.

   ```bash
   printf 'int f(int x) { return x * 5; }\n' > f.c
   clang -S -masm=intel -O0 -fno-asynchronous-unwind-tables f.c -o f0.s
   clang -S -masm=intel -O2 -fno-asynchronous-unwind-tables f.c -o f2.s
   diff f0.s f2.s
   ```

2. Inspect the machine code of the compiled object. The disassembly should show the same instructions as the `.s` file, with their byte encodings.

   ```bash
   clang -c -O2 f.c -o f.o && objdump -d -M intel f.o
   ```

3. Compile the `sum` function at `-O2` and `-O1` and look for a backward jump. Try changing `s += i` to `s += i * i` or `s ^= i`, and see when the loop survives.

4. Open https://godbolt.org, paste any C function, pick x86-64 clang, and add `-O2 -masm=intel`. The colors link each C line to its instructions.

## Build it step by step

The exercise is a set of small functions over assembly text, plus one function in assembly.

1. `instructions(asm)` returns the instruction lines. For each line, cut at `#` (use `line.split("#", 1)[0]`), strip spaces, and skip it when it is empty, starts with `.`, or ends with `:`. The common mistake is to keep lines that end with a comment after the label, such as `f:   # @f`, so strip the comment first.
2. `mnemonics(asm)` returns the first word of each instruction in lowercase. Build it on `instructions`.
3. `count_instructions(asm)` returns how many instructions there are. Another one-liner on `instructions`.
4. `has_loop(asm)` scans top to bottom with a set of labels seen so far. A line that ends with a colon adds a label. A line whose first word starts with `j` is a jump, and its last word is the target. Return true when the target is already in the set. The common mistake is to scan all labels first: then forward jumps look like loops.
5. `memory_accesses(asm)` counts instructions that contain `[` but are not `lea`. Remember that `lea` writes an address without reading memory.
6. `uses_lea_times5(asm)` looks for `lea` with the pattern `[reg + 4*reg]`, with the same register twice. A regular expression with a back-reference, `(\w+)\s*\+\s*4\s*\*\s*\1`, does this. The mistake is to match `[rdi + 4*rsi]`, which is `rdi + 4*rsi`, not a multiply by 5.
7. `instruction_counts(c_source)` compiles with `cputools.c_to_asm` at `-O0` and `-O2` and returns both counts as a tuple.
8. `score_asm()` returns assembly for `int score(int a, int b) { return a * 5 + b * 8 - 3; }`. The arguments are in `edi` and `esi`. Use no memory and fewer instructions than clang's `-O0` listing. The mistake to avoid is writing the answer to `rax`: write to `eax`, so the result wraps at 32 bits.

## Where this breaks

**Optimization changes with the version.** A loop that clang 19 turns into a formula may stay a loop in clang 15. Predicates over assembly text describe one compiler's choices, so a check like "the loop is gone" is a measurement, not a law.

**Undefined behavior gives the optimizer permission.** In C, signed overflow is undefined. The compiler may assume `x + 1 > x` is always true and delete the test. Lesson 15 covered why; here you see its effect: the optimized code may not match what you expect from the unoptimized code on inputs that overflow.

**Optimized code is hard to debug.** Variables disappear into registers, and lines of source are reordered or merged. That is why `-O0` is the default and why release builds are rarely debugged line by line.

**The optimizer can delete your benchmark.** A loop whose result is never used is dead code. Benchmark code must use its result, or hide it from the optimizer.

**Text predicates are fragile.** Clang prints `inc rdx` today and could print `add rdx, 1` tomorrow. Write predicates for stable properties, such as "a backward jump exists", and not for a specific instruction sequence.

## Further reading

- [Compiler Explorer](https://godbolt.org) shows the assembly for any C snippet with a color-coded mapping to the source. It is the fastest way to build intuition for what the compiler does.
- [Felix Cloutier's x86 reference](https://www.felixcloutier.com/x86/) documents every instruction you meet in a listing, including `lea`, `imul`, and `paddq`.
- [Agner Fog's optimization manuals](https://www.agner.org/optimize/) give instruction timings and explain why `lea` is a favorite of compilers.
- [The clang command-line reference](https://clang.llvm.org/docs/CommandGuide/clang.html) lists the optimization flags and what they enable.

## The exercise

You write seven Python functions over assembly text and one assembly function. The text functions are `instructions`, `mnemonics`, `count_instructions`, `has_loop`, `memory_accesses`, and `uses_lea_times5`. `instruction_counts` calls the real compiler. The checks run your predicates on small hand-written listings and on real clang output at `-O0` and `-O2`, including the `sum` loop that disappears and the array loop that stays.

`score_asm` returns assembly for `score(a, b) = a*5 + b*8 - 3`. The checks assemble it, call it through `ctypes` in a separate child process so that a crash fails one check, and compare the result with a Python reference on edge cases, including values that overflow 32 bits. They also check that your code uses no memory and no more instructions than clang's `-O0` listing.
