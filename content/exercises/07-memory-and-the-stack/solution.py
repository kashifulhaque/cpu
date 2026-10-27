"""Memory, the stack, and endianness.

Reference solution.
"""

import cputools


class MemoryFault(Exception):
    """An access outside memory, or a misaligned one on a strict machine."""


class StackError(Exception):
    """A pop from an empty stack."""


def to_le_bytes(value, size):
    """The `size` little-endian bytes of `value` (wrapped to that many bytes)."""
    value &= (1 << (8 * size)) - 1          # keep only the low 8*size bits
    return bytes((value >> (8 * k)) & 0xFF for k in range(size))  # byte 0 is least significant


def from_le_bytes(data, signed=False):
    """The integer stored in little-endian `data`."""
    value = 0
    for k, byte in enumerate(data):
        value |= byte << (8 * k)
    if signed and data and value >> (8 * len(data) - 1):   # top bit set: negative
        value -= 1 << (8 * len(data))
    return value


class Memory:
    """A byte-addressed memory of `size` bytes, all zero at the start."""

    def __init__(self, size, strict_align=False):
        self.data = bytearray(size)
        self.strict_align = strict_align

    def _check(self, addr, size):
        if size not in (1, 2, 4, 8):
            raise ValueError(f"size must be 1, 2, 4, or 8, not {size}")
        if addr < 0 or addr + size > len(self.data):
            raise MemoryFault(f"address {addr:#x} (+{size}) is outside memory")
        if self.strict_align and addr % size:
            raise MemoryFault(f"address {addr:#x} is not aligned to {size} bytes")

    def store(self, addr, value, size):
        self._check(addr, size)
        self.data[addr:addr + size] = to_le_bytes(value, size)

    def load(self, addr, size, signed=False):
        self._check(addr, size)
        return from_le_bytes(self.data[addr:addr + size], signed)


def is_aligned(addr, size):
    """True when addr is a multiple of size."""
    return addr % size == 0


class Stack:
    """A stack in `memory` that grows down from `top`. Each slot is 8 bytes."""

    def __init__(self, memory, top):
        self.memory = memory
        self.top = top
        self.sp = top          # empty stack: sp sits at the top

    def push(self, value):
        self.sp -= 8                              # grow downward first ...
        self.memory.store(self.sp, value, 8)      # ... then write into the new slot

    def pop(self):
        if self.sp >= self.top:
            raise StackError("pop from an empty stack")
        value = self.memory.load(self.sp, 8)      # read the slot ...
        self.sp += 8                              # ... then shrink
        return value

    def call(self, return_address):
        self.push(return_address)

    def ret(self):
        return self.pop()


def factorial_with_stack(stack, n):
    """Compute n! (n >= 1) the way a recursive function would, using `stack`.

    Returns (result, depths, returns): depths[i] is the bytes on the stack after
    call i+1 (n values), returns holds the return addresses popped, innermost first.
    """
    MAIN_RET, SELF_RET = 0x400, 0x500
    start = stack.sp
    depths = []
    # Going down: factorial(n) calls factorial(n-1), ... down to factorial(1).
    for k in range(n, 0, -1):
        stack.call(MAIN_RET if k == n else SELF_RET)   # return address
        stack.push(k)                                   # saved argument
        depths.append(start - stack.sp)
    # Coming back up: the base case returns 1, each frame multiplies by its k.
    result, returns = 1, []
    for _ in range(n):
        k = stack.pop()
        returns.append(stack.ret())
        result *= k
    return result, depths, returns


def x86_immediate_bytes(value):
    """The 4 immediate bytes in the machine code for `mov eax, value` on x86-64."""
    code = cputools.machine_code(f"mov eax, {value}")
    return code[1:5]            # byte 0 is the opcode 0xB8; the next four are the immediate


if __name__ == "__main__":
    mem = Memory(64)
    mem.store(0, 0x11223344, 4)
    print("bytes in memory:", " ".join(f"{b:02x}" for b in mem.data[:4]))
    print("load 1 byte at 0:", hex(mem.load(0, 1)))
    stack = Stack(mem, 64)
    result, depths, returns = factorial_with_stack(stack, 4)
    print("4! =", result, "stack bytes used:", depths, "sp back at top:", stack.sp == 64)
    print("x86 mov eax, 0x11223344 immediate:", x86_immediate_bytes(0x11223344).hex(" "))
