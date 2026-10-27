"""Functions, the stack, and the System V calling convention.

Each function returns Intel-syntax assembly text. The checks assemble it and
call it in a child process, through a small harness that fills the
callee-saved registers with known values and checks them afterwards.

System V rules used here:
  arguments:      rdi, rsi, rdx, rcx, r8, r9, then the stack
  result:         rax
  callee-saved:   rbx, rbp, r12, r13, r14, r15  (you must restore them)
  caller-saved:   everything else (a call may change them)
  alignment:      rsp is a multiple of 16 at the moment of every `call`
"""

import cputools


def fact_asm() -> str:
    """Assembly for `long fact(long n)`: n factorial, written recursively.

    fact(5) is 120, and fact(n) is 1 for n <= 1. The function must call itself.
    """
    raise NotImplementedError


def fib_asm() -> str:
    """Assembly for `long fib(long n)`: the n-th Fibonacci number, written with two recursive calls.

    fib(0) is 0, fib(1) is 1, fib(10) is 55. The function must call itself.
    """
    raise NotImplementedError


def apply_twice_asm() -> str:
    """Assembly for `long apply_twice(long (*fn)(long), long x)`: fn(fn(x)).

    fn arrives in rdi and x in rsi. If fn adds 3, apply_twice(fn, 10) is 16.
    """
    raise NotImplementedError


def sum_map_asm() -> str:
    """Assembly for `long sum_map(long (*fn)(long), long n)`: fn(0) + fn(1) + ... + fn(n - 1).

    The result is 0 when n <= 0. The loop must survive every call to fn.
    """
    raise NotImplementedError


def sum7_asm() -> str:
    """Assembly for `long sum7(long a, long b, long c, long d, long e, long f, long g)`.

    The first six arguments are in registers. The seventh, g, is on the stack.
    sum7(1, 2, 3, 4, 5, 6, 7) is 28.
    """
    raise NotImplementedError


if __name__ == "__main__":
    import ctypes

    lib = cputools.assemble(fact_asm())
    lib.fact.argtypes = [ctypes.c_int64]
    lib.fact.restype = ctypes.c_int64
    print("fact(5) =", lib.fact(5))
    print("fact(20) =", lib.fact(20))
    listing = cputools.disassemble(cputools.assemble_object(fact_asm()))
    print("\n".join(line for line in listing.splitlines() if line.startswith(" ") or "<" in line))
