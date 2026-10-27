"""Checks for the C exercise."""

import ctypes
import itertools
import json
import os
import random
import select
import signal
import time

import cputools
from cpucheck import check, equal, fail, has

INT_MIN, INT_MAX = -(1 << 31), (1 << 31) - 1
PTR = ctypes.c_void_p

# type name -> (size, alignment) on x86-64 Linux. The tests keep their own copy.
SA = {"char": (1, 1), "short": (2, 2), "int": (4, 4), "float": (4, 4),
      "long": (8, 8), "double": (8, 8), "void*": (8, 8)}


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
    return cputools.compile_c(text_fn())


def _ref_layout(types):
    pos, top = 0, 1
    offsets = []
    for t in types:
        size, align = SA[t]
        pos = -(-pos // align) * align
        offsets.append(pos)
        pos += size
        top = max(top, align)
    return {"offsets": offsets, "size": -(-pos // top) * top, "align": top}


def _real_layouts(all_types):
    """Ask clang, in one compile, for sizeof, _Alignof, and offsetof of structs with these fields."""
    parts = ["#include <stddef.h>"]
    for k, types in enumerate(all_types):
        fields = "\n".join(f"    {t} f{i};" for i, t in enumerate(types))
        offs = ", ".join(f"offsetof(struct S{k}, f{i})" for i in range(len(types)))
        parts.append(f"""
struct S{k} {{
{fields}
}};
unsigned long size_of{k}(void) {{ return sizeof(struct S{k}); }}
unsigned long align_of{k}(void) {{ return _Alignof(struct S{k}); }}
unsigned long offset_of{k}(int i) {{
    static const unsigned long table[] = {{ {offs} }};
    return table[i];
}}
""")
    lib = cputools.compile_c("\n".join(parts), opt="-O0")
    out = []
    for k, types in enumerate(all_types):
        for name in (f"size_of{k}", f"align_of{k}", f"offset_of{k}"):
            getattr(lib, name).restype = ctypes.c_ulong
        getattr(lib, f"offset_of{k}").argtypes = [ctypes.c_int]
        out.append({"offsets": [getattr(lib, f"offset_of{k}")(i) for i in range(len(types))],
                    "size": getattr(lib, f"size_of{k}")(), "align": getattr(lib, f"align_of{k}")()})
    return out


STRUCTS = [
    ["char", "int", "char"],
    ["char", "short", "int", "long"],
    ["int", "char", "double", "char"],
    ["char", "char", "char"],
    ["double"],
    ["short", "char", "float", "void*", "char"],
    ["char", "long", "char"],
    ["long", "int", "short", "char"],
]


@check("sum_ptr_c: sum_ptr(begin, end) adds the longs from begin up to end, walking a pointer")
def test_sum_ptr(sub):
    text = has(sub, "sum_ptr_c")()
    if "[" in text:
        fail("this check wants pointer arithmetic, with no `[ ]` indexing. Walk a pointer from `begin` up to `end`.")
    lib = cputools.compile_c(text)
    lib.sum_ptr.argtypes = [PTR, PTR]
    lib.sum_ptr.restype = ctypes.c_int64
    rng = random.Random(0)
    cases = [[], [5], [1, 2, 3], [-4, 4, -4], [1 << 40, 1 << 40], [rng.randint(-1000, 1000) for _ in range(100)]]

    def call(values):
        arr = (ctypes.c_int64 * max(len(values), 1))(*values)
        base = ctypes.addressof(arr)
        return int(lib.sum_ptr(base, base + 8 * len(values)))

    got = safe_cases(cases, call, describe=lambda v: f"sum_ptr over {v[:6]}")
    for values, g in zip(cases, got):
        equal(g, sum(values), label=f"sum_ptr over {len(values)} values {values[:6]}")


@check("swap_c: swap(&x, &y) exchanges two ints, and swap(&x, &x) changes nothing")
def test_swap(sub):
    lib = _lib(has(sub, "swap_c"))
    lib.swap.argtypes = [PTR, PTR]
    lib.swap.restype = None
    cases = [(1, 2), (-5, 9), (0, 0), (INT_MIN, INT_MAX), (7, 7)]

    def call(pair):
        x, y = ctypes.c_int32(pair[0]), ctypes.c_int32(pair[1])
        lib.swap(ctypes.addressof(x), ctypes.addressof(y))
        z = ctypes.c_int32(pair[0])
        lib.swap(ctypes.addressof(z), ctypes.addressof(z))
        return [x.value, y.value, z.value]

    got = safe_cases(cases, call, describe=lambda p: f"swap on {p}")
    for (a, b), g in zip(cases, got):
        # The same-pointer call is the trap: an XOR swap would turn x into 0.
        equal(g, [b, a, a], label=f"swap(&x, &y) then swap(&z, &z) with x={a}, y={b}, z={a}: [x, y, z]")


@check("array_vs_pointer_c: a local int[10] is 40 bytes, but a parameter int a[10] is a pointer of 8")
def test_array_vs_pointer(sub):
    lib = _lib(has(sub, "array_vs_pointer_c"))
    for name in ("local_array_size", "param_size"):
        fn = getattr(lib, name, None)
        if fn is None:
            fail(f"your C source defines no function `{name}`")
        fn.restype = ctypes.c_long
    lib.param_size.argtypes = [PTR]
    got = safe_cases([0], lambda _: [int(lib.local_array_size()), int(lib.param_size(None))])[0]
    # 10 ints * 4 bytes = 40. The parameter decays to an int *, 8 bytes on x86-64.
    equal(got, [40, 8], label="[local_array_size(), param_size(...)]")


@check("struct_layout: field offsets, size, and alignment match what clang reports")
def test_struct_layout(sub):
    layout = has(sub, "struct_layout")
    # Hand check for the first one: char at 0, int at 4, char at 8, size 12.
    wants = _real_layouts(STRUCTS)
    for types, want in zip(STRUCTS, wants):
        equal(layout(list(types)), want, label=f"struct_layout({types})")


@check("struct_layout: padding after the last field rounds the size up to the alignment")
def test_struct_tail(sub):
    layout = has(sub, "struct_layout")
    # char, long: offsets 0 and 8, size 16. long, char: offsets 0 and 8, size 16, not 9.
    equal(layout(["long", "char"])["size"], 16, label="size of {long, char}")
    equal(layout(["double", "char", "char"])["size"], 16, label="size of {double, char, char}")
    equal(layout(["char"]), {"offsets": [0], "size": 1, "align": 1}, label="struct_layout(['char'])")


@check("best_order: the reordered struct has the smallest size over every ordering")
def test_best_order(sub):
    best = has(sub, "best_order")
    small = [t for t in STRUCTS if len(t) <= 6]
    orders = []
    for types in small:
        order = best(list(types))
        if sorted(order) != sorted(types):
            fail(f"best_order({types}) returned {order}, which is not a reordering of the same fields")
        orders.append(order)
    for types, order, real in zip(small, orders, _real_layouts(orders)):
        want = min(_ref_layout(list(p))["size"] for p in itertools.permutations(types))
        equal(real["size"], want, label=f"clang's sizeof for the order best_order({types}) gave, {order}")


@check("wrap_add_c: wrap_add(a, b) wraps at 32 bits using unsigned arithmetic")
def test_wrap_add(sub):
    text = has(sub, "wrap_add_c")()
    if "unsigned" not in text:
        fail("signed overflow is undefined behaviour. This check wants the addition done on `unsigned` values.")
    lib = cputools.compile_c(text, opt="-O2")
    lib.wrap_add.argtypes = [ctypes.c_int32, ctypes.c_int32]
    lib.wrap_add.restype = ctypes.c_int32
    cases = [(1, 2), (-1, 1), (INT_MAX, 1), (INT_MIN, -1), (INT_MAX, INT_MAX), (INT_MIN, INT_MIN), (123456789, 987654321)]

    def wrap(x):
        x &= 0xFFFFFFFF
        return x - (1 << 32) if x >> 31 else x

    got = safe_cases(cases, lambda c: int(lib.wrap_add(*c)), describe=lambda c: f"wrap_add{c}")
    for case, g in zip(cases, got):
        # INT_MAX + 1 wraps to INT_MIN.
        equal(g, wrap(case[0] + case[1]), label=f"wrap_add{case}")


@check("safe_div_c: safe_div rejects b == 0 and INT_MIN / -1, and truncates toward zero otherwise")
def test_safe_div(sub):
    lib = _lib(has(sub, "safe_div_c"))
    lib.safe_div.argtypes = [ctypes.c_int32, ctypes.c_int32, PTR]
    lib.safe_div.restype = ctypes.c_int
    cases = [(7, 2), (-7, 2), (7, -2), (-7, -2), (0, 5), (5, 0), (INT_MIN, -1), (INT_MIN, 1), (INT_MAX, -1), (6, 3)]

    def call(c):
        out = ctypes.c_int32(12345)
        ok = lib.safe_div(c[0], c[1], ctypes.addressof(out))
        return [int(ok), out.value]

    def ref(a, b):
        if b == 0 or (a == INT_MIN and b == -1):
            return [0, 12345]
        q = abs(a) // abs(b)
        return [1, q if (a < 0) == (b < 0) else -q]

    got = safe_cases(cases, call, describe=lambda c: f"safe_div{c}")
    for case, g in zip(cases, got):
        # [return value, *out]; *out stays 12345 when the division is refused. -7 / 2 is -3.
        equal(g, ref(*case), label=f"safe_div{case}: [result, *out]")
