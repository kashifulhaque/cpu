---
title: "C for the curious: types, pointers, and memory"
slug: 15-c-for-the-curious
part: "Part 3 — From C to machine code"
summary: Learn the C you need to follow code down to machine code, and predict how a struct lays out in memory.
minutes: 60
gpu: false
objectives:
  - Say how big each basic C type is on x86-64 Linux, and what a pointer holds.
  - Use pointer arithmetic and explain why p + 1 moves by the size of the pointed-to type.
  - Compute the offsets, padding, and size of a struct by hand and check them against clang.
  - Explain, with examples, why undefined behaviour lets a compiler change what your program does.
prereqs:
  - 14-functions-and-the-calling-convention
exercise: 15-c-for-the-curious
---

# C for the curious: types, pointers, and memory

For three lessons you wrote the machine's own language. You counted bytes, computed addresses, and kept registers safe. Nobody writes whole programs that way. They write C, or a language like it, and a compiler produces the assembly.

This lesson teaches the part of C you need to read what the compiler does. C is small, and it is honest about memory. Every variable has a size. Every pointer is an address. Every struct is a block of bytes with fields at fixed offsets. Python hides all of that, and C shows it, which makes C the best bridge between the assembly you can write and the compiler lessons that follow.

You write small C functions in strings, compile them with `cputools.compile_c`, and call them from Python. You also predict how a struct sits in memory, in Python, and check the prediction against what clang really does.

## What you already know

- A pointer is an integer holding an address, and `[reg + index*scale]` reads memory at an array element (lesson 13).
- Assembly functions take arguments in `rdi`, `rsi`, and `rdx`, and return in `rax` (lessons 11 and 14).
- Memory is bytes, multi-byte values are little-endian, and a cache line is 64 bytes (lessons 7 and 9).
- Two's complement integers wrap around when they overflow (lesson 3).
- `ctypes` calls compiled code from Python when you set `argtypes` and `restype` (lesson 11).

## Types have sizes

Every C variable has a *type*, and the type fixes how many bytes it occupies and how those bytes are read. The next table lists the basic types on x86-64 Linux, the machine this course uses. The sizes are not the same everywhere. Windows, for instance, makes `long` 4 bytes.

| Type | Size in bytes | Alignment | Notes |
|---|---|---|---|
| `char` | 1 | 1 | signed on x86 Linux |
| `short` | 2 | 2 | |
| `int` | 4 | 4 | |
| `long` | 8 | 8 | 4 bytes on 64-bit Windows |
| `float` | 4 | 4 | |
| `double` | 8 | 8 | |
| any pointer, such as `int *` | 8 | 8 | holds an address |

*Alignment* is the rule that a value of this type should sit at an address that is a multiple of some number, usually its own size. An `int` belongs at an address divisible by 4. The operator `sizeof` tells you a type's size at compile time, and `_Alignof` tells you its alignment.

Signed and unsigned are two readings of the same bits (lesson 3). `unsigned int` uses all 32 bits for magnitude. `int` uses two's complement.

> [!KEY]
> A C type is a size, an alignment, and a way of reading bytes. Everything else in C follows from those three facts.

## Pointers

A pointer variable stores an address. `int *p` means "`p` holds the address of an `int`". Two operators connect values and addresses:

- `&x` is the address of `x`.
- `*p` is the value stored at the address `p` holds.

Here is `swap`, which exchanges two ints through pointers. Without pointers, a function receives copies and cannot change the caller's variables:

```c
void swap(int *a, int *b) {
    int t = *a;      /* read the value a points at */
    *a = *b;         /* copy b's value into a's target */
    *b = t;          /* write the saved value into b's target */
}
```

Suppose `x = 1` lives at address `0x1000` and `y = 2` lives at `0x1004`. The call `swap(&x, &y)` passes `rdi = 0x1000` and `rsi = 0x1004`. After the three lines, the memory at `0x1000` holds 2 and the memory at `0x1004` holds 1.

