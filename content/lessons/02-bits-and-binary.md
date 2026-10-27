---
title: Bits, binary, and hexadecimal
slug: 02-bits-and-binary
part: "Part 0 — Getting started"
summary: Read and write numbers in binary and hex, pick bits apart with masks and shifts, and lay numbers out in bytes in both byte orders.
minutes: 55
gpu: false
objectives:
  - Convert between decimal, binary, and hexadecimal with a loop, by hand and in code.
  - Extract and change fields of bits with masks and shifts.
  - Count the set bits of a number.
  - Lay a multi-byte number out as bytes in little-endian and big-endian order.
prereqs:
  - 01-python-you-need
exercise: 02-bits-and-binary
---

# Bits, binary, and hexadecimal

Everything inside a computer is a number, and every number is stored as a row of switches that are each off or on. A letter, a photo, a program, and the address of a box in memory are all rows of switches. To read what a machine holds, you need to know how those rows map to numbers and how to pick them apart.

This matters for the rest of the course. A CPU instruction is a 32-bit number cut into fields. A memory address is a number split into the parts a cache uses. A flag such as "the last result was zero" is one bit. A reader who cannot move between binary, hex, and decimal cannot read a CPU manual.

You learn the arithmetic of bits first, then build the tools every later lesson uses: converters, masks, and byte packing.

## What you already know

- A Python function takes values in and returns a value out.
- A `for` loop and a `while` loop repeat work, and `//` and `%` give the quotient and remainder of a division.
- `hex`, `bin`, and `int(text, base)` convert between numbers and text, and `bytes` holds numbers from 0 to 255.
- A list holds values in order, and you read one by its index.

## Bits and bytes

A *bit* is one switch. It holds 0 or 1. The word is short for "binary digit".

One bit says little. Eight bits together are a *byte*. A byte holds 256 different patterns, from `00000000` to `11111111`. A byte is the unit memory hands out: every address names one byte.

Each extra bit doubles the number of patterns, so $n$ bits hold $2^n$ patterns.

| Bits | Patterns | Largest unsigned number |
|---|---|---|
| 1 | 2 | 1 |
| 8 | 256 | 255 |
| 16 | 65,536 | 65,535 |
| 32 | 4,294,967,296 | 4,294,967,295 |
| 64 | about 1.8 × 10^19 | 18,446,744,073,709,551,615 |

That is why a 32-bit address can name 4,294,967,296 bytes, which is 4 GiB.

## Binary: counting with two digits

You count in *base 10*. You have ten digits, and each position is worth ten times the one to its right. The number 345 means 3 hundreds, 4 tens, and 5 ones.

*Binary*, or base 2, works the same way with two digits. Each position is worth twice the one to its right: 1, 2, 4, 8, 16, and so on. To read `1101`, add up the positions that hold a 1.

```text
position value:   8    4    2    1
bits:             1    1    0    1
                  |    |         |
                  8  + 4    +    1   = 13
```

To go the other way and write 13 in binary, divide by 2 again and again, and keep each remainder.

```text
13 // 2 = 6   remainder 1   <- lowest bit
 6 // 2 = 3   remainder 0
 3 // 2 = 1   remainder 1
 1 // 2 = 0   remainder 1   <- highest bit

Read the remainders from the bottom up: 1101
```

The remainder `n % 2` is the lowest bit. The quotient `n // 2` throws that bit away and moves everything down one place. Repeat until the number is 0. The bits come out lowest first, so reverse them at the end.

Reading digits goes the other way. Start with a total of 0. For each digit, from left to right, multiply the total by the base and add the digit. For `1101`: 0 becomes 1, then 3, then 6, then 13.

Both methods work in any base. You use them for base 2 and base 16 in the exercise.

## Hexadecimal: binary in shorthand

Long rows of bits are hard to read. `1101111010101101` is a lot to take in. *Hexadecimal*, or hex, is a shorthand. It is base 16, so it needs sixteen digits. It uses `0` to `9`, then `a` to `f` for the values 10 to 15.

One hex digit matches exactly four bits. You convert by cutting the bits into groups of four, starting from the right.

```text
binary:   1101  1110  1010  1101
hex:        d     e     a     d      ->  0xdead
```

Programmers write `0x` before a hex number, so `0xdead` is hex. A byte is two hex digits, `0x00` to `0xff`. That is why dumps of memory show pairs of hex digits, and why `255`, `0xff`, and `11111111` are one number written three ways.

| Hex | Binary | Hex | Binary |
|---|---|---|---|
| 0 | 0000 | 8 | 1000 |
| 1 | 0001 | 9 | 1001 |
| 2 | 0010 | a | 1010 |
| 3 | 0011 | b | 1011 |
| 4 | 0100 | c | 1100 |
| 5 | 0101 | d | 1101 |
| 6 | 0110 | e | 1110 |
| 7 | 0111 | f | 1111 |

