---
title: "Performance, vectorization, and SIMD"
slug: 25-performance-and-simd
part: "Part 5 — The back end and performance"
summary: Measure the same C loop at -O0, -O2, and -O3, find the vector instructions in its assembly, and write an SSE2 loop yourself.
minutes: 70
gpu: false
objectives:
  - Measure a loop fairly, and say why a timing is a report and not a proof.
  - Find packed vector instructions and register widths in clang's assembly output.
  - Explain what SIMD means, and what `paddd` does to an xmm register.
  - Write an SSE2 loop that adds four `int32` values at a time, with a scalar tail for the leftovers.
prereqs:
  - 24-instruction-selection-and-register-allocation
exercise: 25-performance-and-simd
---

# Performance, vectorization, and SIMD

You have followed a program from C to IR to machine code. This lesson asks the last question: how fast does it run, and what can the compiler and you do about it? The answer starts with a surprise. The same C loop, compiled with different flags, can run four to five times faster, and nothing in the source changed.

Part of that speedup comes from the passes and register allocation you have already seen. The rest comes from a different idea: doing several operations with one instruction. A modern CPU has registers that are wider than 64 bits, and instructions that treat them as a row of small numbers and work on all of them at once. This is **SIMD**, which stands for single instruction, multiple data. A compiler that uses it automatically is **vectorizing** your loop.

In this lesson you measure a loop at three optimization settings, find the vector instructions in the assembly, and write a vectorized loop in assembly by hand.

## What you already know

- Clang's `-O0` keeps every variable in memory, and `-O2` keeps values in registers.
- An x86-64 instruction like `add eax, ebx` works on one 32-bit value in a register.
- A memory operand such as `[rsi + rax*4]` reads the element at index `rax` of an array of 4-byte values.
- A loop is a counter, a body, a compare, and a backward jump.
- `cputools.c_to_asm`, `compile_c`, and `assemble` turn C or assembly into assembly text or a library.

## The loop

Here is the function the whole lesson uses. It adds two arrays of 32-bit integers, element by element, into a third:

```c
void add_arrays(int *dst, const int *a, const int *b, long n) {
    for (long i = 0; i < n; i++)
        dst[i] = a[i] + b[i];
}
```

Each trip through the loop does two loads, one add, and one store. With `n` in the millions, the loop runs the same four operations millions of times. That makes it a good subject: any speedup has to come from doing those operations more cheaply.

## Measuring honestly

Timing code is harder than it looks. The first call runs slowly because memory pages are touched for the first time. Another process steals the core for a moment. The CPU changes its clock speed. A single number can be off by a factor of two for reasons that have nothing to do with your code.

A fair measurement follows a few habits:

- Run the function several times and keep the **smallest** time. The minimum is the run with the least interference.
- Make the data large enough that the call takes at least a fraction of a millisecond, or the timer's own cost dominates.
- Change one thing at a time: compile the same source with different flags.
- Report the machine. A number without a CPU model is not much use.

The checks in this exercise follow one more rule: they never pass or fail on a time. Timing depends on the machine, and the machine here is a shared two-core virtual machine. The checks report times with `timed` and verify results instead.

> [!KEY]
> A timing describes one program on one machine at one moment. Use it to learn, report it with the machine, and never treat it as a test.

## Three optimization settings

`cputools.compile_c(src, opt="-O0")` compiles with no optimization. `-O2` is the usual setting for release builds. `-O3` is more aggressive about unrolling and vectorizing. The exercise also compiles at `-O3 -mavx2`, which lets the compiler use the AVX2 instruction set. It uses explicit flags rather than `-march=native`. The `native` setting means "the CPU of the machine running the compiler", so the output would depend on where you run it.

Here are the results of one run of the exercise's loop on a two-core virtual machine with an Intel Skylake-class Xeon. Your numbers will differ.

| Setting | 4,096 elements (fits in cache) | 8,000,000 elements (from memory) |
|---|---|---|
| `-O0` | 3.2 ns per element | 3.2 ns per element |
| `-O2` | 0.62 ns | 1.06 ns |
| `-O3 -mavx2` | 0.59 ns | 1.03 ns |
| your SSE2 loop | 0.62 ns | 1.08 ns |