Take care with `swap(&x, &x)`, where both pointers are the same. The version above is fine: it reads 1, writes 1, writes 1. A clever swap using XOR (`*a ^= *b; *b ^= *a; *a ^= *b;`) sets `x` to zero in that case, because the first line makes `*a` zero. The checks test this call on purpose.

## Pointer arithmetic

Add 1 to a pointer, and it moves by one *element*, not one byte. If `p` has type `long *`, then `p + 1` is 8 bytes after `p`. The compiler multiplies by `sizeof(*p)` for you. This is the scale factor from lesson 13, written once in the type instead of by hand in every instruction.

Two pointers into the same array subtract to an element count: `end - begin` is how many elements lie between them, not how many bytes. And `a[i]` is defined as `*(a + i)`, so indexing is pointer arithmetic with different notation. The next function walks a pointer from `begin` to `end`:

```c
long sum_ptr(const long *begin, const long *end) {
    long total = 0;
    for (const long *p = begin; p < end; p++) {
        total += *p;
    }
    return total;
}
```

Compile it at `-O1` with `-S -masm=intel` and the loop body is `add rax, [rdi]` then `add rdi, 8`. The `8` is `sizeof(long)`, filled in by the compiler. If `begin == end`, the loop body never runs and the sum is 0.

The `const` means this function does not modify what the pointers point to. The compiler enforces it, and it also tells readers and optimizers something useful.

## Arrays are not pointers

An array and a pointer look alike in C, and they are different things. An array variable *is* the block of storage. When you use its name in an expression, it *decays* to a pointer to its first element. A pointer variable is only an address.

The next table shows where the difference appears, for `int a[10]` declared as a local variable and `int *p`.

| Expression | `a` (local array) | `p` (pointer) |
|---|---|---|
| `sizeof a` | 40 (ten ints) | 8 (one address) |
| `&a` | the address of the array, the same number as `&a[0]` | the address of the variable `p` itself |
| `a = something` | not allowed | allowed |

There is one famous trap. A function parameter written `int a[10]` is *not* an array. The language rewrites it to `int *a`. So inside the function, `sizeof a` is 8, the size of a pointer, however big the caller's array was. The 10 is documentation the compiler ignores. Clang warns about `sizeof` on an array parameter. The exercise has you observe both numbers: 40 for a local array and 8 for the parameter.

This is why C functions that take arrays also take a length argument, as your assembly functions in lesson 13 did.

## Structs and layout

A `struct` bundles named fields. Memory has no names, so the compiler turns each field into an *offset*: how many bytes after the start of the struct the field lives. Fields are placed in declaration order. Each must sit at an address that satisfies its type's alignment, so the compiler inserts unused *padding* bytes where needed.

The rules, which you code in this lesson, are:

1. Start at offset 0.
2. For each field, round the running offset up to a multiple of the field's alignment. That is the field's offset. Then add the field's size.
3. The struct's alignment is the largest alignment of any field.
4. Round the final size up to a multiple of the struct's alignment.

Rule 4 is the least obvious. It exists so that in an array of structs, every element starts aligned. Work through `struct { char a; int b; char c; }`:

```text
offset:   0     1  2  3    4  5  6  7    8     9 10 11
        +-----+-----------+-------------+-----+-----------+
        |  a  |  padding  |      b      |  c  |  padding  |
        +-----+-----------+-------------+-----+-----------+
         char     3 bytes      int         char    3 bytes

a at 0 (alignment 1)
b: running offset is 1, rounded up to a multiple of 4 gives 4
c: running offset is 8, alignment 1, so c is at 8
size: running offset is 9, struct alignment is 4, round up to 12
```

Twelve bytes hold six bytes of data. The same fields in a different order waste less. Put the big alignments first, as `int b; char a; char c;`, and the layout is `b` at 0, `a` at 4, `c` at 5, and the size is 6 rounded up to 8. A rule of thumb: sort fields by alignment, largest first, and the padding is minimal.