> [!KEY]
> Binary is what the machine stores. Hex is how people read it. One hex digit is four bits, so two hex digits are one byte.

## Bitwise operators

Arithmetic treats a number as a quantity. *Bitwise* operators treat it as a row of bits and work on each position on its own. Python spells them with symbols.

| Operator | Name | Rule | Example |
|---|---|---|---|
| `a & b` | AND | 1 only where both bits are 1 | `0b1100 & 0b1010` is `0b1000` |
| `a \| b` | OR | 1 where either bit is 1 | `0b1100 \| 0b1010` is `0b1110` |
| `a ^ b` | XOR | 1 where the bits differ | `0b1100 ^ 0b1010` is `0b0110` |
| `a << n` | shift left | move bits up `n` places, fill with 0 | `0b0011 << 2` is `0b1100` |
| `a >> n` | shift right | move bits down `n` places, drop the low ones | `0b1100 >> 2` is `0b0011` |

A shift left by one doubles a number, because every bit moves to a position worth twice as much. A shift right by one halves it, and drops the remainder. So `x << 3` is `x * 8` and `x >> 3` is `x // 8`.

### Masks

A *mask* is a number made to pick out bits with AND. Where the mask has a 1, the bit of the other number passes through. Where it has a 0, the result is 0.

A mask with `n` ones in a row is `(1 << n) - 1`. Look at `n = 3`. The value `1 << 3` is `0b1000`, and subtracting 1 gives `0b0111`.

To read a field of bits out of a number, shift the field down to position 0, then mask off what lies above it. Here is how to get bits 2 to 4 of `0b110100`:

```text
x            = 1 1 0 1 0 0      bits 5 4 3 2 1 0
x >> 2       =     1 1 0 1      the field starts at bit 0 
mask (3 ones)=         1 1 1
(x >> 2) & 7 =         1 0 1    = 5
```

In Python, that is `(x >> lo) & ((1 << width) - 1)`, where `width` is `hi - lo + 1`. This pattern is how a CPU reads fields out of an instruction. In lesson 06 you use it to pull a register number out of a 32-bit machine instruction.

To set bit `i`, OR with `1 << i`. To clear it, AND with the opposite mask, `~(1 << i)`.

```python
x = 0b0110
x = x | (1 << 0)      # set bit 0     -> 0b0111
x = x & ~(1 << 1)     # clear bit 1   -> 0b0101
```

> [!KEY]
> To read a field, shift it down and mask it. To set a bit, OR with a one in that position. To clear a bit, AND with a mask that has a zero there.

### Counting set bits

The *population count*, or popcount, of a number is how many of its bits are 1. It is a real instruction on x86-64 (`popcnt`). Here you write it with a loop. Test the lowest bit with `value & 1`, add it to a count, then shift right by one. Stop when the value reaches 0.

For `0b1011`, the loop sees 1, 1, 0, 1 as the number shrinks, and the count is 3.

## Bytes and byte order

A number that needs more than 8 bits does not fit in one byte, so memory stores it in several. The question is the order. Take the 32-bit number `0x12345678`. Its four bytes are `12`, `34`, `56`, and `78`. The byte `12` is the *most significant*, because it carries the largest place values. The byte `78` is the *least significant*.

Two orders exist, and both are in real use.

- **Big-endian** stores the most significant byte first, at the lowest address. It reads like a number on paper.
- **Little-endian** stores the least significant byte first.

```text
number 0x12345678

address:          0    1    2    3
big-endian:      12   34   56   78
little-endian:   78   56   34   12
```

Every x86-64 machine is little-endian, and so are most ARM systems you will meet. Network protocols, such as the headers of internet packets, use big-endian, which is why it is sometimes called network order.

To split a number into bytes, take the low byte with `value & 0xFF`, then shift right by 8 and repeat. Byte number `i`, counting from the least significant end, is `(value >> (8 * i)) & 0xFF`. That gives the little-endian order directly. Big-endian is the same list reversed.

To read bytes back, add each byte shifted into its place. For little-endian, byte `i` is worth `256 ** i`, which is `byte << (8 * i)`. For big-endian, reverse the bytes first and use the same loop.

> [!WARNING]
> Byte order only changes how a number is laid out in memory. The number is the same. `0x12345678` is the same value in both orders, and a program that reads memory with the wrong order gets a different number. Bytes `78 56 34 12` read as big-endian are `0x78563412`.

## Try it on your own machine

1. Convert a number each way in a Python session: `python3 -c "n = 3735928559; print(hex(n), bin(n), int('deadbeef', 16))"`. Look at how `0xdeadbeef` is 8 hex digits and 32 binary digits.
2. Ask Python for its machine's byte order: `python3 -c "import sys; print(sys.byteorder)"`. On an x86-64 machine it prints `little`.
3. See both byte orders of one number: `python3 -c "n = 0x12345678; print(n.to_bytes(4, 'little').hex(' '), '|', n.to_bytes(4, 'big').hex(' '))"`. Look for `78 56 34 12 | 12 34 56 78`.
4. Dump the bytes of a file as hex. Run `printf 'ABC' | xxd`. The `xxd` tool is on most Linux systems and ships with macOS. Look for `4142 43`, the hex codes of the letters. On Linux, `lscpu | grep 'Byte Order'` reports the byte order of your CPU.

