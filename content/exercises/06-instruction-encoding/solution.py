"""Instruction encoding: a tiny assembler and disassembler for RV32I.

Reference solution.

Supported instructions: add, sub, addi, lw, sw, beq, jal.
"""

# Opcodes (low 7 bits of the word).
OP_R = 0b0110011      # add, sub
OP_I = 0b0010011      # addi
OP_LOAD = 0b0000011   # lw
OP_STORE = 0b0100011  # sw
OP_BRANCH = 0b1100011  # beq
OP_JAL = 0b1101111    # jal

ABI_NAMES = {"zero": 0, "ra": 1, "sp": 2}


def register_number(name):
    """'x5' -> 5, 'zero' -> 0, 'ra' -> 1, 'sp' -> 2. ValueError otherwise."""
    name = name.strip().lower()
    if name in ABI_NAMES:
        return ABI_NAMES[name]
    if name.startswith("x") and name[1:].isdigit() and 0 <= int(name[1:]) <= 31:
        return int(name[1:])
    raise ValueError(f"unknown register {name!r}")


def sign_extend(value, bits):
    """Read the low `bits` bits of value as a two's complement number."""
    value &= (1 << bits) - 1
    if value >> (bits - 1):          # top bit set: the number is negative
        value -= 1 << bits
    return value


def _check_imm(imm, bits, what, even=False):
    low, high = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    if not low <= imm <= high:
        raise ValueError(f"{what} {imm} does not fit in {bits} signed bits ({low}..{high})")
    if even and imm % 2:
        raise ValueError(f"{what} {imm} must be even")


