"""Checks for the integers, two's complement, and overflow exercise."""

import ctypes
import random

import cputools
from cpucheck import check, equal, fail, has


@check("to_unsigned wraps any int into 0 .. 2**bits - 1")
def test_to_unsigned(sub):
    to_unsigned = has(sub, "to_unsigned")
    equal(to_unsigned(-1, 8), 255, label="to_unsigned(-1, 8)")
    equal(to_unsigned(256, 8), 0, label="to_unsigned(256, 8)")
    equal(to_unsigned(300, 8), 44, label="to_unsigned(300, 8)")  # 300 - 256
    equal(to_unsigned(-129, 8), 127, label="to_unsigned(-129, 8)")  # -129 + 256
    equal(to_unsigned(-1, 32), 0xFFFFFFFF, label="to_unsigned(-1, 32)")
    equal(to_unsigned(2**64 + 5, 64), 5, label="to_unsigned(2**64 + 5, 64)")
    equal(to_unsigned(7, 4), 7, label="to_unsigned(7, 4)")


@check("to_signed reads a pattern as two's complement")
def test_to_signed(sub):
    to_signed = has(sub, "to_signed")
    equal(to_signed(0xFF, 8), -1, label="to_signed(0xFF, 8)")
    equal(to_signed(0x7F, 8), 127, label="to_signed(0x7F, 8)")
    equal(to_signed(0x80, 8), -128, label="to_signed(0x80, 8)")
    equal(to_signed(0, 8), 0, label="to_signed(0, 8)")
    equal(to_signed(200, 8), -56, label="to_signed(200, 8)")  # 200 - 256
    equal(to_signed(0xFFFFFFFF, 32), -1, label="to_signed(0xFFFFFFFF, 32)")
    equal(to_signed(0x80000000, 32), -(2**31), label="to_signed(0x80000000, 32)")
    equal(to_signed(-3, 8), -3, label="to_signed(-3, 8) already fits")
    equal(to_signed(0b1000, 4), -8, label="to_signed(0b1000, 4)")


@check("int_range gives the smallest and largest value for a width")
def test_int_range(sub):
    int_range = has(sub, "int_range")
    equal(int_range(8, True), (-128, 127), label="int_range(8, True)")
    equal(int_range(8, False), (0, 255), label="int_range(8, False)")
    equal(int_range(32, True), (-(2**31), 2**31 - 1), label="int_range(32, True)")
    equal(int_range(64, False), (0, 2**64 - 1), label="int_range(64, False)")
    equal(int_range(1, True), (-1, 0), label="int_range(1, True)")


@check("negate flips every bit and adds one")
def test_negate(sub):
    negate = has(sub, "negate")
    equal(negate(1, 8), 255, label="negate(1, 8)")
    equal(negate(0, 8), 0, label="negate(0, 8)")
    equal(negate(5, 8), 0b11111011, label="negate(5, 8)")  # ~00000101 = 11111010, + 1
    equal(negate(128, 8), 128, label="negate(128, 8): the most negative number is its own negative")
    for bits in (4, 8, 16):
        for pattern in range(0, 1 << bits, 1 if bits < 16 else 97):
            equal(negate(pattern, bits), (-pattern) % (1 << bits), label=f"negate({pattern}, {bits})")


@check("add_overflows reports unsigned and signed overflow separately")
def test_add_overflows(sub):
    add_overflows = has(sub, "add_overflows")
    equal(tuple(add_overflows(200, 100, 8)), (True, False), label="add_overflows(200, 100, 8)")
    equal(tuple(add_overflows(100, 100, 8)), (False, True), label="add_overflows(100, 100, 8)")
    equal(tuple(add_overflows(1, 2, 8)), (False, False), label="add_overflows(1, 2, 8)")
    equal(tuple(add_overflows(255, 1, 8)), (True, False), label="add_overflows(255, 1, 8)")  # -1 + 1 = 0
    equal(tuple(add_overflows(128, 128, 8)), (True, True), label="add_overflows(128, 128, 8)")  # -128 + -128
    equal(tuple(add_overflows(127, 1, 8)), (False, True), label="add_overflows(127, 1, 8)")
    # Every pair of 4-bit patterns, against the plain arithmetic definition.
    for a in range(16):
        for b in range(16):
            sa, sb = (a - 16 if a >= 8 else a), (b - 16 if b >= 8 else b)
            want = (a + b > 15, not (-8 <= sa + sb <= 7))
            equal(tuple(add_overflows(a, b, 4)), want, label=f"add_overflows({a}, {b}, 4)")


@check("zero_extend and sign_extend widen a pattern")
def test_extend(sub):
    zero_extend, sign_extend = has(sub, "zero_extend"), has(sub, "sign_extend")
    equal(zero_extend(0xFF, 8, 16), 0x00FF, label="zero_extend(0xFF, 8, 16)")
    equal(sign_extend(0xFF, 8, 16), 0xFFFF, label="sign_extend(0xFF, 8, 16)")
    equal(sign_extend(0x7F, 8, 16), 0x007F, label="sign_extend(0x7F, 8, 16)")
    equal(sign_extend(0x80, 8, 32), 0xFFFFFF80, label="sign_extend(0x80, 8, 32)")
    equal(sign_extend(0b101, 3, 8), 0b11111101, label="sign_extend(0b101, 3, 8)")
    equal(sign_extend(5, 8, 8), 5, label="sign_extend to the same width")
    to_signed = has(sub, "to_signed")
    for pattern in range(256):
        wide = sign_extend(pattern, 8, 32)
        equal(to_signed(wide, 32), to_signed(pattern, 8), label=f"sign_extend({pattern}) keeps its value")