## Build it step by step

Fill the functions in this order. The checks run in the same order.

1. `to_binary(n)` and `to_hex(n)` take a non-negative int and return text with no prefix. Use the divide-and-collect loop above, with a digit string `"0123456789abcdef"` to turn a remainder into a character. Do not call `bin` or `hex`. The two functions differ only in the base, so one helper with a base parameter serves both. The usual mistake is forgetting that 0 needs its own answer: the loop body never runs for 0, so return `"0"` first.
2. `from_binary(text)` and `from_hex(text)` take text and return an int. Use the multiply-and-add loop. Look each character up with `DIGITS.index(ch)`, after lowercasing the text for hex. Raise `ValueError` for an empty string, or for a digit that is too big for the base, such as `"2"` in binary.
3. `get_bits(value, lo, hi)` returns bits `lo` through `hi`, both included, moved down to start at bit 0. The width is `hi - lo + 1`. The usual mistake is an off-by-one: bits 2 through 4 are three bits wide, not two.
4. `set_bit(value, index, on=True)` sets or clears one bit. Use `|` with `1 << index` to set, and `&` with `~(1 << index)` to clear.
5. `popcount(value)` counts the 1 bits with the loop above.
6. `pack_le(value, size)` and `pack_be(value, size)` return a `bytes` value of exactly `size` bytes. Raise `ValueError` if the value is negative or too large for `size` bytes. Check with `value >> (8 * size)`, which is nonzero when bits are left over. Build the little-endian list first, then reverse it for big-endian.
7. `unpack_le(data)` and `unpack_be(data)` read a `bytes` value back into an int. Loop with `enumerate(data)`, which gives each byte and its index, and add `byte << (8 * index)`.

You are free to use `int.to_bytes` to compare against while you test, but the exercise wants you to write the loops. They are short, and writing them is the point.

## Where this breaks

- **Python ints have no width.** In a CPU, `~0b0101` in 4 bits is `0b1010`. In Python, `~5` is `-6`, because Python's number has no fixed width and flips infinitely many leading zeros. When you need a fixed width, AND the result with a mask: `~5 & 0b1111` is `10`. Lesson 03 builds a full toolkit around this.
- **Shifting past the width loses bits in hardware.** In 8 bits, `0b10000001 << 1` drops the top bit and keeps `0b00000010`. Python keeps the extra bit and gives `0b100000010`. A model that forgets the mask gets wrong answers.
- **Right shifts of negative numbers split into two operations.** Hardware has a logical shift that fills with 0 and an arithmetic shift that copies the top bit. Python's `>>` on a negative int is arithmetic. Lesson 03 returns to this.
- **Byte order shows up at boundaries.** Inside one program, endianness is invisible. It matters when you read a file, a network packet, or a memory dump written on another system. Bytes in files do not say which order they use, so the format has to.
- **Bit fields cost time in software.** Shifting and masking take a few instructions each. Hardware does the same work in wires, for free, which is why instruction formats are built from fixed bit ranges.

## Further reading

- [Hexadecimal on Wikipedia](https://en.wikipedia.org/wiki/Hexadecimal) covers the number system and why programmers prefer it to decimal.
- [Endianness on Wikipedia](https://en.wikipedia.org/wiki/Endianness) lists which systems use which order, and the history behind the name from *Gulliver's Travels*.
- [Python's bitwise operations](https://docs.python.org/3/library/stdtypes.html#bitwise-operations-on-integer-types) states exactly how `&`, `|`, `^`, `~`, `<<`, and `>>` treat negative numbers.
- [Bit Twiddling Hacks](https://graphics.stanford.edu/~seander/bithacks.html) is a long collection of bit tricks, including several faster popcounts than the loop you write here.
- [Felix Cloutier's x86 reference entry for POPCNT](https://www.felixcloutier.com/x86/popcnt) shows the real instruction that does your `popcount` in one step.

## The exercise

You write base conversion, bit manipulation, and byte packing in one file: `to_binary`, `to_hex`, `from_binary`, `from_hex`, `get_bits`, `set_bit`, `popcount`, `pack_le`, `pack_be`, `unpack_le`, and `unpack_be`.

The checks compare each function against numbers worked out by hand, then against Python's own `format` and `int.to_bytes` on a few hundred random values from a fixed seed. They also check that a number survives a round trip: converted to text and back, or packed to bytes and unpacked, it comes back unchanged. The last checks make sure bad input, such as a value that does not fit in its bytes, raises `ValueError`.
