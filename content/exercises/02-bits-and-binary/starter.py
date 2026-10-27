"""Bits, binary, and hexadecimal: base conversion, masks, and byte order."""

DIGITS = "0123456789abcdef"


def to_binary(n):
    """Write a non-negative int in binary, without a prefix. Use a loop, not bin().

    to_binary(10) -> "1010"; to_binary(0) -> "0"
    """
    raise NotImplementedError


def to_hex(n):
    """Write a non-negative int in lowercase hex, without a prefix. Use a loop, not hex().

    to_hex(255) -> "ff"; to_hex(4096) -> "1000"; to_hex(0) -> "0"
    """
    raise NotImplementedError


def from_binary(text):
    """Read a string of 0s and 1s as an int. Use a loop, not int(text, 2).

    from_binary("1010") -> 10
    Raise ValueError for an empty string or any other character.
    """
    raise NotImplementedError


def from_hex(text):
    """Read a hex string (upper or lower case, no prefix) as an int. Use a loop.

    from_hex("ff") -> 255; from_hex("DEAD") -> 57005
    Raise ValueError for an empty string or a character that is not a hex digit.
    """
    raise NotImplementedError


def get_bits(value, lo, hi):
    """Return bits lo through hi of value, both included, shifted down to start at 0.
    Bit 0 is the least significant bit.

    get_bits(0b110100, 2, 4) -> 0b101 == 5
    get_bits(0xABCD, 8, 15) -> 0xAB
    """
    raise NotImplementedError


def set_bit(value, index, on=True):
    """Return value with bit `index` set to 1 (on=True) or cleared to 0 (on=False).

    set_bit(0b0000, 2) -> 0b0100; set_bit(0b0110, 1, on=False) -> 0b0100
    """
    raise NotImplementedError


def popcount(value):
    """Count the 1 bits in a non-negative int.

    popcount(0b1011) -> 3; popcount(0) -> 0
    """
    raise NotImplementedError


def pack_le(value, size):
    """Pack a non-negative int into `size` bytes, least significant byte first.

    pack_le(0x12345678, 4) -> b"\\x78\\x56\\x34\\x12"
    Raise ValueError if the value does not fit in `size` bytes.
    """
    raise NotImplementedError


def pack_be(value, size):
    """Pack a non-negative int into `size` bytes, most significant byte first.

    pack_be(0x12345678, 4) -> b"\\x12\\x34\\x56\\x78"
    Raise ValueError if the value does not fit in `size` bytes.
    """
    raise NotImplementedError


def unpack_le(data):
    """Read a bytes value as a little-endian unsigned int.

    unpack_le(b"\\x78\\x56\\x34\\x12") -> 0x12345678
    """
    raise NotImplementedError


def unpack_be(data):
    """Read a bytes value as a big-endian unsigned int.

    unpack_be(b"\\x12\\x34\\x56\\x78") -> 0x12345678
    """
    raise NotImplementedError


if __name__ == "__main__":
    n = 0xDEADBEEF
    print(f"{n} = 0x{to_hex(n)} = 0b{to_binary(n)}")
    print("round trip:", from_hex(to_hex(n)) == n)
    print("bits 8..15:", hex(get_bits(n, 8, 15)), "popcount:", popcount(n))
    print("little-endian:", pack_le(n, 4).hex(" "))
    print("big-endian:   ", pack_be(n, 4).hex(" "))
