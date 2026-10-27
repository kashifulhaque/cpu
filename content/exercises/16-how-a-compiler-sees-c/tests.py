"""Checks for the compiler-output exercise."""

import ctypes
import json
import os
import select
import signal
import time

import cputools
from cpucheck import check, equal, fail, has


def in_child(work, timeout=10):
    """Run work() in a forked child and return its JSON-able result.

    A crash (segfault, bad stack) or a hang in the reader's assembly then fails
    one check instead of killing the whole run.
    """
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        code = 1
        try:
            os.close(r)
            try:
                payload = {"ok": work()}
            except BaseException as exc:  # noqa: BLE001
                payload = {"error": f"{type(exc).__name__}: {exc}"}
            os.write(w, json.dumps(payload).encode())
            code = 0
        finally:
            os._exit(code)
    os.close(w)
    chunks, deadline = [], time.monotonic() + timeout
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([r], [], [], left)[0]:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                fail(f"your code ran for more than {timeout} seconds; is there a missing ret, or a loop that never ends?")
            data = os.read(r, 65536)
            if not data:
                break
            chunks.append(data)
    finally:
        os.close(r)
    _, status = os.waitpid(pid, 0)
    if os.WIFSIGNALED(status):
        fail(f"your assembly crashed with signal {os.WTERMSIG(status)} (a segfault usually means a bad address or a missing ret)")
    if not chunks:
        fail("your assembly ended the process before returning; check that every path reaches ret")
    payload = json.loads(b"".join(chunks))
    if "error" in payload:
        fail(payload["error"])
    return payload["ok"]


SAMPLE = """\
    .text
    .globl f                  # exported
f:                            # @f
# %bb.0:
    mov eax, 1
.L1:
    add eax, eax              # double it
    dec edi
    jnz .L1
    ret
    .size f, .-f
"""


@check("instructions drops comments, labels, directives, and blank lines")
def test_instructions(sub):
    instructions = has(sub, "instructions")
    equal(
        instructions(SAMPLE),
        ["mov eax, 1", "add eax, eax", "dec edi", "jnz .L1", "ret"],
        label="instructions of a small function",
    )
    equal(instructions(""), [], label="empty text")
    equal(instructions("  \n# only a comment\n.L0:\n"), [], label="no instructions")


@check("mnemonics and count_instructions agree with the instruction list")
def test_mnemonics(sub):
    mnemonics, count = has(sub, "mnemonics"), has(sub, "count_instructions")
    equal(mnemonics(SAMPLE), ["mov", "add", "dec", "jnz", "ret"], label="mnemonics")
    equal(count(SAMPLE), 5, label="count_instructions")
    equal(mnemonics("MOV EAX, 1\nRET"), ["mov", "ret"], label="uppercase mnemonics are lowercased")


@check("has_loop is true only when a jump goes backward to an earlier label")
def test_has_loop(sub):
    has_loop = has(sub, "has_loop")
    equal(has_loop(SAMPLE), True, label="a counted loop")
    forward = "  test edi, edi\n  jle .L2\n  inc edi\n.L2:\n  ret\n"
    equal(has_loop(forward), False, label="a forward jump (an if) is not a loop")
    equal(has_loop("  mov eax, 1\n  ret\n"), False, label="straight-line code")
    equal(has_loop(".L9:\n  jmp .L9\n"), True, label="an unconditional jump to itself")


@check("memory_accesses counts bracketed operands but not lea")
def test_memory(sub):
    mem = has(sub, "memory_accesses")
    asm = "push rbp\nmov dword ptr [rbp - 4], edi\nmov eax, dword ptr [rbp - 4]\nlea eax, [rdi + 4*rdi]\nret\n"
    equal(mem(asm), 2, label="two stack accesses and one lea")
    equal(mem("lea eax, [rdi + rsi]\nret\n"), 0, label="lea alone")


@check("uses_lea_times5 recognises [reg + 4*reg] and nothing else")
def test_lea5(sub):
    f = has(sub, "uses_lea_times5")
    equal(f("lea eax, [rdi + 4*rdi]\nret\n"), True, label="rdi + 4*rdi")
    equal(f("lea ecx, [rax+4*rax]\nret\n"), True, label="rax + 4*rax with no spaces")
    equal(f("lea eax, [rdi + 4*rsi]\nret\n"), False, label="two different registers")
    equal(f("lea eax, [rdi + 2*rdi]\nret\n"), False, label="times 3, not 5")
    equal(f("imul eax, edi, 5\nret\n"), False, label="imul is not lea")


