"""Pointers and arrays in x86-64 assembly.

Every function takes pointers. Python hands over a ctypes array, which is a
block of real memory, and the assembly reads and writes it directly.

System V reminders: arguments in rdi, rsi, rdx, rcx; result in rax.
A size_t or pointer is 64 bits wide, so use the 64-bit names.
"""

import ctypes

import cputools


def make_array(values, kind=ctypes.c_int64):
    """Copy a Python list into a ctypes array of `kind`. Given in full."""
    return (kind * len(values))(*values)


def nth_asm() -> str:
    """Assembly for `long nth(const long *a, unsigned long i)`: the value a[i].

    The array holds 8-byte integers. nth([10, 20, 30], 2) is 30.
    """
    return """
    .globl nth
nth:
    mov rax, [rdi + rsi*8]
    ret
"""


def sum_i64_asm() -> str:
    """Assembly for `long sum_i64(const long *a, unsigned long n)`: the sum of n 8-byte values.

    sum_i64([1, 2, 3], 3) is 6. sum_i64(a, 0) is 0.
    """
    # rax is the total, rcx the index.
    return """
    .globl sum_i64
sum_i64:
    xor eax, eax
    xor ecx, ecx
.Lloop:
    cmp rcx, rsi
    jae .Ldone
    add rax, [rdi + rcx*8]
    inc rcx
    jmp .Lloop
.Ldone:
    ret
"""


def sum_i32_asm() -> str:
    """Assembly for `long sum_i32(const int *a, unsigned long n)`: the sum of n 4-byte ints, as a 64-bit result.

    Negative elements must stay negative: sum_i32([-1, -2], 2) is -3.
    """
    return """
    .globl sum_i32
sum_i32:
    xor eax, eax
    xor ecx, ecx
.Lloop:
    cmp rcx, rsi
    jae .Ldone
    movsxd rdx, dword ptr [rdi + rcx*4]
    add rax, rdx
    inc rcx
    jmp .Lloop
.Ldone:
    ret
"""


def max_i64_asm() -> str:
    """Assembly for `long max_i64(const long *a, unsigned long n)`: the largest of n >= 1 signed 8-byte values.

    max_i64([3, 9, -4], 3) is 9.
    """
    return """
    .globl max_i64
max_i64:
    mov rax, [rdi]
    mov ecx, 1
.Lloop:
    cmp rcx, rsi
    jae .Ldone
    mov rdx, [rdi + rcx*8]
    cmp rdx, rax
    cmovg rax, rdx
    inc rcx
    jmp .Lloop
.Ldone:
    ret
"""


def reverse_asm() -> str:
    """Assembly for `void reverse_i64(long *a, unsigned long n)`: reverse n 8-byte values in place.

    [1, 2, 3, 4] becomes [4, 3, 2, 1]. Touch nothing outside a[0..n-1].
    """
    # rdi walks up from the first element, rdx walks down from the last.
    return """
    .globl reverse_i64
reverse_i64:
    lea rdx, [rdi + rsi*8 - 8]
.Lloop:
    cmp rdi, rdx
    jae .Ldone
    mov rax, [rdi]
    mov rcx, [rdx]
    mov [rdi], rcx
    mov [rdx], rax
    add rdi, 8
    sub rdx, 8
    jmp .Lloop
.Ldone:
    ret
"""


def strlen_asm() -> str:
    """Assembly for `unsigned long my_strlen(const char *s)`: bytes before the first zero byte.

    my_strlen("hello") is 5. my_strlen("") is 0.
    """
    return """
    .globl my_strlen
my_strlen:
    xor eax, eax
.Lloop:
    cmp byte ptr [rdi + rax], 0
    je .Ldone
    inc rax
    jmp .Lloop
.Ldone:
    ret
"""


def copy_bytes_asm() -> str:
    """Assembly for `void copy_bytes(char *dst, const char *src, unsigned long n)`: copy n bytes from src to dst.

    Do not call libc. Touch nothing outside dst[0..n-1].
    """
    return """
    .globl copy_bytes
copy_bytes:
    xor ecx, ecx
.Lloop:
    cmp rcx, rdx
    jae .Ldone
    mov al, [rsi + rcx]
    mov [rdi + rcx], al
    inc rcx
    jmp .Lloop
.Ldone:
    ret
"""


if __name__ == "__main__":
    lib = cputools.assemble(sum_i64_asm())
    lib.sum_i64.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    lib.sum_i64.restype = ctypes.c_int64
    data = make_array([10, 20, 30, 40, 50])
    print("sum_i64([10, 20, 30, 40, 50], 5) =", lib.sum_i64(data, len(data)))
