---
title: "Your first x86-64 assembly"
slug: 11-first-assembly
part: "Part 2 — x86-64 assembly"
summary: Write real x86-64 functions in Intel-syntax assembly, assemble them, and call them from Python with ctypes.
minutes: 55
gpu: false
objectives:
  - Name the System V argument registers and say where a function leaves its result.
  - Explain why writing a 32-bit register clears the upper half of the 64-bit one.
  - Use mov, add, lea, imul, and the shift instructions to compute simple expressions.
  - Call assembly from Python with ctypes, setting argtypes and restype correctly.
prereqs:
  - 10-branch-prediction-and-out-of-order
exercise: 11-first-assembly
---

# Your first x86-64 assembly

Every program you have ever run ended up as machine code: bytes the processor decodes and executes. In Part 1 you built a toy CPU and encoded RISC-V instructions by hand. This lesson moves to the real thing. You write instructions for the processor in the machine under your desk, an x86-64 chip, and you run them.

You do not write the bytes. You write *assembly language*, a text form of machine code where each line is one instruction with a readable name. A program called an *assembler* turns the text into bytes. Assembly is the lowest level a person reasonably reads and writes, and every compiler in the rest of this course produces it.

You will write small functions that return a number, add, multiply, and shift. The checks assemble your text and call your functions from Python, so you see real results from real instructions within minutes.

## What you already know

- A bit is a 0 or 1, and a 64-bit register holds 64 of them (lesson 2).
- Two's complement represents negative numbers, and sign extension widens a number without changing its value (lesson 3).
- A CPU fetches an instruction, decodes it, and executes it, using a small set of named registers (lesson 5).
- An instruction is a few bytes with fields for the operation and its operands (lesson 6).
- Memory is a long row of bytes, and a function call saves a return address (lesson 7).

## Registers: the CPU's named variables

A *register* is a tiny, named storage slot inside the CPU. Instructions read and write registers directly, which is far faster than touching memory. An x86-64 processor has 16 general-purpose registers, each 64 bits wide:

```text
rax  rbx  rcx  rdx  rsi  rdi  rbp  rsp
r8   r9   r10  r11  r12  r13  r14  r15
```

The names `rax` through `rsp` are historical. The `r` means "64-bit". Older processors had 32-bit registers named `eax`, `ebx`, and so on, and 16-bit ones before that. The 64-bit registers kept the old names as smaller windows onto the same storage.

The next diagram shows the windows into `rax`. Bit 63 is on the left and bit 0 on the right.

```text
bit 63                         32 31             16 15      8 7       0
+-------------------------------+-----------------+---------+---------+
|                               |                 |   ah    |   al    |
|                               |                 +---------+---------+
|                               |                ax                   |
|                               +-------------------------------------+
|                               |                eax                  |
+-------------------------------+-------------------------------------+
|                               rax                                    |
+----------------------------------------------------------------------+
```

The next table lists the names for four registers. Registers `r8` to `r15` use the suffixes `d`, `w`, and `b`.

| 64-bit | 32-bit | 16-bit | 8-bit (low) |
|---|---|---|---|
| `rax` | `eax` | `ax` | `al` |
| `rdi` | `edi` | `di` | `dil` |
| `rsi` | `esi` | `si` | `sil` |
| `r8` | `r8d` | `r8w` | `r8b` |

A name tells the instruction how wide the operation is. `add eax, esi` adds 32-bit values. `add rax, rsi` adds 64-bit values.

> [!KEY]
> A 32-bit write to a register clears the upper 32 bits of the 64-bit register. Writes to the 16-bit and 8-bit names leave the other bits alone.

Here is the rule in action. Suppose `rax` holds `0xFFFFFFFF_FFFFFFFF`. After `mov eax, 5`, `rax` holds `0x00000000_00000005`. The upper half is cleared, because the 32-bit write zero-extends. After `mov al, 5` instead, `rax` holds `0xFFFFFFFF_FFFFFF05`. Only the low byte changed.

