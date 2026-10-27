"""Checks for the instruction encoding exercise."""

import random

from cpucheck import check, equal, fail, has

# Reference words. Each was produced by LLVM's RISC-V assembler (clang
# --target=riscv32 -march=rv32i), not by this exercise's reference solution.
KNOWN = [
    ("addi x1, x0, 5", 0x00500093),
    ("add x3, x1, x2", 0x002081B3),
    ("sub x3, x1, x2", 0x402081B3),
    ("lw x5, 8(x2)", 0x00812283),
    ("sw x5, 8(x2)", 0x00512423),
    ("beq x1, x2, 8", 0x00208463),
    ("jal x1, 8", 0x008000EF),
    ("addi x31, x30, -2048", 0x800F0F93),
    ("addi x1, x2, 2047", 0x7FF10093),
    ("add x31, x30, x29", 0x01DF0FB3),
    ("sub x1, x0, x31", 0x41F000B3),
    ("lw x1, 2047(x31)", 0x7FFFA083),
    ("lw x1, -2048(x31)", 0x800FA083),
    ("sw x31, -2048(x1)", 0x81F0A023),
    ("sw x31, 2047(x1)", 0x7FF0AFA3),
    ("sw x1, -1(x2)", 0xFE112FA3),
    ("sw x1, 100(x2)", 0x06112223),
    ("beq x31, x30, 4094", 0x7FEF8FE3),
    ("beq x1, x2, -4096", 0x80208063),
    ("beq x0, x0, 2016", 0x7E000063),
    ("beq x3, x4, -20", 0xFE4186E3),
    ("jal x1, 1048574", 0x7FFFF0EF),
    ("jal x1, -1048576", 0x800000EF),
    ("jal x0, 2048", 0x0010006F),
    ("jal x5, -20", 0xFEDFF2EF),
    ("jal x1, 524288", 0x000800EF),
]


def _fails(fn, *args):
    """True when fn raised ValueError; fail if it returned."""
    try:
        got = fn(*args)
    except ValueError:
        return True
    fail(f"expected ValueError, but {fn.__name__}{args!r} returned {got!r}")


@check("sign_extend and register_number read fields correctly")
def test_helpers(sub):
    sign_extend, register_number = has(sub, "sign_extend"), has(sub, "register_number")
    # 12 bits: 0xFFF is -1, 0x800 is -2048 (-2^11), 0x7FF is 2047.
    for value, bits, want in [(0xFFF, 12, -1), (0x800, 12, -2048), (0x7FF, 12, 2047), (0, 12, 0),
                              (0x1FFF, 13, -1), (0x1000, 13, -4096), (0xFFF, 13, 4095),
                              (0x100000, 21, -1048576)]:
        equal(sign_extend(value, bits), want, label=f"sign_extend({value:#x}, {bits})")
    equal(register_number("x0"), 0)
    equal(register_number("x31"), 31)
    equal(register_number("zero"), 0)
    equal(register_number("sp"), 2)
    _fails(register_number, "x32")
    _fails(register_number, "banana")


@check("encode_r packs add and sub with the right fields")
def test_encode_r(sub):
    encode_r = has(sub, "encode_r")
    OP_R = has(sub, "OP_R")
    # add x3, x1, x2: rs2=2<<20 = 0x200000, rs1=1<<15 = 0x8000, rd=3<<7 = 0x180, opcode 0x33.
    # 0x200000 + 0x8000 + 0x180 + 0x33 = 0x2081B3.
    equal(encode_r(0, 2, 1, 0, 3, OP_R), 0x002081B3, label="add x3, x1, x2")
    # sub only changes funct7 to 0100000: 0x20 << 25 = 0x40000000 added to the add word.
    equal(encode_r(0b0100000, 2, 1, 0, 3, OP_R), 0x402081B3, label="sub x3, x1, x2")


