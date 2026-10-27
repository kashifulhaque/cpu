---
title: "Instruction encoding: from text to bits"
slug: 06-instruction-encoding
part: "Part 1 — How a CPU works"
summary: Pack RISC-V instructions into 32-bit words and decode them back, field by field, including immediates split across the word.
minutes: 60
gpu: false
objectives:
  - Split a 32-bit RISC-V word into opcode, register, function, and immediate fields by hand.
  - Name the R, I, S, B, and J formats and say what each one is for.
  - Encode and decode an immediate that the format scatters across the word, including negative ones.
  - "Write an assembler with labels and a disassembler for seven RV32I instructions, and check them against LLVM."
prereqs:
  - 05-a-toy-cpu
exercise: 06-instruction-encoding
---

# Instruction encoding: from text to bits

A CPU does not read text. When you write `add x3, x1, x2`, something has to turn those characters into the pattern of electrical ones and zeros the CPU's circuits can act on. That pattern is the instruction's **encoding**, and the program that produces it is an **assembler**.

In the toy CPU of lesson 05, an instruction was a Python tuple. A real instruction is a fixed number of bits, and everything the CPU needs — what to do, which registers, which constant — must fit inside them. The designers of an instruction set decide where each piece goes, and a clever layout makes the decoder small and fast.

This lesson builds an assembler and a disassembler for a subset of **RISC-V**, an instruction set designed to be clean and regular. You learn the five encoding formats, see why an immediate sometimes sits in scattered pieces, and check your work against LLVM's assembler. The lesson ends at x86-64.

## What you already know

- A 32-bit word is written as eight hex digits (lesson 02).
- A shift and a mask pull a group of bits out of a number: `(x >> lo) & ((1 << width) - 1)`.
- A two's complement number with its top bit set is negative, and sign extension copies that bit leftward (lesson 03).
- A register is a named storage slot inside the CPU, and an instruction names the registers it reads and writes (lesson 05).
- The program counter holds the address of the next instruction, and a jump changes it (lesson 05).

## The problem: fit everything in 32 bits

RISC-V's base integer instruction set is called **RV32I**: "RV" for RISC-V, "32" for 32-bit registers, "I" for integer. It has 32 registers named `x0` to `x31`. Register `x0` is special: it always reads as zero, and writing to it does nothing.

Every RV32I instruction is exactly 32 bits, or 4 bytes. The instruction at address 0 is followed by the one at address 4, then 8, so the CPU never has to work out where an instruction ends.

An instruction needs to say three things:

- **What to do.** Add, subtract, load, store, branch.
- **Which registers.** Naming one of 32 takes 5 bits, because 2^5 = 32.
- **Which constant**, if any. A constant inside an instruction is an **immediate**, because it comes immediately with the instruction instead of from a register or memory.

A **field** is a group of bits that holds one of these. The `opcode` (operation code) field holds the low 7 bits of every instruction and says which format the rest of the word follows.

> [!KEY]
> An encoding is an agreement about which bits of a word mean what. The assembler writes the fields and the CPU's decoder reads them. Both use the same layout.

## The six fields and five formats

Here are the field names you will meet, with their widths:

| Field | Bits | Meaning |
|---|---|---|
| `opcode` | 7 | Which family of instruction, and so which format. |
| `rd` | 5 | The destination register: where the result goes. |
| `rs1`, `rs2` | 5 each | The two source registers. |
| `funct3` | 3 | Picks one instruction inside an opcode family. |
| `funct7` | 7 | A further selector, such as `add` versus `sub`. |
| immediate | 12, 13, or 21 | A constant, stored in different places per format. |

Different instructions need different fields, so RISC-V defines **formats**: layouts of the same 32 bits. This lesson covers five. Each diagram numbers the bits from 31 on the left down to 0 on the right.

```text
        31       25 24   20 19   15 14  12 11      7 6      0
R-type  | funct7   | rs2   | rs1   |funct3| rd      | opcode |   add, sub
I-type  | imm[11:0]        | rs1   |funct3| rd      | opcode |   addi, lw
S-type  | imm[11:5]| rs2   | rs1   |funct3| imm[4:0]| opcode |   sw
B-type  |i[12|10:5]| rs2   | rs1   |funct3|i[4:1|11]| opcode |  beq
J-type  | imm[20|10:1|11|19:12]            | rd      | opcode |   jal
```

The notation `imm[11:5]` means "bits 11 down to 5 of the immediate". A name such as `imm[20|10:1|11|19:12]` lists the pieces in the order they sit in the word.

Read the diagram for what stays put. The opcode is always in bits 6 to 0, `rd` in bits 11 to 7, `rs1` in bits 19 to 15, and `rs2` in bits 24 to 20. That regularity lets the hardware start reading registers before it has decoded the whole instruction.

