"""Memory, the stack, and endianness.

Fill in every function and method that raises NotImplementedError.
"""

import cputools  # for x86_immediate_bytes


class MemoryFault(Exception):
    """An access outside memory, or a misaligned one on a strict machine."""


class StackError(Exception):
    """A pop from an empty stack."""


def to_le_bytes(value, size):
    """The `size` little-endian bytes of `value`, wrapped to that many bytes.

    to_le_bytes(0x11223344, 4) == b"\\x44\\x33\\x22\\x11"
    to_le_bytes(-1, 2) == b"\\xff\\xff"
    """
    raise NotImplementedError


def from_le_bytes(data, signed=False):
    """The integer stored in little-endian `data` (a bytes or bytearray).

    from_le_bytes(b"\\x44\\x33\\x22\\x11") == 0x11223344
    from_le_bytes(b"\\xff\\xff", signed=True) == -1
    """
    raise NotImplementedError


class Memory:
    """A byte-addressed memory of `size` bytes, all zero at the start.

    `self.data` is the bytearray. With strict_align=True, an access whose
    address is not a multiple of its size raises MemoryFault.
    """

    def __init__(self, size, strict_align=False):
        raise NotImplementedError

    def store(self, addr, value, size):
        """Write `value` at `addr` as `size` little-endian bytes (size 1, 2, 4, or 8).

        Raise MemoryFault when any of the bytes is outside memory (including a
        negative address), or when strict_align is on and addr % size != 0.
        Raise ValueError for any other size.
        """
        raise NotImplementedError

    def load(self, addr, size, signed=False):
        """Read `size` bytes at `addr` as a little-endian integer.

        Same faults as store. mem.store(0, 0x11223344, 4); mem.load(0, 1) == 0x44.
        """
        raise NotImplementedError


def is_aligned(addr, size):
    """True when addr is a multiple of size.  is_aligned(8, 4) is True; is_aligned(6, 4) is False."""
    raise NotImplementedError


class Stack:
    """A stack in `memory` that grows down from address `top`. Each slot is 8 bytes.

    The empty stack has sp == top. `sp` is a public attribute.
    """

    def __init__(self, memory, top):
        raise NotImplementedError

    def push(self, value):
        """sp -= 8, then store `value` (8 bytes) at sp."""
        raise NotImplementedError

    def pop(self):
        """Load the 8 bytes at sp, then sp += 8. Raise StackError when empty."""
        raise NotImplementedError

    def call(self, return_address):
        """Push the return address."""
        raise NotImplementedError

    def ret(self):
        """Pop and return the return address."""
        raise NotImplementedError


def factorial_with_stack(stack, n):
    """Compute n! (n >= 1) the way a recursive function would, using `stack`.

    Each call is two pushes: the return address (0x400 for the call from main,
    0x500 for the recursive calls), then the argument k. Calls go n, n-1, ..., 1.
    Then unwind: pop k, then ret(), multiply the result by k.

    Returns (result, depths, returns):
      depths  - list of n numbers, the bytes on the stack after each call
                (measured from where sp started), e.g. [16, 32, 48, 64] for n = 4
      returns - the return addresses popped by ret(), innermost call first,
                e.g. [0x500, 0x500, 0x500, 0x400] for n = 4
    The stack is empty again at the end.
    """
    raise NotImplementedError


def x86_immediate_bytes(value):
    """The 4 immediate bytes in the machine code for `mov eax, value` on x86-64.

    Assemble the instruction with cputools.machine_code and slice the bytes out.
    x86_immediate_bytes(0x11223344) == b"\\x44\\x33\\x22\\x11"
    """
    raise NotImplementedError


if __name__ == "__main__":
    mem = Memory(64)
    mem.store(0, 0x11223344, 4)
    print("bytes in memory:", " ".join(f"{b:02x}" for b in mem.data[:4]))
    print("load 1 byte at 0:", hex(mem.load(0, 1)))
    stack = Stack(mem, 64)
    result, depths, returns = factorial_with_stack(stack, 4)
    print("4! =", result, "stack bytes used:", depths, "sp back at top:", stack.sp == 64)
    print("x86 mov eax, 0x11223344 immediate:", x86_immediate_bytes(0x11223344).hex(" "))