Three things stand out. First, `-O0` is five times slower than `-O2` in cache and three times slower from memory. Second, `-O3 -mavx2` is barely faster than `-O2`, although its instructions are twice as wide. Third, the large array is slower per element than the small one for every setting except `-O0`: the data no longer fits in cache, and memory cannot feed the CPU as fast as the CPU can add.

Wider vectors help when the loop is limited by arithmetic. This loop is limited by loads and stores, so doubling the add width adds little. Lesson 9 showed why: the cache hierarchy sets the speed.

## Finding vector code in assembly

The speedup from `-O0` to `-O2` has two parts. Less memory traffic is one. Vectorization is the other. You can see it in the assembly. Here is the core of the real `-O2` output of `cputools.c_to_asm(src, opt="-O2")`, with the setup and cleanup left out:

```asm
.LBB0_10:
    movdqu  xmm0, xmmword ptr [rsi + 4*r8]
    movdqu  xmm1, xmmword ptr [rsi + 4*r8 + 16]
    movdqu  xmm2, xmmword ptr [rdx + 4*r8]
    paddd   xmm2, xmm0
    movdqu  xmm0, xmmword ptr [rdx + 4*r8 + 16]
    paddd   xmm0, xmm1
    movdqu  xmmword ptr [rdi + 4*r8], xmm2
    movdqu  xmmword ptr [rdi + 4*r8 + 16], xmm0
    add     r8, 8
    cmp     rax, r8
    jne     .LBB0_10
```

The index `r8` goes up by 8 per trip. Each trip loads two groups of four ints from `a`, two from `b`, adds them with two `paddd`, and stores two groups of four. That is eight elements per trip. The loop was also **unrolled** by two: it does two vector adds per trip to amortize the cost of the counter and the branch.

At `-O3 -mavx2`, the same loop uses `vmovdqu` and `vpaddd` with `ymm` registers, which hold eight ints each. The `v` prefix marks an instruction that uses the AVX encoding.

To look for vector code automatically, look at the instruction names and the registers they name. This is the first function you write, `vector_width(asm)`. It reports the widest packed arithmetic register in the text:

| Text | Meaning | Width |
|---|---|---|
| `paddd xmm0, xmm1` | packed 32-bit integer add, SSE2 | 128 |
| `vpaddd ymm0, ymm1, ymm2` | the same with AVX2 | 256 |
| `addps xmm0, xmm1` | packed single-precision float add | 128 |
| `addss xmm0, xmm1` | scalar float add: one value | 0 |
| `movdqu xmm0, [rdi]` | a move, not arithmetic | 0 |

The `p` in `paddd` stands for packed, and the last letter says the element size: `b` byte, `w` 16-bit word, `d` 32-bit doubleword, `q` 64-bit quadword. So `paddd` adds packed doublewords. For floats, `ps` means packed single (32-bit) and `pd` packed double (64-bit). The scalar forms, `ss` and `sd`, use only the lowest lane of the register, so they do not count.

## SIMD registers and paddd

An **xmm register** is 128 bits wide. SSE2, introduced in 2001, is part of the x86-64 baseline, so every x86-64 CPU has 16 xmm registers (`xmm0` through `xmm15`). An xmm register can hold four 32-bit integers, which are called **lanes**:

```text
xmm0   +----------+----------+----------+----------+
       |  a[i+3]  |  a[i+2]  |  a[i+1]  |   a[i]   |    128 bits = 4 lanes of 32 bits
       +----------+----------+----------+----------+
xmm1   +----------+----------+----------+----------+
       |  b[i+3]  |  b[i+2]  |  b[i+1]  |   b[i]   |
       +----------+----------+----------+----------+

paddd xmm0, xmm1:  each lane is added to the lane above it, separately

xmm0   +----------+----------+----------+----------+
       | a3 + b3  | a2 + b2  | a1 + b1  | a0 + b0  |
       +----------+----------+----------+----------+
```

Lane 0 sits at the low end, which is the lowest memory address, because x86-64 is little-endian (lesson 2). There is no carry from one lane into the next: each lane wraps around by itself, exactly like a 32-bit `add`. So `paddd` gives the same answer as four separate adds, in about the time of one.

AVX2 doubles the width to 256 bits with `ymm` registers, and AVX-512 doubles it again with `zmm`. Each wider set needs a CPU that supports it. A program using AVX2 instructions on a CPU without them fails with an illegal-instruction fault. That is why the exercise's helper `cpu_has_avx2()` reads `/proc/cpuinfo` before calling the AVX2 library.

