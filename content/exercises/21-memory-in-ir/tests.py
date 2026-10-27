"""Checks for the memory-in-IR exercise."""

import ctypes
import json
import os
import select

import cputools
from cpucheck import check, equal, fail, has


def _child(fn, seconds=10):
    """Run fn() in a forked child and return its JSON-able result.

    Reader IR can crash when it reads or writes the wrong address, and a crash
    in this process would end the whole run, so the compiled code runs in a child.
    """
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        code = 1
        try:
            os.close(r)
            os.write(w, json.dumps(fn()).encode())
            code = 0
        except BaseException:
            pass
        finally:
            os._exit(code)
    os.close(w)
    data = b""
    ready, _, _ = select.select([r], [], [], seconds)
    if ready:
        while True:
            chunk = os.read(r, 65536)
            if not chunk:
                break
            data += chunk
    else:
        os.kill(pid, 9)
    os.close(r)
    _, status = os.waitpid(pid, 0)
    if not data:
        fail("your IR crashed or timed out when it ran (a wrong address, or a loop that never ends)")
    return json.loads(data)


SAMPLE = """\
define i32 @f(i32 %x) {
entry:
  %x.addr = alloca i32, align 4
  store i32 %x, ptr %x.addr, align 4
  %0 = load i32, ptr %x.addr, align 4
  %add = add nsw i32 %0, 1
  ; a comment line
  ret i32 %add
}
"""


@check("count_opcodes counts instructions by opcode inside function bodies")
def test_count(sub):
    count = has(sub, "count_opcodes")
    equal(count(SAMPLE), {"alloca": 1, "store": 1, "load": 1, "add": 1, "ret": 1})
    ir = "declare i32 @puts(ptr)\n" + SAMPLE + "\ndefine void @g() {\nloop:\n  %c = tail call i32 @puts(ptr null)\n  br label %loop\n}\n"
    got = count(ir)
    equal(got.get("call"), 1, label="a `tail call` counts as call")
    equal(got.get("br"), 1, label="br")
    equal(got.get("loop:"), None, label="labels are not instructions")
    equal(got.get("declare"), None, label="declarations are not instructions")


@check("mem2reg_report: -O0 code is full of alloca/load/store, and mem2reg removes all of them")
def test_report_straight(sub):
    rep = has(sub, "mem2reg_report")("int f(int x) { int y = x + 1; return y * 2; }")
    equal(sorted(rep["before"]), ["alloca", "load", "phi", "store"], label="keys of before")
    # x.addr and y are the two allocas; each is stored once and loaded once.
    equal(rep["before"], {"alloca": 2, "load": 2, "store": 2, "phi": 0}, label="before")
    equal(rep["after"], {"alloca": 0, "load": 0, "store": 0, "phi": 0}, label="after")


@check("mem2reg_report: a loop's variables become phi nodes")
def test_report_loop(sub):
    src = "int sum(int *a, int n) { int s = 0; for (int i = 0; i < n; i++) s += a[i]; return s; }"
    rep = has(sub, "mem2reg_report")(src)
    b, a = rep["before"], rep["after"]
    if not (b["alloca"] >= 4 and b["store"] >= b["alloca"]):
        fail(f"expected at least 4 allocas in the -O0 IR (a, n, s, i), got {b}")
    equal(a["alloca"], 0, label="allocas after mem2reg")
    equal(a["store"], 0, label="stores after mem2reg")
    # s and i each need a phi at the loop header.
    if a["phi"] < 2:
        fail(f"expected at least 2 phi nodes (s and i) after mem2reg, got {a}")
    # The load of a[i] stays: it reads the caller's array, not a local variable.
    equal(a["load"], 1, label="loads after mem2reg (only a[i] remains)")


@check("swap_ir swaps two ints through pointers")
def test_swap(sub):
    ir = has(sub, "swap_ir")()
    cputools.verify_ir(ir)
    lib = cputools.ir_to_lib(ir, opt="-O0")
    lib.swap.restype = None
    lib.swap.argtypes = [ctypes.POINTER(ctypes.c_int32)] * 2

    def run():
        out = []
        for x, y in [(3, 9), (-1, 5), (0, 0), (2**31 - 1, -(2**31))]:
            a, b = ctypes.c_int32(x), ctypes.c_int32(y)
            lib.swap(ctypes.byref(a), ctypes.byref(b))
            out.append([a.value, b.value])
        return out

    equal(_child(run), [[9, 3], [5, -1], [0, 0], [-(2**31), 2**31 - 1]])