The seven instructions in this lesson use these values:

| Instruction | Format | `opcode` | `funct3` | `funct7` | What it does |
|---|---|---|---|---|---|
| `add rd, rs1, rs2` | R | `0110011` | `000` | `0000000` | `rd = rs1 + rs2` |
| `sub rd, rs1, rs2` | R | `0110011` | `000` | `0100000` | `rd = rs1 - rs2` |
| `addi rd, rs1, imm` | I | `0010011` | `000` | none | `rd = rs1 + imm` |
| `lw rd, imm(rs1)` | I | `0000011` | `010` | none | load a 4-byte word from address `rs1 + imm` |
| `sw rs2, imm(rs1)` | S | `0100011` | `010` | none | store a 4-byte word to address `rs1 + imm` |
| `beq rs1, rs2, imm` | B | `1100011` | `000` | none | if `rs1 == rs2`, jump to `pc + imm` |
| `jal rd, imm` | J | `1101111` | none | none | `rd = pc + 4`, then jump to `pc + imm` |

`add` and `sub` differ in one bit of `funct7`, at word bit 30.

## Worked example: `addi x1, x0, 5`

Start with an I-type instruction. The assembly means "put 0 + 5 into register `x1`". Fill in each field:

```text
field    value   width   bits
imm      5       12      000000000101
rs1      0 (x0)  5       00000
funct3   0       3       000
rd       1 (x1)  5       00001
opcode           7       0010011
```

Place them left to right and regroup into hex digits:

```text
000000000101 00000 000 00001 0010011
0000 0000 0101 0000 0000 0000 1001 0011
   0    0    5    0    0    0    9    3     ->  0x00500093
```

Read it back with shifts and masks: `0x00500093 & 0x7F` is `0x13`, the opcode, and `0x00500093 >> 20` is 5, the immediate.

## R-type: `add x3, x1, x2`

An R-type instruction (R for register) uses three registers and no immediate.

```text
funct7   0000000   (add)
rs2      00010     (x2)
rs1      00001     (x1)
funct3   000
rd       00011     (x3)
opcode   0110011

0000000 00010 00001 000 00011 0110011
0000 0000 0010 0000 1000 0001 1011 0011
   0    0    2    0    8    1    B    3     ->  0x002081B3
```

For `sub x3, x1, x2`, `funct7` becomes `0100000`. That sets word bit 30 and adds `0x40000000`, giving `0x402081B3`.

## I-type and negative immediates

An I-type immediate is 12 bits wide and signed, so it holds -2048 to 2047. The CPU **sign-extends** it: it copies bit 11 into the upper 20 bits to build a 32-bit value. That is how `addi x7, x7, -1` can subtract.

In 12 bits, -1 is `111111111111`, or `0xFFF`. In Python, masking gives those bits:

```python
imm = -1
bits = imm & 0xFFF          # 0xFFF
```

To decode, do the reverse: a 12-bit field with its top bit set is negative, so subtract `1 << 12`. For `0xFFF`, that is `0xFFF - 0x1000 = -1`.

> [!WARNING]
> Python integers have no fixed width, so `-1` is not "all ones" until you mask it. Forget `& 0xFFF` and a negative immediate spills into the register fields.

## Loads and stores

`lw x5, 8(x2)` loads the 4 bytes at address `x2 + 8` into `x5`. It is I-type: the offset 8 is the immediate and `x2` is `rs1`.

```text
imm 000000001000 | rs1 00010 | funct3 010 | rd 00101 | opcode 0000011
0000 0000 1000 0001 0010 0010 1000 0011  ->  0x00812283
```

`sw x5, 8(x2)` stores `x5` to the same address. A store has no destination register, so it has no `rd`, but it needs two sources: the base (`rs1`) and the value (`rs2`). The designers kept both in their usual places and split the 12-bit immediate: the high 7 bits go where `funct7` normally sits, and the low 5 bits go where `rd` normally sits.

```text
imm[11:5] 0000000 | rs2 00101 | rs1 00010 | funct3 010 | imm[4:0] 01000 | opcode 0100011
0000 0000 0101 0001 0010 0100 0010 0011  ->  0x00512423
```

> [!KEY]
> RISC-V puts `rs1`, `rs2`, and `rd` in the same bit positions in every format that has them. When the immediate has to share the word, it is cut into pieces that fill the gaps.

## Branches: scattering the offset

`beq x1, x2, 8` jumps 8 bytes forward when the two registers are equal. The offset is relative to the branch's own address, which keeps a program valid wherever it loads in memory.

The B-type immediate is 13 bits, bits 12 down to 1. Bit 0 is not stored: instructions sit at even addresses, so every offset is even. Dropping it buys range, and a branch reaches -4096 to +4094 bytes. The pieces land like this:

