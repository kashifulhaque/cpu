---
title: Logic gates and adders
slug: 04-logic-gates-and-adders
part: "Part 0 — Getting started"
summary: Build every logic gate from NAND, then wire gates into an adder and a small ALU that sets the zero, negative, carry, and overflow flags.
minutes: 60
gpu: false
objectives:
  - Build NOT, AND, OR, and XOR from NAND gates alone.
  - Build a half adder, a full adder, and an N-bit ripple-carry adder over lists of bits.
  - Subtract with the same adder by adding the two's complement.
  - Compute the zero, negative, carry, and overflow flags of an ALU result.
prereqs:
  - 03-integers-and-overflow
exercise: 04-logic-gates-and-adders
---

# Logic gates and adders

Lesson 03 said that hardware adds numbers and keeps the low N bits. It did not say how. A CPU has no idea what a number is. It has wires that carry either a low voltage or a high one, and small circuits that combine those wires.

This lesson shows that arithmetic comes out of a handful of such circuits. You start with one tiny building block, the NAND gate, and build everything else from copies of it: the other gates, an adder, a subtractor, and the *arithmetic logic unit*, or ALU, which is the part of a CPU that does the math. By the end, you will have a working model of the circuit that sits behind every `add` instruction.

None of this needs electronics. Treat a wire as a bit. A circuit is then a function from bits to bits, and you can write it in Python.

## What you already know

- A bit is 0 or 1, and a number is a row of bits.
- Two's complement negates a number by flipping every bit and adding one.
- An addition has a carry flag for unsigned overflow and an overflow flag for signed overflow.
- A Python function takes values in and returns values out, and a list of ints holds a row of bits.

## Gates: functions from bits to a bit

A *logic gate* is a small circuit with one or two input wires and one output wire. Each wire carries a bit. The gate's output depends only on its inputs, and you describe it completely with a *truth table*, a list of every input and the output it gives.

Real gates are built from *transistors*, tiny electrically controlled switches. A modern CPU holds billions of them. You do not need the electronics, only the behaviour.

The three classic gates:

| a | b | AND | OR | XOR |
|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 |
| 0 | 1 | 0 | 1 | 1 |
| 1 | 0 | 0 | 1 | 1 |
| 1 | 1 | 1 | 1 | 0 |

AND outputs 1 only when both inputs are 1. OR outputs 1 when at least one input is 1. XOR, short for "exclusive or", outputs 1 when the inputs differ. NOT has one input and flips it.

In Python, a gate is a function over the ints 0 and 1. Here are the first two, with Python's own operators to start:

```python
def not_(a):
    return 1 - a

def and_(a, b):
    return a & b
```

The names end in an underscore because `not`, `and`, and `or` are reserved words in Python.

## NAND: the one gate you need

*NAND* means "NOT AND". It outputs 0 only when both inputs are 1.

| a | b | NAND |
|---|---|---|
| 0 | 0 | 1 |
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 1 | 1 | 0 |

NAND is *universal*: every other gate can be built from NAND alone. That is a useful fact. A chip maker can build one kind of cell, make millions of copies, and wire them into anything.

Start with NOT. Give NAND the same bit on both inputs. NAND of 1 and 1 is 0, and NAND of 0 and 0 is 1. That is NOT.

```python
def not_(a):
    return nand(a, a)
```

AND is a NAND followed by a NOT, which undoes the inversion:

```python
def and_(a, b):
    return not_(nand(a, b))
```

OR takes a small trick. A rule called *De Morgan's law* says that "a OR b" equals "NOT (NOT a AND NOT b)". NAND is NOT-AND, so OR is NAND of the two inverted inputs:

```python
def or_(a, b):
    return nand(not_(a), not_(b))
```

Check it for `a = 0, b = 1`. The inversions give 1 and 0. NAND of 1 and 0 is 1. That matches OR.

XOR takes four NANDs. Let `n = nand(a, b)`. Then feed `a` and `n` into one NAND, `b` and `n` into another, and NAND the two results.

