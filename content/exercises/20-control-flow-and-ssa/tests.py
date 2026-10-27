"""Checks for the control flow and SSA exercise."""

import ctypes
import json
import math
import os
import random
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


def verified(ir):
    """Verify IR text, and fail with LLVM's own message when it is rejected."""
    if not isinstance(ir, str):
        fail(f"the function should return a string of IR, got {type(ir).__name__}")
    try:
        cputools.verify_ir(ir)
    except cputools.ToolError as exc:
        fail(f"LLVM rejected your IR.\n{exc}")
    return ir


DIAMOND = """\
define i32 @pick(i32 %a, i32 %b) {
entry:
  %gt = icmp sgt i32 %a, %b
  br i1 %gt, label %then, label %else
then:
  br label %done
else:
  br label %done
done:
  %r = phi i32 [ %a, %then ], [ %b, %else ]
  ret i32 %r
}
"""

LOOP = """\
define i64 @count(i64 %n) {
entry:
  br label %loop
loop:                                             ; preds = %body, %entry
  %i = phi i64 [ 0, %entry ], [ %i.next, %body ]
  %c = icmp slt i64 %i, %n
  br i1 %c, label %body, label %exit
body:
  %i.next = add i64 %i, 1
  br label %loop
exit:
  ret i64 %i
}
"""


def loaded(ir, name, nargs):
    lib = cputools.ir_to_lib(verified(ir), opt="-O0")
    fn = getattr(lib, name)
    fn.restype = ctypes.c_int64 if name != "imax" and name != "iabs" else ctypes.c_int32
    ty = ctypes.c_int32 if name in ("imax", "iabs") else ctypes.c_int64
    fn.argtypes = [ty] * nargs
    return fn


def need(ir, *words):
    for w in words:
        if w not in ir:
            fail(f"this function should use `{w}`")


@check("build_cfg finds the blocks, successors, and predecessors of an if/else diamond")
def test_cfg_diamond(sub):
    cfg = has(sub, "build_cfg")(DIAMOND)
    equal(list(cfg), ["entry", "then", "else", "done"], label="block labels in order")
    equal(cfg["entry"].succs, ["then", "else"], label="successors of entry")
    equal(cfg["then"].succs, ["done"], label="successors of then")
    equal(cfg["done"].succs, [], label="done ends in ret")
    equal(cfg["entry"].preds, [], label="the entry block has no predecessors")
    equal(cfg["done"].preds, ["then", "else"], label="predecessors of done")
    equal(cfg["then"].preds, ["entry"], label="predecessors of then")


@check("build_cfg handles a loop, where a block is its own ancestor")
def test_cfg_loop(sub):
    cfg = has(sub, "build_cfg")(LOOP)
    equal(list(cfg), ["entry", "loop", "body", "exit"], label="block labels (a comment after a label is ignored)")
    equal(cfg["loop"].succs, ["body", "exit"], label="successors of loop")
    equal(cfg["loop"].preds, ["entry", "body"], label="predecessors of loop")
    equal(cfg["body"].succs, ["loop"], label="the body jumps back to loop")
    equal(cfg["exit"].preds, ["loop"], label="predecessors of exit")


@check("build_cfg is consistent on IR that clang generates: b is in a's succs exactly when a is in b's preds")
def test_cfg_clang(sub):
    build_cfg = has(sub, "build_cfg")
    programs = [
        "int f(int a, int b) { return a > b ? a : b; }",
        "int f(int n) { int s = 0; for (int i = 0; i < n; i++) { if (i % 3 == 0) s += i; } return s; }",
        "int f(int n) { int c = 0; while (n > 1) { n = (n % 2) ? 3 * n + 1 : n / 2; c++; } return c; }",
        "int f(int a, int b) { return (a && b) || (a < 0); }",
    ]
    for src in programs:
        ir = cputools.c_to_ir(src, opt="-O0")
        cfg = build_cfg(ir)
        if len(cfg) < 2:
            fail(f"expected several blocks for {src!r}, got {list(cfg)}")
        for a, block in cfg.items():
            for b in block.succs:
                if b not in cfg:
                    fail(f"block {a} jumps to {b}, which is not a block of the function")
                if a not in cfg[b].preds:
                    fail(f"{a} lists {b} as a successor, but {b} does not list {a} as a predecessor")
            for p in block.preds:
                if b_missing(cfg, p, a):
                    fail(f"{a} lists {p} as a predecessor, but {p} does not jump to {a}")
        # In IR from clang, the entry block is first, has no predecessors, and every `ret` block has no successors.
        equal(list(cfg.values())[0].preds, [], label=f"entry preds for {src!r}")
        rets = [b for b in cfg.values() if not b.succs]
        if not rets:
            fail(f"expected at least one block that ends in ret for {src!r}")


def b_missing(cfg, p, a):
    return p not in cfg or a not in cfg[p].succs


@check("phi_problems accepts correct phis, including the ones mem2reg creates from clang -O0 IR")
def test_phi_ok(sub):
    problems = has(sub, "phi_problems")
    equal(problems(DIAMOND), [], label="diamond")
    equal(problems(LOOP), [], label="loop")
    src = "int f(int n) { int s = 0; for (int i = 0; i < n; i++) { if (i % 3 == 0) s += i; } return s; }"
    ir = cputools.run_opt(cputools.c_to_ir(src, opt="-O0"), "mem2reg")
    if "phi" not in ir:
        fail("expected mem2reg to create phi instructions")
    equal(problems(ir), [], label="phis after mem2reg")