A second example: `struct { int i; char c; double d; char e; }` puts `i` at 0, `c` at 4, `d` at 8 (the offset 5 rounds up to 8), `e` at 16, and the size is 17 rounded up to 24. Reordered as `double d; int i; char c; char e;` it takes 16 bytes.

To round `x` up to a multiple of `a` in Python, write `(x + a - 1) // a * a`. In C, the standard header `stddef.h` provides `offsetof(struct S, field)`, so you can ask the compiler for the truth. The exercise does exactly that: it computes the layout in Python, then compiles a struct and compares your numbers against `sizeof`, `_Alignof`, and `offsetof`.

Layout matters for speed and for compatibility. A struct whose size is a power of two divides evenly into 64-byte cache lines (lesson 9). A struct shared between two programs, or written to a file, needs the same layout on both sides.

## Undefined behaviour

C defines what most operations do, and for some it says *nothing*. These are *undefined behaviour*, abbreviated UB. The standard places no requirement on what happens. The program can crash, return a wrong answer, or work today and fail tomorrow with a different compiler. Common examples:

| Operation | Why it is undefined |
|---|---|
| Signed integer overflow, such as `INT_MAX + 1` | The standard leaves it unspecified, so the compiler may assume it never occurs |
| Dereferencing a null or dangling pointer | There is no object there |
| Reading or writing outside an array | There is no object there |
| Reading an uninitialized local variable | The value is indeterminate |
| Shifting by the width of the type or more | `1 << 32` for a 32-bit `int` |
| Dividing by zero, or `INT_MIN / -1` | The result is not representable |

Unsigned overflow is *not* undefined. `UINT_MAX + 1` is 0, by definition, in every compiler.

Why does the standard leave holes? So the compiler can assume the holes never happen, and optimize. Take this function:

```c
int always_true(int x) {
    return x + 1 > x;
}
```

For every `x` except `INT_MAX`, the answer is 1. For `INT_MAX`, the hardware would wrap to `INT_MIN` and the answer would be 0. But `INT_MAX + 1` is undefined, so the compiler is allowed to assume `x` is never `INT_MAX`. At `-O1` or higher, clang compiles the function to `mov eax, 1; ret`. You can check this with `cputools.c_to_asm`. The machine code does not do the comparison at all.

The fix is to write code that never relies on UB. For wraparound, do the arithmetic in `unsigned int` and convert back. For division, check the divisor and the `INT_MIN / -1` case first. Both are exercise functions.

## Try it on your own machine

1. Write a program that prints `sizeof(int)`, `sizeof(long)`, `sizeof(void *)`, and `sizeof(struct s)` for a struct with a `char`, an `int`, and a `char`. Build it with `clang prog.c -o prog && ./prog`. Compare with the table above.
2. Compile a function containing `int a[10]; return sizeof a;` and the parameter version `int f(int a[10]) { return sizeof a; }` with `clang -Wall -c`. Look for the clang warning on the second.
3. Compile `always_true` with `clang -O0 -S -masm=intel` and with `-O2`. At `-O0` you see a real comparison, and at `-O2` the constant 1.
4. Add `-fsanitize=undefined` to a program that overflows an `int`, such as `int x = 2147483647; x = x + atoi("1");`. Run it, and clang's runtime reports "signed integer overflow". This needs the sanitizer runtime that ships with clang on most Linux installs.
5. If the `pahole` tool is installed (package `dwarves`), `pahole ./prog` prints each struct's offsets and marks the padding holes.

## Build it step by step

Fill in `starter.py` in this order. Seven functions: five return C source as a string, and two are Python. The checks compile your C with `cputools.compile_c` and run it in a child process.

