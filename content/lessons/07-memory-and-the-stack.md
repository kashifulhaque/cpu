---
title: "Memory, the stack, and endianness"
slug: 07-memory-and-the-stack
part: "Part 1 — How a CPU works"
summary: Model byte-addressed memory with little-endian values and alignment, then build the stack that makes function calls possible.
minutes: 55
gpu: false
objectives:
  - Lay out a multi-byte integer in memory in little-endian order and read it back at any size.
  - Say what alignment is and why a misaligned access costs more or faults.
  - "Implement a downward-growing stack with push, pop, call, and ret, and trace a recursive call by hand."
  - See little-endian bytes in real x86-64 machine code.
prereqs:
  - 05-a-toy-cpu
  - 06-instruction-encoding
exercise: 07-memory-and-the-stack
---

# Memory, the stack, and endianness

A register holds a handful of bytes. A program needs far more: arrays, strings, the local variables of a function that is halfway through running. All of it lives in **memory**, a huge row of storage slots outside the CPU's registers.

Two questions follow. First, how do multi-byte numbers fit into a row of single bytes, and in which order? Second, when one function calls another that calls another, where do they keep their local data and the way back? The first answer is **endianness** and **alignment**. The second is the **stack**.

This lesson builds both in Python, with the same rules a real x86-64 machine follows. At the end you ask the real assembler to confirm the byte order.

## What you already know

- A byte is eight bits, and two hex digits name one byte (lesson 02).
- A shift and a mask extract one byte of a larger number: `(x >> 8) & 0xFF`.
- A negative number in two's complement has its top bit set, and masking wraps it to a width (lesson 03).
- The toy CPU's memory was a Python list indexed by address (lesson 05).
- An instruction such as `lw x5, 8(x2)` reads memory at a register plus an offset (lesson 06).

## Memory is a row of bytes

Think of a long street of mailboxes. Each holds one byte, and each has a number, its **address**. A machine with 16 GiB of RAM has about 17 billion boxes. Python models this well with a `bytearray` indexed by address: `data[5]` reads address 5.

Most data is wider than one byte. A C `int` takes 4 bytes, a pointer 8. A wider value occupies several neighbouring boxes, and its address is the address of the first box. The standard sizes are 1, 2, 4, and 8 bytes. Programs say how many bytes they want when they read or write.

## Endianness: which byte goes first

Take the 32-bit number `0x11223344`. It has four bytes: `11`, `22`, `33`, and `44`. `44` is the **least significant byte**, the one that counts the smallest part of the value. `11` is the **most significant byte**. Stored at address 0x1000, which byte goes in the first box?

There are two conventions, and both are in use:

- **Little-endian** puts the least significant byte at the lowest address.
- **Big-endian** puts the most significant byte at the lowest address.

```text
value 0x11223344 stored at address 0x1000

address:        0x1000  0x1001  0x1002  0x1003
little-endian:    44      33      22      11
big-endian:       11      22      33      44
```

x86-64 is little-endian, and so are ARM chips in nearly every phone and laptop, and RISC-V as it is usually built. Big-endian survives in network protocols, where it is called "network byte order", and in some file formats.

Little-endian has one practical advantage. The byte at the address is always the least significant, whatever the width. Reading the 1-byte value at 0x1000 gives `0x44`, which is the number's low byte. Reading 2 bytes there gives `0x3344`. Code can read a narrower value from the same address and get the low part, with no adjustment.

> [!KEY]
> Little-endian stores the least significant byte at the lowest address. The same address read at width 1, 2, or 4 gives the low 1, 2, or 4 bytes of the value.

### Writing it as a loop

Byte `k` of a value, counting from the least significant, is `(value >> (8 * k)) & 0xFF`. Storing a value is that expression for `k = 0, 1, 2, ...`, placed at address, address + 1, address + 2, and so on:

```python
def to_le_bytes(value, size):
    value &= (1 << (8 * size)) - 1                 # wrap to `size` bytes
    return bytes((value >> (8 * k)) & 0xFF for k in range(size))
```

Check it by hand: `to_le_bytes(0x11223344, 4)` computes `0x44`, `0x33`, `0x22`, `0x11`. The first line wraps a value that is too big or negative. For `-1` in 2 bytes, `-1 & 0xFFFF` is `0xFFFF`, so the bytes are `ff ff`.

