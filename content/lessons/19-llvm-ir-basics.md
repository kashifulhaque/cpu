---
title: "LLVM IR: the language in the middle"
slug: 19-llvm-ir-basics
part: "Part 4 — Compilers and LLVM IR"
summary: Read and write typed LLVM IR with arithmetic, comparisons, and conversions, then verify, run, and call it from Python.
minutes: 65
gpu: false
objectives:
  - Explain why a compiler uses an intermediate representation between the source language and the machine.
  - Read a small LLVM IR function and name its type, its values, and its instructions.
  - Choose between `sext`, `zext`, and `trunc`, and between signed and unsigned operations.
  - Write IR by hand and run it through the verifier, `lli`, and a shared library.
prereqs:
  - 18-what-a-compiler-is
exercise: 19-llvm-ir-basics
---

# LLVM IR: the language in the middle

Your parser from lesson 18 produces a tree. Your processor runs x86-64 instructions. Between them lies a gap that every compiler has to cross, and the way it crosses decides how much work a new language or a new processor costs.

The usual answer is an **intermediate representation**, or **IR**: a small language that is neither the source language nor the machine language. The front end of the compiler translates source into IR. The back end translates IR into machine code. Everything in between, including all of the optimizations, works on IR. LLVM, the project behind clang, is built around one such language, **LLVM IR**.

This lesson teaches you to read and write it. IR looks like assembly with types. By the end you will write short functions in it, check them with LLVM's verifier, run them, and call them from Python.

## What you already know

- Integers have a fixed width, and sign extension copies the top bit when it widens a number.
- An assembly function takes arguments in registers, and returns a result in `eax` or `rax`.
- A compiler translates one representation into another in stages.
- `ctypes` calls a function in a compiled library when you set its argument and result types.
- Division and comparison come in signed and unsigned forms, as with `jl` and `jb`.

## Why a middle language

Suppose there are $N$ source languages (C, Rust, Swift, your own) and $M$ processors (x86-64, ARM, RISC-V). Without an IR, each pair needs its own compiler: $N \times M$ of them. With one, you write $N$ front ends and $M$ back ends, and any front end works with any back end.

```text
   C ──────┐                              ┌────── x86-64
   Rust ───┤                              ├────── ARM64
   Swift ──┼───►  LLVM IR  ──optimizer──► ├────── RISC-V
   yours ──┘                              └────── WebAssembly
```

The optimizer works on IR, so it is written once and helps every language and every processor. That is the reason Rust and Swift get fast code without their authors writing an optimizer.

## The IR for `x * 5`

Ask clang for the IR of the function from lesson 16, using `cputools.c_to_ir(src, opt="-O0")`. This is the real output, trimmed to the function.

```llvm
define dso_local i32 @f(i32 noundef %x) #0 {
entry:
  %x.addr = alloca i32, align 4
  store i32 %x, ptr %x.addr, align 4
  %0 = load i32, ptr %x.addr, align 4
  %mul = mul nsw i32 %0, 5
  ret i32 %mul
}
```

Here is how to read it, line by line.

- `define i32 @f(i32 %x)` starts a function named `f`. It returns an `i32`, a 32-bit integer, and takes one `i32` argument called `x`. The words `dso_local`, `noundef`, and `#0` are extra information for the optimizer that you can ignore.
- `entry:` is a **label**. It names the first block of instructions.
- `alloca`, `store`, and `load` reserve a stack slot, write `%x` into it, and read it back. This is the `-O0` habit from lesson 16, in IR form. Lesson 21 covers it.
- `%mul = mul nsw i32 %0, 5` multiplies two `i32` values. The word `nsw` means "no signed wrap": the compiler promises that this multiply never overflows a signed integer.
- `ret i32 %mul` returns the value.

Names that start with `@` are **global**: functions and global variables. Names that start with `%` are **local**: arguments and the results of instructions. A name like `%0` with only a number is a **temporary** that clang did not name.

Compare it with what you write by hand. Without the stack slot, the function is three lines.

```llvm
define i32 @times5(i32 %x) {
entry:
  %r = mul i32 %x, 5
  ret i32 %r
}
```

> [!KEY]
> LLVM IR is typed assembly for a machine with unlimited registers. Every value has a type, and every instruction names the types it works on.

## Types

Every value in IR has a **type**, and the type is part of the instruction. The integer types are written `i` followed by a number of bits: `i1`, `i8`, `i32`, `i64`, and any other width up to a very large limit. `i1` is one bit, which holds the result of a comparison.

Types have no sign. An `i32` is 32 bits, and whether those bits mean a signed or an unsigned number is decided by the instruction that uses them. The pattern repeats across the instruction set.

| Operation | Signed | Unsigned | Same either way |
|---|---|---|---|
| Add, subtract, multiply | | | `add`, `sub`, `mul` |
| Divide | `sdiv` | `udiv` | |
| Remainder | `srem` | `urem` | |
| Shift right | `ashr` (copies the sign bit) | `lshr` (fills with zeros) | |
| Shift left | | | `shl` |
| Bitwise | | | `and`, `or`, `xor` |
| Compare | `icmp slt`, `sgt`, `sle`, `sge` | `icmp ult`, `ugt`, `ule`, `uge` | `icmp eq`, `ne` |

