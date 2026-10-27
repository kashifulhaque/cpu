"""Checks for the functions and calling convention exercise.

The checks run your code through a small harness written in assembly. It fills
rbx, rbp, and r12 to r15 with known values, calls your function, and reports
which of them changed. Its callbacks record a misaligned stack, and they
overwrite every caller-saved register before they return.
"""

import ctypes
import json
import os
import re
import select
import signal
import time

import cputools
from cpucheck import check, equal, fail, has

I64 = ctypes.c_int64
CALLEE_SAVED = ["rbx", "rbp", "r12", "r13", "r14", "r15"]


def safe_cases(cases, call, describe=repr, timeout=5.0):
    """Run `call(case)` for every case in a forked child and return the results.

    Reader assembly can crash or hang. A crash in this process would end the
    whole check run, so the compiled code runs in a child. The child writes one
    JSON line per case to a pipe and always ends with os._exit. The parent
    reports a crash or a hang as a readable failure.
    """
    cases = list(cases)
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        code = 1
        try:
            os.close(r)
            for case in cases:
                try:
                    line = json.dumps({"ok": call(case)})
                except Exception as exc:  # a bad ctypes call, not a crash
                    line = json.dumps({"err": f"{type(exc).__name__}: {exc}"})
                os.write(w, (line + "\n").encode())
            code = 0
        finally:
            os._exit(code)
    os.close(w)
    deadline = time.monotonic() + timeout
    buf = b""
    timed_out = False
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            timed_out = True
            break
        ready, _, _ = select.select([r], [], [], left)
        if not ready:
            timed_out = True
            break
        chunk = os.read(r, 65536)
        if not chunk:
            break
        buf += chunk
    os.close(r)
    if timed_out:
        os.kill(pid, signal.SIGKILL)
    _, status = os.waitpid(pid, 0)
    lines = [json.loads(x) for x in buf.decode().splitlines() if x.strip()]
    for entry in lines:
        if "err" in entry:
            fail(f"calling your function raised {entry['err']}")
    done = len(lines)
    where = describe(cases[done]) if done < len(cases) else "the last case"
    if timed_out:
        fail(
            f"your function did not return within {timeout:g} seconds on {where}. "
            "Look for a loop that never reaches its exit condition, or a missing `ret`."
        )
    if os.WIFSIGNALED(status):
        name = signal.Signals(os.WTERMSIG(status)).name
        why = {
            "SIGFPE": "An integer division by zero, or INT_MIN / -1, causes this.",
            "SIGILL": "The CPU hit bytes that are not an instruction. A missing `ret` or a damaged stack usually causes this.",
        }.get(name, "A bad address, a damaged stack, or running past the end of your code (a missing `ret`) usually causes this.")
        fail(f"your function crashed with signal {name} on {where}. {why}")
    if done < len(cases):
        fail(f"the process running your function ended early on {where}.")
    return [entry["ok"] for entry in lines]


def _callback(name, body):
    """Assembly for a callback that checks alignment and clobbers caller-saved registers."""
    return f"""
    .globl {name}
{name}:
    lea rax, [rsp + 8]
    test al, 15
    jz .Laligned_{name}
    mov dword ptr [rip + misaligned], 1
.Laligned_{name}:
{body}
    mov rcx, -1
    mov rdx, -1
    mov rsi, -1
    mov rdi, -1
    mov r8, -1
    mov r9, -1
    mov r10, -1
    mov r11, -1
    ret
"""


def _compare(reg, value):
    return f"""
    movabs rdx, {value}
    cmp {reg}, rdx
    je .Lsame_{reg}
    or ecx, {1 << CALLEE_SAVED.index(reg)}
.Lsame_{reg}:
"""


_SENTINELS = {reg: 0x1111111111111111 * (i + 1) for i, reg in enumerate(CALLEE_SAVED)}

HARNESS = """
    .data
misaligned: .long 0
    .text

    .globl get_misaligned
get_misaligned:
    mov eax, dword ptr [rip + misaligned]
    ret

    .globl clear_misaligned
clear_misaligned:
    mov dword ptr [rip + misaligned], 0
    ret
""" + _callback("cb_add3", "    lea rax, [rdi + 3]") + _callback("cb_square", "    mov rax, rdi\n    imul rax, rdi") + """
    # call_checked(target, a1, a2, out): calls target(a1, a2) with known values
    # in the callee-saved registers. Returns rax, and stores in *out a bit mask
    # of the registers that changed.
    .globl call_checked
call_checked:
    push rbp
    push rbx
    push r12
    push r13
    push r14
    push r15
    push rcx
""" + "".join(f"    movabs {reg}, {val}\n" for reg, val in _SENTINELS.items()) + """
    mov rax, rdi
    mov rdi, rsi
    mov rsi, rdx
    call rax
    xor ecx, ecx
""" + "".join(_compare(reg, val) for reg, val in _SENTINELS.items()) + """
    mov rdx, [rsp]
    mov [rdx], rcx
    pop rcx
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret
"""

_harness = None


def _get_harness():
    global _harness
    if _harness is None:
        h = cputools.assemble(HARNESS)
        h.call_checked.argtypes = [ctypes.c_void_p, I64, I64, ctypes.c_void_p]
        h.call_checked.restype = I64
        h.get_misaligned.restype = ctypes.c_int
        _harness = h
    return _harness


def _addr(func):
    return ctypes.cast(func, ctypes.c_void_p).value


