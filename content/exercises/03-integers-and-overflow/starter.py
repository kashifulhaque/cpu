"""Integers, two's complement, and overflow in a fixed number of bits.

A "pattern" below is an unsigned int in the range 0 .. 2**bits - 1. It is the
row of bits the hardware stores. A "value" is the number you get by reading the
pattern as signed or unsigned.
"""


def to_unsigned(x, bits):
    """Wrap any int into the pattern range 0 .. 2**bits - 1.

    to_unsigned(-1, 8) -> 255; to_unsigned(256, 8) -> 0; to_unsigned(300, 8) -> 44
    """
    raise NotImplementedError


def to_signed(x, bits):
    """Read the low `bits` bits of x as a two's complement signed number.

    to_signed(0xFF, 8) -> -1; to_signed(0x7F, 8) -> 127; to_signed(200, 8) -> -56
    Any int works: wrap it first.
    """
    raise NotImplementedError


def int_range(bits, signed):
    """Return (smallest, largest) value for a `bits`-bit integer.

    int_range(8, True) -> (-128, 127); int_range(8, False) -> (0, 255)
    """
    raise NotImplementedError


def negate(pattern, bits):
    """Two's complement negation of a pattern: flip every bit, then add one.
    Return the resulting pattern.

    negate(1, 8) -> 255 (0b11111111); negate(0, 8) -> 0; negate(128, 8) -> 128
    """
    raise NotImplementedError


def add_overflows(a, b, bits):
    """For two patterns, say whether adding them overflows.
    Return (unsigned_overflow, signed_overflow) as two bools.

    add_overflows(200, 100, 8) -> (True, False)   # 300 > 255, but -56 + 100 = 44 fits
    add_overflows(100, 100, 8) -> (False, True)   # 200 <= 255, but 100 + 100 > 127
    add_overflows(1, 2, 8) -> (False, False)
    """
    raise NotImplementedError


def zero_extend(pattern, from_bits, to_bits):
    """Widen a `from_bits`-bit pattern to `to_bits` bits, filling the top with zeros.

    zero_extend(0xFF, 8, 16) -> 0x00FF
    """
    raise NotImplementedError


def sign_extend(pattern, from_bits, to_bits):
    """Widen a `from_bits`-bit pattern to `to_bits` bits, copying the top bit upward.
    Return the wider pattern.

    sign_extend(0xFF, 8, 16) -> 0xFFFF; sign_extend(0x7F, 8, 16) -> 0x007F
    """
    raise NotImplementedError


if __name__ == "__main__":
    print("300 in 8 bits:", to_unsigned(300, 8), "or as signed:", to_signed(300, 8))
    print("-5 as an 8-bit pattern:", bin(to_unsigned(-5, 8)))
    print("negate(5, 8) =", bin(negate(5, 8)))
    print("100 + 100 in 8 bits overflows (unsigned, signed):", add_overflows(100, 100, 8))
    print("sign_extend(0xF0, 8, 16) =", hex(sign_extend(0xF0, 8, 16)))
    import cputools

    lib = cputools.compile_c("#include <stdint.h>\nint32_t f(int32_t x) { return (int8_t)x; }")
    print("real C says (int8_t)200 is", lib.f(200), "and you say", to_signed(200, 8))