```text
        +--------------- nand(a, n) --+
a ------+                             |
        +-- n = nand(a, b) --+        +-- nand(...) --> a XOR b
b ------+                    |        |
        +--------------- nand(b, n) --+
```

Work it for `a = 1, b = 1`. Then `n = 0`, so both `nand(a, n)` and `nand(b, n)` give 1, and `nand(1, 1)` is 0. XOR of 1 and 1 is 0. For `a = 1, b = 0`: `n = 1`, `nand(1, 1)` is 0, `nand(0, 1)` is 1, and `nand(0, 1)` is 1. XOR is 1.

> [!KEY]
> NAND alone can build every other gate, so a whole CPU is, at bottom, copies of one simple circuit. The exercise gives you `nand` and asks you to build NOT, AND, OR, and XOR from it.

## Adding two bits: the half adder

Add two single bits by hand: 0 + 0 = 0, 0 + 1 = 1, 1 + 0 = 1, and 1 + 1 = 10 in binary. The last case needs two output bits: a *sum* bit of 0 and a *carry* bit of 1.

Look at the truth table of the two outputs:

| a | b | sum | carry |
|---|---|---|---|
| 0 | 0 | 0 | 0 |
| 0 | 1 | 1 | 0 |
| 1 | 0 | 1 | 0 |
| 1 | 1 | 0 | 1 |

The sum column is XOR, and the carry column is AND. So a *half adder* is two gates:

```python
def half_adder(a, b):
    return xor_(a, b), and_(a, b)    # (sum, carry)
```

It is called "half" because it cannot take a carry in from a lower position. That is what the next piece does.

## Adding three bits: the full adder

When you add two multi-digit numbers on paper, you add each column, and a carry from the column on the right joins the next column. So each column adds three bits: `a`, `b`, and a *carry-in*. The result is a sum bit and a *carry-out*.

A *full adder* is made of two half adders and one OR gate. The first half adder adds `a` and `b`. The second adds that sum to the carry-in. A carry comes out of either half adder, never both, so OR combines them.

```text
a ---+---------+
     | half    |--- s1 ---+---------+
b ---+ adder 1 |          | half    |--- sum
     +---+-----+ c1       | adder 2 |
         |        carry-in-+----+----+
         |                      | c2
         +-------- OR ----------+--- carry-out
```

In code:

```python
def full_adder(a, b, carry_in):
    s1, c1 = half_adder(a, b)
    s2, c2 = half_adder(s1, carry_in)
    return s2, or_(c1, c2)
```

Try `1 + 1 + 1`. The first half adder gives sum 0 and carry 1. The second adds 0 and the carry-in 1, giving sum 1 and carry 0. OR of the carries is 1. The result is sum 1, carry-out 1, which is 11 in binary, which is 3. Correct.

## The ripple-carry adder

To add N-bit numbers, put N full adders in a row. The first adds the lowest bits with a carry-in of 0. Its carry-out feeds the next adder's carry-in, and so on up. The carry *ripples* from the bottom to the top, which gives the circuit its name.

In this lesson a number is a list of bits with the *least significant bit first*. So `[1, 0, 1, 0]` is 1 + 4 = 5. This order matches the order the carry travels, which keeps the loop simple.

Here is 3 + 5 in four bits, column by column:

```text
bit position:    0    1    2    3
a = 3          [ 1,   1,   0,   0 ]
b = 5          [ 1,   0,   1,   0 ]

column 0:  1 + 1 + 0 = sum 0, carry 1
column 1:  1 + 0 + 1 = sum 0, carry 1
column 2:  0 + 1 + 1 = sum 0, carry 1
column 3:  0 + 0 + 1 = sum 1, carry 0

result         [ 0,   0,   0,   1 ]  = 8, carry out 0
```

The code is a loop that carries one value from column to column:

```python
def ripple_add(a_bits, b_bits, carry_in=0):
    out = []
    carry = carry_in
    for a, b in zip(a_bits, b_bits):
        s, carry = full_adder(a, b, carry)
        out.append(s)
    return out, carry
```

The function returns the sum bits and the final carry. That final carry is the carry flag from lesson 03. If it is 1, the unsigned result did not fit.

