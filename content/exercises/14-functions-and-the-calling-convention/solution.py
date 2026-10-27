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
    # n lives in rbx across the recursive call, so rbx is saved and restored.
    # The single push also brings rsp to a multiple of 16 before the call.
    return """
    .globl fact
fact:
    cmp rdi, 1
    jg .Lrecurse
    mov eax, 1
    ret
.Lrecurse:
    push rbx
    mov rbx, rdi
    lea rdi, [rdi - 1]
    call fact
    imul rax, rbx
    pop rbx
    ret
"""


def fib_asm() -> str:
    """Assembly for `long fib(long n)`: the n-th Fibonacci number, written with two recursive calls.

    fib(0) is 0, fib(1) is 1, fib(10) is 55. The function must call itself.
    """
    # rbx holds n, r12 holds fib(n - 1) while the second call runs.
    # Two pushes leave rsp 8 bytes off a 16-byte boundary, so `sub rsp, 8` pads it.
    return """
    .globl fib
fib:
    cmp rdi, 2
    jge .Lrecurse
    mov rax, rdi
    ret
.Lrecurse:
    push rbx
    push r12
    sub rsp, 8
    mov rbx, rdi
    lea rdi, [rbx - 1]
    call fib
    mov r12, rax
    lea rdi, [rbx - 2]
    call fib
    add rax, r12
    add rsp, 8
    pop r12
    pop rbx
    ret
"""


def apply_twice_asm() -> str:
    """Assembly for `long apply_twice(long (*fn)(long), long x)`: fn(fn(x)).

    fn arrives in rdi and x in rsi. If fn adds 3, apply_twice(fn, 10) is 16.
    """
    return """
    .globl apply_twice
apply_twice:
    push rbx
    mov rbx, rdi
    mov rdi, rsi
    call rbx
    mov rdi, rax
    call rbx
    pop rbx
    ret
"""


def sum_map_asm() -> str:
    """Assembly for `long sum_map(long (*fn)(long), long n)`: fn(0) + fn(1) + ... + fn(n - 1).

    The result is 0 when n <= 0. The loop must survive every call to fn.
    """
    # rbx = fn, r12 = n, r13 = i, r14 = total. Four pushes plus `sub rsp, 8`
    # leave rsp a multiple of 16 at each call.
    return """
    .globl sum_map
sum_map:
    push rbx
    push r12
    push r13
    push r14
    sub rsp, 8
    mov rbx, rdi
    mov r12, rsi
    xor r13d, r13d
    xor r14d, r14d
.Lloop:
    cmp r13, r12
    jge .Ldone
    mov rdi, r13
    call rbx
    add r14, rax
    inc r13
    jmp .Lloop
.Ldone:
    mov rax, r14
    add rsp, 8
    pop r14
    pop r13
    pop r12
    pop rbx
    ret
"""


def sum7_asm() -> str:
    """Assembly for `long sum7(long a, long b, long c, long d, long e, long f, long g)`.

    The first six arguments are in registers. The seventh, g, is on the stack.
    sum7(1, 2, 3, 4, 5, 6, 7) is 28.
    """
    return """
    .globl sum7
sum7:
    lea rax, [rdi + rsi]
    add rax, rdx
    add rax, rcx
    add rax, r8
    add rax, r9
    add rax, [rsp + 8]
    ret
"""


if __name__ == "__main__":
    import ctypes

    lib = cputools.assemble(fact_asm())
    lib.fact.argtypes = [ctypes.c_int64]
    lib.fact.restype = ctypes.c_int64
    print("fact(5) =", lib.fact(5))
    print("fact(20) =", lib.fact(20))
    listing = cputools.disassemble(cputools.assemble_object(fact_asm()))
    print("\n".join(line for line in listing.splitlines() if line.startswith(" ") or "<" in line))
