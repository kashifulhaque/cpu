---
title: Integers, two's complement, and overflow
slug: 03-integers-and-overflow
part: "Part 0 — Getting started"
summary: See how a fixed number of bits holds negative numbers, why additions wrap around, and how hardware detects overflow.
minutes: 55
gpu: false
objectives:
  - Wrap any Python int into an N-bit unsigned or signed value.
  - Negate a number in two's complement by flipping the bits and adding one.
  - Tell unsigned overflow (carry) from signed overflow, and detect each one.
  - Extend a narrow value to a wider one with zero extension or sign extension.
prereqs:
  - 02-bits-and-binary
exercise: 03-integers-and-overflow
---

# Integers, two's complement, and overflow

A Python int can be as large as memory allows. A number in a CPU register cannot. It has a fixed number of bits, usually 8, 16, 32, or 64, and when a result needs more bits than that, the extra ones are lost. A byte that holds 255 and gets 1 added to it holds 0.

Every program you will read at the assembly level depends on this. The `int` in C, the `rax` register, and the flags that tell a program "that addition went wrong" are all about fixed-width numbers. A reader who does not know how they behave will misread loops, comparisons, and compiler output.

In this lesson you build Python versions of the rules, and then you check them against a real C compiler. If your Python agrees with the machine on hundreds of inputs, you have understood the rules.

## What you already know

- A number is a row of bits, and `bin` and `hex` show the bits.
- `%` gives a remainder, and `x % 256` is always in the range 0 to 255 in Python.
- `x & 0xFF` keeps the low 8 bits of `x`, and `x >> n` and `x << n` shift bits.
- A byte holds 256 patterns, and N bits hold $2^N$ patterns.

## Fixed width and wrap-around

Think of an odometer on a car. It has a fixed number of wheels. When it shows 99999 and the car drives one more kilometre, it rolls over to 00000. It does not show 100000, because there is no sixth wheel.

A register is the same. An 8-bit register holds the patterns 0 to 255. If the true answer is 256, the hardware keeps the low 8 bits, which is 0. The arithmetic is *modular*: numbers wrap around at $2^N$.

In this lesson a *pattern* is the row of N bits, read as an unsigned number from 0 to $2^N - 1$. The same pattern can mean different numbers depending on how you read it. The rest of the lesson is about that choice.

To wrap any Python int into the N-bit range, take the remainder after dividing by $2^N$:

```python
def to_unsigned(x, bits):
    return x % (1 << bits)

# to_unsigned(300, 8) -> 44      300 - 256
# to_unsigned(-1, 8)  -> 255     -1 + 256
```

The second line shows why Python's `%` is useful here. For a positive divisor it never returns a negative number, so `-1 % 256` is `255`. In C, `-1 % 256` is `-1`, and a different method would be needed.

> [!KEY]
> A fixed-width register does arithmetic modulo $2^N$. The hardware keeps the low N bits of every result and drops the rest.

## Two's complement: negative numbers in bits

How do you store -5 in a row of bits? There is no minus sign. The scheme that almost every computer uses is *two's complement*. Read the pattern as an unsigned number, then subtract $2^N$ if the top bit is 1.

For 8 bits, the patterns 0 to 127 mean themselves. The patterns 128 to 255 mean negative numbers: pattern `p` means `p - 256`.

```text
pattern (binary)   unsigned   signed
00000000                0          0
00000001                1          1
01111111              127        127
10000000              128       -128
10000001              129       -127
11111110              254         -2
11111111              255         -1
```

The top bit is called the *sign bit*. It is 1 for every negative number. It also has a weight: in 8 bits it counts as -128 instead of +128. To read `11111011`, add the weights of the 1 bits: -128 + 64 + 32 + 16 + 8 + 2 + 1 = -5.

The range of an N-bit signed number is $-2^{N-1}$ to $2^{N-1} - 1$.

| Bits | Signed range | Unsigned range |
|---|---|---|
| 8 | -128 to 127 | 0 to 255 |
| 16 | -32,768 to 32,767 | 0 to 65,535 |
| 32 | -2,147,483,648 to 2,147,483,647 | 0 to 4,294,967,295 |

There is one more negative number than positive ones, because zero uses up a pattern on the non-negative side.

Reading a pattern as signed takes two steps. Wrap it to N bits, then subtract $2^N$ if the sign bit is set.

```python
def to_signed(x, bits):
    pattern = x % (1 << bits)
    if pattern >> (bits - 1):      # top bit set?
        return pattern - (1 << bits)
    return pattern

# to_signed(200, 8) -> -56    200 - 256
```

### Negation: flip and add one

Why this scheme? Because the same adder hardware works for signed and unsigned numbers. And negation is cheap. To negate a number, flip every bit, then add one.

Here is -5 built from 5 in 8 bits:

```text
 5          = 0 0 0 0 0 1 0 1
flip bits   = 1 1 1 1 1 0 1 0     (this is 250, or -6)
add one     = 1 1 1 1 1 0 1 1     = 251, which reads as -5
```

Check it: 5 plus its negation should wrap to 0. Adding `00000101` and `11111011` gives `100000000`, which is 9 bits. The hardware keeps 8, so the result is `00000000`. 

