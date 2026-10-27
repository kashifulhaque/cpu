---
title: "Memory, pointers, and arrays in assembly"
slug: 13-memory-and-arrays-in-assembly
part: "Part 2 — x86-64 assembly"
summary: Read and write memory with [base + index*scale] addressing, and write array and string loops that work on data handed over from Python.
minutes: 60
gpu: false
objectives:
  - Write the address of array element i as [base + index*scale] and pick the right scale for the element size.
  - Load and store bytes, 32-bit ints, and 64-bit values, choosing zero- or sign-extension on load.
  - Write loops that sum, search, reverse, and copy memory.
  - Pass arrays and strings from Python to assembly through ctypes.
prereqs:
  - 12-flags-and-control-flow
exercise: 13-memory-and-arrays-in-assembly
---

# Memory, pointers, and arrays in assembly

Registers hold a handful of values. Real data does not fit: a list of a million numbers, a string, an image. That data lives in memory, and the CPU reaches it by *address*. This lesson teaches the instructions and the address arithmetic that reach it.

An array of numbers is a row of equal-size slots, one after another. A string is a row of bytes that ends at a zero byte. Both are reached the same way: start at an address, then step along. A loop that does the stepping is the core of most programs.

You will write a sum, a search for the largest value, a reverse in place, a string length, and a copy. Python builds the arrays with `ctypes` and your assembly reads the same bytes. Because a wrong address can crash a process, the checks run your code in a child process and tell you what went wrong.

## What you already know

- Memory is a long row of bytes, each with an address, and multi-byte values are stored little-endian (lesson 7).
- A pointer is an integer holding an address, and the first argument arrives in `rdi`, the second in `rsi` (lessons 7 and 11).
- `cmp` and conditional jumps build loops, and `jae` compares unsigned values (lesson 12).
- `movsxd` sign-extends a 32-bit value into 64 bits, and a 32-bit write zero-extends (lesson 11).
- A cache fetches memory in 64-byte lines, so walking memory in order is fast (lesson 9).

## A pointer is a number in a register

Suppose Python hands your function an array of three 8-byte integers, 10, 20, and 30. The array sits at address `0x1000`. The function receives that address in `rdi`. Nothing marks the register as special. It is a 64-bit integer that happens to be an address.

Square brackets mean "the memory at this address". `[rdi]` is the data stored at the address in `rdi`. The next diagram shows the array in memory. Each slot is 8 bytes wide, and the bytes within a slot are little-endian, so 10 is stored as `0a 00 00 00 00 00 00 00`.

```text
address   0x1000       0x1008       0x1010
         +------------+------------+------------+
         |     10     |     20     |     30     |
         +------------+------------+------------+
              a[0]         a[1]         a[2]
rdi = 0x1000
```

To load the first element, write `mov rax, [rdi]`. The brackets are the difference between the two readings:

- `mov rax, rdi` copies the *address*, `0x1000`.
- `mov rax, [rdi]` copies the *value stored there*, 10.

The width of the access usually comes from the register. `mov rax, [rdi]` loads 8 bytes, and `mov eax, [rdi]` loads 4. When no register fixes the width, you state it with a size word: `byte ptr`, `word ptr` (2 bytes), `dword ptr` (4 bytes), or `qword ptr` (8 bytes). For example, `cmp byte ptr [rdi], 0` compares one byte with zero.

## The addressing mode

Element `i` of an array of 8-byte values sits at `base + i * 8`. The CPU computes this sum in hardware as part of the load, using the general form:

```text
[ base + index*scale + displacement ]
```

- `base` is a register holding the start address.
- `index` is a register holding the element number.
- `scale` is 1, 2, 4, or 8. It must match the element size.
- `displacement` is a constant added to the address.

Only `base` is required. The other parts are optional. Here is `nth(a, i)`, which returns `a[i]`:

```asm
    .globl nth
nth:
    mov rax, [rdi + rsi*8]    # rdi = array address, rsi = index
    ret
```