Two's complement makes add, subtract, and multiply identical for signed and unsigned values, as you saw in lesson 3. Divide, shift right, and ordering need a choice.

Both operands of an instruction must have the same type. `add i32 %a, %b` is valid only when `%a` and `%b` are both `i32`. If one is `i64`, the verifier rejects it, and the error message tells you which one.

### Comparisons produce `i1`

`icmp` compares two integers and produces an `i1`: 1 for true and 0 for false.

```llvm
%neg = icmp slt i32 %x, 0      ; %neg is an i1: 1 if x < 0, signed
```

A function that returns an `i32` cannot return an `i1`. Widen it first with `zext`, described next.

## Changing width

Three instructions convert between integer widths. Each names the source type and the target type: `trunc i32 %x to i8`.

| Instruction | What it does | When to use it |
|---|---|---|
| `trunc` | Keeps the low bits and drops the rest | Narrowing to fewer bits |
| `zext` | Pads the top with zeros | Widening an unsigned value, or an `i1` |
| `sext` | Pads the top with copies of the sign bit | Widening a signed value |

Work through one value by hand. Take the 32-bit number `0x000001FF`, which is 511.

- `trunc i32 %x to i8` keeps the low 8 bits: `0xFF`.
- `zext i8 0xFF to i32` gives `0x000000FF`, which is 255.
- `sext i8 0xFF to i32` reads `0xFF` as the signed 8-bit number -1 and gives `0xFFFFFFFF`, which is -1.

The pair `trunc` then `sext` is how you take the low byte of a number as a signed value. Written in IR:

```llvm
%b = trunc i32 %x to i8
%r = sext i8 %b to i32
```

The widening conversion `sext` also prevents overflow. To multiply two `i32` values without losing bits, widen both to `i64` first. The product of two 32-bit numbers always fits in 64 bits: $(2^{31})^2 = 2^{62}$.

```llvm
%wa = sext i32 %a to i64
%wb = sext i32 %b to i64
%p  = mul i64 %wa, %wb
```

### Wrapping and `nsw`

Without a flag, `add i32` wraps around on overflow like the C `unsigned` type: `0x7FFFFFFF + 1` is `0x80000000`. The flags `nsw` and `nuw` ("no unsigned wrap") are promises that overflow never happens. If the promise is false, the result is **poison**, a value on which the optimizer may assume anything. Clang writes `nsw` for C `int` arithmetic because signed overflow in C is undefined behavior. When you write IR by hand, leave the flags off, and your function wraps predictably.

## A module and a `main`

A file of IR is a **module**. It holds functions and declarations. The function named `@main` is the program's entry point when you run the module with `lli`, LLVM's interpreter. Its `i32` return value becomes the process exit code.

```llvm
define i32 @main() {
entry:
  %p = mul i32 7, 6
  ret i32 %p
}
```

Run it with `cputools.run_ir`:

```python
>>> cputools.run_ir(ir)
Result(returncode=42, stdout='', stderr='')
```

The exit code is 42. Constants such as `7` and `6` can appear directly as operands. A function calls another with `call`: `%r = call i32 @times5(i32 %x)`.

For functions you want to call from Python, compile the module into a shared library with `cputools.ir_to_lib` and use `ctypes`, as you did with assembly. Set `restype` and `argtypes` for anything that is not a plain `int`.

```python
lib = cputools.ir_to_lib(ir)
lib.mul_wide.restype = ctypes.c_int64
lib.mul_wide.argtypes = [ctypes.c_int32, ctypes.c_int32]
lib.mul_wide(65536, 65536)      # 4294967296
```

## IR to assembly

LLVM's back end turns IR into machine code. `cputools.ir_to_asm` runs `llc` and prints the result. For the function `add3(a, b, c)` that returns `a + b + c`, `llc -O2` gives:

```asm
add3:
    lea eax, [rdi + rsi]
    add eax, edx
    ret
```

The three arguments arrived in `edi`, `esi`, and `edx`, following the System V convention you know. The back end picked `lea` for the first add, as clang did in lesson 16. The IR said nothing about registers or instructions: the choice was the back end's. Lesson 24 shows how it decides.

## When IR is wrong

LLVM checks IR with a **verifier**. `cputools.verify_ir(ir)` runs it and raises `cputools.ToolError` with the tool's own message. Two mistakes you will make:

A type mismatch:

```llvm
define i32 @f(i32 %x, i64 %y) {
entry:
  %z = add i32 %x, %y
  ret i32 %z
}
```

```text
<stdin>:3:20: error: '%y' defined with type 'i64' but expected 'i32'
  %z = add i32 %x, %y
                   ^
```

A block with no terminator:

```text
<stdin>:4:1: error: expected instruction opcode
}
^
```

Read the line and column first. The caret marks the exact spot. In the exercise, the checks pass this message on to you.