Two cases deserve a look. Negating 0 gives 0. Negating `10000000` (-128) gives `10000000` again, because +128 does not exist in 8 bits. The most negative number is its own negative.

> [!WARNING]
> The most negative number has no positive partner. `-INT_MIN` and `abs(INT_MIN)` overflow in every fixed width, and in C they are real bugs.

## Overflow: two different problems

An addition *overflows* when the true answer does not fit in N bits. The trouble is that "fit" has two meanings, one for each way of reading the bits. The same addition can overflow for one reading and not the other.

Take two 8-bit patterns, 200 and 100. Read as unsigned they are 200 and 100, and the sum is 300. That is more than 255, so it overflows as unsigned. Read as signed they are -56 and 100, and the sum is 44. That fits. The pattern the hardware produces is the same: 300 wraps to 44.

Take 100 and 100. Unsigned, the sum is 200, which fits. Signed, 100 + 100 = 200 is more than 127, so it overflows as signed. The pattern 200 reads as -56, which is wrong as a signed sum of two positive numbers.

| a | b | unsigned sum | overflow as unsigned? | signed sum | overflow as signed? |
|---|---|---|---|---|---|
| 200 | 100 | 300 | yes | -56 + 100 = 44 | no |
| 100 | 100 | 200 | no | 100 + 100 = 200 | yes |
| 255 | 1 | 256 | yes | -1 + 1 = 0 | no |
| 128 | 128 | 256 | yes | -128 + -128 = -256 | yes |
| 1 | 2 | 3 | no | 3 | no |

Hardware reports each case with its own *flag*, a single bit that remembers something about the last operation. The *carry flag* is set when the unsigned sum is too large, which means a 1 was carried out of the top bit. The *overflow flag* is set when the signed result is wrong. You build both flags from gates in lesson 04.

A neat rule for signed overflow: it happens when you add two numbers with the same sign and the result has the opposite sign. Adding a positive and a negative number can never overflow, because the result lies between them.

> [!KEY]
> Carry means the unsigned result did not fit. Overflow means the signed result did not fit. The adder is the same for both, and the program decides which reading to believe.

In code, you test both with plain arithmetic. For patterns `a` and `b`:

```python
unsigned_overflow = a + b > (1 << bits) - 1
signed_sum = to_signed(a, bits) + to_signed(b, bits)
signed_overflow = not (-(1 << (bits - 1)) <= signed_sum <= (1 << (bits - 1)) - 1)
```

## Extending a value to more bits

Sometimes a program moves a narrow number into a wider register: an 8-bit value into 32 bits. The question is what the upper bits hold.

- *Zero extension* fills the upper bits with 0. It is right for unsigned numbers. The pattern `0xFF` (255) widens to `0x000000FF`, still 255.
- *Sign extension* copies the sign bit into all the upper bits. It is right for signed numbers. The pattern `0xFF` (-1) widens to `0xFFFFFFFF`, still -1.

```text
8-bit pattern     0xF0   =  1111 0000   (signed -16, unsigned 240)

zero-extend to 16 bits:   0000 0000 1111 0000  = 0x00F0 = 240
sign-extend to 16 bits:   1111 1111 1111 0000  = 0xFFF0 = -16
```

Sign extension keeps the signed value the same. In Python, convert to signed first, then wrap into the wider width: `to_unsigned(to_signed(p, 8), 16)`. Narrowing goes the other way and is plain wrapping: it keeps the low bits and throws away the rest.

## Check yourself against real C

It is easy to believe your Python is right. It is better to ask the machine. C has fixed-width integer types in the header `stdint.h`: `int8_t` is a signed 8-bit number and `uint32_t` is an unsigned 32-bit one. A *cast* such as `(int8_t)x` converts a value to a type.

Here is a C function that casts a 32-bit int to 8 bits and back:

```c
#include <stdint.h>

int32_t as_i8(int32_t x) { return (int8_t)x; }
```

For `x = 200`, the cast keeps the low 8 bits, `0xC8`, and reads them as signed: -56. Your `to_signed(200, 8)` must give the same answer. The checks in this lesson compile C like this with `cputools.compile_c`, call it from Python through `ctypes`, and compare every answer with yours.

```python
import cputools

lib = cputools.compile_c(
    "#include <stdint.h>\nint32_t as_i8(int32_t x) { return (int8_t)x; }"
)
print(lib.as_i8(200))    # -56
```

For arguments that are not a plain `int`, you tell `ctypes` the types. For example, `lib.add_u32.argtypes = [ctypes.c_uint32, ctypes.c_uint32]` and `lib.add_u32.restype = ctypes.c_uint32`. Without that, `ctypes` assumes 32-bit signed arguments and results.

Clang can also report the overflow flag for you. The built-in `__builtin_add_overflow(a, b, &result)` adds two numbers and returns 1 when the true sum does not fit in the type of `result`. One of the checks compares it with your `add_overflows` function on random pairs.

## Try it on your own machine

