"""Instruction encoding: a tiny assembler and disassembler for RV32I.

Supported instructions: add, sub, addi, lw, sw, beq, jal.
Fill in every function that raises NotImplementedError.
"""

# Opcodes (the low 7 bits of a word). Given.
OP_R = 0b0110011       # add, sub
OP_I = 0b0010011       # addi
OP_LOAD = 0b0000011    # lw
OP_STORE = 0b0100011   # sw
OP_BRANCH = 0b1100011  # beq
OP_JAL = 0b1101111     # jal

ABI_NAMES = {"zero": 0, "ra": 1, "sp": 2}  # Given: the only ABI names this exercise needs.


def register_number(name):
    """Turn a register name into its number.

    register_number("x5") == 5, register_number("zero") == 0,
    register_number("sp") == 2. Raise ValueError for anything else, such as
    "x32" or "foo".
    """
    raise NotImplementedError


def sign_extend(value, bits):
    """Read the low `bits` bits of `value` as a two's complement number.

    sign_extend(0xFFF, 12) == -1, sign_extend(0x7FF, 12) == 2047,
    sign_extend(0x800, 12) == -2048.
    """
    raise NotImplementedError


def encode_r(funct7, rs2, rs1, funct3, rd, opcode):
    """Pack an R-type word (add, sub). All arguments are small ints.

    encode_r(0, 2, 1, 0, 3, OP_R) == 0x002081B3   # add x3, x1, x2
    """
    raise NotImplementedError


def encode_i(imm, rs1, funct3, rd, opcode):
    """Pack an I-type word (addi, lw). `imm` is a signed 12-bit number.

    encode_i(5, 0, 0, 1, OP_I) == 0x00500093   # addi x1, x0, 5
    Raise ValueError when imm is outside -2048..2047.
    """
    raise NotImplementedError


def encode_s(imm, rs2, rs1, funct3, opcode):
    """Pack an S-type word (sw). `imm` is a signed 12-bit offset.

    encode_s(8, 5, 2, 2, OP_STORE) == 0x00512423   # sw x5, 8(x2)
    Raise ValueError when imm is outside -2048..2047.
    """
    raise NotImplementedError


def encode_b(imm, rs2, rs1, funct3, opcode):
    """Pack a B-type word (beq). `imm` is a signed, even 13-bit byte offset.

    encode_b(8, 2, 1, 0, OP_BRANCH) == 0x00208463   # beq x1, x2, 8
    Raise ValueError when imm is odd or outside -4096..4094.
    """
    raise NotImplementedError


def encode_j(imm, rd, opcode):
    """Pack a J-type word (jal). `imm` is a signed, even 21-bit byte offset.

    encode_j(8, 1, OP_JAL) == 0x008000EF   # jal x1, 8
    Raise ValueError when imm is odd or outside -1048576..1048574.
    """
    raise NotImplementedError


def assemble_line(line):
    """Assemble one instruction whose branch and jump offsets are numbers.

    assemble_line("addi x1, x0, 5") == 0x00500093
    assemble_line("lw x5, 8(x2)")   == 0x00812283
    A '#' starts a comment. Raise ValueError for an unknown instruction, a
    wrong operand count, a bad register, or an immediate that does not fit.
    """
    raise NotImplementedError


def assemble(lines):
    """Assemble a list of lines, with labels, into a list of 32-bit words.

    A label is a name followed by ':' on its own line or before an
    instruction. beq and jal may name a label; the offset is
    label_address - this_instruction_address, with 4 bytes per instruction.

    assemble(["loop: addi x1, x1, -1", "beq x1, x0, loop"])
        == [0xFFF08093, 0xFE008EE3]
    """
    raise NotImplementedError


def disassemble_word(word):
    """Decode a 32-bit word to text, with signed decimal immediates.

    disassemble_word(0x00500093) == "addi x1, x0, 5"
    disassemble_word(0x402081B3) == "sub x3, x1, x2"
    Raise ValueError for a word that is none of the seven instructions.
    """
    raise NotImplementedError


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
