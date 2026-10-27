"""Performance and SIMD: measure C at several optimization levels, find vector
instructions in the assembly, and write a SIMD loop by hand."""

import ctypes
import re
import time

import cputools

# ---------------------------------------------------------------------------
# Provided helpers (the same in the solution).
# ---------------------------------------------------------------------------

VARIANTS = {
    "O0": {"opt": "-O0", "flags": ()},
    "O2": {"opt": "-O2", "flags": ()},
    "O3_avx2": {"opt": "-O3", "flags": ("-mavx2",)},  # explicit flags, not -march=native
}


def cpu_has_avx2() -> bool:
    """True when this machine's CPU can run AVX2 instructions (Linux: /proc/cpuinfo)."""
    try:
        with open("/proc/cpuinfo") as f:
            return any("avx2" in line.split() for line in f if line.startswith("flags"))
    except OSError:
        return False


def call_add(lib, a: list[int], b: list[int]) -> list[int]:
    """Call `lib.add_arrays(dst, a, b, n)` on Python lists and return dst as a list."""
    n = len(a)
    arr = ctypes.c_int32 * max(n, 1)
    pa, pb, dst = arr(*a), arr(*b), arr()
    fn = lib.add_arrays
    fn.restype = None
    fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]
    fn(dst, pa, pb, n)
    return list(dst)[:n]


# ---------------------------------------------------------------------------
# What you write
# ---------------------------------------------------------------------------


def add_arrays_c() -> str:
    """C source for `void add_arrays(int *dst, const int *a, const int *b, long n)`.

    It sets dst[i] = a[i] + b[i] for i from 0 to n - 1 with a plain loop, and
    does nothing when n <= 0. Int overflow wraps in practice on x86-64.
    """
    raise NotImplementedError


def vector_width(asm: str) -> int:
    """The widest packed-arithmetic register in assembly text: 0, 128, 256, or 512.

    A line counts when its mnemonic (first word, ignoring `#` and `;` comments)
    is packed integer arithmetic such as paddd, psubq, pmulld, vpaddd, or packed
    floating-point arithmetic such as addps, mulpd, vaddps, and the line names
    an xmm (128), ymm (256), or zmm (512) register. Moves (movdqu), scalar
    float ops (addss, addsd), and zeroing (pxor) do not count.

    vector_width("paddd xmm0, xmm1") is 128.
    vector_width("vpaddd ymm0, ymm1, ymm2") is 256.
    vector_width("addss xmm0, xmm1") is 0.
    """
    raise NotImplementedError


def asm_variants(c_source: str) -> dict[str, str]:
    """The assembly clang writes for `c_source` under each setting in VARIANTS.

    Returns {"O0": asm, "O2": asm, "O3_avx2": asm}, using cputools.c_to_asm with
    each setting's `opt` and `flags`.
    """
    raise NotImplementedError


def compile_variants(c_source: str) -> dict[str, "ctypes.CDLL"]:
    """The same source compiled and loaded under each setting in VARIANTS.

    Returns {"O0": lib, "O2": lib, "O3_avx2": lib}, using cputools.compile_c.
    The "O3_avx2" library holds AVX2 instructions: only call it when
    cpu_has_avx2() is True.
    """
    raise NotImplementedError


def sse2_add_asm() -> str:
    """x86-64 Intel assembly for `void add_arrays(int *dst, const int *a, const int *b, long n)`.

    Define a global function `add_arrays`. dst arrives in rdi, a in rsi, b in
    rdx, and n (64 bits) in rcx. Add four int32 at a time with `movdqu` and
    `paddd` while four or more elements remain, then finish the 0 to 3 leftover
    elements one at a time. It must work for any n >= 0 and any alignment, and
    also when dst is the same array as a.
    """
    raise NotImplementedError


def time_variants(libs: dict, n: int = 1_000_000, repeats: int = 3) -> dict[str, float]:
    """Seconds for one add_arrays call on n elements, best of `repeats`, per variant.

    Use time.perf_counter around the call. Skip "O3_avx2" when cpu_has_avx2()
    is False. This only measures: nothing in the course compares the numbers.
    """
    raise NotImplementedError


if __name__ == "__main__":
    src = add_arrays_c()
    asm = asm_variants(src)
    libs = compile_variants(src)
    for name in VARIANTS:
        print(f"{name:8} vector width {vector_width(asm[name])}")
    print("sample:", call_add(libs["O2"], [1, 2, 3, 4, 5], [10, 20, 30, 40, 50]))
    mine = cputools.assemble(sse2_add_asm())
    print("SSE2:  ", call_add(mine, [1, 2, 3, 4, 5], [10, 20, 30, 40, 50]))
    for name, seconds in time_variants(libs, n=200_000).items():
        print(f"{name:8} {seconds * 1000:7.3f} ms per call")