1. `sum_ptr_c()` returns C source for `sum_ptr(begin, end)`. Walk a pointer. The check fails if your text contains `[`, so use `*p` and `p++`. The common mistake is `p <= end`, which reads one element past the array.
2. `swap_c()` returns C source for `swap(a, b)`. Use a temporary. The check also swaps a variable with itself.
3. `array_vs_pointer_c()` returns C source for two functions: `local_array_size()`, which declares `int a[10]` and returns `sizeof a`, and `param_size(int a[10])`, which returns `sizeof a`. Expect 40 and 8.
4. `struct_layout(types)` is Python. It takes a list of type names such as `["char", "int", "char"]` and returns `{"offsets": [...], "size": ..., "align": ...}`. Use `SIZE_ALIGN`, which the starter provides. The common mistake is forgetting rule 4, the final rounding.
5. `best_order(types)` is Python. It returns the same type names reordered for the smallest struct. A sort by alignment does it. The check asks clang for the real `sizeof` of your order and compares it with the best of every possible ordering.
6. `wrap_add_c()` returns C source for `wrap_add(a, b)`, which wraps at 32 bits without undefined behaviour. Convert both arguments to `unsigned int`, add, and convert back. The check reads your text for `unsigned`, and compiles it at `-O2`.
7. `safe_div_c()` returns C source for `safe_div(a, b, out)`. Return 0 and leave `*out` unchanged when `b` is 0 or when `a` is `INT_MIN` and `b` is -1. Otherwise store the quotient and return 1. A divide by zero would kill the process with `SIGFPE`, and the checks report it.

## Where this breaks

- **Sizes depend on the platform.** `long` is 8 bytes on Linux and macOS and 4 on 64-bit Windows. Use the fixed-width types `int32_t` and `int64_t` from `stdint.h` when the size matters, such as in file formats.
- **Layout is a compiler decision.** The rules here are the System V ones. `#pragma pack` and `__attribute__((packed))` remove padding, and then fields may be misaligned. Bit-fields have implementation-defined layout.
- **`char` may be signed or unsigned.** On x86 Linux it is signed. On ARM Linux it is unsigned. Code that stores a byte above 127 in a plain `char` and then widens it behaves differently on the two.
- **Padding is real memory.** Writing a whole struct to a file or a socket also writes the padding bytes, which may hold stale data from earlier use. That is a source of information leaks.
- **Dangling pointers.** Returning the address of a local variable hands the caller a pointer into a stack frame that no longer exists (lesson 14). C does not stop you.
- **Strict aliasing.** The standard says a `float` object may not be read through an `int *`. Compilers use that to reorder loads and stores, so a program that breaks the rule may misbehave at `-O2`.
- **UB is not a crash you can count on.** The same code can pass every test at `-O0`, and fail after an upgrade or at `-O2`. Use `-Wall`, `-fsanitize=undefined,address` in testing, and write code that never depends on UB.

## Further reading

- [What Every C Programmer Should Know About Undefined Behavior](https://blog.llvm.org/2011/05/what-every-c-programmer-should-know.html) is a three-part LLVM blog series by Chris Lattner on why compilers exploit UB.
- [The Lost Art of Structure Packing](http://www.catb.org/esr/structure-packing/) is Eric Raymond's guide to alignment, padding, and reordering, with diagrams.
- [UndefinedBehaviorSanitizer](https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html) documents clang's `-fsanitize=undefined`, which catches the examples in this lesson at run time.
- [cppreference C reference](https://en.cppreference.com/w/c) is a complete, searchable description of the C language, including `sizeof`, `_Alignof`, and `offsetof`.
- [Compiler Explorer](https://godbolt.org) shows the assembly for any function you write. Compare `always_true` at `-O0` and `-O2`.

## The exercise

You write three kinds of things. The C functions `sum_ptr_c`, `swap_c`, `array_vs_pointer_c`, `wrap_add_c`, and `safe_div_c` return C source text, which the checks compile with clang and call through `ctypes`. The Python functions `struct_layout` and `best_order` predict memory layout.

For layout, the checks compile real structs with eight different field lists and compare your offsets, size, and alignment against `offsetof`, `sizeof`, and `_Alignof`. For the C functions, calls run in a forked child, so a crash reports its signal. Inputs include `INT_MIN`, `INT_MAX`, empty ranges, and pointers to the same variable.