@check("the predicates describe real clang output: -O0 uses the stack, -O2 uses lea")
def test_real_times5(sub):
    mem, lea5, count = has(sub, "memory_accesses"), has(sub, "uses_lea_times5"), has(sub, "count_instructions")
    src = "int f(int x) { return x * 5; }"
    o0 = cputools.c_to_asm(src, opt="-O0")
    o2 = cputools.c_to_asm(src, opt="-O2")
    if mem(o0) < 1:
        fail(f"clang -O0 keeps x in memory, so memory_accesses should be at least 1; got {mem(o0)}")
    equal(mem(o2), 0, label="memory accesses at -O2")
    equal(lea5(o2), True, label="-O2 multiplies by 5 with lea")
    equal(lea5(o0), False, label="-O0 uses imul instead")
    if not count(o2) < count(o0):
        fail(f"-O2 should need fewer instructions than -O0, got {count(o2)} and {count(o0)}")


@check("has_loop sees the loop in -O0 code for sum 1..n, and none in the -O2 code")
def test_real_loop(sub):
    has_loop = has(sub, "has_loop")
    src = "int sum(int n) { int s = 0; for (int i = 1; i <= n; i++) s += i; return s; }"
    equal(has_loop(cputools.c_to_asm(src, opt="-O0")), True, label="-O0 keeps the loop")
    # clang 19 at -O2 turns this loop into the closed form n(n+1)/2, so no backward jump remains.
    equal(has_loop(cputools.c_to_asm(src, opt="-O2")), False, label="-O2 replaces the loop with arithmetic")
    mem_src = "long total(const long *a, int n) { long s = 0; for (int i = 0; i < n; i++) s += a[i]; return s; }"
    equal(has_loop(cputools.c_to_asm(mem_src, opt="-O2")), True, label="a sum over memory keeps a loop at -O2")


@check("instruction_counts returns (count at -O0, count at -O2) from the real compiler")
def test_counts(sub):
    counts = has(sub, "instruction_counts")
    o0, o2 = counts("int f(int x) { return x * 5; }")
    if not (isinstance(o0, int) and isinstance(o2, int)):
        fail(f"expected two ints, got {(o0, o2)!r}")
    if not (o0 >= 4 and 1 <= o2 <= 3 and o2 < o0):
        fail(f"for x * 5 expected a longer -O0 listing and a 1 to 3 instruction -O2 listing, got ({o0}, {o2})")
    big0, big2 = counts("int g(int x) { int y = x; y = y + 1; y = y * 2; return y - x; }")
    if not big2 < big0:
        fail(f"-O2 should beat -O0 on g, got ({big0}, {big2})")


@check("score_asm computes a*5 + b*8 - 3 in 32-bit arithmetic without touching memory")
def test_score(sub):
    text = has(sub, "score_asm")()
    mem = has(sub, "memory_accesses")
    count = has(sub, "count_instructions")
    lib = cputools.assemble(text)
    lib.score.argtypes = [ctypes.c_int32, ctypes.c_int32]
    lib.score.restype = ctypes.c_int32
    cases = [(0, 0), (1, 1), (2, 3), (-4, 9), (100, -100), (2**30, 1), (-(2**31), 2**31 - 1), (2**31 - 1, 2**31 - 1)]

    def run():
        return [lib.score(a, b) for a, b in cases]

    got = in_child(run)

    def wrap(v):
        v &= 0xFFFFFFFF
        return v - (1 << 32) if v >= (1 << 31) else v

    # 2*5 + 3*8 - 3 = 31; the large cases wrap around like a C int.
    for (a, b), g in zip(cases, got):
        equal(g, wrap(a * 5 + b * 8 - 3), label=f"score({a}, {b})")
    equal(mem(text), 0, label="memory accesses in your assembly")
    o0 = count(cputools.c_to_asm("int score(int a, int b) { return a * 5 + b * 8 - 3; }", opt="-O0"))
    if count(text) > o0:
        fail(f"your function has {count(text)} instructions; clang -O0 needs {o0}, and you should need fewer")