def _array_sum_run(lib):
    lib.sum_array.restype = ctypes.c_int32
    lib.sum_array.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.c_int32]
    out = []
    for values in ([], [7], [1, 2, 3, 4], list(range(100)), [-5, 5, -7, 100, 2**30]):
        arr = (ctypes.c_int32 * max(len(values), 1))(*values)
        out.append(lib.sum_array(arr, len(values)))
    arr = (ctypes.c_int32 * 1)(5)
    out.append(lib.sum_array(arr, 0))
    out.append(lib.sum_array(arr, -3))
    return out


@check("sum_array_ir sums an int array passed from Python (0 for n <= 0)")
def test_sum_array(sub):
    ir = has(sub, "sum_array_ir")()
    cputools.verify_ir(ir)
    lib = cputools.ir_to_lib(ir, opt="-O1")
    # 0+1+...+99 = 4950; -5+5-7+100+2^30 = 1073741917
    equal(_child(lambda: _array_sum_run(lib)), [0, 7, 10, 4950, 1073741917, 0, 0])


@check("sum_array_ir uses getelementptr to reach elements (checked in your IR text)")
def test_sum_gep(sub):
    ir = has(sub, "sum_array_ir")()
    if "getelementptr" not in ir:
        fail("sum_array_ir never uses `getelementptr`; it is how IR computes the address of a[i]")


class _Point(ctypes.Structure):
    # C layout of struct { int a; long b; }: a at byte 0, 4 bytes of padding, b at byte 8.
    _fields_ = [("a", ctypes.c_int32), ("b", ctypes.c_int64)]


@check("get_b_ir reads field b of a { i32, i64 } struct and set_a writes field a")
def test_struct(sub):
    ir = has(sub, "get_b_ir")()
    cputools.verify_ir(ir)
    lib = cputools.ir_to_lib(ir, opt="-O1")
    lib.get_b.restype = ctypes.c_int64
    lib.get_b.argtypes = [ctypes.POINTER(_Point)]
    lib.set_a.restype = None
    lib.set_a.argtypes = [ctypes.POINTER(_Point), ctypes.c_int32]

    def run():
        out = []
        for a, b in [(5, 70), (-1, -(2**40)), (0, 2**62)]:
            p = _Point(a, b)
            out.append(lib.get_b(ctypes.byref(p)))
            lib.set_a(ctypes.byref(p), 123)
            out.append([p.a, p.b])
        return out

    equal(
        _child(run),
        [70, [123, 70], -(2**40), [123, -(2**40)], 2**62, [123, 2**62]],
    )
    equal(_Point.b.offset, 8, label="sanity: C puts b at byte offset 8")


@check("local_sum_ir keeps its variables in allocas (no phi) and computes 1 + ... + n")
def test_local_sum(sub):
    ir = has(sub, "local_sum_ir")()
    cputools.verify_ir(ir)
    count = has(sub, "count_opcodes")
    ops = count(ir)
    if ops.get("alloca", 0) < 2:
        fail(f"expected at least 2 `alloca` instructions (the total and the counter), found {ops.get('alloca', 0)}")
    equal(ops.get("phi", 0), 0, label="phi nodes in your IR")
    lib = cputools.ir_to_lib(ir, opt="-O0")
    lib.local_sum.restype = ctypes.c_int32
    lib.local_sum.argtypes = [ctypes.c_int32]

    def run():
        return [lib.local_sum(n) for n in (-4, 0, 1, 10, 100)]

    # n(n+1)/2: 55 for 10, 5050 for 100
    equal(_child(run), [0, 0, 1, 55, 5050])


@check("mem2reg removes every alloca from local_sum_ir and the answers stay the same")
def test_local_sum_mem2reg(sub):
    ir = has(sub, "local_sum_ir")()
    count = has(sub, "count_opcodes")
    after = cputools.run_opt(ir, "mem2reg")
    got = count(after)
    equal(got.get("alloca", 0), 0, label="allocas after mem2reg")
    equal(got.get("store", 0), 0, label="stores after mem2reg")
    if got.get("phi", 0) < 2:
        fail(f"expected at least 2 phi nodes after mem2reg, got {got}")
    lib = cputools.ir_to_lib(after, opt="-O0")
    lib.local_sum.restype = ctypes.c_int32
    lib.local_sum.argtypes = [ctypes.c_int32]
    equal(_child(lambda: [lib.local_sum(n) for n in (-4, 0, 1, 10, 100)]), [0, 0, 1, 55, 5050])