For `i = 2` the address is `0x1000 + 2*8 = 0x1010`, which holds 30. The same address expression appears in `lea` (lesson 11), which computes the address without reading memory. A `lea` with the same brackets is how you get a pointer to element `i` instead of its value.

The next table maps C element types to scales.

| C type | Size | Scale | Load into a register |
|---|---|---|---|
| `char` | 1 | 1 | `movzx eax, byte ptr [...]` or `mov al, [...]` |
| `short` | 2 | 2 | `movzx eax, word ptr [...]` |
| `int` | 4 | 4 | `mov eax, [...]` or `movsxd rax, dword ptr [...]` |
| `long`, pointers | 8 | 8 | `mov rax, [...]` |

> [!KEY]
> The scale in `[base + index*scale]` is the element size in bytes. A wrong scale gives a valid address that points at the wrong data, and the program often runs without a crash.

## Loads, stores, and the rule against memory to memory

`mov reg, [mem]` loads, and `mov [mem], reg` stores. An x86 instruction can name at most one memory operand, so there is no `mov [a], [b]`. To copy a value you go through a register: load into it, then store from it.

Arithmetic can take a memory operand directly: `add rax, [rdi + rcx*8]` loads an element and adds it in one instruction.

## Narrow loads and sign

A 32-bit load into `eax` *zero-extends* into `rax`. That is wrong for a signed `int`. Take the int -1, stored as the four bytes `ff ff ff ff`. The two loads give different results:

```asm
    mov edx, [rdi]                # rdx = 0x00000000FFFFFFFF = 4294967295
    movsxd rdx, dword ptr [rdi]   # rdx = 0xFFFFFFFFFFFFFFFF = -1
```

If you sum `int` values into a 64-bit total, use `movsxd` on each element. The 32-bit load adds 4294967295 where -1 belongs.

## A loop over an array

The index form is the easiest to read. Here is `sum_i64(a, n)`, with `rcx` as the index and `rax` as the total. The index is compared with `n` as an unsigned number, so `jae` ("jump if above or equal") ends the loop:

```asm
    .globl sum_i64
sum_i64:
    xor eax, eax                  # total = 0
    xor ecx, ecx                  # i = 0
.Lloop:
    cmp rcx, rsi                  # i versus n
    jae .Ldone                    # if i >= n, stop
    add rax, [rdi + rcx*8]        # total += a[i]
    inc rcx
    jmp .Lloop
.Ldone:
    ret
```

With `n = 0`, the first compare exits, and the function returns 0. Index 0 is never read, so an empty array is safe, even if its address is junk.

## Two pointers walking toward each other

Reversing in place swaps `a[0]` with `a[n-1]`, then `a[1]` with `a[n-2]`, and so on. Walk one pointer up from the start and another down from the end. Stop when they meet. The next diagram shows four elements. The `lo` pointer starts at element 0 and the `hi` pointer starts at element 3:

```text
start:   [ 1 | 2 | 3 | 4 ]       lo -> 1   hi -> 4
swap:    [ 4 | 2 | 3 | 1 ]       lo -> 2   hi -> 3
swap:    [ 4 | 3 | 2 | 1 ]       lo and hi cross, so stop
```

In assembly the pointers are plain registers, and each step moves them by 8 bytes:

```asm
    .globl reverse_i64
reverse_i64:
    lea rdx, [rdi + rsi*8 - 8]    # hi = address of a[n-1]
.Lloop:
    cmp rdi, rdx
    jae .Ldone                    # lo >= hi: finished
    mov rax, [rdi]                # load both values
    mov rcx, [rdx]
    mov [rdi], rcx                # store them swapped
    mov [rdx], rax
    add rdi, 8                    # lo moves up one element
    sub rdx, 8                    # hi moves down one element
    jmp .Lloop
.Ldone:
    ret
```

