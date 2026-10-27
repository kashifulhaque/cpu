"""Flags, comparisons, and control flow in x86-64 assembly.

Each function returns Intel-syntax assembly text. The checks assemble it with
cputools.assemble and call it through ctypes.

System V reminders: arguments in rdi, rsi, rdx, rcx; result in rax.
"""

import ctypes

import cputools


def max2_asm() -> str:
    """Assembly for `int max2(int a, int b)`: the larger of two signed 32-bit ints.

    max2(3, 7) is 7 and max2(-5, -9) is -5.
    """
    # Start with a as the answer, then take b if a is signed-less-than b.
    return """
    .globl max2
max2:
    mov eax, edi
    cmp edi, esi
    cmovl eax, esi
    ret
"""


def abs_asm() -> str:
    """Assembly for `int abs32(int x)`: the absolute value of a signed 32-bit int.

    abs32(-5) is 5. abs32(INT_MIN) is INT_MIN, because 2147483648 does not fit.
    """
    return """
    .globl abs32
abs32:
    mov eax, edi
    test edi, edi
    jns .Ldone
    neg eax
.Ldone:
    ret
"""


def clamp_asm() -> str:
    """Assembly for `int clamp(int x, int lo, int hi)`, signed, with lo <= hi.

    Returns lo if x < lo, hi if x > hi, and x otherwise. clamp(50, 0, 10) is 10.
    """
    return """
    .globl clamp
clamp:
    mov eax, edi
    cmp eax, esi
    cmovl eax, esi
    cmp eax, edx
    cmovg eax, edx
    ret
"""


def compare_asm() -> str:
    """Assembly for two functions that return 0 or 1 as an int:

    less_signed(long a, long b):          1 if a < b, comparing as signed
    less_unsigned(unsigned long a, unsigned long b):  1 if a < b, as unsigned

    less_signed(-1, 1) is 1, but less_unsigned(2**64 - 1, 1) is 0.
    """
    return """
    .globl less_signed
less_signed:
    xor eax, eax
    cmp rdi, rsi
    setl al
    ret

    .globl less_unsigned
less_unsigned:
    xor eax, eax
    cmp rdi, rsi
    setb al
    ret
"""


def sum_to_asm() -> str:
    """Assembly for `long sum_to(long n)`: 1 + 2 + ... + n, and 0 when n <= 0.

    Write a real loop. sum_to(4) is 10.
    """
    # rax is the running total and rcx is the counter, from 1 up to n.
    return """
    .globl sum_to
sum_to:
    xor eax, eax
    mov ecx, 1
.Lloop:
    cmp rcx, rdi
    jg .Ldone
    add rax, rcx
    inc rcx
    jmp .Lloop
.Ldone:
    ret
"""


def popcount_asm() -> str:
    """Assembly for `int popcount(unsigned long x)`: how many bits of x are 1.

    Write a loop; do not use the `popcnt` instruction. popcount(0b1011) is 3.
    """
    # Test the lowest bit, add it to the count, shift right, stop when x is 0.
    return """
    .globl popcount
popcount:
    xor eax, eax
.Lloop:
    test rdi, rdi
    jz .Ldone
    mov rcx, rdi
    and ecx, 1
    add eax, ecx
    shr rdi, 1
    jmp .Lloop
.Ldone:
    ret
"""


if __name__ == "__main__":
    lib = cputools.assemble(max2_asm())
    lib.max2.argtypes = [ctypes.c_int32, ctypes.c_int32]
    lib.max2.restype = ctypes.c_int32
    print("max2(3, 7) =", lib.max2(3, 7))

    cmp_lib = cputools.assemble(compare_asm())
    cmp_lib.less_signed.argtypes = [ctypes.c_int64, ctypes.c_int64]
    cmp_lib.less_unsigned.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
    # The same 64 bits, all ones, are -1 as signed and 2**64 - 1 as unsigned.
    print("signed:   -1 < 1 ->", cmp_lib.less_signed(-1, 1))
    print("unsigned: 2**64-1 < 1 ->", cmp_lib.less_unsigned(2**64 - 1, 1))