@check("encode_i, encode_s pack immediates, including negative ones")
def test_encode_is(sub):
    encode_i, encode_s = has(sub, "encode_i"), has(sub, "encode_s")
    OP_I, OP_LOAD, OP_STORE = has(sub, "OP_I"), has(sub, "OP_LOAD"), has(sub, "OP_STORE")
    # addi x1, x0, 5: imm 5<<20 = 0x500000, rd 1<<7 = 0x80, opcode 0x13 -> 0x00500093.
    equal(encode_i(5, 0, 0, 1, OP_I), 0x00500093, label="addi x1, x0, 5")
    # imm -1 is 0xFFF in 12 bits: 0xFFF << 20 = 0xFFF00000.
    equal(encode_i(-1, 0, 0, 0, OP_I), 0xFFF00013, label="addi x0, x0, -1")
    equal(encode_i(-2048, 30, 0, 31, OP_I), 0x800F0F93, label="addi x31, x30, -2048")
    equal(encode_i(8, 2, 2, 5, OP_LOAD), 0x00812283, label="lw x5, 8(x2)")
    # sw x5, 8(x2): imm[11:5] = 0, imm[4:0] = 8 -> 8<<7 = 0x400; rs2 5<<20 = 0x500000;
    # rs1 2<<15 = 0x10000; funct3 2<<12 = 0x2000; opcode 0x23 -> 0x00512423.
    equal(encode_s(8, 5, 2, 2, OP_STORE), 0x00512423, label="sw x5, 8(x2)")
    # imm -2048 is 0x800: imm[11:5] = 0b1000000 (word bits 31:25 = 0x80000000 + 0x1000000 shifted down), imm[4:0] = 0.
    equal(encode_s(-2048, 31, 1, 2, OP_STORE), 0x81F0A023, label="sw x31, -2048(x1)")
    equal(encode_s(-1, 1, 2, 2, OP_STORE), 0xFE112FA3, label="sw x1, -1(x2)")
    _fails(encode_i, 2048, 0, 0, 1, OP_I)
    _fails(encode_i, -2049, 0, 0, 1, OP_I)
    _fails(encode_s, 2048, 1, 2, 2, OP_STORE)


@check("encode_b scatters a branch offset across the word")
def test_encode_b(sub):
    encode_b, OP_BRANCH = has(sub, "encode_b"), has(sub, "OP_BRANCH")
    # beq x1, x2, 8: imm = 0b0_0_000000_0100_0 -> imm[4:1] = 0100 lands in bits 11:8 (0x400).
    # rs2 2<<20 = 0x200000, rs1 1<<15 = 0x8000, opcode 0x63 -> 0x00208463.
    equal(encode_b(8, 2, 1, 0, OP_BRANCH), 0x00208463, label="beq x1, x2, 8")
    # -20 is 0x1FEC in 13 bits: bit 12 = 1 (word bit 31), imm[10:5] = 0b111111, imm[4:1] = 0110,
    # imm[11] = 1 (word bit 7).
    equal(encode_b(-20, 4, 3, 0, OP_BRANCH), 0xFE4186E3, label="beq x3, x4, -20")
    equal(encode_b(4094, 30, 31, 0, OP_BRANCH), 0x7FEF8FE3, label="beq x31, x30, 4094")
    equal(encode_b(-4096, 2, 1, 0, OP_BRANCH), 0x80208063, label="beq x1, x2, -4096")
    equal(encode_b(2016, 0, 0, 0, OP_BRANCH), 0x7E000063, label="beq x0, x0, 2016")
    _fails(encode_b, 3, 2, 1, 0, OP_BRANCH)      # odd offset
    _fails(encode_b, 4096, 2, 1, 0, OP_BRANCH)   # one past the largest offset
    _fails(encode_b, -4098, 2, 1, 0, OP_BRANCH)


@check("encode_j scatters a jump offset across the word")
def test_encode_j(sub):
    encode_j, OP_JAL = has(sub, "encode_j"), has(sub, "OP_JAL")
    # jal x1, 8: imm[10:1] = 4 goes to bits 30:21 -> 4<<21 = 0x800000; rd 1<<7 = 0x80; opcode 0x6F.
    equal(encode_j(8, 1, OP_JAL), 0x008000EF, label="jal x1, 8")
    # 2048 is bit 11: it lands in word bit 20 -> 0x100000, plus rd 0 and opcode 0x6F.
    equal(encode_j(2048, 0, OP_JAL), 0x0010006F, label="jal x0, 2048")
    # 524288 is bit 19: it lands in word bit 19 -> 0x80000.
    equal(encode_j(524288, 1, OP_JAL), 0x000800EF, label="jal x1, 524288")
    equal(encode_j(-20, 5, OP_JAL), 0xFEDFF2EF, label="jal x5, -20")
    equal(encode_j(1048574, 1, OP_JAL), 0x7FFFF0EF, label="jal x1, 1048574")
    equal(encode_j(-1048576, 1, OP_JAL), 0x800000EF, label="jal x1, -1048576")
    _fails(encode_j, 1, 1, OP_JAL)
    _fails(encode_j, 1048576, 1, OP_JAL)