> [!TIP]
> To test an adder, add every pair of small numbers and compare with Python's `+`. With 4 bits there are only 256 pairs, so you can check them all.

## Subtracting with the same adder

Computing `a - b` needs no extra circuit. Two's complement says that `-b` is "flip the bits of `b`, add one". So:

$$
a - b = a + \lnot b + 1
$$

The subtractor inverts every bit of `b` and sets the carry-in to 1. That is why the carry-in of `ripple_add` is a parameter. One adder does both jobs.

Here is 5 - 3 in four bits:

```text
a            = 0101   (5)
b            = 0011   (3)
NOT b        = 1100
a + NOT b + 1:
  0101 + 1100 + 1 = 1 0010   -> low four bits 0010 = 2, carry-out 1
```

The result is 2, and the carry-out is 1. For subtraction, a carry-out of 1 means no borrow was needed, so `a >= b` as unsigned numbers. This course reports that bit as the C flag, the same as ARM chips do. An x86-64 CPU reports the inverse, called the borrow flag: it sets CF when a borrow was needed. The adder is the same, and only the reporting differs.

## The ALU and its flags

An ALU takes two numbers and an operation code, and returns a result plus a few *flags*. The flags are single bits that describe the result. Later instructions, such as a conditional jump, read them. Your ALU supports `add`, `sub`, `and`, and `or`, and four flags.

| Flag | Name | Set when |
|---|---|---|
| `Z` | zero | every bit of the result is 0 |
| `N` | negative | the top bit of the result is 1 |
| `C` | carry | a carry came out of the top bit of the adder |
| `V` | overflow | the signed result of an add or subtract is wrong |

The first two are easy. `Z` is true when all result bits are 0. `N` is the top bit.

`C` is the carry-out of `ripple_add`. For `and` and `or`, there is no carry, so `C` is 0.

`V` uses the rule from lesson 03: overflow happens when two operands of the same sign give a result of the opposite sign. For an add, compare the top bit of `a`, the top bit of `b`, and the top bit of the result. For a subtract, use the top bit of the inverted `b`, because the adder really added that. In gates:

```python
same_sign = not_(xor_(a_sign, b_sign))        # 1 when the two signs match
changed   = xor_(a_sign, result_sign)         # 1 when the result's sign differs
overflow  = and_(same_sign, changed)
```

Here is `7 + 1` in four bits, with the flags:

```text
a = 0111 (7)   b = 0001 (1)   a + b = 1000

result bits 1000  -> 8 as unsigned, but -8 as signed
Z = 0             the result is not zero
N = 1             the top bit is 1
C = 0             nothing carried out of the top bit
V = 1             two positives gave a negative
```

A programmer reads this as: "unsigned, 7 + 1 = 8 is fine. Signed, it overflowed." Both facts come out of the same eight wires.

## Try it on your own machine

1. Print the truth table of XOR built from Python operators: `python3 -c "print([(a, b, a ^ b) for a in (0, 1) for b in (0, 1)])"`. Look for `[(0, 0, 0), (0, 1, 1), (1, 0, 1), (1, 1, 0)]`.
2. See NAND universality in one line: `python3 -c "n = lambda a, b: 1 - (a & b); print([n(n(a, a), n(a, a)) for a in (0, 1)])"`. Look for `[0, 1]`, because NOT of NOT is the original bit.
3. Ask the compiler how a CPU adds. Run `printf 'int f(int a, int b) { return a + b; }' > add.c && clang -O1 -S -masm=intel -o - add.c`. This needs `clang`. Look for a single `add` or `lea` instruction in the output. One instruction replaces your whole ripple-carry circuit, and the real adder is faster than yours.
4. On Linux, list the flags your own CPU's feature set includes: `grep -m1 flags /proc/cpuinfo`. The list names CPU features, and it is a taste of how much hardware sits around the ALU.

## Build it step by step

Open the exercise. The function `nand` is given. `bits_from_int` and `int_from_bits` are given too, to convert between ints and bit lists.

