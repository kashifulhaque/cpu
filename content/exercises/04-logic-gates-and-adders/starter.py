"""Logic gates and adders, built from NAND.

A bit is the int 0 or 1. A number is a list of bits with the least significant
bit first, so [1, 0, 1, 0] is 1 + 4 = 5 in four bits.
"""


def nand(a, b):
    """The one gate we are given: 0 only when both inputs are 1."""
    return 0 if (a and b) else 1


def not_(a):
    """NOT, built only from nand.  not_(0) -> 1; not_(1) -> 0"""
    raise NotImplementedError


def and_(a, b):
    """AND, built only from nand.  and_(1, 1) -> 1; and_(1, 0) -> 0"""
    raise NotImplementedError


def or_(a, b):
    """OR, built only from nand.  or_(0, 0) -> 0; or_(1, 0) -> 1"""
    raise NotImplementedError


def xor_(a, b):
    """XOR, built only from nand.  xor_(1, 1) -> 0; xor_(1, 0) -> 1"""
    raise NotImplementedError


def half_adder(a, b):
    """Add two bits. Return (sum, carry).

    half_adder(1, 1) -> (0, 1)
    """
    raise NotImplementedError


def full_adder(a, b, carry_in):
    """Add three bits. Return (sum, carry_out).

    full_adder(1, 1, 1) -> (1, 1)
    """
    raise NotImplementedError


def ripple_add(a_bits, b_bits, carry_in=0):
    """Add two equal-length bit lists, least significant bit first.
    Return (sum_bits, carry_out). sum_bits has the same length as the inputs.

    ripple_add([1, 1, 0, 0], [1, 0, 1, 0]) -> ([0, 0, 0, 1], 0)   # 3 + 5 = 8
    ripple_add([1, 1], [1, 0]) -> ([0, 0], 1)                      # 3 + 1 = 4, overflows 2 bits
    """
    raise NotImplementedError


def alu(op, a_bits, b_bits):
    """A tiny arithmetic logic unit. `op` is "add", "sub", "and", or "or".
    Return (result_bits, flags), where flags is a dict with four bools-as-ints:

      Z  1 if every result bit is 0
      N  1 if the top result bit is 1 (negative in two's complement)
      C  carry out of the top bit of the adder (0 for "and" and "or").
         For "sub" this is 1 when there was no borrow, as on ARM.
      V  1 if the add or subtract overflowed as signed numbers (0 for "and" and "or")

    "sub" computes a + NOT(b) + 1 on the same adder.

    alu("add", [1,1,1,0], [1,0,0,0]) -> ([0,0,0,1], {"Z":0, "N":1, "C":0, "V":1})   # 7 + 1 = -8
    """
    raise NotImplementedError


def bits_from_int(n, width):
    """Turn an int into `width` bits, least significant first. Provided for you.

    bits_from_int(5, 4) -> [1, 0, 1, 0]
    """
    return [(n >> i) & 1 for i in range(width)]


def int_from_bits(bits):
    """Turn a least-significant-first bit list into an unsigned int. Provided for you."""
    return sum(bit << i for i, bit in enumerate(bits))


if __name__ == "__main__":
    a, b = bits_from_int(11, 4), bits_from_int(6, 4)
    total, carry = ripple_add(a, b)
    print("11 + 6 in 4 bits:", total, "=", int_from_bits(total), "carry out", carry)
    result, flags = alu("sub", a, b)
    print("11 - 6:", int_from_bits(result), flags)
    result, flags = alu("add", bits_from_int(7, 4), bits_from_int(1, 4))
    print("7 + 1:", int_from_bits(result), flags)
