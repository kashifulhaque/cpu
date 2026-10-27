"""Logic gates and adders, built from NAND.

A bit is the int 0 or 1. A number is a list of bits with the least significant
bit first, so [1, 0, 1, 0] is 1 + 4 = 5 in four bits.
"""


def nand(a, b):
    """The one gate we are given: 0 only when both inputs are 1."""
    return 0 if (a and b) else 1


def not_(a):
    """NOT, built only from nand.  not_(0) -> 1; not_(1) -> 0"""
    return nand(a, a)  # a bit with itself: 1 only when the bit is 0


def and_(a, b):
    """AND, built only from nand.  and_(1, 1) -> 1; and_(1, 0) -> 0"""
    return not_(nand(a, b))  # undo the NAND's inversion


def or_(a, b):
    """OR, built only from nand.  or_(0, 0) -> 0; or_(1, 0) -> 1"""
    return nand(not_(a), not_(b))  # De Morgan: a OR b = NOT(NOT a AND NOT b)


def xor_(a, b):
    """XOR, built only from nand.  xor_(1, 1) -> 0; xor_(1, 0) -> 1"""
    n = nand(a, b)
    return nand(nand(a, n), nand(b, n))  # the classic four-NAND XOR


def half_adder(a, b):
    """Add two bits. Return (sum, carry).

    half_adder(1, 1) -> (0, 1)
    """
    return xor_(a, b), and_(a, b)


def full_adder(a, b, carry_in):
    """Add three bits. Return (sum, carry_out).

    full_adder(1, 1, 1) -> (1, 1)
    """
    s1, c1 = half_adder(a, b)
    s2, c2 = half_adder(s1, carry_in)
    return s2, or_(c1, c2)  # at most one of the two half adders carries


def ripple_add(a_bits, b_bits, carry_in=0):
    """Add two equal-length bit lists, least significant bit first.
    Return (sum_bits, carry_out). sum_bits has the same length as the inputs.

    ripple_add([1, 1, 0, 0], [1, 0, 1, 0]) -> ([0, 0, 0, 1], 0)   # 3 + 5 = 8
    ripple_add([1, 1], [1, 0]) -> ([0, 0], 1)                      # 3 + 1 = 4, overflows 2 bits
    """
    if len(a_bits) != len(b_bits):
        raise ValueError("the two numbers need the same number of bits")
    out = []
    carry = carry_in
    for a, b in zip(a_bits, b_bits):  # lowest bit first: the carry ripples upward
        s, carry = full_adder(a, b, carry)
        out.append(s)
    return out, carry


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
    carry = overflow = 0
    if op in ("add", "sub"):
        if op == "add":
            operand, carry_in = b_bits, 0
        else:
            operand, carry_in = [not_(b) for b in b_bits], 1
        result, carry = ripple_add(a_bits, operand, carry_in)
        a_sign, b_sign, r_sign = a_bits[-1], operand[-1], result[-1]
        # Overflow: two operands with the same sign produced a result of the other sign.
        overflow = and_(not_(xor_(a_sign, b_sign)), xor_(a_sign, r_sign))
    elif op == "and":
        result = [and_(a, b) for a, b in zip(a_bits, b_bits)]
    elif op == "or":
        result = [or_(a, b) for a, b in zip(a_bits, b_bits)]
    else:
        raise ValueError(f"unknown operation {op!r}")
    zero = 1
    for bit in result:
        zero = and_(zero, not_(bit))
    return result, {"Z": zero, "N": result[-1], "C": carry, "V": overflow}


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
