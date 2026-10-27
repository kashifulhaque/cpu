"""Checks for the logic gates and adders exercise."""

from cpucheck import check, equal, fail, has

BITS = (0, 1)


def _counting_nand(sub):
    """Swap sub.nand for a version that counts its calls. Returns (counter, restore)."""
    original = sub.nand
    counter = {"calls": 0}

    def counting(a, b):
        counter["calls"] += 1
        return original(a, b)

    sub.nand = counting
    return counter, lambda: setattr(sub, "nand", original)


@check("not_, and_, or_, and xor_ match their truth tables")
def test_gates(sub):
    not_, and_, or_, xor_ = (has(sub, n) for n in ("not_", "and_", "or_", "xor_"))
    for a in BITS:
        equal(not_(a), 1 - a, label=f"not_({a})")
        for b in BITS:
            equal(and_(a, b), a & b, label=f"and_({a}, {b})")
            equal(or_(a, b), a | b, label=f"or_({a}, {b})")
            equal(xor_(a, b), a ^ b, label=f"xor_({a}, {b})")


@check("the gates are built from nand: each one calls nand at least once")
def test_gates_use_nand(sub):
    names = ("not_", "and_", "or_", "xor_")
    funcs = {n: has(sub, n) for n in names}
    counter, restore = _counting_nand(sub)
    try:
        for name, func in funcs.items():
            before = counter["calls"]
            args = (1,) if name == "not_" else (1, 0)
            func(*args)
            if counter["calls"] == before:
                fail(f"{name} never called nand; build it from nand instead of Python's & | ^ ~")
        # Spot-check how many nands each needs: NOT 1, AND 2, OR 3, XOR 4.
        for name, minimum in (("not_", 1), ("and_", 2), ("or_", 3), ("xor_", 4)):
            before = counter["calls"]
            funcs[name](*((1,) if name == "not_" else (1, 1)))
            used = counter["calls"] - before
            if used < minimum:
                fail(f"{name} used {used} nand call(s); a pure-NAND {name} needs at least {minimum}")
    finally:
        restore()


@check("half_adder adds two bits into (sum, carry)")
def test_half_adder(sub):
    half_adder = has(sub, "half_adder")
    for a, b, want in [(0, 0, (0, 0)), (0, 1, (1, 0)), (1, 0, (1, 0)), (1, 1, (0, 1))]:
        equal(tuple(half_adder(a, b)), want, label=f"half_adder({a}, {b})")


@check("full_adder adds three bits into (sum, carry_out)")
def test_full_adder(sub):
    full_adder = has(sub, "full_adder")
    for a in BITS:
        for b in BITS:
            for c in BITS:
                total = a + b + c
                equal(tuple(full_adder(a, b, c)), (total & 1, total >> 1), label=f"full_adder({a}, {b}, {c})")


@check("ripple_add adds bit lists, lowest bit first, with a carry out")
def test_ripple_add(sub):
    ripple_add = has(sub, "ripple_add")
    from_int, to_int = has(sub, "bits_from_int"), has(sub, "int_from_bits")
    equal(ripple_add([1, 1, 0, 0], [1, 0, 1, 0]), ([0, 0, 0, 1], 0), label="3 + 5 in 4 bits")
    equal(ripple_add([1, 1], [1, 0]), ([0, 0], 1), label="3 + 1 in 2 bits")
    equal(ripple_add([1, 1], [1, 0], 1), ([1, 0], 1), label="3 + 1 + carry-in 1 in 2 bits")
    for a in range(32):
        for b in range(32):
            bits, carry = ripple_add(from_int(a, 5), from_int(b, 5))
            equal((to_int(bits), carry), ((a + b) % 32, (a + b) // 32), label=f"{a} + {b} in 5 bits")
    bits, carry = ripple_add(from_int(2**63 + 5, 64), from_int(2**63 + 9, 64))
    equal((to_int(bits), carry), (14, 1), label="a 64-bit add that carries out")


@check("alu add and sub give the right result and Z, N, C, V flags (every 4-bit pair)")
def test_alu_arith(sub):
    alu = has(sub, "alu")
    from_int, to_int = has(sub, "bits_from_int"), has(sub, "int_from_bits")

    def signed(x):
        return x - 16 if x >= 8 else x

    for a in range(16):
        for b in range(16):
            result, flags = alu("add", from_int(a, 4), from_int(b, 4))
            r = (a + b) % 16
            want = {"Z": int(r == 0), "N": r >> 3, "C": int(a + b > 15),
                    "V": int(not -8 <= signed(a) + signed(b) <= 7)}
            equal((to_int(result), dict(flags)), (r, want), label=f"alu('add') {a} + {b}")
            result, flags = alu("sub", from_int(a, 4), from_int(b, 4))
            r = (a - b) % 16
            # C is 1 when no borrow is needed, that is when a >= b as unsigned numbers.
            want = {"Z": int(r == 0), "N": r >> 3, "C": int(a >= b),
                    "V": int(not -8 <= signed(a) - signed(b) <= 7)}
            equal((to_int(result), dict(flags)), (r, want), label=f"alu('sub') {a} - {b}")


@check("alu and / or work bit by bit and clear C and V")
def test_alu_logic(sub):
    alu = has(sub, "alu")
    from_int, to_int = has(sub, "bits_from_int"), has(sub, "int_from_bits")
    for a in range(16):
        for b in range(16):
            for op, r in (("and", a & b), ("or", a | b)):
                result, flags = alu(op, from_int(a, 4), from_int(b, 4))
                want = {"Z": int(r == 0), "N": r >> 3, "C": 0, "V": 0}
                equal((to_int(result), dict(flags)), (r, want), label=f"alu({op!r}) {a}, {b}")


@check("alu works at 8 bits and rejects an unknown operation")
def test_alu_wide(sub):
    alu = has(sub, "alu")
    from_int, to_int = has(sub, "bits_from_int"), has(sub, "int_from_bits")
    result, flags = alu("add", from_int(100, 8), from_int(100, 8))
    equal((to_int(result), dict(flags)), (200, {"Z": 0, "N": 1, "C": 0, "V": 1}), label="100 + 100 in 8 bits")
    result, flags = alu("sub", from_int(5, 8), from_int(5, 8))
    equal((to_int(result), dict(flags)), (0, {"Z": 1, "N": 0, "C": 1, "V": 0}), label="5 - 5 in 8 bits")
    result, flags = alu("add", from_int(200, 8), from_int(100, 8))
    equal((to_int(result), dict(flags)), (44, {"Z": 0, "N": 0, "C": 1, "V": 0}), label="200 + 100 in 8 bits")
    try:
        alu("mul", from_int(1, 4), from_int(1, 4))
    except ValueError:
        return
    except NotImplementedError:
        raise
    fail("alu('mul', ...) should raise ValueError")