Loading reverses it. Byte `k` is shifted left by `8 * k` and the pieces are OR-ed together. For a **signed** load, check the top bit of the highest byte. When it is set, subtract `1 << (8 * size)`. The bytes `ff ff` read as unsigned 65535, as signed -1.

A signed load is **sign extension**, and an unsigned one is **zero extension**. Real instruction sets have both: `movsx` and `movzx` on x86-64, `lb` and `lbu` on RISC-V. The choice depends on whether the byte in memory means a small signed number or a small unsigned one.

## Alignment

An address is **aligned** for a size when it is a multiple of that size. A 4-byte value at address 8 is aligned. A 4-byte value at address 6 is not.

```text
address:   0  1  2  3  4  5  6  7  8
4-byte:    [-- aligned ---][-- aligned ---]
                     [-- misaligned --]
```

The hardware reads memory in chunks, such as 8 or 64 bytes, and each chunk starts at a multiple of its size. An aligned value sits inside one chunk. A misaligned value can straddle two, which takes two reads and a stitch. The cost grows when the chunks are cache lines (lesson 09) or memory pages.

What a machine does about a misaligned access varies:

- **x86-64** allows it for ordinary loads and stores, a little slower. Some SSE instructions, such as `movaps`, fault when the address is not 16-byte aligned.
- **RISC-V** may trap, and the operating system or firmware can emulate it slowly. Implementations differ.
- Older ARM and many microcontrollers fault.

The compiler avoids the problem by **padding**: it places each variable at an address that suits its size, and a C struct gets gaps between members. Lesson 15 measures that.

The exercise's `Memory(size, strict_align=True)` models a machine that faults: a 4-byte load at address 2 raises `MemoryFault`, and so does a 2-byte store at address 3. A 1-byte access is always aligned.

## A memory with faults

An access outside the memory a program may touch makes the hardware raise a fault, and the operating system usually kills the program: you see "segmentation fault". The exercise's `Memory` raises `MemoryFault` when an access runs past the end or, in strict mode, is misaligned.

The range test needs care. An access at `addr` of `size` bytes touches `addr` to `addr + size - 1`. It is in range when `addr >= 0` and `addr + size <= len(data)`. Python's negative indexes make `data[-1]` legal, so you must test `addr >= 0` yourself, or a store at address -4 silently writes at the far end.

> [!WARNING]
> A failed store must change nothing. Check range and alignment before you write any byte, or a store that runs off the end leaves its first bytes behind.

## The stack

Every function needs somewhere to keep its local variables and to remember where to return. Functions call other functions, and each call needs its own private space that disappears on return. The structure that fits is a **stack**: a region of memory used last-in, first-out, like a pile of plates. You add a plate to the top and remove from the top.

A **stack pointer**, a register named `rsp` on x86-64 and `sp` on RISC-V, holds the address of the top item. On nearly all machines the stack **grows down**: the pile starts at a high address, and each push moves the stack pointer to a lower one.

```text
high addresses
   0x100  +----------------+   <- top (empty stack: sp = 0x100)
   0x0F8  |  value pushed  |
          +----------------+
   0x0F0  |  value pushed  |   <- sp after two pushes
          +----------------+
          |      free      |
low addresses
```

With 8-byte slots, the two operations are:

- **push** `value`: `sp = sp - 8`, then store `value` at `sp`.
- **pop**: load the 8 bytes at `sp`, then `sp = sp + 8`.

The order matters. Push moves first and writes second, so `sp` always points at the last thing written. Pop reads first and moves second.

A pop from an empty stack, where `sp` equals the top, is a bug. The exercise raises `StackError`.

### call and ret

A function call has to remember where to resume. The instruction after the call sits at a **return address**. The `call` instruction pushes that address on the stack, then jumps to the function. The `ret` instruction pops an address into the program counter, and execution continues after the call.

```text
call f   =   push (address of the next instruction)
             pc = address of f
ret      =   pc = pop
```

The stack makes nesting work. If `f` calls `g`, `g`'s return address sits on top of `f`'s. When `g` returns, its address pops, and `f`'s is exposed, ready for `f`'s own `ret`.

This is why a **stack overflow** happens. Unbounded recursion keeps pushing frames until the stack runs into the end of its region. On Linux the default stack for the main thread is 8 MiB (check with `ulimit -s`). The hardware faults, and the program dies.

