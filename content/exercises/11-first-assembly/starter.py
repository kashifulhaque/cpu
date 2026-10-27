"""Your first x86-64 functions.

Each function below returns assembly text in Intel syntax. The checks assemble
that text with cputools.assemble and call the result from Python.

x86-64 System V reminders:
  arguments:  rdi, rsi, rdx, rcx, r8, r9   (32-bit names edi, esi, edx, ecx)
  result:     rax                          (32-bit name eax)
"""

import ctypes

import cputools


def forty_two_asm() -> str:
    """Assembly for `long forty_two(void)`, which returns 42.

    >>> "forty_two:" in forty_two_asm()
    True
    """
    raise NotImplementedError


def add64_asm() -> str:
    """Assembly for `long add64(long a, long b)`: a + b with 64-bit wraparound."""
    raise NotImplementedError


def add32_asm() -> str:
    """Assembly for `int add32(int a, int b)`: a + b with 32-bit wraparound."""
    raise NotImplementedError


def lea_asm() -> str:
    """Assembly for `long scale4_add(long a, long b)`: a * 4 + b, using one `lea`."""
    raise NotImplementedError


def imul_asm() -> str:
    """Assembly for `long times7(long x)`: x * 7 with 64-bit wraparound."""
    raise NotImplementedError


def shifts_asm() -> str:
    """Assembly for three functions, each taking one 64-bit argument:

    shl3(x): x shifted left by 3
    sar3(x): signed x shifted right by 3, copying the sign bit
    shr3(x): unsigned x shifted right by 3, filling with zeros
    """
    raise NotImplementedError


def low32_asm() -> str:
    """Assembly for `unsigned long low32(unsigned long x)`: only the low 32 bits of x."""
    raise NotImplementedError


def widen_asm() -> str:
    """Assembly for `long widen(int x)`: the 32-bit int x, sign-extended to 64 bits."""
    raise NotImplementedError


if __name__ == "__main__":
    text = add64_asm()
    lib = cputools.assemble(text)
    lib.add64.argtypes = [ctypes.c_int64, ctypes.c_int64]
    lib.add64.restype = ctypes.c_int64
    print("add64(40, 2) =", lib.add64(40, 2))
    listing = cputools.disassemble(cputools.assemble_object(text))
    print("machine code:")
    print("\n".join(line for line in listing.splitlines() if line.startswith(" ") or "<" in line))