## Anatomy of an assembly function

Intel syntax puts the *destination first*: `mov rax, rdi` copies `rdi` into `rax`. (The other common style, AT&T syntax, reverses the order and adds `%` signs. This course uses Intel syntax.) The next listing is a complete function that returns 42:

```asm
    .globl forty_two
forty_two:
    mov eax, 42
    ret
```

Each piece has a job:

- `.globl forty_two` is a directive, an instruction to the assembler rather than the CPU. It makes the name visible outside the file, so Python can find it.
- `forty_two:` is a *label*, a name for the address of the next instruction. A function is the address its label marks.
- `mov eax, 42` copies the number 42 into `eax`. It also clears the top half of `rax`, so `rax` holds exactly 42.
- `ret` returns to the caller. Without it, the CPU keeps executing whatever bytes follow, which crashes the program.

Why `eax` and not `rax`? The instruction `mov eax, 42` encodes in 5 bytes, `b8 2a 00 00 00`. The 64-bit `mov rax, 42` takes 7. A shorter encoding means less memory to fetch, and the result is identical. Compilers use the 32-bit form whenever the value fits.

## The System V calling convention, first look

How does a function learn its inputs, and where does it leave its answer? Both sides must agree in advance. That agreement is the *calling convention*. On Linux for x86-64 it is the System V AMD64 ABI. (ABI means application binary interface: the rules for how compiled code talks to other compiled code.)

The first six integer or pointer arguments go in registers, in this order. The result goes in `rax`:

| Role | Register | 32-bit name |
|---|---|---|
| 1st argument | `rdi` | `edi` |
| 2nd argument | `rsi` | `esi` |
| 3rd argument | `rdx` | `edx` |
| 4th argument | `rcx` | `ecx` |
| 5th argument | `r8` | `r8d` |
| 6th argument | `r9` | `r9d` |
| Result | `rax` | `eax` |

So a C function `long add64(long a, long b)` receives `a` in `rdi` and `b` in `rsi`. Lesson 14 covers the rest of the convention: more arguments, which registers survive a call, and stack alignment.

Python calls your function through `ctypes`, which follows the same convention. By default ctypes treats every argument and result as a C `int`, 32 bits. For anything else you declare the types:

```python
import ctypes
import cputools

lib = cputools.assemble(text)            # text holds your assembly
lib.add64.argtypes = [ctypes.c_int64, ctypes.c_int64]
lib.add64.restype = ctypes.c_int64
print(lib.add64(40, 2))                  # 42
```

Forget `restype = c_int64` and Python keeps only the low 32 bits of `rax`. A correct 64-bit answer then looks wrong. That is the most common confusing result in this course.

## mov, add, and sub

`mov dst, src` copies. `add dst, src` computes `dst = dst + src`, and `sub dst, src` computes `dst = dst - src`. The destination is also an input. There is no three-operand `add`.

Here is `add64`, with each register's value traced for the call `add64(40, 2)`:

```asm
    .globl add64
add64:
    mov rax, rdi        # rax = 40
    add rax, rsi        # rax = 40 + 2 = 42
    ret
```

The 32-bit version uses the 32-bit names. It wraps at 32 bits, exactly like C's `int` addition on this machine. Here `edi` is 2147483647, the largest signed 32-bit value, and `esi` is 1:

```asm
    .globl add32
add32:
    mov eax, edi        # eax = 0x7FFFFFFF
    add eax, esi        # eax = 0x80000000, which is -2147483648 as a signed int
    ret
```

The CPU does not know whether your numbers are signed. It adds the bits and sets flags. Lesson 12 uses the flags. The wrapped result `0x80000000` is -2147483648 only because you read it as two's complement.

## lea: arithmetic with the address unit

The CPU has hardware that computes addresses, such as "base plus index times 4". The `lea` instruction (load effective address) exposes that hardware as a calculator. It computes the address expression and stores the *number*, without reading any memory.

