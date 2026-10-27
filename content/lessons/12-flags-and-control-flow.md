---
title: "Flags, comparisons, and control flow"
slug: 12-flags-and-control-flow
part: "Part 2 — x86-64 assembly"
summary: Use cmp, test, flags, conditional jumps, cmov, and setcc to write max, abs, clamp, and loops in x86-64 assembly.
minutes: 60
gpu: false
objectives:
  - Say which flags cmp sets and how a conditional jump reads them.
  - Write a loop in x86-64 assembly with a counter, a compare, and a backward jump.
  - "Choose the right condition for the data: jl for signed values, jb for unsigned."
  - Pick between a branch and a conditional move for a two-way choice.
prereqs:
  - 11-first-assembly
exercise: 12-flags-and-control-flow
---

# Flags, comparisons, and control flow

So far your assembly ran straight down: first instruction, second instruction, `ret`. Real programs make choices and repeat work. A function that returns the larger of two numbers must look at both. A function that sums 1 to *n* must go back and do the same step again.

Assembly has no `if` or `while`. It has two ingredients instead. One instruction compares two values and records the outcome in the flags. Another instruction jumps to a different place if the flags say so. Every `if`, `for`, and `while` you have ever written becomes a pattern of those two.

This lesson teaches the pattern. The surprise is that the CPU never records whether a comparison was "signed" or "unsigned". It records facts about the subtraction, and the *jump you choose* decides how to read them.

## What you already know

- A flag is one bit of CPU state set by an arithmetic result, such as zero, negative, carry, and overflow (lesson 4).
- Subtraction is addition of the two's complement, and a borrow means the unsigned result went below zero (lesson 3).
- A register holds 64 bits, and `eax` is its low half (lesson 11).
- A branch changes the program counter, and CPUs predict branches to keep the pipeline full (lessons 5 and 10).
- The first arguments arrive in `rdi`, `rsi`, and `rdx`, and the result goes in `rax` (lesson 11).

## The four flags

The CPU keeps a register called `rflags`. Most arithmetic instructions update a few of its bits. Four matter for control flow:

| Flag | Name | Set to 1 when |
|---|---|---|
| `ZF` | zero | the result is zero |
| `SF` | sign | the top bit of the result is 1 |
| `CF` | carry | an unsigned operation carried out of the top bit, or borrowed in a subtraction |
| `OF` | overflow | a signed operation's result does not fit |

You met all four in the ALU of lesson 4. The x86 flags are the same idea.

The instruction `cmp a, b` computes `a - b`, throws the answer away, and keeps the flags. The instruction `test a, b` computes `a AND b`, throws the answer away, and sets `ZF` and `SF` from it. A common use is `test rdi, rdi`, which sets `ZF` when `rdi` is zero and `SF` when it is negative.

> [!KEY]
> `cmp a, b` is a subtraction that only keeps the flags. A conditional jump that follows reads those flags and decides.

## Worked example: cmp 3, 7 in 8 bits

Use 8-bit numbers so every bit fits on the page. Compute `3 - 7`:

```text
  00000011   (3)
- 00000111   (7)
----------
  11111100   = 0xFC   (the borrow out of the top bit is 1)

ZF = 0   the result is not zero
SF = 1   the top bit is 1
CF = 1   a borrow happened: as unsigned, 3 < 7
OF = 0   as signed, 3 - 7 = -4 fits in 8 bits
```

Now try `cmp 100, -100`. In 8 bits, -100 is `10011100`, which is 156 when read as unsigned. The true signed answer is 100 - (-100) = 200, which does not fit in a signed byte, because the range ends at 127. The CPU computes the 8-bit result `0xC8`:

```text
  01100100   (100)
- 10011100   (-100, or 156 unsigned)
----------
  11001000   = 0xC8   (a borrow out of the top bit)

ZF = 0
SF = 1   the top bit of 0xC8 is 1
CF = 1   a borrow happened: as unsigned, 100 < 156
OF = 1   as signed, the true answer 200 does not fit in 8 bits
```

The sign bit alone cannot tell you "less than". Here `SF = 1`, yet 100 is *greater* than -100 as signed numbers. The test that works is `SF != OF`. Here `SF = 1` and `OF = 1`, so they are equal, and the answer is "not less". That is correct.

## Conditional jumps read the flags

A conditional jump has the form `jcc label`, where `cc` is a condition code. If the condition holds, the CPU continues at the label. Otherwise it goes on to the next instruction.

The next table shows the common conditions. Pick the row by what the data means, not by what the numbers look like.

| Meaning | Signed data | Unsigned data | Flags tested |
|---|---|---|---|
| a == b | `je` | `je` | `ZF = 1` |
| a != b | `jne` | `jne` | `ZF = 0` |
| a < b | `jl` | `jb` (below) | signed: `SF != OF`, unsigned: `CF = 1` |
| a <= b | `jle` | `jbe` | signed: `ZF = 1` or `SF != OF`, unsigned: `CF = 1` or `ZF = 1` |
| a > b | `jg` | `ja` (above) | signed: `ZF = 0` and `SF = OF`, unsigned: `CF = 0` and `ZF = 0` |
| a >= b | `jge` | `jae` | signed: `SF = OF`, unsigned: `CF = 0` |