> [!KEY]
> SIMD does the same operation on several values packed into one wide register. `paddd` on an xmm register is four 32-bit additions, with no carry between lanes.

## Writing the loop by hand

Now write `add_arrays` in assembly. The System V convention puts the arguments in `rdi` (dst), `rsi` (a), `rdx` (b), and `rcx` (n). Because `n` is a `long`, all 64 bits of `rcx` are valid.

The plan has two loops. The **vector loop** handles four elements per trip. The **tail loop** handles the 0 to 3 leftovers one at a time. In C the shape is:

```c
long i = 0;
while (i + 4 <= n) {        // vector loop
    /* dst[i..i+3] = a[i..i+3] + b[i..i+3] with one paddd */
    i += 4;
}
while (i < n) {             // tail loop
    dst[i] = a[i] + b[i];
    i += 1;
}
```

For an array of 11 elements, the vector loop runs twice (elements 0 to 7), and the tail loop runs three times (elements 8 to 10). For an array of 2 elements, the vector loop runs zero times and the tail runs twice. Both loops must handle `n = 0`.

The vector loop body has four instructions, each with an addressing mode you know from lesson 13:

```asm
movdqu xmm0, [rsi + rax*4]    # load four ints from a
movdqu xmm1, [rdx + rax*4]    # load four ints from b
paddd  xmm0, xmm1             # four adds
movdqu [rdi + rax*4], xmm0    # store four ints to dst
```

`movdqu` means "move double quadword unaligned". It moves 16 bytes between an xmm register and memory at any address. The aligned version, `movdqa`, faults if the address is not a multiple of 16. Your array pointers come from Python's `ctypes` or from the middle of a bigger array, so you cannot assume alignment. Use `movdqu`. On modern CPUs it costs the same as `movdqa` when the address happens to be aligned.

The tail loop uses 32-bit scalar instructions on one element at a time. Here is the question to answer when you write it: after the vector loop ends, how many elements are left, and what is `i`? The vector loop stops when fewer than four remain. The tail loop starts from that same `i`, so you need no separate counter.

The code the compiler wrote at `-O2` has the same two-loop structure. It also has extra checks before the vector loop: it tests whether `dst` overlaps `a` or `b` closer than 32 bytes, and falls back to the scalar loop if so. Your loop needs no such check, because loading before storing makes overlap safe for any `dst`. When `dst` is `a`, each trip reads its four elements before it writes them back.

> [!WARNING]
> A vector loop that does not handle the leftover elements is the most common bug. It passes when `n` is a multiple of 4 and silently skips elements, or writes past the end, for every other length. The checks try lengths 0 to 17 on purpose.

## Try it on your own machine

Each command works on Linux with clang installed.

1. Save `add_arrays` as `f.c`. Run `clang -O2 -S -masm=intel f.c -o - | grep -E 'paddd|xmm'`. You see `paddd` and `xmm` registers.
2. Run the same with `-O0`. The grep finds nothing, because the loop is scalar.
3. Run `clang -O3 -mavx2 -S -masm=intel f.c -o - | grep -E 'vpaddd|ymm'`. You see 256-bit registers.
4. Run `grep -m1 flags /proc/cpuinfo | tr ' ' '\n' | grep -E '^(sse2|avx|avx2|avx512f)$'` to see which vector instruction sets your CPU has.
5. Run `clang -O2 -Rpass=loop-vectorize -c f.c -o /dev/null`. Clang prints a remark that says the loop was vectorized and gives the vectorization factor.

> [!RECAP]
> - A timing is a report from one machine; take the minimum of several runs and never pass or fail on it.
> - Vectorized code shows packed instructions such as `paddd` on `xmm` registers (128 bits) or `vpaddd` on `ymm` (256 bits).
> - `paddd` adds four 32-bit lanes at once with no carry between lanes.
> - A hand-written vector loop needs `movdqu` for unaligned data and a scalar tail for the leftover 0 to 3 elements.

## Build it step by step

The starter provides `VARIANTS` (the three compiler settings), `cpu_has_avx2`, and `call_add`, which calls `add_arrays` on Python lists. You write six functions.

1. `add_arrays_c()` returns the C source above. Keep the signature exactly: `void add_arrays(int *dst, const int *a, const int *b, long n)`. A `long` index makes the loop one the vectorizer handles well.

