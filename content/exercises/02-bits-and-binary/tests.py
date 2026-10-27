"""Checks for the bits, binary, and hexadecimal exercise."""

import random

from cpucheck import check, equal, fail, has


def expect_error(kind, action, what):
    try:
        action()
    except kind:
        return
    except NotImplementedError:
        raise
    except Exception as exc:  # noqa: BLE001
        fail(f"{what}: raised {type(exc).__name__}, expected {kind.__name__}")
    fail(f"{what}: expected {kind.__name__}, but nothing was raised")


@check("to_binary and to_hex write numbers in base 2 and base 16")
def test_to_base(sub):
    to_binary = has(sub, "to_binary")
    to_hex = has(sub, "to_hex")
    equal(to_binary(0), "0", label="to_binary(0)")
    equal(to_binary(10), "1010", label="to_binary(10)")  # 8 + 2
    equal(to_binary(255), "11111111", label="to_binary(255)")
    equal(to_binary(256), "100000000", label="to_binary(256)")
    equal(to_hex(0), "0", label="to_hex(0)")
    equal(to_hex(255), "ff", label="to_hex(255)")
    equal(to_hex(4096), "1000", label="to_hex(4096)")  # 16 ** 3
    equal(to_hex(3735928559), "deadbeef", label="to_hex(3735928559)")
    expect_error(ValueError, lambda: to_binary(-1), "to_binary(-1)")


@check("from_binary and from_hex read digit strings and reject bad ones")
def test_from_base(sub):
    from_binary = has(sub, "from_binary")
    from_hex = has(sub, "from_hex")
    equal(from_binary("1010"), 10, label="from_binary('1010')")
    equal(from_binary("0"), 0, label="from_binary('0')")
    equal(from_binary("0001"), 1, label="from_binary('0001')")
    equal(from_hex("ff"), 255, label="from_hex('ff')")
    equal(from_hex("FF"), 255, label="from_hex('FF')")
    equal(from_hex("dead"), 57005, label="from_hex('dead')")  # 13*4096+14*256+10*16+13
    expect_error(ValueError, lambda: from_binary("102"), "from_binary('102')")
    expect_error(ValueError, lambda: from_binary(""), "from_binary('')")
    expect_error(ValueError, lambda: from_hex("xyz"), "from_hex('xyz')")


@check("converting to a base and back gives the number you started with")
def test_round_trip(sub):
    to_binary, to_hex = has(sub, "to_binary"), has(sub, "to_hex")
    from_binary, from_hex = has(sub, "from_binary"), has(sub, "from_hex")
    rng = random.Random(0)
    for _ in range(200):
        n = rng.randrange(0, 2**64)
        equal(to_binary(n), format(n, "b"), label=f"to_binary({n})")
        equal(to_hex(n), format(n, "x"), label=f"to_hex({n})")
        equal(from_binary(to_binary(n)), n, label=f"from_binary(to_binary({n}))")
        equal(from_hex(to_hex(n)), n, label=f"from_hex(to_hex({n}))")


@check("get_bits extracts a field of bits, both ends included")
def test_get_bits(sub):
    get_bits = has(sub, "get_bits")
    # 0b110100 shifted right 2 is 0b1101; the low 3 bits of that are 0b101.
    equal(get_bits(0b110100, 2, 4), 0b101, label="get_bits(0b110100, 2, 4)")
    equal(get_bits(0xABCD, 0, 7), 0xCD, label="get_bits(0xABCD, 0, 7)")
    equal(get_bits(0xABCD, 8, 15), 0xAB, label="get_bits(0xABCD, 8, 15)")
    equal(get_bits(0xABCD, 4, 7), 0xC, label="get_bits(0xABCD, 4, 7)")
    equal(get_bits(0b1000, 3, 3), 1, label="get_bits(0b1000, 3, 3)")
    equal(get_bits(0xFFFFFFFF, 0, 31), 0xFFFFFFFF, label="get_bits of all 32 bits")


@check("set_bit sets and clears one bit and leaves the rest alone")
def test_set_bit(sub):
    set_bit = has(sub, "set_bit")
    equal(set_bit(0b0000, 2), 0b0100, label="set_bit(0b0000, 2)")
    equal(set_bit(0b0100, 2), 0b0100, label="setting a set bit changes nothing")
    equal(set_bit(0b0110, 1, on=False), 0b0100, label="set_bit(0b0110, 1, on=False)")
    equal(set_bit(0b0100, 1, on=False), 0b0100, label="clearing a clear bit changes nothing")
    equal(set_bit(0, 63), 1 << 63, label="set_bit(0, 63)")
    equal(set_bit(0xFF, 0, on=False), 0xFE, label="set_bit(0xFF, 0, on=False)")


@check("popcount counts the 1 bits")
def test_popcount(sub):
    popcount = has(sub, "popcount")
    equal(popcount(0), 0, label="popcount(0)")
    equal(popcount(0b1011), 3, label="popcount(0b1011)")
    equal(popcount(255), 8, label="popcount(255)")
    equal(popcount(2**64 - 1), 64, label="popcount(2**64 - 1)")
    rng = random.Random(1)
    for _ in range(100):
        n = rng.randrange(0, 2**32)
        equal(popcount(n), bin(n).count("1"), label=f"popcount({n})")


@check("pack_le and pack_be lay bytes out in the two byte orders")
def test_pack(sub):
    pack_le, pack_be = has(sub, "pack_le"), has(sub, "pack_be")
    equal(pack_le(0x12345678, 4), b"\x78\x56\x34\x12", label="pack_le(0x12345678, 4)")
    equal(pack_be(0x12345678, 4), b"\x12\x34\x56\x78", label="pack_be(0x12345678, 4)")
    equal(pack_le(1, 4), b"\x01\x00\x00\x00", label="pack_le(1, 4)")
    equal(pack_be(1, 4), b"\x00\x00\x00\x01", label="pack_be(1, 4)")
    equal(pack_le(0x0102, 8), b"\x02\x01" + bytes(6), label="pack_le(0x0102, 8)")
    equal(pack_be(0, 2), b"\x00\x00", label="pack_be(0, 2)")
    if not isinstance(pack_le(5, 2), bytes):
        fail("pack_le should return a bytes value")
    expect_error(ValueError, lambda: pack_le(256, 1), "pack_le(256, 1)")
    expect_error(ValueError, lambda: pack_be(2**32, 4), "pack_be(2**32, 4)")


@check("unpack_le and unpack_be read bytes back, matching Python's int.from_bytes")
def test_unpack(sub):
    unpack_le, unpack_be = has(sub, "unpack_le"), has(sub, "unpack_be")
    pack_le, pack_be = has(sub, "pack_le"), has(sub, "pack_be")
    equal(unpack_le(b"\x78\x56\x34\x12"), 0x12345678, label="unpack_le of 78 56 34 12")
    equal(unpack_be(b"\x12\x34\x56\x78"), 0x12345678, label="unpack_be of 12 34 56 78")
    equal(unpack_le(b""), 0, label="unpack_le(b'')")
    rng = random.Random(2)
    for _ in range(100):
        size = rng.choice([1, 2, 4, 8])
        n = rng.randrange(0, 2 ** (8 * size))
        equal(pack_le(n, size), n.to_bytes(size, "little"), label=f"pack_le({n}, {size})")
        equal(pack_be(n, size), n.to_bytes(size, "big"), label=f"pack_be({n}, {size})")
        equal(unpack_le(pack_le(n, size)), n, label=f"little-endian round trip of {n}")
        equal(unpack_be(pack_be(n, size)), n, label=f"big-endian round trip of {n}")
