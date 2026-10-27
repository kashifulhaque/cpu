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
    out = []
    for line in asm.splitlines():
        line = line.split("#", 1)[0].strip()  # drop the comment, then the margins
        if not line or line.startswith("."):
            continue  # blank line or directive
        if line.endswith(":"):
            continue  # label
        out.append(line)
    return out


def mnemonics(asm: str) -> list[str]:
    """The first word of every instruction, in order.

    >>> mnemonics("f:\\n  mov eax, 1\\n  ret\\n")
    ['mov', 'ret']
    """
    return [line.split()[0].lower() for line in instructions(asm)]


def count_instructions(asm: str) -> int:
    """How many instructions `asm` holds.

    >>> count_instructions("f:\\n  mov eax, 1\\n  ret\\n")
    2
    """
    return len(instructions(asm))


def has_loop(asm: str) -> bool:
    """True if some jump goes backward: its target label appears earlier in `asm`.

    >>> has_loop(".L1:\\n  dec edi\\n  jnz .L1\\n  ret\\n")
    True
    >>> has_loop("  test edi, edi\\n  jle .L2\\n  inc edi\\n.L2:\\n  ret\\n")
    False
    """
    seen = set()  # labels defined so far, scanning top to bottom
    for raw in asm.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.endswith(":") and " " not in line:
            seen.add(line[:-1])
        elif line and not line.startswith("."):
            parts = line.split()
            if parts[0].lower().startswith("j") and parts[-1] in seen:
                return True  # the target was defined above: this jump goes back
    return False


def memory_accesses(asm: str) -> int:
    """How many instructions read or write memory.

    An instruction touches memory when it has a bracketed operand, such as
    `[rbp - 4]`, and is not `lea` (which only computes an address).

    >>> memory_accesses("mov dword ptr [rbp - 4], edi\\nlea eax, [rdi + 4*rdi]\\nret\\n")
    1
    """
    return sum(1 for line in instructions(asm) if "[" in line and line.split()[0].lower() != "lea")


def uses_lea_times5(asm: str) -> bool:
    """True if some `lea` multiplies a register by 5 as `[reg + 4*reg]`.

    >>> uses_lea_times5("lea eax, [rdi + 4*rdi]\\nret\\n")
    True
    >>> uses_lea_times5("lea eax, [rdi + 4*rsi]\\nret\\n")
    False
    """
    pattern = re.compile(r"^lea\s+\w+,\s*\[\s*(\w+)\s*\+\s*4\s*\*\s*\1\s*\]", re.IGNORECASE)
    return any(pattern.match(line) for line in instructions(asm))


def instruction_counts(c_source: str) -> tuple[int, int]:
    """Compile `c_source` with clang at -O0 and at -O2, and return the
    instruction counts as `(count_at_O0, count_at_O2)`.

    Use `cputools.c_to_asm(src, opt="-O0")` and `count_instructions`.
    """
    o0 = count_instructions(cputools.c_to_asm(c_source, opt="-O0"))
    o2 = count_instructions(cputools.c_to_asm(c_source, opt="-O2"))
    return (o0, o2)


def score_asm() -> str:
    """Assembly for this C function (symbol `score`, System V ABI):

        int score(int a, int b) { return a * 5 + b * 8 - 3; }

    The arguments arrive in edi and esi, and the result goes in eax. Use no
    memory at all, and no more instructions than clang needs at -O0.

    Return the text of the function, starting with `.globl score` and `score:`.
    """
    return """
    .globl score
score:
    lea eax, [rdi + 4*rdi]      # eax = a*5
    lea eax, [rax + 8*rsi - 3]  # eax = a*5 + b*8 - 3
    ret
"""


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