@check("phi_problems reports a phi that misses a predecessor or names a block that is not one")
def test_phi_bad(sub):
    problems = has(sub, "phi_problems")
    missing = DIAMOND.replace("[ %a, %then ], [ %b, %else ]", "[ %a, %then ]")
    got = problems(missing)
    if not got or not any("done" in p and "%r" in p and "else" in p for p in got):
        fail(f"phi %r in block done has no value for else; expected a problem naming the block, the phi, and else, got {got}")
    wrong = LOOP.replace("[ %i.next, %body ]", "[ %i.next, %exit ]")
    got = problems(wrong)
    if not any("loop" in p and "%i" in p and "exit" in p for p in got) or not any("body" in p for p in got):
        fail(f"expected problems about the phi %i in block loop (exit is not a predecessor, body has no value), got {got}")


@check("back_edges finds the edge that closes each loop and none in straight-line branches")
def test_back_edges(sub):
    build_cfg, back_edges = has(sub, "build_cfg"), has(sub, "back_edges")
    equal(back_edges(build_cfg(DIAMOND)), [], label="the diamond has no loop")
    equal(back_edges(build_cfg(LOOP)), [("body", "loop")], label="the loop")
    nested = """\
define void @f(i64 %n) {
entry:
  br label %outer
outer:
  %i = phi i64 [ 0, %entry ], [ %i.next, %outer.latch ]
  %c = icmp slt i64 %i, %n
  br i1 %c, label %inner, label %exit
inner:
  %j = phi i64 [ 0, %outer ], [ %j.next, %inner ]
  %j.next = add i64 %j, 1
  %d = icmp slt i64 %j.next, %n
  br i1 %d, label %inner, label %outer.latch
outer.latch:
  %i.next = add i64 %i, 1
  br label %outer
exit:
  ret void
}
"""
    equal(back_edges(build_cfg(nested)), [("inner", "inner"), ("outer.latch", "outer")], label="nested loops, one a self-loop")


@check("max_ir returns the larger of two signed ints with br and phi")
def test_max(sub):
    ir = has(sub, "max_ir")()
    f = loaded(ir, "imax", 2)
    need(ir, "phi", "br i1")
    cases = [(3, 7), (7, 3), (-5, 2), (-1, -9), (0, 0), (5, 5), (-(2**31), 2**31 - 1), (2**31 - 1, -(2**31)), (-(2**31), -(2**31) + 1)]
    got = in_child(lambda: [f(a, b) for a, b in cases])
    for (a, b), g in zip(cases, got):
        equal(g, max(a, b), label=f"imax({a}, {b})")


@check("abs_ir returns the absolute value, and wraps for the most negative int like C")
def test_abs(sub):
    ir = has(sub, "abs_ir")()
    f = loaded(ir, "iabs", 1)
    need(ir, "phi", "br i1")
    cases = [0, 1, -1, 5, -5, 2**31 - 1, -(2**31) + 1, -(2**31)]
    got = in_child(lambda: [f(x) for x in cases])
    for x, g in zip(cases, got):
        want = -(2**31) if x == -(2**31) else abs(x)  # -(-2**31) wraps back to -2**31
        equal(g, want, label=f"iabs({x})")


@check("sum_to_ir loops with two phis: 1 + 2 + ... + n, and 0 for n <= 0")
def test_sum(sub):
    ir = has(sub, "sum_to_ir")()
    f = loaded(ir, "sum_to", 1)
    need(ir, "phi")
    cases = [0, 1, 4, 10, 100, 100000, -3, -(2**40)]
    got = in_child(lambda: [f(n) for n in cases])
    for n, g in zip(cases, got):
        equal(g, n * (n + 1) // 2 if n > 0 else 0, label=f"sum_to({n})")  # sum_to(4) = 1+2+3+4 = 10
    if ir.count("phi") < 2:
        fail("sum_to_ir needs a phi for the counter and a phi for the running sum")


@check("factorial_ir computes n! for 0..20 and gives 1 for n <= 1")
def test_fact(sub):
    ir = has(sub, "factorial_ir")()
    f = loaded(ir, "fact", 1)
    need(ir, "phi")
    cases = list(range(-2, 21))
    got = in_child(lambda: [f(n) for n in cases])
    for n, g in zip(cases, got):
        equal(g, math.factorial(max(n, 0)), label=f"fact({n})")  # fact(5) = 120; fact(20) = 2432902008176640000


@check("gcd_ir runs Euclid's algorithm on 64-bit values")
def test_gcd(sub):
    ir = has(sub, "gcd_ir")()
    f = loaded(ir, "gcd", 2)
    need(ir, "phi", "srem")
    rng = random.Random(0)
    cases = [(12, 18), (18, 12), (7, 0), (0, 7), (0, 0), (1, 1), (17, 13), (100, 75), (2**40, 2**20 * 3)]
    cases += [(rng.randrange(0, 10**12), rng.randrange(0, 10**12)) for _ in range(40)]
    got = in_child(lambda: [f(a, b) for a, b in cases])
    for (a, b), g in zip(cases, got):
        equal(g, math.gcd(a, b), label=f"gcd({a}, {b})")


@check("your CFG tools agree with your own IR: sum_to has exactly one back edge and consistent phis")
def test_own_ir(sub):
    ir = has(sub, "sum_to_ir")()
    verified(ir)
    cfg = has(sub, "build_cfg")(ir)
    back = has(sub, "back_edges")(cfg)
    if len(back) != 1:
        fail(f"a single loop should give one back edge, got {back} for blocks {list(cfg)}")
    equal(has(sub, "phi_problems")(ir), [], label="phi problems in your sum_to_ir")