## Tracing a recursive call

A recursive `factorial(n)` calls itself with `n - 1` until `n` is 1. Each call has a **stack frame**: the slice of stack that belongs to one call. In this model a frame holds two 8-byte slots, the return address and the saved argument `k`. Real frames hold more, such as saved registers and local variables.

The exercise calls `factorial(4)` from "main" with return address `0x400`. Recursive calls return into the function itself, at `0x500`. The stack starts at top `0x100` (256).

The calls go down from `k = 4` to `k = 1`. After each call, the stack looks like this:

```text
address   contents        after call for
0x0F8     0x400  (ret to main)    k = 4
0x0F0     4                       k = 4      sp = 0xF0, 16 bytes used
0x0E8     0x500  (ret into self)  k = 3
0x0E0     3                       k = 3      sp = 0xE0, 32 bytes used
0x0D8     0x500                   k = 2
0x0D0     2                       k = 2      sp = 0xD0, 48 bytes used
0x0C8     0x500                   k = 1
0x0C0     1                       k = 1      sp = 0xC0, 64 bytes used
```

The depths are `[16, 32, 48, 64]`. At `k = 1` the base case returns 1. Then unwind. Each frame pops `k`, pops its return address with `ret`, and multiplies the running result by `k`:

```text
pop k=1, ret -> 0x500    result = 1 * 1 = 1
pop k=2, ret -> 0x500    result = 1 * 2 = 2
pop k=3, ret -> 0x500    result = 2 * 3 = 6
pop k=4, ret -> 0x400    result = 6 * 4 = 24
```

The return addresses come out innermost first: `[0x500, 0x500, 0x500, 0x400]`. The final one goes back to `main`. `sp` is back at `0x100`, so the stack is empty again. A function that leaves `sp` anywhere else corrupts its caller.

## Connect to the real machine

On x86-64 the stack works as described, with a few facts to add:

- `rsp` is the stack pointer, and `push rax` is `sub rsp, 8` followed by a store of `rax` at `[rsp]`.
- `call` pushes an 8-byte return address, and `ret` pops it.
- The System V calling convention keeps `rsp` 16-byte aligned at the moment of a call. Lesson 14 explains why.
- A process's stack is a region in the address space. `cat /proc/self/maps` shows a `[stack]` line near the top.

Endianness is visible in machine code. The instruction `mov eax, 0x11223344` assembles to five bytes:

```text
b8  44 33 22 11
 |   \_________/
 |    the 32-bit immediate, least significant byte first
 opcode: mov eax, imm32
```

The `b8` byte is the opcode. The immediate follows in little-endian order, exactly as `to_le_bytes(0x11223344, 4)` produces it. The exercise's last function asks the real assembler for those bytes through `cputools.machine_code`.

## Try it on your own machine

1. Ask Python for your machine's byte order and a packed value:

   ```bash
   python3 -c "import sys, struct; print(sys.byteorder, struct.pack('<I', 0x11223344).hex(), struct.pack('>I', 0x11223344).hex())"
   ```

   Expect `little 44332211 11223344`. The `<` selects little-endian and `>` big-endian.

2. See the immediate's bytes in real x86-64 machine code:

   ```bash
   printf '.intel_syntax noprefix\nmov eax, 0x11223344\n' > m.s
   clang -c m.s -o m.o && llvm-objdump -d -M intel m.o
   ```

   The disassembly lists the instruction's bytes beside it. Look for `b8 44 33 22 11`.

3. Read the stack limit and see the stack mapping (Linux):

   ```bash
   ulimit -s
   grep stack /proc/self/maps
   ```

   Expect `8192` (kilobytes, so 8 MiB) and a `[stack]` line.

4. Watch a stack overflow in C:

   ```bash
   printf 'int f(int n) { return f(n + 1) + 1; }\nint main(void) { return f(0); }\n' > so.c
   clang -O0 so.c -o so && ./so; echo "exit code $?"
   ```

   Expect "Segmentation fault" and exit code 139. At `-O0` each call pushes a frame until the stack runs out. At higher optimization levels the compiler can rewrite the recursion into something else.

> [!RECAP]
> - Memory is a row of bytes. A wider value uses neighbouring bytes, and little-endian puts the least significant byte first.
> - An address is aligned for a size when it is a multiple of that size. Misaligned accesses cost more or fault.
> - The stack grows down: push decrements `sp` then writes, pop reads then increments.
> - `call` pushes a return address and `ret` pops it, which is what makes nested and recursive calls work.