```text
word bit 31     = imm[12]
word bits 30:25 = imm[10:5]
word bits 11:8  = imm[4:1]
word bit  7     = imm[11]
```

Why scatter? A branch reuses the S-type slot for imm[4:1] and moves imm[11] into bit 7, where S-type holds imm[0]. Most immediate wires are then shared between the two formats, and the sign bit is always word bit 31, so sign extension can start early.

The offset 8 is `0b0_1000` in bits 12..0, so imm[4:1] is `0100` and every other piece is zero:

```text
bit 31  imm[12]    0
30:25   imm[10:5]  000000
24:20   rs2        00010
19:15   rs1        00001
14:12   funct3     000
11:8    imm[4:1]   0100
7       imm[11]    0
6:0     opcode     1100011

0 000000 00010 00001 000 0100 0 1100011
0000 0000 0010 0000 1000 0100 0110 0011  ->  0x00208463
```

A backward branch has a negative offset. `beq x1, x0, -4` is `1_1111_1111_1100` in 13 bits, so word bit 31 is set, and the word is `0xFE008EE3`.

## Jumps: `jal`

`jal` (jump and link) saves the address of the next instruction, `pc + 4`, in `rd`, then jumps to `pc + imm`. With `rd` as `x1` (also called `ra`, the return address register), this is a function call. With `x0`, the saved address is thrown away and `jal` is a plain jump.

The J-type immediate is 21 bits, again without bit 0, so it reaches about one mebibyte each way:

```text
word bit 31      = imm[20]
word bits 30:21  = imm[10:1]
word bit 20      = imm[11]
word bits 19:12  = imm[19:12]
word bits 11:7   = rd
```

For `jal x1, 8`, imm[10:1] is 4 (`0000000100`):

```text
0 0000000100 0 00000000 00001 1101111
0000 0000 1000 0000 0000 0000 1110 1111  ->  0x008000EF
```

## Labels: the assembler's second pass

Programmers write `beq x1, x0, done`, not `beq x1, x0, 8`. A **label** is a name for an address, and the assembler works out each offset. It needs two passes, because a branch can name a label that appears later.

1. **Pass one** walks the lines, strips comments, and records each label's address: 4 times the number of instructions before it.
2. **Pass two** encodes each instruction. A label operand becomes `label_address - address_of_this_instruction`.

Here is a loop and its addresses:

```text
addr   source
0x00         addi x1, x0, 3
0x04   loop: addi x1, x1, -1
0x08         beq  x1, x0, done     # done is 0x10: offset 0x10 - 0x08 = 8
0x0C         jal  x0, loop         # loop is 0x04: offset 0x04 - 0x0C = -8
0x10   done: sw   x1, 8(x2)
```

## The disassembler

A **disassembler** goes the other way. It reads the opcode, picks a format, extracts the fields with shifts and masks, and prints text. For B-type and J-type it glues the scattered pieces back together before it sign-extends them.

## Connect to the real machine

You can check your words against a real assembler. `clang --target=riscv32` assembles RISC-V on an x86-64 machine, because clang is a cross-compiler. The exercise's reference table came from it.

x86-64 uses the same idea with a different layout. Its instructions are 1 to 15 bytes: optional prefixes, an opcode, an optional "ModRM" byte that names registers and addressing modes, and an optional immediate. The instruction `mov eax, 5` is five bytes, `b8 05 00 00 00`. The `b8` means "move an immediate into `eax`", and the next four bytes are the immediate in little-endian order (the next lesson explains that order). Variable length packs common instructions into fewer bytes, and the price is a decoder that must find where each instruction ends.

> [!TIP]
> When a field looks wrong, print the word with `format(word, "032b")` and count to the field boundaries from the right.

## Try it on your own machine

1. Assemble RISC-V (needs a clang with the RISC-V backend, which most distribution packages include):

   ```bash
   printf 'addi x1, x0, 5\nadd x3, x1, x2\nbeq x1, x2, 8\n' > t.s
   clang --target=riscv32 -march=rv32i -c t.s -o t.o
   llvm-objdump -d t.o
   ```

   Look for `00500093`, `002081b3`, and `00208463` beside the instructions. LLVM prints `li ra, 0x5` for the first one, a pseudo-instruction name for `addi` from `x0`, and ABI names such as `ra` and `sp` for `x1` and `x2`.

2. Split a word into fields in Python:

   ```bash
   python3 -c "w = 0x002081B3; print(w & 0x7F, (w >> 7) & 0x1F, (w >> 12) & 7, (w >> 15) & 0x1F, (w >> 20) & 0x1F, w >> 25)"
   ```

   Expect `51 3 0 1 2 0`: the opcode `0b0110011`, then `rd`, `funct3`, `rs1`, `rs2`, and `funct7`.