```asm
    .globl scale4_add
scale4_add:
    lea rax, [rsi + rdi*4]    # rax = b + a*4, no memory is touched
    ret
```

Inside the brackets you may write `base + index*scale + displacement`, where the scale is 1, 2, 4, or 8. One `lea` does a multiply by a small power of two, two adds, and the move. With `a = 10` and `b = 7` the result is 7 + 10 × 4 = 47. Compilers love `lea` for ordinary arithmetic, so you will see it everywhere.

## imul and the shifts

`imul` multiplies signed values. Its three-operand form takes a register and a constant: `imul rax, rdi, 7` computes `rax = rdi * 7`. The result keeps only the low 64 bits, so overflow wraps.

Shifts move bits left or right by a count. There are three:

| Instruction | Name | Fills the vacated bits with | Same as |
|---|---|---|---|
| `shl rax, 3` | shift left | zeros | multiply by 8 |
| `shr rax, 3` | shift right, logical | zeros | unsigned divide by 8 |
| `sar rax, 3` | shift right, arithmetic | copies of the sign bit | signed divide by 8, rounding down |

Take -9 as an 8-bit value, `11110111`. A logical shift right by 3 gives `00011110`, which is 30. An arithmetic shift right by 3 copies the sign bit into the top, giving `11111110`, which is -2. And -9 divided by 8 rounds *down* to -2, so `sar` computes the floor of the quotient. At 64 bits, `shr` of -9 gives `0x1FFFFFFFFFFFFFFE`, a huge positive number.

The rule for choosing: use `sar` for signed values and `shr` for unsigned ones. The instruction, not the data, carries the signedness.

## Widening and narrowing, again

Lesson 3 covered sign and zero extension. The same ideas appear here as instructions.

- `mov eax, edi` keeps the low 32 bits of `rdi` and zero-extends. The upper half of `rax` becomes 0.
- `movsxd rax, edi` sign-extends the 32-bit value in `edi` into all of `rax`. If `edi` is `0xFFFFFFF6` (-10), `rax` becomes `0xFFFFFFFFFFFFFFF6`, still -10.

When a C function takes an `int`, the ABI promises only that the *low 32 bits* of `rdi` hold the value. The upper 32 bits can contain anything. So a function that reads `rdi` as a full 64-bit number when its argument is an `int` has a bug. It works until some caller leaves junk in the top half. Use `edi`, and use `movsxd` when you need the value widened.

> [!WARNING]
> Never read the upper half of an argument register for a 32-bit argument. The ABI leaves it undefined, and the checks fill it with junk on purpose.

## Try it on your own machine

These commands need only `clang`, which you already use in this course.

1. Write the C function `long f(long a, long b) { return a * 4 + b; }` in `f.c`. Run `clang -O2 -S -masm=intel -fno-asynchronous-unwind-tables f.c -o -`. Look for a single `lea` instruction: the compiler picked the same trick as `scale4_add` above.
2. Assemble and disassemble in one step with `clang -c -O2 f.c -o f.o && objdump -d -M intel f.o`. The hex bytes on the left are the machine code. Find `ret`, which is the single byte `c3`.
3. Open https://godbolt.org, choose C, type the function above, and pick x86-64 clang with `-O2`. The right pane shows assembly, colour-matched to your source lines.
4. In Python, run `import ctypes; print(ctypes.CDLL(None).labs(-5))`. The default result type is `int`, which happens to work for a small number. Then try `ctypes.CDLL(None).strlen(b"hello")` and set `restype = ctypes.c_size_t` to see how a wider result type is declared. This works on Linux and macOS.

## Build it step by step

Fill in the functions in `starter.py` in this order. Each returns assembly text as a string. Every function needs `.globl name` and `name:` with the exact name in its docstring, and ends in `ret`.