The function reuses `rdi` as `lo`. That is allowed: argument registers are ordinary registers once you have read them. For `n = 0`, `hi` is 8 bytes *before* the array, so `lo >= hi` holds immediately, and nothing is touched. For an odd `n`, the middle element ends with `lo == hi` and stays where it is.

## Strings are bytes up to a zero

A C string is a row of bytes that ends at the first zero byte. The length is how many bytes come before it. `strlen` walks the bytes until it finds the zero:

```asm
    .globl my_strlen
my_strlen:
    xor eax, eax                      # length = 0
.Lloop:
    cmp byte ptr [rdi + rax], 0       # is s[length] the end marker?
    je .Ldone
    inc rax
    jmp .Lloop
.Ldone:
    ret
```

For the bytes `68 65 6c 6c 6f 00` ("hello"), the counter stops at 5, where the byte is 0. The scale is 1, so the address expression needs no `*`. Notice that one register, `rax`, is both the index and the answer. Copying bytes is the same loop with a load into `al` and a store from `al` in place of the compare.

## Passing memory from Python

A ctypes array is a block of real memory. `(ctypes.c_int64 * 3)(10, 20, 30)` allocates 24 bytes and fills them. Passing it to a function whose parameter is declared `c_void_p` hands over the address of the first byte. For strings, `ctypes.create_string_buffer(b"hello")` makes a writable buffer with a zero byte at the end.

```python
import ctypes
import cputools

lib = cputools.assemble(sum_i64_asm())
lib.sum_i64.argtypes = [ctypes.c_void_p, ctypes.c_size_t]   # pointer, count
lib.sum_i64.restype = ctypes.c_int64
data = (ctypes.c_int64 * 3)(10, 20, 30)
print(lib.sum_i64(data, 3))                                 # 60
```

A `size_t` is an unsigned 64-bit integer, so `n` arrives in all 64 bits of `rsi`. That is why the loops here compare with the unsigned `jae` and use full 64-bit registers for indexes.

## What a mistake looks like

Assembly has no bounds checking. Read one element too many and the CPU fetches the next 8 bytes, whatever they are, and the program usually keeps running with a wrong answer. Write past the end and you corrupt a neighbour. Use a bad address, such as an index where a pointer belongs, and the processor raises a fault. The operating system turns it into the signal `SIGSEGV` (segmentation fault) and kills the process.

Your checks run in a child process, so a crash becomes a message such as "your function crashed with signal SIGSEGV on nth(a, 0)". For the in-place functions, the checks also put guard values on both sides of the array and verify they never change. That catches an off-by-one write, which would otherwise corrupt memory and pass.

## Try it on your own machine

1. Compile `long sum(const long *a, long n) { long s = 0; for (long i = 0; i < n; i++) s += a[i]; return s; }` with `clang -O1 -S -masm=intel -fno-asynchronous-unwind-tables`. Find the `[rdi + rax*8]` or `[rdi + rcx*8]` addressing mode in the loop.
2. Compile the same function with `-O3 -march=native` and look for `ymm` registers. The compiler processes four 8-byte numbers per instruction (lesson 25 returns to this).
3. Run `objdump -d -M intel` on the object file and see the same `[reg + reg*8]` form with its encoded bytes.
4. In Python, run `import ctypes; a = (ctypes.c_int32 * 3)(-1, 2, 3); print(bytes(a).hex())`. You see `ffffffff0200000003000000`: -1 as four `ff` bytes, then 2 and 3 in little-endian order.

## Build it step by step

Fill in `starter.py` in this order. Every function takes pointers as `c_void_p` and counts as `c_size_t`. `make_array` is given in full.