3. See x86-64 variable-length encoding (Linux):

   ```bash
   printf '.intel_syntax noprefix\nmov eax, 5\nret\n' > x.s
   clang -c x.s -o x.o && llvm-objdump -d -M intel x.o
   ```

   Look at the bytes: `mov eax, 5` takes five, and `ret` takes one.

> [!RECAP]
> - Every RV32I instruction is 32 bits, with `rd`, `rs1`, `rs2`, and `opcode` in fixed positions.
> - The five formats (R, I, S, B, J) differ in where the immediate goes.
> - Signed immediates are masked to their width to encode and sign-extended to decode.
> - Branch and jump offsets are even, relative to the instruction's own address, and scattered across the word.
> - An assembler needs two passes so that a branch can name a label defined later.

## Build it step by step

Open `starter.py`. The opcode constants and `ABI_NAMES` are given. You write these functions in this order.

1. `register_number(name)` takes `"x5"`, `"zero"`, `"ra"`, or `"sp"` and returns the number. Raise `ValueError` for anything else. The common mistake is to accept `"x99"` because it starts with `x`.

2. `sign_extend(value, bits)` reads the low `bits` bits as a signed number: mask, test the top bit, subtract `1 << bits` when it is set.

3. `encode_r`, `encode_i`, and `encode_s` take field values and return a word. Shift each field to its position and combine with `|`. For I and S, mask the immediate with `& 0xFFF` and raise `ValueError` when it does not fit in 12 signed bits. The common mistake is to forget the mask on negative immediates.

4. `encode_b(imm, rs2, rs1, funct3, opcode)` takes the byte offset and scatters it as shown above. Raise `ValueError` when the offset is odd or outside -4096 to 4094. The common mistake is to shift the offset right by one before scattering. Take each piece at its own position: `(imm >> 5) & 0x3F` goes to word bit 25, and `(imm >> 1) & 0xF` goes to word bit 8.

5. `encode_j(imm, rd, opcode)` does the same for the 21-bit jump offset.

6. `assemble_line(line)` splits one line into a mnemonic and operands, parses registers and numbers (`int(text, 0)` reads decimal and hex), and calls the right encoder. A `#` starts a comment. Raise `ValueError` for anything it cannot encode. For `lw` and `sw`, split `"8(x2)"` into the offset and the register.

7. `assemble(lines)` is the two-pass assembler. Labels may sit on their own line or in front of an instruction. A label operand on `beq` or `jal` becomes `label_address - this_address`.

8. `disassemble_word(word)` decodes a word to text such as `"addi x1, x0, 5"` and `"sw x5, 8(x2)"`. Use signed decimal immediates. Raise `ValueError` for a word that is none of the seven instructions.

## Where this breaks

- **Immediates are small.** A 12-bit immediate cannot hold `0x12345678`. RISC-V builds big constants with `lui` (load upper immediate, 20 bits) followed by `addi`. A branch reaches only 4 KiB, so a farther target needs an inverted branch around a `jal`. Assemblers do this rewriting for you.
- **Fixed length wastes bits.** RISC-V has an optional 16-bit "C" extension and ARM has Thumb, which trade a simple decoder for denser code.
- **Variable length is hard to decode.** Real x86-64 CPUs cache decoded instructions in a "micro-op cache".
- **Real RV32I has more.** It has 40 base instructions, including `and`, `or`, shifts, `bne`, `blt`, `jalr`, `lui`, and `auipc`. They fit these layouts, plus a U-type for `lui` and `auipc`.

## Further reading

- [The RISC-V ISA specifications](https://riscv.org/technical/specifications/) hold the official RV32I chapter, with every format and every immediate layout.
- [RISC-V Reader: An Open Architecture Atlas](http://www.riscvbook.com/) is a short book that explains why the encoding looks the way it does.
- [Felix Cloutier's x86 and amd64 instruction reference](https://www.felixcloutier.com/x86/) shows the byte-level encoding of every x86-64 instruction.
- [LLVM's RISC-V documentation](https://llvm.org/docs/RISCVUsage.html) lists the extensions and options that clang supports.

## The exercise

You build a working assembler and disassembler for `add`, `sub`, `addi`, `lw`, `sw`, `beq`, and `jal`. Five `encode_*` functions pack fields into words, `assemble_line` and `assemble` turn text into words (with labels), and `disassemble_word` turns words back into text. `register_number` and `sign_extend` are the helpers underneath.

The checks compare your words to 26 encodings produced by LLVM's RISC-V assembler, including the extreme immediates -2048, 2047, -4096, 4094, and -1048576. They also check that bad immediates raise `ValueError`, that labels resolve forward and backward, and that 500 random instructions survive an encode-then-decode round trip.