def _run_checked(target, cases, describe, want, fn_name, check_alignment=False):
    """Call target(a1, a2) for every (a1, a2) case in a child, then verify everything."""
    h = _get_harness()
    tgt = _addr(target)

    def call(case):
        h.clear_misaligned()
        out = ctypes.c_int64(0)
        res = h.call_checked(tgt, case[0], case[1], ctypes.addressof(out))
        return [int(res), int(out.value), int(h.get_misaligned())]

    got = safe_cases(cases, call, describe=describe)
    for case, (res, mask, bad) in zip(cases, got):
        equal(res, want(case), label=describe(case))
        if mask:
            names = ", ".join(r for i, r in enumerate(CALLEE_SAVED) if mask >> i & 1)
            fail(
                f"{describe(case)} returned the right value, but changed {names}. "
                "Those registers are callee-saved: `push` each one before you change it and `pop` it before `ret`."
            )
        if check_alignment and bad:
            fail(
                f"{describe(case)} called a function with rsp not a multiple of 16. "
                "At entry rsp is 8 bytes off a 16-byte boundary. Each `push` moves it 8 bytes, "
                "so count your pushes and add `sub rsp, 8` when needed."
            )


def _fact(n):
    out = 1
    for k in range(2, n + 1):
        out *= k
    return out


def _fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


@check("fact_asm: fact(n) is n factorial, and your function calls itself")
def test_fact(sub):
    text = has(sub, "fact_asm")()
    if not re.search(r"\bcall\s+fact\b", text):
        fail("fact must be recursive: it should contain `call fact`")
    lib = cputools.assemble(text)
    cases = [(n, 0) for n in [0, 1, 2, 3, 5, 10, 15, 20, -4]]
    # 5! = 120 and 20! = 2432902008176640000, the largest that fits in 64 bits.
    _run_checked(lib.fact, cases, lambda c: f"fact({c[0]})", lambda c: _fact(c[0]) if c[0] > 1 else 1, "fact")


@check("fact_asm: fact leaves rbx, rbp, and r12 to r15 as it found them")
def test_fact_regs(sub):
    lib = cputools.assemble(has(sub, "fact_asm")())
    cases = [(n, 0) for n in [0, 1, 2, 6, 12]]
    _run_checked(lib.fact, cases, lambda c: f"fact({c[0]})", lambda c: _fact(c[0]), "fact")


@check("fib_asm: fib(n) is the n-th Fibonacci number with two recursive calls")
def test_fib(sub):
    text = has(sub, "fib_asm")()
    if len(re.findall(r"\bcall\s+fib\b", text)) < 2:
        fail("fib should call itself twice: once for n - 1 and once for n - 2")
    lib = cputools.assemble(text)
    cases = [(n, 0) for n in [0, 1, 2, 3, 4, 5, 10, 20, 25]]
    # fib: 0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55 ... so fib(10) = 55 and fib(25) = 75025.
    _run_checked(lib.fib, cases, lambda c: f"fib({c[0]})", lambda c: _fib(c[0]), "fib")


@check("fib_asm: fib keeps callee-saved registers intact across recursion")
def test_fib_regs(sub):
    lib = cputools.assemble(has(sub, "fib_asm")())
    cases = [(n, 0) for n in [0, 1, 2, 7, 15]]
    _run_checked(lib.fib, cases, lambda c: f"fib({c[0]})", lambda c: _fib(c[0]), "fib")


@check("apply_twice_asm: apply_twice(fn, x) calls the callback twice, with an aligned stack")
def test_apply_twice(sub):
    lib = cputools.assemble(has(sub, "apply_twice_asm")())
    h = _get_harness()
    fn = _addr(h.cb_add3)
    # cb_add3 adds 3, so fn(fn(x)) is x + 6.
    cases = [(fn, x) for x in [0, 10, -7, 1000000, -(1 << 40)]]
    _run_checked(lib.apply_twice, cases, lambda c: f"apply_twice(cb_add3, {c[1]})", lambda c: c[1] + 6,
                 "apply_twice", check_alignment=True)


@check("sum_map_asm: sum_map(fn, n) sums fn(i) for i < n; the loop survives every call")
def test_sum_map(sub):
    lib = cputools.assemble(has(sub, "sum_map_asm")())
    h = _get_harness()
    fn = _addr(h.cb_square)
    # cb_square returns i * i and overwrites rax, rcx, rdx, rsi, rdi, r8 to r11,
    # so a loop counter kept in one of those registers is lost.
    cases = [(fn, n) for n in [0, 1, 2, 3, 10, 100, -5]]
    want = lambda c: sum(i * i for i in range(c[1])) if c[1] > 0 else 0
    _run_checked(lib.sum_map, cases, lambda c: f"sum_map(cb_square, {c[1]})", want,
                 "sum_map", check_alignment=True)


@check("sum7_asm: sum7 adds seven arguments, the seventh read from the stack")
def test_sum7(sub):
    lib = cputools.assemble(has(sub, "sum7_asm")())
    lib.sum7.argtypes = [I64] * 7
    lib.sum7.restype = I64
    cases = [(1, 2, 3, 4, 5, 6, 7), (0,) * 7, (1, 10, 100, 1000, 10000, 100000, 1000000),
             (-1, -2, -3, -4, -5, -6, -7), (0, 0, 0, 0, 0, 0, 99), (1 << 40, 0, 0, 0, 0, 0, 1 << 41)]
    # 1 + 2 + ... + 7 = 28, and the powers of ten add up to 1111111.
    got = safe_cases(cases, lambda c: int(lib.sum7(*c)), describe=lambda c: f"sum7{c}")
    for case, g in zip(cases, got):
        equal(g, sum(case), label=f"sum7{case}")
