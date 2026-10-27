"""Checks for the LLVM IR basics exercise."""

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
                fail(f"your code ran for more than {timeout} seconds; does a loop never end?")
            data = os.read(r, 65536)
            if not data:
                break
            chunks.append(data)
    finally:
        os.close(r)
    _, status = os.waitpid(pid, 0)
    if os.WIFSIGNALED(status):
        fail(f"your compiled IR crashed with signal {os.WTERMSIG(status)}")
    if not chunks:
        fail("the child process ended before returning")
    payload = json.loads(b"".join(chunks))
    if "error" in payload:
        fail(payload["error"])
    return payload["ok"]


def verified(ir):
    """Verify IR text, and fail with LLVM's own message when it is rejected."""
    if not isinstance(ir, str):
        fail(f"the function should return a string of IR, got {type(ir).__name__}")
    try:
        cputools.verify_ir(ir)
    except cputools.ToolError as exc:
        fail(f"LLVM rejected your IR.\n{exc}")
    return ir


def load(ir, name, restype, argtypes):
    """Verify, compile, and return the function `name` with its ctypes signature."""
    lib = cputools.ir_to_lib(verified(ir), opt="-O0")
    fn = getattr(lib, name)
    fn.restype = restype
    fn.argtypes = argtypes
    return fn


def wrap32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v >= (1 << 31) else v


INTS = [0, 1, -1, 2, -2, 7, 255, 256, 0x17F, 0x1FF, -129, 65536, 2**30, 2**31 - 1, -(2**31)]


@check("ir_opcodes lists the opcode of each instruction, skipping labels and comments")
def test_opcodes(sub):
    ops = has(sub, "ir_opcodes")
    ir = """\
; a comment line
define i32 @f(i32 %a) {
entry:
  %b = add nsw i32 %a, 1   ; bump
  %c = icmp slt i32 %b, 10
  br i1 %c, label %yes, label %no
yes:
  ret i32 %b
no:
  call void @g()
  ret i32 0
}
"""
    equal(ops(ir), ["add", "icmp", "br", "ret", "call", "ret"], label="opcodes of f")
    equal(ops("declare void @g()\n"), [], label="a declaration has no body")
    two = "define i32 @a() {\n  ret i32 1\n}\ndefine i32 @b() {\nentry:\n  %x = mul i32 2, 3\n  ret i32 %x\n}\n"
    equal(ops(two), ["ret", "mul", "ret"], label="two functions")


@check("ir_opcodes reads the IR clang emits")
def test_opcodes_real(sub):
    ops = has(sub, "ir_opcodes")
    got = ops(cputools.c_to_ir("int sq(int x) { return x * x; }", opt="-O0"))
    equal(got, ["alloca", "store", "load", "load", "mul", "ret"], label="opcodes of clang -O0 IR for x * x")
    o2 = ops(cputools.c_to_ir("int sq(int x) { return x * x; }", opt="-O2"))
    equal(o2, ["mul", "ret"], label="opcodes at -O2")


@check("add3_ir verifies and adds three i32 values, wrapping like a C int")
def test_add3(sub):
    f = load(has(sub, "add3_ir")(), "add3", ctypes.c_int32, [ctypes.c_int32] * 3)
    cases = [(1, 2, 3), (0, 0, 0), (-1, -2, -3), (2**31 - 1, 1, 0), (-(2**31), -1, -1), (100, -100, 5)]
    got = in_child(lambda: [f(*c) for c in cases])
    for c, g in zip(cases, got):
        equal(g, wrap32(sum(c)), label=f"add3{c}")  # for example 1 + 2 + 3 = 6


@check("mul_wide_ir widens with sext, so the 64-bit product never overflows")
def test_mul_wide(sub):
    ir = has(sub, "mul_wide_ir")()
    f = load(ir, "mul_wide", ctypes.c_int64, [ctypes.c_int32] * 2)
    cases = [(3, 4), (-3, 4), (65536, 65536), (2**31 - 1, 2**31 - 1), (-(2**31), -(2**31)), (-(2**31), 2**31 - 1), (0, 5)]
    got = in_child(lambda: [f(a, b) for a, b in cases])
    for (a, b), g in zip(cases, got):
        equal(g, a * b, label=f"mul_wide({a}, {b})")  # 65536 * 65536 = 4294967296
    if "sext" not in ir:
        fail("mul_wide_ir should widen its arguments with sext")


@check("is_negative_ir uses icmp and zext to return 1 for negative inputs and 0 otherwise")
def test_is_negative(sub):
    ir = has(sub, "is_negative_ir")()
    f = load(ir, "is_negative", ctypes.c_int32, [ctypes.c_int32])
    got = in_child(lambda: [f(x) for x in INTS])
    for x, g in zip(INTS, got):
        equal(g, 1 if x < 0 else 0, label=f"is_negative({x})")
    if "icmp" not in ir or "zext" not in ir:
        fail("is_negative_ir should use icmp and zext")


@check("low_byte_ir truncates to i8 and sign-extends back")
def test_low_byte(sub):
    ir = has(sub, "low_byte_ir")()
    f = load(ir, "low_byte", ctypes.c_int32, [ctypes.c_int32])
    got = in_child(lambda: [f(x) for x in INTS])
    for x, g in zip(INTS, got):
        want = ((x & 0xFF) ^ 0x80) - 0x80  # 0x1FF -> 0xFF -> -1; 0x17F -> 0x7F -> 127
        equal(g, want, label=f"low_byte({x})")
    if "trunc" not in ir or "sext" not in ir:
        fail("low_byte_ir should use trunc and sext")


@check("avg_ir computes (a + b) / 2 in 64 bits, truncating toward zero")
def test_avg(sub):
    f = load(has(sub, "avg_ir")(), "avg", ctypes.c_int32, [ctypes.c_int32] * 2)
    cases = [(2, 4), (3, 4), (-3, -4), (-3, 4), (2**31 - 1, 2**31 - 1), (-(2**31), -(2**31)), (2**31 - 1, 2**31 - 2), (0, 1), (-1, 0)]
    got = in_child(lambda: [f(a, b) for a, b in cases])

    def want(a, b):
        s = a + b
        q = abs(s) // 2
        return q if s >= 0 else -q  # (-3 + 4) / 2 = 0; (-3 - 4) / 2 = -3

    for (a, b), g in zip(cases, got):
        equal(g, want(a, b), label=f"avg({a}, {b})")


@check("main_ir runs under lli and exits with (7 * 6 - 2) / 2 = 20, built from mul, sub, and sdiv")
def test_main(sub):
    ir = verified(has(sub, "main_ir")())
    result = cputools.run_ir(ir)
    equal(result.returncode, 20, label="exit code of @main")
    for op in ("mul", "sub", "sdiv"):
        if op not in ir:
            fail(f"main_ir should use the {op} instruction")