1. Write the C cast yourself and run it. Run `printf '#include <stdio.h>\nint main(void){ int x = 200; printf("%%d\\n", (signed char)x); return 0; }' > t.c && clang t.c -o t && ./t`. Look for `-56`. A `signed char` is the type `int8_t` is usually defined as.
2. See unsigned wrap in Python with a mask: `python3 -c "print((250 + 10) & 0xFF)"`. Look for `4`.
3. See sign extension as a mask: `python3 -c "print(hex(-16 & 0xFFFF))"`. Look for `0xfff0`, the 16-bit pattern of -16.
4. Look at your machine's integer sizes with `getconf INT_MAX`, `getconf LONG_MAX`, and `getconf CHAR_BIT`. Look for `2147483647`, `9223372036854775807`, and `8` on a 64-bit Linux system.

## Build it step by step

Fill the functions in this order. Everything works on *patterns*, the unsigned numbers from 0 to $2^{bits} - 1$.

1. `to_unsigned(x, bits)` wraps any int into the pattern range. One line with `%` and `1 << bits`.
2. `to_signed(x, bits)` reads the low `bits` bits as two's complement. Wrap first, test the top bit with `pattern >> (bits - 1)`, and subtract `1 << bits` if it is set. The usual mistake is to compare against `1 << bits` rather than testing the single top bit.
3. `int_range(bits, signed)` returns `(smallest, largest)`. For signed it is `-(1 << (bits - 1))` to `(1 << (bits - 1)) - 1`. For unsigned it is 0 to `(1 << bits) - 1`.
4. `negate(pattern, bits)` flips the bits and adds one, then wraps. In Python `~x` is `-x - 1`, so `~pattern + 1` is negative until you wrap it with `to_unsigned`. Forgetting the wrap is the most common slip.
5. `add_overflows(a, b, bits)` returns a pair of bools: `(unsigned_overflow, signed_overflow)`. Use the arithmetic tests from the previous section. The inputs are patterns, so convert with `to_signed` before the signed test.
6. `zero_extend(pattern, from_bits, to_bits)` returns the wider pattern. For zero extension the number does not change, but wrap it to `from_bits` first so a stray high bit does not leak in.
7. `sign_extend(pattern, from_bits, to_bits)` returns the wider pattern. Read the narrow pattern as signed, then wrap that value into `to_bits`.

The last three checks run your functions against real C. If one fails, the message names the input, so you can work the case by hand.

## Where this breaks

- **Signed overflow is undefined in C.** The patterns wrap in hardware, but the C language says a signed `int` that overflows is *undefined behaviour*: the compiler may assume it never happens, and generate code that surprises you. Unsigned overflow is defined to wrap. The check uses unsigned types for adding, and a compiler built-in to detect signed overflow, for this reason. Lesson 15 covers undefined behaviour.
- **Casts to a narrower signed type are not fully specified in older C.** Converting 200 to `int8_t` is implementation-defined in C before C23. Clang and GCC wrap it as described here, and so does every compiler you will meet.
- **`>>` on a signed number has two meanings.** An arithmetic shift copies the sign bit, so `-8 >> 1` is `-4`. A logical shift fills with 0. Hardware offers both, and C picks one by type. Python's `>>` is arithmetic.
- **Mixed signedness bites.** In C, comparing a signed `-1` with an unsigned `1u` converts the `-1` to a huge unsigned number, and `-1 < 1u` is false. Lesson 12 shows why `jl` and `jb` exist as separate jumps.
- **Two's complement is not the only scheme.** Sign-magnitude and one's complement were used on older machines, and floating-point numbers use their own sign bit. Every machine this course covers uses two's complement for integers.

## Further reading

- [Two's complement on Wikipedia](https://en.wikipedia.org/wiki/Two%27s_complement) gives the history, the proofs, and the tables for other widths.
- [Integer overflow on Wikipedia](https://en.wikipedia.org/wiki/Integer_overflow) describes wrap-around, saturation, and the bugs overflow has caused in real systems.
- [Felix Cloutier's x86 reference entry for ADD](https://www.felixcloutier.com/x86/add) shows exactly which flags the real instruction sets, including CF and OF.
- [Computer Systems: A Programmer's Perspective](https://csapp.cs.cmu.edu/) has a full chapter on integer representation and arithmetic, with the same rules and many practice problems.
- [Clang's documentation of arithmetic overflow built-ins](https://clang.llvm.org/docs/LanguageExtensions.html#checked-arithmetic-builtins) lists `__builtin_add_overflow` and its relatives, which the checks use.

## The exercise

You write the arithmetic of a fixed-width register in Python: `to_unsigned`, `to_signed`, `int_range`, `negate`, `add_overflows`, `zero_extend`, and `sign_extend`. Each function takes the width as a parameter, so the same code serves 4, 8, 32, or 64 bits.

The first checks compare your functions with hand-worked answers, and with every 4-bit input where that is cheap. The last three checks compile small C functions with clang, call them through `ctypes`, and compare the results with yours: the casts to `int8_t`, `uint8_t`, `int16_t`, and `int32_t`, a `uint32_t` addition and negation, a sign-extending conversion, and the compiler's own overflow detection. You write only Python. The checks write the C.