@check("assemble_line matches LLVM's encodings for 26 instructions")
def test_assemble_line(sub):
    assemble_line = has(sub, "assemble_line")
    for text, want in KNOWN:
        equal(assemble_line(text), want, label=text)
    # Extra spacing, upper case, and a comment do not change the word.
    equal(assemble_line("  ADDI  x1 ,x0,  5   # five"), 0x00500093, label="loose syntax")
    equal(assemble_line("add ra, zero, sp"), 0x002000B3, label="ABI names")


@check("assemble_line rejects bad input with ValueError")
def test_assemble_line_errors(sub):
    assemble_line = has(sub, "assemble_line")
    for bad in ["mul x1, x2, x3", "addi x1, x0", "addi x1, x0, 2048", "add x1, x2, x32",
                "lw x1, 8", "beq x1, x2, 3", "sw x1, 4096(x2)", "jal x1"]:
        _fails(assemble_line, bad)


@check("assemble resolves labels, forward and backward")
def test_assemble_labels(sub):
    assemble = has(sub, "assemble")
    # loop is at address 0; the beq at address 4 jumps back by -4:
    # imm -4 = 0x1FFC -> bit 12 = 1, imm[10:5] = 111111, imm[4:1] = 1110, imm[11] = 1.
    equal(assemble(["loop: addi x1, x1, -1", "beq x1, x0, loop"]), [0xFFF08093, 0xFE008EE3])
    program = [
        "      addi x1, x0, 3",     # 0x00
        "loop: addi x1, x1, -1",    # 0x04
        "      beq  x1, x0, done",  # 0x08: done is at 0x10, offset 8
        "      jal  x0, loop",      # 0x0C: loop is at 0x04, offset -8
        "done: sw   x1, 8(x2)",     # 0x10
    ]
    want = [assemble_line_word(sub, t) for t in
            ["addi x1, x0, 3", "addi x1, x1, -1", "beq x1, x0, 8", "jal x0, -8", "sw x1, 8(x2)"]]
    equal(assemble(program), want, label="loop program")
    equal(want[3], 0xFF9FF06F, label="jal x0, -8 (checked against LLVM)")
    # Labels on their own lines, comments, and blank lines take no space.
    equal(assemble(["# start", "", "top:", "  addi x5, x5, 1  # count", "  jal x0, top"]),
          [0x00128293, 0xFFDFF06F])


def assemble_line_word(sub, text):
    return has(sub, "assemble_line")(text)


@check("disassemble_word decodes every known word back to its text")
def test_disassemble(sub):
    disassemble_word = has(sub, "disassemble_word")
    for text, word in KNOWN:
        equal(disassemble_word(word), text, label=f"{word:#010x}")
    _fails(disassemble_word, 0x00000000)
    _fails(disassemble_word, 0xFFFFFFFF)


@check("assemble_line and disassemble_word round-trip on 500 random instructions")
def test_roundtrip(sub):
    assemble_line, disassemble_word = has(sub, "assemble_line"), has(sub, "disassemble_word")
    rng = random.Random(0)
    for _ in range(500):
        kind = rng.choice(["add", "sub", "addi", "lw", "sw", "beq", "jal"])
        a, b, c = rng.randrange(32), rng.randrange(32), rng.randrange(32)
        if kind in ("add", "sub"):
            text = f"{kind} x{a}, x{b}, x{c}"
        elif kind == "addi":
            text = f"addi x{a}, x{b}, {rng.randrange(-2048, 2048)}"
        elif kind == "lw":
            text = f"lw x{a}, {rng.randrange(-2048, 2048)}(x{b})"
        elif kind == "sw":
            text = f"sw x{a}, {rng.randrange(-2048, 2048)}(x{b})"
        elif kind == "beq":
            text = f"beq x{a}, x{b}, {2 * rng.randrange(-2048, 2048)}"
        else:
            text = f"jal x{a}, {2 * rng.randrange(-524288, 524288)}"
        word = assemble_line(text)
        if not 0 <= word < (1 << 32):
            fail(f"{text!r} assembled to {word!r}, which is not a 32-bit word")
        equal(disassemble_word(word), text, label=f"round trip of {text!r} ({word:#010x})")