Equality is the same either way. Ordering is not.

Here is the proof that signedness lives in the jump. Compare the 64-bit values `rdi = -1` and `rsi = 1` with `cmp rdi, rsi`. The bits of -1 are all ones, `0xFFFFFFFFFFFFFFFF`.

```text
  0xFFFFFFFFFFFFFFFF - 0x0000000000000001 = 0xFFFFFFFFFFFFFFFE

ZF = 0
SF = 1   the top bit is 1
CF = 0   no borrow: as unsigned, 2^64 - 1 is not below 1
OF = 0   as signed, -1 - 1 = -2 fits

jl  : SF != OF  ->  1 != 0  ->  taken     (-1 < 1 as signed)
jb  : CF = 1    ->  0       ->  not taken (2^64 - 1 < 1 is false as unsigned)
```

One `cmp`, two opposite answers. The data is the same 64 bits. In C the types `long` and `unsigned long` make the compiler pick `jl` or `jb`. In assembly, you pick.

> [!WARNING]
> Using `jl` on unsigned data, or `jb` on signed data, gives wrong answers when the two values differ in their top bit. Test with `-1` and the maximum value, not only small numbers.

## An if in assembly

Write absolute value for a 32-bit `int`. In C it reads `if (x < 0) x = -x;`. In assembly the structure is a test, a skip, and the work:

```asm
    .globl abs32
abs32:
    mov eax, edi        # answer starts as x
    test edi, edi       # sets SF from x
    jns .Ldone          # jump if not sign: x >= 0, nothing to do
    neg eax             # x was negative: eax = -x
.Ldone:
    ret
```

Labels that start with `.L` are local: they do not appear in the symbol table, so two functions can reuse a name. The control flow looks like this, with one arrow skipping the `neg`:

```text
        mov eax, edi
        test edi, edi
             |
     jns ----+------------+
             |            | (x >= 0)
        neg eax           |
             |            |
             +------------+
             |
           .Ldone: ret
```

One edge case: `abs32(INT_MIN)`. The value -2147483648 has no positive partner in 32 bits, because 2147483648 does not fit. `neg` leaves it as `0x80000000`, which is -2147483648 again. C calls signed overflow undefined behaviour, and the hardware wraps.

## cmov and setcc: choose without jumping

A *conditional move*, `cmovcc dst, src`, copies `src` into `dst` only if the condition holds. There is no jump and no label. The `max` of two signed ints is three instructions:

```asm
    .globl max2
max2:
    mov eax, edi        # assume a is the answer
    cmp edi, esi        # compare a with b
    cmovl eax, esi      # if a < b (signed), take b instead
    ret
```

The `setcc` family writes a single byte, 0 or 1, from a condition. It writes only the low byte, `al`, so clear the whole register first:

```asm
    .globl less_signed
less_signed:
    xor eax, eax        # eax = 0, and this also clears the upper half of rax
    cmp rdi, rsi        # the flags come from this
    setl al             # al = 1 if rdi < rsi (signed)
    ret
```

The order matters. `xor` changes the flags, so it must come *before* `cmp`. If you write `cmp` first and `xor eax, eax` second, `setl` reads the flags of the `xor`, and every answer is wrong.

A branch or a conditional move? A branch is cheap when the CPU predicts it. A *misprediction* flushes the pipeline and costs roughly 15 to 20 cycles on modern x86 processors (lesson 10). A `cmov` always costs the same, a cycle or two, because the choice becomes ordinary data flow. But `cmov` computes both sides, so it loses when one side is expensive or when the branch is predictable. Compilers weigh this with heuristics, and the choice changes between versions.

## Loops: a label, a body, and a backward jump

A loop is a conditional jump to an earlier label. Here is `sum_to(n)`, which adds 1 + 2 + ... + n and returns 0 when n is zero or negative. Two registers carry the state: `rax` is the total and `rcx` is the counter.

```asm
    .globl sum_to
sum_to:
    xor eax, eax        # total = 0
    mov ecx, 1          # i = 1
.Lloop:
    cmp rcx, rdi        # compare i with n
    jg .Ldone           # if i > n (signed), stop
    add rax, rcx        # total += i
    inc rcx             # i += 1
    jmp .Lloop          # back to the top
.Ldone:
    ret
```

The test sits at the top, so a loop that should run zero times does. For n = -3, the first compare says `1 > -3` and the function returns 0 at once. Here is the trace for n = 4:

| Pass | `rcx` at compare | `rcx > n`? | `rax` after the body |
|---|---|---|---|
| 1 | 1 | no | 1 |
| 2 | 2 | no | 3 |
| 3 | 3 | no | 6 |
| 4 | 4 | no | 10 |
| 5 | 5 | yes, exit | 10 |

The jump `jmp .Lloop` goes backward, to an address lower than itself. A backward jump is the machine-level signature of a loop. A static predictor (lesson 10) guesses that a backward branch is a loop and predicts it taken.