1. `nth_asm()` defines `nth(a, i)`, which returns the 8-byte value `a[i]`. One load with a scale of 8. The common mistake is forgetting the scale and reading bytes at `a + i`.
2. `sum_i64_asm()` defines `sum_i64(a, n)`. Loop with a counter, and end when the counter reaches `n`. For `n = 0` return 0. The common mistake is `jbe`, which runs one pass too many and reads past the end.
3. `sum_i32_asm()` defines `sum_i32(a, n)`, over 4-byte ints with a 64-bit result. Use scale 4 and `movsxd`. The check sums three `INT_MAX` values and negative values, so both a missing sign extension and a 32-bit total fail.
4. `max_i64_asm()` defines `max_i64(a, n)` for `n >= 1`. Start from `a[0]`, and use `cmp` and `cmovg` on each later element. The common mistake is starting from 0, which is wrong for an all-negative array.
5. `reverse_asm()` defines `reverse_i64(a, n)`. Use the two-pointer loop. The check includes empty, one-element, even, and odd lengths, and verifies the guard words.
6. `strlen_asm()` defines `my_strlen(s)`. Compare each byte with zero using `byte ptr`. The common mistake is a 64-bit compare, which looks at 8 bytes at once.
7. `copy_bytes_asm()` defines `copy_bytes(dst, src, n)`. Move one byte per pass through `al`. The check leaves spare bytes after the destination and confirms they stay unchanged.

## Where this breaks

- **No bounds, no warnings.** An off-by-one read returns plausible garbage. Real systems add bounds checks in the language (Rust, Python), canaries and sanitizers (`-fsanitize=address`), and guard pages that turn overruns into crashes.
- **Overlapping copies.** `copy_bytes` going forward corrupts the data if `dst` starts inside `src`. The C library's `memmove` checks which direction is safe, and `memcpy` promises nothing for overlap.
- **Aliasing.** The compiler cannot always prove two pointers point to different memory. If they might overlap, it must reload values after every store, which blocks optimisations.
- **Alignment.** x86 allows an 8-byte load from any address, but one that straddles a 64-byte cache line costs extra cycles. Some other processors fault on a misaligned load.
- **Signed indexes.** A negative index in a 64-bit register is a valid backward step. A negative 32-bit index written with a 32-bit instruction is zero-extended, so it becomes a jump of about four billion elements and a crash. Use `movsxd` to widen it.
- **Speed.** One byte or one element per iteration is slow. Libraries copy 32 bytes at a time with vector registers, or use `rep movsb`, which modern processors accelerate. The C library's `strlen` reads 16 to 32 bytes per step and takes care never to cross into an unmapped page.

## Further reading

- [Felix Cloutier's x86 reference](https://www.felixcloutier.com/x86/) documents `mov`, `movzx`, `movsxd`, `lea`, and the string instructions such as `rep movsb`.
- [Compiler Explorer](https://godbolt.org) shows how clang indexes arrays at each `-O` level. Switch the element type between `char`, `int`, and `long` and watch the scale change.
- [The Python ctypes documentation](https://docs.python.org/3/library/ctypes.html) covers arrays, `create_string_buffer`, `argtypes`, and pointers.
- [Computer Systems: A Programmer's Perspective](https://csapp.cs.cmu.edu/) chapter 3 develops addressing modes, array access, and the struct and pointer idioms in assembly.
- [AddressSanitizer](https://clang.llvm.org/docs/AddressSanitizer.html) is clang's tool for catching out-of-bounds reads and writes in compiled C.

## The exercise

You write seven functions: `nth_asm`, `sum_i64_asm`, `sum_i32_asm`, `max_i64_asm`, `reverse_asm`, `strlen_asm`, and `copy_bytes_asm`. Each returns Intel-syntax text defining the symbol named in its docstring (`nth`, `sum_i64`, `sum_i32`, `max_i64`, `reverse_i64`, `my_strlen`, and `copy_bytes`).

Every check runs your code in a forked child process with a time limit. A crash reports the signal, and a hang reports the case that never finished. Inputs include empty arrays, one element, even and odd lengths, the extremes of `int32` and `int64`, strings with bytes above 127, and strings with data after the zero byte.