2. `vector_width(asm)` takes assembly text and returns 0, 128, 256, or 512. Strip comments, take the first word of each line as the mnemonic, test it against a regular expression for packed arithmetic, and read the register names off the operands. The common mistake is matching `xmm` anywhere: even scalar code uses xmm registers for floating point, and `pxor xmm0, xmm0` is a zeroing idiom, not arithmetic.

3. `asm_variants(c_source)` returns a dict from `"O0"`, `"O2"`, and `"O3_avx2"` to assembly, using `cputools.c_to_asm` with the options in `VARIANTS`. The checks require width 0, 128, and 256.

4. `compile_variants(c_source)` returns the same dict with libraries from `cputools.compile_c`.

5. `sse2_add_asm()` returns the assembly for a global function `add_arrays`. Use a vector loop with `movdqu` and `paddd`, then a scalar tail. The common mistake is `jl` or `jle` with the wrong operand order: when `n` is 0, the loop condition must fail at once, and the comparison is signed, because `n` is a `long`.

6. `time_variants(libs, n, repeats)` calls each library's `add_arrays` on arrays of `n` elements and returns the best time per variant. Skip `"O3_avx2"` when `cpu_has_avx2()` is false. The result is a report. No check compares two numbers.

## Where this breaks

- **Not every loop vectorizes.** A loop whose iterations depend on each other, such as `a[i] = a[i-1] + b[i]`, cannot run four at a time. A loop with a function call or an early exit often blocks vectorization. Clang's `-Rpass-missed=loop-vectorize` flag tells you why it gave up.
- **Pointers might overlap.** If `dst` and `a` could point to nearby memory, vectorizing could change the answer. The compiler either proves they do not overlap, adds a run-time check as it did here, or skips the loop. The C keyword `restrict` is a promise to the compiler that they do not overlap.
- **Wider is not always faster.** The 256-bit version of this loop was no faster, because loads and stores limit it. Some CPUs also lower their clock speed when running wide instructions. AVX-512 is the best-known case.
- **Instruction sets differ between machines.** Code built for AVX2 crashes on a CPU without it. Software that must run everywhere ships several versions and picks one at run time. The flag `-march=native` builds for the machine doing the compiling, which suits a build for your own use and no one else's.
- **Alignment and tails cost.** Real vectorized code often aligns its loads, and its leftover handling is a sizeable part of the code. For short arrays the setup can cost more than the vector loop saves.
- **Timings are noisy.** A shared virtual machine adds interference, and the first call pays for page faults. Repeat the measurement, take the minimum, and report the CPU model.

## Further reading

- [Agner Fog's optimization manuals](https://www.agner.org/optimize/) — instruction timings and throughput for real CPUs, including every SSE and AVX instruction used here.
- [Felix Cloutier's x86 reference](https://www.felixcloutier.com/x86/) — `PADDD`, `MOVDQU`, and every other instruction in this lesson, with the exact lane behavior.
- [LLVM Auto-Vectorization](https://llvm.org/docs/Vectorizers.html) — how LLVM's loop and SLP vectorizers decide, and the flags that show their decisions.
- [Compiler Explorer](https://godbolt.org) — compile `add_arrays` with `-O2`, `-O3 -mavx2`, and different compilers, side by side, and see the vector instructions.
- [LLVM Language Reference](https://llvm.org/docs/LangRef.html) — the vector types, such as `<4 x i32>`, that LLVM IR uses for the same idea before it becomes `xmm` code.

## The exercise

In `starter.py` you write `add_arrays_c`, `vector_width`, `asm_variants`, `compile_variants`, `sse2_add_asm`, and `time_variants`. The checks test `vector_width` on small handwritten snippets, then on clang's real output: `-O0` must show width 0, `-O2` must show 128 (SSE2 is the x86-64 baseline), and `-O3 -mavx2` must show 256. They compile your C at all three settings and call it on many lengths, including 0 and lengths that are not multiples of 4.

Your assembly loop is checked for correctness on lengths 0 to 17 with aligned and unaligned pointers, on long arrays, on overflow, and in place. Guard values around each array catch writes past the end. One check reads your assembly text and requires `paddd` on an xmm register. The generated code runs in a child process, so a wrong address fails a check without stopping the run. The last check reports timings with `timed` for each variant and never compares them.
