"""Checks for the performance and SIMD exercise."""

import array
import ctypes
import json
import os
import random
import select

import cputools
from cpucheck import check, equal, fail, has, timed

SENTINEL = 0x5A5A5A5A


def _child(fn, seconds=15):
    """Run fn() in a forked child and return its JSON-able result.

    C or assembly written by the reader can crash on a bad address, so compiled
    code runs in a child. The parent reads the answer from a pipe.
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
    os.waitpid(pid, 0)
    if not data:
        fail("your code crashed or never returned when it ran (a bad address, or a loop that does not end)")
    return json.loads(data)


def _wrap(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x & 0x80000000 else x


def _setup(fn):
    fn.restype = None
    fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]
    return fn


def _lengths_and_offsets(lib, lengths, offsets=(0, 1), seed=0):
    """Run add_arrays for each (length, byte offset) and return per-case failures.

    The arrays sit inside bigger buffers so a write past the end or before the
    start shows up as a changed sentinel. Offsets of 0 and 1 elements give a
    pointer that is 16-byte aligned and one that is not.
    """
    fn = _setup(lib.add_arrays)
    rng = random.Random(seed)
    problems = []
    for n in lengths:
        for off in offsets:
            pad = 8
            size = n + 2 * pad + 4
            a = (ctypes.c_int32 * size)(*[rng.randint(-(2**31), 2**31 - 1) for _ in range(size)])
            b = (ctypes.c_int32 * size)(*[rng.randint(-(2**31), 2**31 - 1) for _ in range(size)])
            d = (ctypes.c_int32 * size)(*([SENTINEL] * size))
            base = ctypes.sizeof(ctypes.c_int32) * (pad + off)
            fn(ctypes.addressof(d) + base, ctypes.addressof(a) + base, ctypes.addressof(b) + base, n)
            want = [SENTINEL] * size
            for i in range(n):
                want[pad + off + i] = _wrap(a[pad + off + i] + b[pad + off + i])
            if list(d) != want:
                bad = next(i for i in range(size) if d[i] != want[i])
                where = bad - (pad + off)
                problems.append(f"n={n}, offset {off}: element {where} is {d[bad]}, expected {want[bad]}")
    return problems


@check("vector_width reads packed arithmetic and ignores moves, scalar math, and comments")
def test_width(sub):
    width = has(sub, "vector_width")
    equal(width("mov eax, 1\nadd eax, ebx\nret"), 0, label="scalar integer code")
    equal(width("paddd xmm0, xmm1"), 128, label="paddd xmm")
    equal(width("    vpaddd ymm0, ymm1, ymm2   # eight at once"), 256, label="vpaddd ymm")
    equal(width("vaddps zmm0, zmm1, zmm2"), 512, label="vaddps zmm")
    equal(width("mulpd xmm0, xmm1"), 128, label="mulpd")
    equal(width("psubq xmm3, xmm4\nvpmulld ymm0, ymm0, ymm1"), 256, label="the widest line wins")
    equal(width("addss xmm0, xmm1\naddsd xmm0, xmm1"), 0, label="scalar float math is not packed")
    equal(width("movdqu xmm0, xmmword ptr [rdi]\npxor xmm0, xmm0"), 0, label="moves and pxor are not arithmetic")
    equal(width("# paddd xmm0, xmm1\n  mov eax, 1  ; paddd xmm0, xmm1"), 0, label="comments do not count")
    equal(width(".LBB0_3:\n    .p2align 4\n    jne .LBB0_3"), 0, label="labels and directives")


@check("add_arrays_c compiles at -O0, -O2, and -O3 -mavx2 and is correct for many lengths")
def test_c_correct(sub):
    src = has(sub, "add_arrays_c")()
    cfgs = [("-O0", ()), ("-O2", ()), ("-O3", ("-mavx2",))]
    libs = [(opt, cputools.compile_c(src, opt=opt, flags=fl), fl) for opt, fl in cfgs]
    avx2 = _has_avx2()
    for opt, lib, fl in libs:
        if fl and not avx2:
            continue  # a CPU without AVX2 would fault on these instructions
        problems = _child(lambda lib=lib: _lengths_and_offsets(lib, [0, 1, 3, 4, 7, 8, 31, 100]))
        if problems:
            fail(f"{opt} {' '.join(fl)}: " + "; ".join(problems[:3]))
    lib = libs[1][1]
    if not _child(lambda: _lengths_and_offsets(lib, [0])) == []:
        fail("n = 0 must write nothing")


def _has_avx2():
    try:
        with open("/proc/cpuinfo") as f:
            return any("avx2" in line.split() for line in f if line.startswith("flags"))
    except OSError:
        return False


@check("asm_variants: -O0 has no vector arithmetic; -O2 uses 128-bit xmm; -O3 -mavx2 uses 256-bit ymm (clang 19)")
def test_variants_asm(sub):
    src = has(sub, "add_arrays_c")()
    width = has(sub, "vector_width")
    asm = has(sub, "asm_variants")(src)
    equal(sorted(asm), ["O0", "O2", "O3_avx2"], label="keys")
    equal(width(asm["O0"]), 0, label="vector width of -O0 code")
    equal(width(asm["O2"]), 128, label="vector width of -O2 code (SSE2 is the x86-64 baseline)")
    equal(width(asm["O3_avx2"]), 256, label="vector width of -O3 -mavx2 code")
    if "paddd" not in asm["O2"]:
        fail("the -O2 assembly should contain `paddd`, four 32-bit adds in one instruction")
    if "vpaddd" not in asm["O3_avx2"]:
        fail("the -O3 -mavx2 assembly should contain `vpaddd`")


@check("compile_variants returns three working libraries, and time_variants reports positive seconds")
def test_variants_run(sub):
    src = has(sub, "add_arrays_c")()
    libs = has(sub, "compile_variants")(src)
    equal(sorted(libs), ["O0", "O2", "O3_avx2"], label="keys")
    avx2 = _has_avx2()

    def run():
        out = {}
        for name, lib in libs.items():
            if name == "O3_avx2" and not avx2:
                continue
            fn = _setup(lib.add_arrays)
            a = (ctypes.c_int32 * 5)(1, 2, 3, 4, 5)
            b = (ctypes.c_int32 * 5)(10, 20, 30, 40, 50)
            d = (ctypes.c_int32 * 5)()
            fn(d, a, b, 5)
            out[name] = list(d)
        return out

    got = _child(run)
    for name, values in got.items():
        equal(values, [11, 22, 33, 44, 55], label=f"{name}: add_arrays on [1..5] + [10..50]")
    with timed("time_variants, 1,000,000 elements"):
        secs = _child(lambda: has(sub, "time_variants")(libs, 1_000_000, 2))
    for name, s in secs.items():
        if not (isinstance(s, float) and s > 0):
            fail(f"time_variants[{name!r}] should be a positive float of seconds, got {s!r}")
    equal(sorted(secs), sorted(libs) if avx2 else ["O0", "O2"], label="variants timed")


@check("sse2_add_asm is correct for lengths 0 to 17 (not only multiples of 4) and for unaligned pointers")
def test_asm_lengths(sub):
    lib = cputools.assemble(has(sub, "sse2_add_asm")())
    problems = _child(lambda: _lengths_and_offsets(lib, list(range(0, 18)), offsets=(0, 1, 3)))
    if problems:
        fail("; ".join(problems[:4]) + (f" ... and {len(problems) - 4} more" if len(problems) > 4 else ""))


@check("sse2_add_asm is correct on long arrays, wraps on overflow, and works in place (dst is a)")
def test_asm_long(sub):
    lib = cputools.assemble(has(sub, "sse2_add_asm")())

    def run():
        problems = _lengths_and_offsets(lib, [100, 1001, 4096], offsets=(0, 1))
        fn = _setup(lib.add_arrays)
        n = 37
        a = (ctypes.c_int32 * n)(*range(n))
        b = (ctypes.c_int32 * n)(*([2**31 - 1] * n))
        fn(a, a, b, n)  # in place: a[i] = a[i] + b[i], which wraps
        want = [_wrap(i + 2**31 - 1) for i in range(n)]
        if list(a) != want:
            problems.append("in-place call (dst is a) gave a wrong result")
        return problems

    problems = _child(run)
    if problems:
        fail("; ".join(problems[:3]))


@check("sse2_add_asm really uses a packed instruction: paddd on an xmm register (checked in your assembly text)")
def test_asm_text(sub):
    asm = has(sub, "sse2_add_asm")()
    if "paddd" not in asm.lower():
        fail("your assembly never uses `paddd`, the instruction that adds four 32-bit integers at once")
    if "xmm" not in asm.lower():
        fail("your assembly never names an xmm register")
    width = has(sub, "vector_width")(asm)
    equal(width, 128, label="vector_width of your own assembly")


@check("timing report: O0, O2, -O3 -mavx2, and your SSE2 loop on 2,000,000 elements (reported, never compared)")
def test_report(sub):
    src = has(sub, "add_arrays_c")()
    libs = has(sub, "compile_variants")(src)
    libs["sse2"] = cputools.assemble(has(sub, "sse2_add_asm")())
    avx2 = _has_avx2()
    n = 2_000_000
    arr = ctypes.c_int32 * n
    a = arr.from_buffer_copy(array.array("i", range(n)))
    b = arr.from_buffer_copy(array.array("i", range(n)))
    dst = arr()
    for name, lib in libs.items():
        if name == "O3_avx2" and not avx2:
            continue
        fn = _setup(lib.add_arrays)

        def verify():
            fn(dst, a, b, n)
            return [dst[0], dst[1], dst[n // 2], dst[n - 1]]

        # The same call, in a child first: if it is going to crash, the child dies and the run survives.
        got = _child(verify)
        equal(got, [0, 2, 2 * (n // 2), 2 * (n - 1)], label=f"{name}: spot checks on the large array")
        with timed(f"{name}: one call, {n:,} elements"):
            fn(dst, a, b, n)
