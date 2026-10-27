"""Read compiler output and beat it by hand.

The first functions take assembly text (as clang prints it with Intel syntax) and
answer questions about it. `instruction_counts` calls the real compiler. The last
function is assembly you write yourself.
"""

import re

import cputools


def instructions(asm: str) -> list[str]:
    """The instruction lines of `asm`, in order, with comments stripped.

    Labels (`foo:`), directives (lines starting with `.`), comments (from `#`
    to the end of the line), and blank lines are not instructions.

    >>> instructions("f:   # entry\\n  mov eax, 1\\n  ret\\n")
    ['mov eax, 1', 'ret']
    """
    raise NotImplementedError


def mnemonics(asm: str) -> list[str]:
    """The first word of every instruction, in order.

    >>> mnemonics("f:\\n  mov eax, 1\\n  ret\\n")
    ['mov', 'ret']
    """
    raise NotImplementedError


def count_instructions(asm: str) -> int:
    """How many instructions `asm` holds.

    >>> count_instructions("f:\\n  mov eax, 1\\n  ret\\n")
    2
    """
    raise NotImplementedError


def has_loop(asm: str) -> bool:
    """True if some jump goes backward: its target label appears earlier in `asm`.

    >>> has_loop(".L1:\\n  dec edi\\n  jnz .L1\\n  ret\\n")
    True
    >>> has_loop("  test edi, edi\\n  jle .L2\\n  inc edi\\n.L2:\\n  ret\\n")
    False
    """
    raise NotImplementedError


def memory_accesses(asm: str) -> int:
    """How many instructions read or write memory.

    An instruction touches memory when it has a bracketed operand, such as
    `[rbp - 4]`, and is not `lea` (which only computes an address).

    >>> memory_accesses("mov dword ptr [rbp - 4], edi\\nlea eax, [rdi + 4*rdi]\\nret\\n")
    1
    """
    raise NotImplementedError


def uses_lea_times5(asm: str) -> bool:
    """True if some `lea` multiplies a register by 5 as `[reg + 4*reg]`.

    >>> uses_lea_times5("lea eax, [rdi + 4*rdi]\\nret\\n")
    True
    >>> uses_lea_times5("lea eax, [rdi + 4*rsi]\\nret\\n")
    False
    """
    raise NotImplementedError


def instruction_counts(c_source: str) -> tuple[int, int]:
    """Compile `c_source` with clang at -O0 and at -O2, and return the
    instruction counts as `(count_at_O0, count_at_O2)`.

    Use `cputools.c_to_asm(src, opt="-O0")` and `count_instructions`.
    """
    raise NotImplementedError


def score_asm() -> str:
    """Assembly for this C function (symbol `score`, System V ABI):

        int score(int a, int b) { return a * 5 + b * 8 - 3; }

    The arguments arrive in edi and esi, and the result goes in eax. Use no
    memory at all, and no more instructions than clang needs at -O0.

    Return the text of the function, starting with `.globl score` and `score:`.
    """
    raise NotImplementedError


if __name__ == "__main__":
    c = "int f(int x) { return x * 5; }"
    o0 = cputools.c_to_asm(c, opt="-O0")
    o2 = cputools.c_to_asm(c, opt="-O2")
    print("-O0 mnemonics:", mnemonics(o0))
    print("-O2 mnemonics:", mnemonics(o2))
    print("counts (O0, O2):", instruction_counts(c))
    print("O2 uses lea times 5:", uses_lea_times5(o2))
    print("O0 memory accesses:", memory_accesses(o0))
    lib = cputools.assemble(score_asm())
    print("score(2, 3) =", lib.score(2, 3), "(want 31)")