def encode_r(funct7, rs2, rs1, funct3, rd, opcode):
    # 31..25 funct7 | 24..20 rs2 | 19..15 rs1 | 14..12 funct3 | 11..7 rd | 6..0 opcode
    return (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def encode_i(imm, rs1, funct3, rd, opcode):
    _check_imm(imm, 12, "immediate")
    # 31..20 imm[11:0] | 19..15 rs1 | 14..12 funct3 | 11..7 rd | 6..0 opcode
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def encode_s(imm, rs2, rs1, funct3, opcode):
    _check_imm(imm, 12, "offset")
    imm &= 0xFFF
    # 31..25 imm[11:5] | 24..20 rs2 | 19..15 rs1 | 14..12 funct3 | 11..7 imm[4:0] | opcode
    return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | ((imm & 0x1F) << 7) | opcode


def encode_b(imm, rs2, rs1, funct3, opcode):
    _check_imm(imm, 13, "branch offset", even=True)
    imm &= 0x1FFF
    # 31 imm[12] | 30..25 imm[10:5] | 24..20 rs2 | 19..15 rs1 | 14..12 funct3
    # | 11..8 imm[4:1] | 7 imm[11] | 6..0 opcode
    return (
        (((imm >> 12) & 1) << 31)
        | (((imm >> 5) & 0x3F) << 25)
        | (rs2 << 20) | (rs1 << 15) | (funct3 << 12)
        | (((imm >> 1) & 0xF) << 8)
        | (((imm >> 11) & 1) << 7)
        | opcode
    )


def encode_j(imm, rd, opcode):
    _check_imm(imm, 21, "jump offset", even=True)
    imm &= 0x1FFFFF
    # 31 imm[20] | 30..21 imm[10:1] | 20 imm[11] | 19..12 imm[19:12] | 11..7 rd | opcode
    return (
        (((imm >> 20) & 1) << 31)
        | (((imm >> 1) & 0x3FF) << 21)
        | (((imm >> 11) & 1) << 20)
        | (((imm >> 12) & 0xFF) << 12)
        | (rd << 7)
        | opcode
    )


def _number(text):
    return int(text.strip(), 0)


def _split(line):
    """'lw x5, 8(x2)' -> ('lw', ['x5', '8(x2)'])."""
    line = line.split("#")[0].strip()
    parts = line.split(None, 1)
    if not parts:
        raise ValueError("empty line")
    operands = [p.strip() for p in parts[1].split(",")] if len(parts) > 1 else []
    return parts[0].lower(), operands


def _memory_operand(text):
    """'8(x2)' -> (8, 2)."""
    if "(" not in text or not text.endswith(")"):
        raise ValueError(f"expected offset(register), got {text!r}")
    offset, reg = text[:-1].split("(")
    return _number(offset), register_number(reg)


def assemble_line(line):
    """Assemble one instruction with numeric offsets into a 32-bit word."""
    op, args = _split(line)
    expected = {"add": 3, "sub": 3, "addi": 3, "lw": 2, "sw": 2, "beq": 3, "jal": 2}
    if op not in expected:
        raise ValueError(f"unknown instruction {op!r}")
    if len(args) != expected[op]:
        raise ValueError(f"{op} takes {expected[op]} operands, got {len(args)}")
    if op in ("add", "sub"):
        rd, rs1, rs2 = (register_number(a) for a in args)
        return encode_r(0b0100000 if op == "sub" else 0, rs2, rs1, 0b000, rd, OP_R)
    if op == "addi":
        return encode_i(_number(args[2]), register_number(args[1]), 0b000, register_number(args[0]), OP_I)
    if op == "lw":
        offset, base = _memory_operand(args[1])
        return encode_i(offset, base, 0b010, register_number(args[0]), OP_LOAD)
    if op == "sw":
        offset, base = _memory_operand(args[1])
        return encode_s(offset, register_number(args[0]), base, 0b010, OP_STORE)
    if op == "beq":
        return encode_b(_number(args[2]), register_number(args[1]), register_number(args[0]), 0b000, OP_BRANCH)
    return encode_j(_number(args[1]), register_number(args[0]), OP_JAL)  # jal


def assemble(lines):
    """Assemble a program with labels. Branch and jump targets may be labels."""
    # Pass 1: strip comments and labels, remember each label's address.
    labels, body = {}, []
    for raw in lines:
        text = raw.split("#")[0].strip()
        while ":" in text:
            name, text = text.split(":", 1)
            labels[name.strip()] = 4 * len(body)
            text = text.strip()
        if text:
            body.append(text)
    # Pass 2: replace a label operand with (label address - this address).
    words = []
    for index, text in enumerate(body):
        op, args = _split(text)
        if op in ("beq", "jal") and args and args[-1] in labels:
            args[-1] = str(labels[args[-1]] - 4 * index)
        words.append(assemble_line(f"{op} " + ", ".join(args)))
    return words


def disassemble_word(word):
    """Decode a 32-bit word back to text such as 'addi x1, x0, 5'."""
    opcode = word & 0x7F
    rd = (word >> 7) & 0x1F
    funct3 = (word >> 12) & 0x7
    rs1 = (word >> 15) & 0x1F
    rs2 = (word >> 20) & 0x1F
    funct7 = word >> 25
    if opcode == OP_R and funct3 == 0 and funct7 in (0, 0b0100000):
        name = "sub" if funct7 else "add"
        return f"{name} x{rd}, x{rs1}, x{rs2}"
    if opcode == OP_I and funct3 == 0:
        return f"addi x{rd}, x{rs1}, {sign_extend(word >> 20, 12)}"
    if opcode == OP_LOAD and funct3 == 0b010:
        return f"lw x{rd}, {sign_extend(word >> 20, 12)}(x{rs1})"
    if opcode == OP_STORE and funct3 == 0b010:
        imm = ((word >> 25) << 5) | ((word >> 7) & 0x1F)
        return f"sw x{rs2}, {sign_extend(imm, 12)}(x{rs1})"
    if opcode == OP_BRANCH and funct3 == 0:
        imm = (
            (((word >> 31) & 1) << 12)
            | (((word >> 7) & 1) << 11)
            | (((word >> 25) & 0x3F) << 5)
            | (((word >> 8) & 0xF) << 1)
        )
        return f"beq x{rs1}, x{rs2}, {sign_extend(imm, 13)}"
    if opcode == OP_JAL:
        imm = (
            (((word >> 31) & 1) << 20)
            | (((word >> 12) & 0xFF) << 12)
            | (((word >> 20) & 1) << 11)
            | (((word >> 21) & 0x3FF) << 1)
        )
        return f"jal x{rd}, {sign_extend(imm, 21)}"
    raise ValueError(f"cannot decode {word:#010x}")


if __name__ == "__main__":
    program = [
        "      addi x1, x0, 3",
        "loop: addi x1, x1, -1",
        "      beq  x1, x0, done",
        "      jal  x0, loop",
        "done: sw   x1, 8(x2)",
    ]
    for address, word in enumerate(assemble(program)):
        print(f"{4 * address:#06x}  {word:08x}  {disassemble_word(word)}")