## Try it on your own machine

1. Get the IR for a C function at `-O0`, and again at `-O2`. Compare how many instructions each has.

   ```bash
   printf 'int sq(int x) { return x * x; }\n' > sq.c
   clang -S -emit-llvm -O0 -fno-discard-value-names sq.c -o sq0.ll
   clang -S -emit-llvm -O2 -fno-discard-value-names sq.c -o sq2.ll
   cat sq0.ll sq2.ll
   ```

2. Write a module by hand, run it with `lli`, and print the exit code. Change the constants and watch the code change.

   ```bash
   printf 'define i32 @main() {\nentry:\n  ret i32 42\n}\n' > m.ll
   lli m.ll; echo $?
   ```

3. Lower the IR to assembly with `llc` and compare it with `clang -S` output.

   ```bash
   llc -O2 -x86-asm-syntax=intel sq2.ll -o -
   ```

4. Check an IR file without running it. A correct file prints nothing.

   ```bash
   opt -passes=verify -disable-output sq0.ll
   ```

5. Paste C into https://godbolt.org and switch the output to LLVM IR with the "Output" menu, to see IR for any snippet.

## Build it step by step

Each `*_ir` function returns IR text. Every one of them has the same shape: a `define` line, an `entry:` label, some instructions, and a `ret`. The checks verify the text, compile it with `cputools.ir_to_lib`, and compare results with Python.

1. `ir_opcodes(ir)` is a Python function over IR text. Only lines between `define ... {` and `}` count. Cut each line at `;` (the comment marker), skip blanks and labels (they end with a colon), and take the word after `=` when the line has one (`%x = add ...` gives `add`), else the first word (`ret`, `br`, `store`). The common mistake is to include `define` lines or `}`.
2. `add3_ir()` is `i32 @add3(i32 %a, i32 %b, i32 %c)`: two `add` instructions and a `ret`.
3. `mul_wide_ir()` is `i64 @mul_wide(i32 %a, i32 %b)`. Widen both arguments with `sext`, then `mul i64`. The common mistake is to multiply first and widen after, which loses the high bits.
4. `is_negative_ir()` returns 1 or 0 as an `i32`. Use `icmp slt` with 0, then `zext i1 ... to i32`.
5. `low_byte_ir()` takes the low byte of its argument as a signed number. Use `trunc` to `i8`, then `sext` back to `i32`.
6. `avg_ir()` computes `(a + b) / 2` without overflow. Do the add in `i64`, divide with `sdiv`, and `trunc` back to `i32`. The common mistake is to add as `i32`: the sum of two large values wraps before the divide.
7. `main_ir()` returns `(7 * 6 - 2) / 2` as the exit code, using `mul`, `sub`, and `sdiv`. The result is 20.

If the verifier rejects your IR, the check shows its message. Fix the first error before the others, because one mistake often causes several.

## Where this breaks

**IR is not portable.** LLVM IR looks target-independent but is not. Clang's output includes a `target datalayout` and a `target triple` line, and the sizes of C types such as `long` differ by platform. IR from x86-64 Linux is not safe to compile for another target.

**IR changes between versions.** The text format is not stable. LLVM 15 made a single `ptr` type the default in place of typed pointers such as `i32*`, and LLVM 17 removed the old form, so examples in older books look different. This course uses LLVM 19.

**Poison and undef make bugs subtle.** Flags such as `nsw`, and values such as `undef`, let the optimizer assume things. A wrong assumption is a wrong program, and the verifier cannot catch it. It checks the shape of the IR, not whether the IR means what you wanted.

**The verifier checks less than you think.** It accepts a loop that never ends and a division by zero. It rejects type errors, missing terminators, and uses of a value before its definition.

**IR is not machine code.** An `i1` or an `i33` has no register of that size. The back end must lower such types, which can cost extra instructions.

## Further reading

- [The LLVM Language Reference](https://llvm.org/docs/LangRef.html) is the authoritative description of every instruction, type, and flag. Keep it open while you write IR.
- [Compiler Explorer](https://godbolt.org) shows LLVM IR next to C for any snippet, and lets you run optimization passes on it.
- [The Kaleidoscope tutorial](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/index.html) builds a language that emits LLVM IR, like the one you will build in lesson 23.
- [LLVM Programmer's Manual](https://llvm.org/docs/ProgrammersManual.html) explains how the C++ API represents the same IR.

## The exercise

You write six functions that return LLVM IR text, `add3_ir`, `mul_wide_ir`, `is_negative_ir`, `low_byte_ir`, `avg_ir`, and `main_ir`, and one Python function, `ir_opcodes`, that lists the opcodes in IR text.

The checks verify your IR with `cputools.verify_ir` and show you LLVM's error message when it fails. They compile each function with `cputools.ir_to_lib` and call it from a child process over edge cases such as zero, negative numbers, `INT_MIN`, and values that overflow 32 bits, against a Python reference. `main_ir` runs under `cputools.run_ir` and must exit with code 20. `ir_opcodes` is tested on hand-written IR and on the IR clang produces for a small C function.
