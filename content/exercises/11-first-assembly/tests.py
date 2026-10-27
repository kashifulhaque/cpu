"""Checks for the first-assembly exercise."""

import ctypes
import json
import os
import select
import signal
import time

import cputools
from cpucheck import check, equal, fail, has

MASK64 = (1 << 64) - 1
INT64_MIN, INT64_MAX = -(1 << 63), (1 << 63) - 1


def s64(x):
    """Wrap a Python int to a signed 64-bit value."""
    x &= MASK64
    return x - (1 << 64) if x >> 63 else x


def s32(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x >> 31 else x


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


def _call2(fn, pairs, name, argt, rest, ref):
    """Call fn on every pair in a child process and compare with ref."""
    fn.argtypes = [argt, argt]
    fn.restype = rest
    got = safe_cases(pairs, lambda p: int(fn(*p)), describe=lambda p: f"{name}{p}")
    for pair, g in zip(pairs, got):
        equal(g, ref(*pair), label=f"{name}{pair}")


def _call1(fn, values, name, argt, rest, ref):
    fn.argtypes = [argt]
    fn.restype = rest
    got = safe_cases(values, lambda v: int(fn(v)), describe=lambda v: f"{name}({v})")
    for v, g in zip(values, got):
        equal(g, ref(v), label=f"{name}({v})")


@check("forty_two_asm: forty_two() returns 42")
def test_forty_two(sub):
    lib = _lib(has(sub, "forty_two_asm"))
    lib.forty_two.restype = ctypes.c_int64
    got = safe_cases([0], lambda _: int(lib.forty_two()))
    equal(got[0], 42, label="forty_two()")


@check("add64_asm: add64(a, b) adds two 64-bit integers, wrapping on overflow")
def test_add64(sub):
    lib = _lib(has(sub, "add64_asm"))
    pairs = [(2, 3), (0, 0), (-5, 2), (-7, -9), (INT64_MAX, 1), (INT64_MIN, -1),
             (1 << 40, 1 << 41), (INT64_MAX, INT64_MAX)]
    _call2(lib.add64, pairs, "add64", ctypes.c_int64, ctypes.c_int64, lambda a, b: s64(a + b))


@check("add32_asm: add32(a, b) adds two 32-bit ints and wraps at 32 bits")
def test_add32(sub):
    lib = _lib(has(sub, "add32_asm"))
    pairs = [(2, 3), (-1, 1), (2147483647, 1), (-2147483648, -1), (1000000, 3000000), (2147483647, 2147483647)]
    # INT_MAX + 1 wraps to -2147483648; INT_MIN + -1 wraps to 2147483647.
    _call2(lib.add32, pairs, "add32", ctypes.c_int32, ctypes.c_int32, lambda a, b: s32(a + b))


@check("lea_asm: scale4_add(a, b) is a * 4 + b, and your text uses `lea`")
def test_lea(sub):
    text = has(sub, "lea_asm")()
    if "lea" not in text.lower():
        fail("this check wants you to compute a * 4 + b with one `lea` instruction, but your text has no `lea`")
    lib = cputools.assemble(text)
    pairs = [(0, 0), (1, 1), (10, 7), (-3, 5), (5, -100), (1 << 61, 1), (INT64_MAX, INT64_MAX)]
    _call2(lib.scale4_add, pairs, "scale4_add", ctypes.c_int64, ctypes.c_int64, lambda a, b: s64(a * 4 + b))


@check("imul_asm: times7(x) multiplies by 7, wrapping at 64 bits")
def test_imul(sub):
    lib = _lib(has(sub, "imul_asm"))
    values = [0, 1, -1, 6, -6, 123456789, INT64_MAX, INT64_MIN]
    _call1(lib.times7, values, "times7", ctypes.c_int64, ctypes.c_int64, lambda x: s64(x * 7))


@check("shifts_asm: shl3, sar3 (signed), and shr3 (unsigned) shift by 3")
def test_shifts(sub):
    lib = _lib(has(sub, "shifts_asm"))
    values = [0, 1, 5, 8, 100, -1, -8, -9, INT64_MAX, INT64_MIN]
    _call1(lib.shl3, values, "shl3", ctypes.c_int64, ctypes.c_int64, lambda x: s64(x << 3))
    # sar copies the sign bit, so it rounds toward negative infinity: -9 >> 3 is -2.
    _call1(lib.sar3, values, "sar3", ctypes.c_int64, ctypes.c_int64, lambda x: x >> 3)
    # shr fills with zeros: as an unsigned number, -1 is 2**64 - 1.
    uvalues = [v & MASK64 for v in values]
    _call1(lib.shr3, uvalues, "shr3", ctypes.c_uint64, ctypes.c_uint64, lambda x: x >> 3)


@check("low32_asm: low32(x) keeps only the low 32 bits (a 32-bit write clears the upper half)")
def test_low32(sub):
    lib = _lib(has(sub, "low32_asm"))
    values = [0, 1, 0xFFFFFFFF, 0x1_0000_0000, 0xDEADBEEF_12345678, MASK64, 1 << 63]
    _call1(lib.low32, values, "low32", ctypes.c_uint64, ctypes.c_uint64, lambda x: x & 0xFFFFFFFF)


@check("widen_asm: widen(x) sign-extends a 32-bit int to 64 bits, ignoring the register's upper half")
def test_widen(sub):
    lib = _lib(has(sub, "widen_asm"))
    # The ABI leaves the upper 32 bits of rdi undefined for an int argument. We
    # fill them with a junk pattern, so only an instruction that reads edi and
    # extends it (movsxd) gives the right answer.
    lows = [0, 1, 5, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0xFFFFFFF6]
    junk = 0xABCD1234_00000000
    values = [junk | low for low in lows]
    _call1(lib.widen, values, "widen", ctypes.c_uint64, ctypes.c_int64, lambda x: s32(x))