1. `not_(a)`, `and_(a, b)`, `or_(a, b)`, and `xor_(a, b)` build the four gates from `nand` only. The checks replace `nand` with a counting version, and they fail a gate that never calls `nand`. Do not use `&`, `|`, `^`, or `~` in these four. The usual mistake is to write `a & b` for `and_`, which passes the truth table and misses the point.
2. `half_adder(a, b)` returns `(sum, carry)`. Reuse `xor_` and `and_`.
3. `full_adder(a, b, carry_in)` returns `(sum, carry_out)`. Reuse `half_adder` twice and `or_` once.
4. `ripple_add(a_bits, b_bits, carry_in=0)` takes two equal-length lists, lowest bit first, and returns `(sum_bits, carry_out)`. Raise `ValueError` if the lengths differ. A frequent mistake is to read the lists from the wrong end. The carry must travel from index 0 upward.
5. `alu(op, a_bits, b_bits)` returns `(result_bits, flags)`. For `add`, call `ripple_add`. For `sub`, invert every bit of `b` with `not_`, then call `ripple_add` with a carry-in of 1. For `and` and `or`, combine bit by bit. Then compute `Z`, `N`, `C`, and `V`. Return the flags as a dict with the keys `"Z"`, `"N"`, `"C"`, and `"V"`, each 0 or 1. Raise `ValueError` for an unknown operation. The two most common mistakes are the overflow rule for `sub` (use the inverted `b`, not `b`) and the carry flag for `sub` (it is 1 when no borrow was needed).

## Where this breaks

- **Ripple-carry is slow.** Each column waits for the carry from the one below. In a 64-bit adder, the signal travels through 64 full adders in a row. Real ALUs use *carry-lookahead* and *carry-select* designs, which compute carries in parallel with extra gates. They trade more gates for less delay.
- **Real gates take time.** A signal needs a short while to pass through each gate, and a chip's clock speed is bounded by the longest path. The count of gates a signal crosses is the *gate depth*, and lesson 08 builds on the idea when it talks about pipelines.
- **NAND is not always the cheapest cell.** Chips use NAND and NOR, but also AND, OR, XOR, and more complex combined cells, because a single custom cell is smaller than four NANDs. NAND is the right tool for a proof of universality, not for a chip layout.
- **The flags differ between machines.** ARM and x86-64 both have Z, N (called SF on x86), C (CF), and V (OF). They disagree on subtract: x86 sets CF when a borrow happens, and ARM sets C when it does not. Lesson 12 uses the x86 flags.
- **Multiplication and division need more.** Adders are cheap. A multiplier is a grid of adders, and division is slower again, so a real instruction set treats them separately.

## Further reading

- [Nand2Tetris](https://www.nand2tetris.org/) is a free course that builds a computer from NAND gates up to a working game, and its first weeks match this lesson.
- [The Nandgame](https://nandgame.com/) is a browser puzzle where you build an adder and an ALU out of relays and NAND gates.
- [Logic gate on Wikipedia](https://en.wikipedia.org/wiki/Logic_gate) lists every gate with its symbol and truth table.
- [Adder (electronics) on Wikipedia](https://en.wikipedia.org/wiki/Adder_(electronics)) covers half adders, full adders, ripple-carry, and carry-lookahead designs with diagrams.
- [Felix Cloutier's x86 reference entry for SUB](https://www.felixcloutier.com/x86/sub) lists how the real instruction sets CF, OF, SF, and ZF.

## The exercise

You build a small arithmetic unit in `starter.py`: `not_`, `and_`, `or_`, `xor_`, `half_adder`, `full_adder`, `ripple_add`, and `alu`. The functions `nand`, `bits_from_int`, and `int_from_bits` are provided.

The checks test each gate against its truth table, and they confirm that each gate calls `nand`. They test the adders on every input, and `ripple_add` on every pair of 5-bit numbers plus a 64-bit case. The `alu` checks run every pair of 4-bit numbers through `add`, `sub`, `and`, and `or`, and compare the result and all four flags with plain Python arithmetic. A last check confirms the 8-bit cases from lesson 03, such as 100 + 100.
