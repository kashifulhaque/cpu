"""Bits, binary, and hexadecimal: base conversion, masks, and byte order."""

DIGITS = "0123456789abcdef"


def _to_base(n, base):
    if n < 0:
        raise ValueError("n must not be negative")
    if n == 0:
        return "0"
    digits = []
    while n > 0:
        digits.append(DIGITS[n % base])  # the remainder is the lowest digit
        n //= base  # dropping that digit moves everything down one place
    return "".join(reversed(digits))  # digits came out lowest first


def _from_base(text, base):
    if text == "":
        raise ValueError("no digits")
    total = 0
    for ch in text.lower():
        digit = DIGITS.index(ch) if ch in DIGITS else -1
        if digit < 0 or digit >= base:
            raise ValueError(f"{ch!r} is not a base {base} digit")
        total = total * base + digit
    return total


def to_binary(n):
    """Write a non-negative int in binary, without a prefix. Use a loop, not bin().

    to_binary(10) -> "1010"; to_binary(0) -> "0"
    """
    return _to_base(n, 2)


def to_hex(n):
    """Write a non-negative int in lowercase hex, without a prefix. Use a loop, not hex().

    to_hex(255) -> "ff"; to_hex(4096) -> "1000"; to_hex(0) -> "0"
    """
    return _to_base(n, 16)


def from_binary(text):
    """Read a string of 0s and 1s as an int. Use a loop, not int(text, 2).

    from_binary("1010") -> 10
    Raise ValueError for an empty string or any other character.
    """
    return _from_base(text, 2)


def from_hex(text):
    """Read a hex string (upper or lower case, no prefix) as an int. Use a loop.

    from_hex("ff") -> 255; from_hex("DEAD") -> 57005
    Raise ValueError for an empty string or a character that is not a hex digit.
    """
    return _from_base(text, 16)


def get_bits(value, lo, hi):
    """Return bits lo through hi of value, both included, shifted down to start at 0.
    Bit 0 is the least significant bit.

    get_bits(0b110100, 2, 4) -> 0b101 == 5
    get_bits(0xABCD, 8, 15) -> 0xAB
    """
    width = hi - lo + 1
    mask = (1 << width) - 1  # `width` ones
    return (value >> lo) & mask


def set_bit(value, index, on=True):
    """Return value with bit `index` set to 1 (on=True) or cleared to 0 (on=False).

    set_bit(0b0000, 2) -> 0b0100; set_bit(0b0110, 1, on=False) -> 0b0100
    """
    if on:
        return value | (1 << index)
    return value & ~(1 << index)


def popcount(value):
    """Count the 1 bits in a non-negative int.

    popcount(0b1011) -> 3; popcount(0) -> 0
    """
    count = 0
    while value:
        count += value & 1  # the lowest bit
        value >>= 1
    return count


def pack_le(value, size):
    """Pack a non-negative int into `size` bytes, least significant byte first.

    pack_le(0x12345678, 4) -> b"\\x78\\x56\\x34\\x12"
    Raise ValueError if the value does not fit in `size` bytes.
    """
    if value < 0 or value >> (8 * size):
        raise ValueError(f"{value} does not fit in {size} bytes")
    return bytes((value >> (8 * i)) & 0xFF for i in range(size))


def pack_be(value, size):
    """Pack a non-negative int into `size` bytes, most significant byte first.

    pack_be(0x12345678, 4) -> b"\\x12\\x34\\x56\\x78"
    Raise ValueError if the value does not fit in `size` bytes.
    """
    return pack_le(value, size)[::-1]  # same bytes, opposite order


def unpack_le(data):
    """Read a bytes value as a little-endian unsigned int.

    unpack_le(b"\\x78\\x56\\x34\\x12") -> 0x12345678
    """
    total = 0
    for i, byte in enumerate(data):
        total |= byte << (8 * i)  # byte i is worth 256**i
    return total


def unpack_be(data):
    """Read a bytes value as a big-endian unsigned int.

    unpack_be(b"\\x12\\x34\\x56\\x78") -> 0x12345678
    """
    return unpack_le(data[::-1])


if __name__ == "__main__":
    n = 0xDEADBEEF
    print(f"{n} = 0x{to_hex(n)} = 0b{to_binary(n)}")
    print("round trip:", from_hex(to_hex(n)) == n)
    print("bits 8..15:", hex(get_bits(n, 8, 15)), "popcount:", popcount(n))
    print("little-endian:", pack_le(n, 4).hex(" "))
    print("big-endian:   ", pack_be(n, 4).hex(" "))