1. `forty_two_asm()` defines `forty_two`, which returns 42. Put the constant in `eax`. The common mistake is forgetting `ret`, which makes the function run into whatever follows.
2. `add64_asm()` defines `add64(a, b)`. Copy `rdi` into `rax`, then add `rsi`. The common mistake is using 32-bit names, which drops the top half of large numbers.
3. `add32_asm()` defines `add32(a, b)` on `int` values. Use `edi`, `esi`, and `eax`. The check passes `INT_MAX` plus 1 and expects -2147483648.
4. `lea_asm()` defines `scale4_add(a, b)`, which returns `a * 4 + b` with one `lea`. The check reads your text and fails if it contains no `lea`.
5. `imul_asm()` defines `times7(x)`. Use the three-operand `imul`. The common mistake is the two-operand form, which needs the constant in a register.
6. `shifts_asm()` defines three functions in one text: `shl3`, `sar3`, and `shr3`. Copy the argument into `rax`, then shift `rax`. The common mistake is swapping `sar` and `shr`, which only shows up on negative inputs.
7. `low32_asm()` defines `low32(x)`, the low 32 bits of a 64-bit unsigned value. One `mov` with 32-bit names does it, because 32-bit writes clear the top half.
8. `widen_asm()` defines `widen(x)`, which sign-extends a 32-bit `int` to 64 bits. The check puts junk in the upper half of `rdi`. Use `movsxd rax, edi`, and a plain `mov rax, rdi` fails.

## Where this breaks

- **Different syntax.** Many tutorials and tools use AT&T syntax, with `%rax` and reversed operands. `mov %rdi, %rax` and `mov rax, rdi` do the same thing. Tools such as `objdump` default to AT&T. Pass `-M intel` to get the Intel form.
- **Different ABIs.** Windows on x86-64 passes the first four arguments in `rcx`, `rdx`, `r8`, and `r9`. Linux and macOS use the System V order from this lesson. Assembly is tied to the operating system's conventions as well as to the processor.
- **Flags are side effects.** `add` and `sub` change the flags, and `mov` and `lea` do not. Lesson 12 shows a bug that comes from clearing a register with `xor` between a compare and the instruction that reads its result.
- **No type checking.** The assembler accepts `add eax, esi` or `add rax, rsi` equally. Mixing widths by accident gives wrong answers with no error. The assembler does reject mismatched sizes within one instruction, such as `add eax, rsi`.
- **A missing `ret` is silent.** The CPU runs on into the next bytes. The result is usually a crash far from the real mistake.
- **A different processor.** ARM, Apple silicon, and RISC-V have other registers and other instructions. The ideas carry over, and the names do not.

## Further reading

- [Felix Cloutier's x86 instruction reference](https://www.felixcloutier.com/x86/) lists every instruction with its operands, encoding, and effect on flags. Look up `mov`, `lea`, `imul`, `sar`, and `movsxd`.
- [Compiler Explorer](https://godbolt.org) shows the assembly clang produces for C you type, live. Try `-O0` and `-O2` on one function.
- [The System V AMD64 ABI](https://gitlab.com/x86-psABIs/x86-64-ABI) is the full specification of the calling convention. Chapter 3.2 covers argument passing.
- [Intel 64 and IA-32 Architectures Software Developer's Manual](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html) is the authoritative reference. Volume 1 describes registers and the 32-bit write rule.
- [Agner Fog's optimization manuals](https://www.agner.org/optimize/) explain what each instruction costs on real processors, including why `lea` is fast.

## The exercise

You write eight small pieces of assembly: `forty_two_asm`, `add64_asm`, `add32_asm`, `lea_asm`, `imul_asm`, `shifts_asm`, `low32_asm`, and `widen_asm`. Each returns Intel-syntax text with the symbol named in its docstring.

The checks assemble your text with `cputools.assemble` and call the result through `ctypes` in a child process, so a crash is reported instead of ending the run. They compare against a Python reference on many inputs, including zero, negative numbers, and the largest and smallest 32- and 64-bit values. Click **Run** to see your `add64` assembled and disassembled once the first functions work.
