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
    """C source for `void add_arrays(int *dst, const int *a, const int *b, long n)`."""
    return """
void add_arrays(int *dst, const int *a, const int *b, long n) {
    for (long i = 0; i < n; i++)
        dst[i] = a[i] + b[i];
}
"""


_PACKED = re.compile(r"v?(?:p(?:add|sub|mul)\w*|(?:add|sub|mul|div)p[sd])")
_WIDTH = {"xmm": 128, "ymm": 256, "zmm": 512}


def vector_width(asm: str) -> int:
    """The widest packed-arithmetic register in assembly text: 0, 128, 256, or 512."""
    widest = 0
    for line in asm.splitlines():
        line = re.split(r"[#;]", line, maxsplit=1)[0].strip()
        if not line or line.startswith("."):
            continue
        parts = line.split(None, 1)
        mnemonic, operands = parts[0], (parts[1] if len(parts) > 1 else "")
        if not _PACKED.fullmatch(mnemonic):
            continue
        for reg in re.findall(r"\b([xyz]mm)\d+", operands):
            widest = max(widest, _WIDTH[reg])
    return widest


def asm_variants(c_source: str) -> dict[str, str]:
    """The assembly clang writes for `c_source` under each setting in VARIANTS."""
    return {
        name: cputools.c_to_asm(c_source, opt=cfg["opt"], flags=cfg["flags"])
        for name, cfg in VARIANTS.items()
    }


def compile_variants(c_source: str) -> dict[str, "ctypes.CDLL"]:
    """The same source compiled and loaded under each setting in VARIANTS."""
    return {
        name: cputools.compile_c(c_source, opt=cfg["opt"], flags=cfg["flags"])
        for name, cfg in VARIANTS.items()
    }


def sse2_add_asm() -> str:
    """x86-64 Intel assembly for add_arrays, four int32 at a time with paddd."""
    return """
    .globl add_arrays
add_arrays:                      # rdi = dst, rsi = a, rdx = b, rcx = n
    xor eax, eax                 # i = 0
.Lvector:
    lea r8, [rax + 4]            # r8 = i + 4
    cmp r8, rcx
    jg .Ltail                    # fewer than 4 elements left
    movdqu xmm0, [rsi + rax*4]   # a[i..i+3]
    movdqu xmm1, [rdx + rax*4]   # b[i..i+3]
    paddd xmm0, xmm1             # four 32-bit adds in one instruction
    movdqu [rdi + rax*4], xmm0   # dst[i..i+3]
    mov rax, r8                  # i += 4
    jmp .Lvector
.Ltail:
    cmp rax, rcx
    jge .Ldone                   # signed compare: n <= 0 skips everything
    mov r9d, [rsi + rax*4]
    add r9d, [rdx + rax*4]
    mov [rdi + rax*4], r9d
    inc rax
    jmp .Ltail
.Ldone:
    ret
"""


def time_variants(libs: dict, n: int = 1_000_000, repeats: int = 3) -> dict[str, float]:
    """Seconds for one add_arrays call on n elements, best of `repeats`, per variant."""
    arr = ctypes.c_int32 * n
    a, b, dst = arr(*range(n)), arr(*range(n)), arr()
    result = {}
    for name, lib in libs.items():
        if name == "O3_avx2" and not cpu_has_avx2():
            continue
        fn = lib.add_arrays
        fn.restype = None
        fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]
        best = float("inf")
        for _ in range(repeats):
            start = time.perf_counter()
            fn(dst, a, b, n)
            best = min(best, time.perf_counter() - start)
        result[name] = best
    return result


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
