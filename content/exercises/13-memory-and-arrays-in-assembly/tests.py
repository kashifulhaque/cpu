"""Checks for the memory and arrays exercise."""

import ctypes
import json
import os
import random
import select
import signal
import time

import cputools
from cpucheck import check, equal, fail, has

INT64_MIN, INT64_MAX = -(1 << 63), (1 << 63) - 1
I64, I32, U8 = ctypes.c_int64, ctypes.c_int32, ctypes.c_uint8
PTR, SIZE = ctypes.c_void_p, ctypes.c_size_t
GUARD = 0x5A5A5A5A5A5A5A5A


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


def _wrap64(x):
    x &= (1 << 64) - 1
    return x - (1 << 64) if x >> 63 else x


def _arrays(rng):
    return [
        [7], [1, 2, 3], [5, -2, 9, 4], [-8, -3, -50], [0, 0, 0, 0],
        [INT64_MAX, 1], [INT64_MIN, -1, 5], list(range(1, 101)),
        [rng.randint(-10**9, 10**9) for _ in range(257)],
    ]


@check("nth_asm: nth(a, i) reads element i of an int64 array")
def test_nth(sub):
    lib = _lib(has(sub, "nth_asm"))
    lib.nth.argtypes = [PTR, SIZE]
    lib.nth.restype = I64
    data = [10, -20, 30, INT64_MAX, INT64_MIN, 7]
    cases = list(range(len(data)))

    def call(i):
        arr = (I64 * len(data))(*data)
        return int(lib.nth(arr, i))

    got = safe_cases(cases, call, describe=lambda i: f"nth(a, {i})")
    equal(got, data, label=f"nth(a, i) for i in 0..{len(data) - 1}, a = {data}")


@check("sum_i64_asm: sum_i64(a, n) adds n int64 values (0 for an empty array)")
def test_sum_i64(sub):
    lib = _lib(has(sub, "sum_i64_asm"))
    lib.sum_i64.argtypes = [PTR, SIZE]
    lib.sum_i64.restype = I64
    cases = [[]] + _arrays(random.Random(0))

    def call(values):
        arr = (I64 * max(len(values), 1))(*values)
        return int(lib.sum_i64(arr, len(values)))

    got = safe_cases(cases, call, describe=lambda v: f"sum_i64 over {len(v)} values {v[:6]}")
    for values, g in zip(cases, got):
        equal(g, _wrap64(sum(values)), label=f"sum_i64 over {len(values)} values {values[:6]}")


@check("sum_i32_asm: sum_i32(a, n) adds int32 values (4-byte elements) into a 64-bit result")
def test_sum_i32(sub):
    lib = _lib(has(sub, "sum_i32_asm"))
    lib.sum_i32.argtypes = [PTR, SIZE]
    lib.sum_i32.restype = I64
    rng = random.Random(1)
    cases = [[], [1], [-1, -2], [2147483647, 2147483647, 2147483647], [-2147483648, -2147483648],
             [rng.randint(-2**31, 2**31 - 1) for _ in range(100)]]

    def call(values):
        arr = (I32 * max(len(values), 1))(*values)
        return int(lib.sum_i32(arr, len(values)))

    got = safe_cases(cases, call, describe=lambda v: f"sum_i32 over {v[:6]}")
    for values, g in zip(cases, got):
        # Three INT_MAX values sum to 6442450941, which only a 64-bit register holds.
        equal(g, sum(values), label=f"sum_i32 over {len(values)} values {values[:6]}")


@check("max_i64_asm: max_i64(a, n) finds the largest signed element")
def test_max(sub):
    lib = _lib(has(sub, "max_i64_asm"))
    lib.max_i64.argtypes = [PTR, SIZE]
    lib.max_i64.restype = I64
    cases = _arrays(random.Random(2)) + [[-5], [3, 9, -4], [9, 3, 1], [-1, -1, -1]]

    def call(values):
        arr = (I64 * len(values))(*values)
        return int(lib.max_i64(arr, len(values)))

    got = safe_cases(cases, call, describe=lambda v: f"max_i64 over {v[:6]}")
    for values, g in zip(cases, got):
        equal(g, max(values), label=f"max_i64 over {len(values)} values {values[:6]}")


@check("reverse_asm: reverse_i64(a, n) reverses in place and writes nothing outside the array")
def test_reverse(sub):
    lib = _lib(has(sub, "reverse_asm"))
    lib.reverse_i64.argtypes = [PTR, SIZE]
    lib.reverse_i64.restype = None
    cases = [[]] + _arrays(random.Random(3)) + [[1, 2], [1, 2, 3, 4], [1, 2, 3, 4, 5]]

    def call(values):
        n = len(values)
        # Guard words on both sides catch writes outside a[0..n-1].
        buf = (I64 * (n + 2))(GUARD, *values, GUARD)
        lib.reverse_i64(ctypes.c_void_p(ctypes.addressof(buf) + 8), n)
        return list(buf)

    got = safe_cases(cases, call, describe=lambda v: f"reverse_i64 on {len(v)} values {v[:6]}")
    for values, g in zip(cases, got):
        want = [GUARD] + values[::-1] + [GUARD]
        equal(g, want, label=f"reverse_i64 on {len(values)} values {values[:6]} (the first and last numbers are guard words that must not change)")


@check("strlen_asm: my_strlen(s) counts bytes up to the first zero byte")
def test_strlen(sub):
    lib = _lib(has(sub, "strlen_asm"))
    lib.my_strlen.argtypes = [PTR]
    lib.my_strlen.restype = SIZE
    cases = [b"", b"a", b"hello", b"x" * 1000, b"abc\0def", b"\xff\x80\x01", b"a" * 63, b"a" * 64]

    def call(raw):
        buf = ctypes.create_string_buffer(raw, len(raw) + 8)
        return int(lib.my_strlen(buf))

    got = safe_cases(cases, call, describe=lambda s: f"my_strlen({s[:12]!r})")
    for raw, g in zip(cases, got):
        # The string ends at the first zero byte, so b"abc\0def" has length 3.
        equal(g, raw.index(0) if 0 in raw else len(raw), label=f"my_strlen({raw[:12]!r})")


@check("copy_bytes_asm: copy_bytes(dst, src, n) copies exactly n bytes")
def test_copy(sub):
    lib = _lib(has(sub, "copy_bytes_asm"))
    lib.copy_bytes.argtypes = [PTR, PTR, SIZE]
    lib.copy_bytes.restype = None
    rng = random.Random(4)
    cases = [0, 1, 2, 7, 8, 9, 100, 1000]
    payloads = {n: bytes(rng.randrange(256) for _ in range(n)) for n in cases}

    def call(n):
        src = ctypes.create_string_buffer(payloads[n], n + 2)
        dst = (U8 * (n + 2))(*([0xEE] * (n + 2)))
        lib.copy_bytes(dst, src, n)
        return bytes(dst).hex()

    got = safe_cases(cases, call, describe=lambda n: f"copy_bytes(dst, src, {n})")
    for n, g in zip(cases, got):
        # The two bytes after the copy keep their starting value, 0xee.
        want = (payloads[n] + b"\xee\xee").hex()
        equal(g, want, label=f"copy_bytes(dst, src, {n}), dst has 2 spare bytes that must stay 0xee")