## Build it step by step

Open `starter.py`. `MemoryFault`, `StackError`, and the module imports are given. You write these in order.

1. `to_le_bytes(value, size)` returns `size` bytes, least significant first, wrapping the value first. The common mistake is to forget the wrap, so `-1` produces an error or a wrong length.

2. `from_le_bytes(data, signed=False)` rebuilds the integer from bytes. With `signed=True`, subtract `1 << (8 * len(data))` when the top bit of the top byte is set.

3. `Memory(size, strict_align=False)` with `store(addr, value, size)` and `load(addr, size, signed=False)`. Keep a `bytearray` in `self.data`. Raise `ValueError` for sizes other than 1, 2, 4, and 8. Raise `MemoryFault` for negative or out-of-range addresses and, when `strict_align` is on, for misaligned ones. Check everything before writing.

4. `is_aligned(addr, size)` returns `addr % size == 0`.

5. `Stack(memory, top)` with `push`, `pop`, `call`, and `ret`. `sp` starts at `top`. Slots are 8 bytes, and the stack grows down. A pop with `sp == top` raises `StackError`. The common mistake is to write the value first and decrement `sp` second, which clobbers the previous top.

6. `factorial_with_stack(stack, n)` makes the calls, `n` down to 1, as two pushes each (return address, then `k`). It records the bytes used after each call, then unwinds. Return `(result, depths, returns)`.

7. `x86_immediate_bytes(value)` asks `cputools.machine_code` to assemble `mov eax, <value>` and returns bytes 1 to 4. Byte 0 is the opcode.

## Where this breaks

- **Misaligned access has real costs.** On x86-64 it works but can be slower, particularly across a cache line (64 bytes). Atomic operations on a misaligned address can fault or lose atomicity. Portable code keeps data aligned.
- **Byte order bugs hide in data exchange.** Writing an `int` straight to a file or socket and reading it on a machine with the other byte order gives a different number. Protocols fix an order and convert, as `htonl` does in C.
- **The stack is small and fixed.** Deep recursion overflows it, and large local arrays can do the same. Real systems put a **guard page**, an unmapped page just below the stack, so an overflow faults instead of silently overwriting memory.
- **Stack data is trusted.** The return address sits next to local variables. A buffer overrun can overwrite it and redirect `ret`, which is the classic stack smashing attack. Defences include stack canaries, a non-executable stack, and address randomization.
- **Real frames hold more.** Saved registers, locals, alignment padding, and arguments passed on the stack all live in a frame. Lesson 14 shows a real one.

## Further reading

- [Computer Systems: A Programmer's Perspective](https://csapp.cs.cmu.edu/) covers byte ordering, alignment, and stack frames in chapters 2 and 3.
- [Felix Cloutier's x86 reference for MOV](https://www.felixcloutier.com/x86/mov) lists the `B8+rd` encoding that carries a 32-bit immediate.
- [The System V AMD64 ABI](https://gitlab.com/x86-psABIs/x86-64-ABI) defines the stack layout and alignment rules Linux uses.
- [Danny Cohen, "On Holy Wars and a Plea for Peace" (1980)](https://www.rfc-editor.org/ien/ien137.txt) is the paper that coined "big-endian" and "little-endian".
- [Smashing the Stack for Fun and Profit](http://phrack.org/issues/49/14.html) explains the stack overrun attack from the original 1996 article.

## The exercise

You build the memory and stack a simple machine needs. `to_le_bytes` and `from_le_bytes` convert between integers and little-endian bytes. `Memory` stores and loads 1, 2, 4, and 8-byte values with range and optional alignment checks. `Stack` grows down from a top address with `push`, `pop`, `call`, and `ret`, and `factorial_with_stack` uses it to run a recursive call. `x86_immediate_bytes` assembles `mov eax, value` with `cputools.machine_code` and extracts the immediate.

The checks cover the hand-worked byte layouts in this lesson, including `0x11223344` and `-1`. They test signed and unsigned loads, faults (including a failed store that must change nothing), the alignment rules, the stack depths `[16, 32, 48, 64]` for `factorial(4)`, a stack that is too small, and that the real assembler produces your little-endian bytes.
