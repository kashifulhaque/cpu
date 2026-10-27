"""Checks for the flags and control flow exercise."""

import ctypes
import json
import os
import random
import re
import select
import signal
import time

import cputools
from cpucheck import check, equal, fail, has

MASK64 = (1 << 64) - 1
INT32_MIN, INT32_MAX = -(1 << 31), (1 << 31) - 1
INT64_MIN, INT64_MAX = -(1 << 63), (1 << 63) - 1


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


def _lib(text_fn):
    # Calling the reader's function first means a starter shows "not implemented yet".
    return cputools.assemble(text_fn())


def _fmt(name, case):
    return f"{name}({', '.join(str(x) for x in case)})"


def _run(fn, argtypes, restype, cases, name, ref):
    """Call fn(*case) in a child for every case and compare with ref(*case)."""
    fn.argtypes = argtypes
    fn.restype = restype
    got = safe_cases(cases, lambda c: int(fn(*c)), describe=lambda c: _fmt(name, c))
    for case, g in zip(cases, got):
        equal(g, ref(*case), label=_fmt(name, case))


def _has_backward_jump(text):
    """True if some jump targets a label that appears earlier in the text."""
    seen = set()
    for line in text.splitlines():
        line = line.split("#")[0].split(";")[0].strip()
        label = re.match(r"^([.\w$]+):", line)
        if label:
            seen.add(label.group(1))
            line = line[label.end():].strip()
        jump = re.match(r"^j\w+\s+([.\w$]+)", line)
        if jump and jump.group(1) in seen:
            return True
    return False


I32 = ctypes.c_int32


@check("max2_asm: max2(a, b) returns the larger signed 32-bit int")
def test_max2(sub):
    lib = _lib(has(sub, "max2_asm"))
    cases = [(3, 7), (7, 3), (-5, 2), (-1, -9), (0, 0), (INT32_MIN, INT32_MAX),
             (INT32_MAX, INT32_MIN), (INT32_MIN, -1), (5, 5)]
    _run(lib.max2, [I32, I32], I32, cases, "max2", max)


@check("abs_asm: abs32(x) is the absolute value, and INT_MIN stays INT_MIN")
def test_abs(sub):
    lib = _lib(has(sub, "abs_asm"))
    cases = [(0,), (1,), (-1,), (5,), (-5,), (INT32_MAX,), (-INT32_MAX,), (INT32_MIN,)]
    # -INT_MIN is 2**31, which wraps back to INT_MIN in 32 bits.
    ref = lambda x: INT32_MIN if x == INT32_MIN else abs(x)
    _run(lib.abs32, [I32], I32, cases, "abs32", ref)


@check("clamp_asm: clamp(x, lo, hi) limits x to the range lo..hi")
def test_clamp(sub):
    lib = _lib(has(sub, "clamp_asm"))
    cases = [(5, 0, 10), (-5, 0, 10), (50, 0, 10), (0, 0, 0), (7, 7, 7), (10, 0, 10),
             (INT32_MIN, -100, 100), (INT32_MAX, -100, 100), (-100, -100, -50), (-60, -100, -50)]
    _run(lib.clamp, [I32, I32, I32], I32, cases, "clamp", lambda x, lo, hi: min(max(x, lo), hi))


@check("compare_asm: less_signed treats the bits as signed numbers")
def test_less_signed(sub):
    lib = _lib(has(sub, "compare_asm"))
    cases = [(1, 2), (2, 1), (3, 3), (-1, 1), (1, -1), (-5, -3), (INT64_MIN, INT64_MAX), (INT64_MAX, INT64_MIN), (0, -1)]
    # -1 < 1 is true when the numbers are signed.
    _run(lib.less_signed, [ctypes.c_int64] * 2, ctypes.c_int, cases, "less_signed", lambda a, b: int(a < b))


@check("compare_asm: less_unsigned treats the same bits as unsigned numbers")
def test_less_unsigned(sub):
    lib = _lib(has(sub, "compare_asm"))
    pairs = [(1, 2), (2, 1), (3, 3), (-1, 1), (1, -1), (-5, -3), (INT64_MIN, INT64_MAX), (INT64_MAX, INT64_MIN), (0, -1)]
    cases = [(a & MASK64, b & MASK64) for a, b in pairs]
    # As unsigned, -1 is 2**64 - 1, the biggest value, so -1 < 1 is false.
    _run(lib.less_unsigned, [ctypes.c_uint64] * 2, ctypes.c_int, cases, "less_unsigned", lambda a, b: int(a < b))


@check("sum_to_asm: sum_to(n) is 1 + 2 + ... + n, 0 for n <= 0, and your text has a backward jump")
def test_sum_to(sub):
    text = has(sub, "sum_to_asm")()
    if not _has_backward_jump(text):
        fail("sum_to should be a loop: a conditional or unconditional jump back to an earlier label. Yours has no backward jump.")
    lib = cputools.assemble(text)
    # n(n+1)/2: 4 -> 10, 100 -> 5050, 100000 -> 5000050000.
    cases = [(0,), (1,), (2,), (4,), (100,), (-3,), (-1,), (100000,), (INT64_MIN,)]
    ref = lambda n: n * (n + 1) // 2 if n > 0 else 0
    _run(lib.sum_to, [ctypes.c_int64], ctypes.c_int64, cases, "sum_to", ref)


@check("popcount_asm: popcount(x) counts set bits with a loop")
def test_popcount(sub):
    text = has(sub, "popcount_asm")()
    if "popcnt" in text.lower():
        fail("this exercise asks for a loop, not the `popcnt` instruction")
    if not _has_backward_jump(text):
        fail("popcount should be a loop: a jump back to an earlier label. Yours has no backward jump.")
    lib = cputools.assemble(text)
    rng = random.Random(0)
    values = [0, 1, 0b1011, 255, 1 << 63, MASK64, 0xF0F0F0F0F0F0F0F0, 0x8000000000000001]
    values += [rng.getrandbits(64) for _ in range(20)]
    _run(lib.popcount, [ctypes.c_uint64], ctypes.c_int, [(v,) for v in values], "popcount", lambda x: bin(x).count("1"))