## Counting bits with a loop

A bit-counting loop tests the lowest bit, adds it, shifts, and stops when nothing is left. The structure is the same as `sum_to`, with `test` for the exit check. For `x = 0b1011`, the loop runs four times, adding 1, 1, 0, and 1, and returns 3. The shift is `shr`, because the input is unsigned: `sar` would copy the sign bit and never reach zero for a negative-looking value.

## Try it on your own machine

1. Compile `int max2(int a, int b) { return a > b ? a : b; }` with `clang -O2 -S -masm=intel -fno-asynchronous-unwind-tables`. Look for `cmov`. Try `-O0` and see a real branch.
2. Compile `long f(long x) { long s = 0; for (long i = 1; i <= x; i++) s += i; return s; }` at `-O2`. Clang can remove the loop and computes the answer with a multiply, because it recognises the sum formula. Look for the missing backward jump.
3. On Linux, `perf stat -e branches,branch-misses ./your_program` reports how many branches ran and how many the predictor missed. This needs the `perf` tool, which is not part of clang.
4. In Python, build the signed and unsigned views of one value: `x = 2**64 - 1; print(x, x - 2**64)`. This prints 18446744073709551615 and -1, the two readings of the same bits.

## Build it step by step

Fill in `starter.py` in this order. Each function returns assembly text with the symbols named in its docstring.

1. `max2_asm()` defines `max2(a, b)` on 32-bit signed ints. Use `cmp` and `cmovl`, or a jump. The common mistake is `cmovb`, which treats the numbers as unsigned and fails for negatives.
2. `abs_asm()` defines `abs32(x)`. Copy `x` into `eax`, test its sign, and negate when negative. The check includes `INT_MIN`, which must come back unchanged.
3. `clamp_asm()` defines `clamp(x, lo, hi)`. Two compares and two conditional moves work: first raise to `lo`, then lower to `hi`. Arguments arrive in `edi`, `esi`, and `edx`.
4. `compare_asm()` defines two functions. In this step, write `less_signed(a, b)` with `setl`. Clear the result register before the `cmp`.
5. In the same text, write `less_unsigned(a, b)` with `setb`. The check feeds it `(-1) & (2**64 - 1)` and expects 0 for `less_unsigned(that, 1)`.
6. `sum_to_asm()` defines `sum_to(n)` with a real loop. The check reads your text and fails when there is no backward jump, so a closed-form formula is rejected. A common mistake is `jge` instead of `jg`, which adds an extra pass.
7. `popcount_asm()` defines `popcount(x)` on a 64-bit unsigned value. Do not use the `popcnt` instruction. The common mistake is a loop that never ends when the shift is `sar`.

## Where this breaks

- **Flags change under your feet.** Any instruction between the `cmp` and its consumer can change the flags. `mov` and `lea` leave them alone. `add`, `sub`, `xor`, `and`, `inc`, and `shr` change them.
- **Off-by-one in the loop test.** Using `jge` where `jg` is needed adds one extra iteration. Trace the smallest input by hand.
- **Infinite loops.** Forget the counter update and the loop never exits. The checks kill a function that runs over five seconds and report which input hung.
- **`cmov` is not free.** It waits for both inputs. If `src` is a memory load, the load happens even when the move is not taken, and a bad address crashes. Compilers avoid `cmov` for unsafe loads.
- **`inc` and `dec` skip `CF`.** They update every arithmetic flag except the carry flag. After `inc rcx`, a `jb` reads an older carry. Avoid mixing them with unsigned conditions.
- **A mispredicted branch dominates.** A loop test that depends on random data costs a flush per miss. Real code uses branchless forms, lookup tables, or sorting the data first.

## Further reading

- [Felix Cloutier's x86 reference](https://www.felixcloutier.com/x86/) gives the exact flag effects of `cmp`, `test`, `neg`, and every `Jcc`, `CMOVcc`, and `SETcc` form.
- [Compiler Explorer](https://godbolt.org) shows when clang picks `cmov` over a branch. Change the `-O` level and the data type and watch the condition code switch between `l` and `b`.
- [Agner Fog's optimization manuals](https://www.agner.org/optimize/) quantify branch misprediction penalties and when `cmov` wins.
- [Computer Systems: A Programmer's Perspective](https://csapp.cs.cmu.edu/) covers condition codes, jumps, and loops in chapter 3, with the same signed and unsigned distinction.
- [The Jcc page of the x86 reference](https://www.felixcloutier.com/x86/jcc) tabulates every conditional jump with its flag condition. Keep it open while you work.

## The exercise

You write seven functions. `max2_asm`, `abs_asm`, and `clamp_asm` choose between values with `cmp` and conditional moves or jumps. `compare_asm` defines `less_signed` and `less_unsigned`, which disagree on the same bits. `sum_to_asm` and `popcount_asm` are loops.

The checks assemble your text and call each function in a child process. A hang or a crash reports the input that caused it. Inputs include `INT_MIN`, `INT_MAX`, zero, and negatives, and the 64-bit comparison checks use the full range, because a wrong condition code shows up only there.