C_SOURCE = """
#include <stdint.h>
int32_t as_i8(int32_t x)  { return (int8_t)x; }
int32_t as_u8(int32_t x)  { return (uint8_t)x; }
int32_t as_i16(int32_t x) { return (int16_t)x; }
int64_t as_i32(int64_t x) { return (int32_t)x; }
uint32_t add_u32(uint32_t a, uint32_t b) { return a + b; }
int32_t sext8(uint8_t x)  { return (int8_t)x; }
int32_t neg_u32(uint32_t x) { return -x; }
int uadd_overflows(uint32_t a, uint32_t b) { uint32_t r; return __builtin_add_overflow(a, b, &r); }
int sadd_overflows(int32_t a, int32_t b)   { int32_t r;  return __builtin_add_overflow(a, b, &r); }
"""


def _lib():
    lib = cputools.compile_c(C_SOURCE)
    for name in ("as_i8", "as_u8", "as_i16", "sext8"):
        getattr(lib, name).restype = ctypes.c_int32
    lib.as_i8.argtypes = lib.as_u8.argtypes = lib.as_i16.argtypes = [ctypes.c_int32]
    lib.as_i32.argtypes, lib.as_i32.restype = [ctypes.c_int64], ctypes.c_int64
    lib.add_u32.argtypes, lib.add_u32.restype = [ctypes.c_uint32, ctypes.c_uint32], ctypes.c_uint32
    lib.sext8.argtypes = [ctypes.c_uint8]
    lib.neg_u32.argtypes, lib.neg_u32.restype = [ctypes.c_uint32], ctypes.c_uint32
    lib.uadd_overflows.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    lib.sadd_overflows.argtypes = [ctypes.c_int32, ctypes.c_int32]
    return lib


@check("your wrapping and sign reading agree with what real C does for (int8_t), (uint8_t), (int16_t), (int32_t)")
def test_against_c_casts(sub):
    to_signed, to_unsigned = has(sub, "to_signed"), has(sub, "to_unsigned")
    lib = _lib()
    rng = random.Random(0)
    values = [0, 1, 127, 128, 200, 255, 256, 300, -1, -128, -129, 32767, 32768, 65535, 2**31 - 1, -(2**31)]
    values += [rng.randrange(-(2**31), 2**31) for _ in range(40)]
    for x in values:
        equal(to_signed(x, 8), lib.as_i8(x), label=f"(int8_t){x} in C vs to_signed({x}, 8)")
        equal(to_unsigned(x, 8), lib.as_u8(x), label=f"(uint8_t){x} in C vs to_unsigned({x}, 8)")
        equal(to_signed(x, 16), lib.as_i16(x), label=f"(int16_t){x} in C vs to_signed({x}, 16)")
    for x in values + [2**31, 2**32 - 1, 2**33 + 7, -(2**40)]:
        equal(to_signed(x, 32), lib.as_i32(x), label=f"(int32_t){x} in C vs to_signed({x}, 32)")


@check("your uint32 add, negate, and sign extension agree with real C")
def test_against_c_arith(sub):
    to_unsigned = has(sub, "to_unsigned")
    negate, sign_extend = has(sub, "negate"), has(sub, "sign_extend")
    lib = _lib()
    rng = random.Random(1)
    pairs = [(0xFFFFFFFF, 1), (0x80000000, 0x80000000), (5, 7)]
    pairs += [(rng.randrange(2**32), rng.randrange(2**32)) for _ in range(40)]
    for a, b in pairs:
        equal(to_unsigned(a + b, 32), lib.add_u32(a, b), label=f"{a} + {b} as uint32_t")
    for x in [0, 1, 5, 0x80000000, 0xFFFFFFFF] + [rng.randrange(2**32) for _ in range(20)]:
        equal(negate(x, 32), lib.neg_u32(x), label=f"-({x}) as uint32_t")
    for x in range(256):
        # C widens an int8_t to int32_t by sign extension; read the result as a pattern.
        equal(sign_extend(x, 8, 32), lib.sext8(x) % 2**32, label=f"sign_extend({x}, 8, 32)")


@check("your add_overflows agrees with the overflow detection built into clang")
def test_against_c_overflow(sub):
    add_overflows, to_unsigned = has(sub, "add_overflows"), has(sub, "to_unsigned")
    lib = _lib()
    rng = random.Random(2)
    pairs = [(2**31 - 1, 1), (-(2**31), -1), (2**31 - 1, 2**31 - 1), (-1, 1), (1, 2)]
    pairs += [(rng.randrange(-(2**31), 2**31), rng.randrange(-(2**31), 2**31)) for _ in range(60)]
    for a, b in pairs:
        pa, pb = to_unsigned(a, 32), to_unsigned(b, 32)
        unsigned_over, signed_over = add_overflows(pa, pb, 32)
        equal(bool(unsigned_over), bool(lib.uadd_overflows(pa, pb)), label=f"unsigned overflow of {pa} + {pb}")
        equal(bool(signed_over), bool(lib.sadd_overflows(a, b)), label=f"signed overflow of {a} + {b}")
