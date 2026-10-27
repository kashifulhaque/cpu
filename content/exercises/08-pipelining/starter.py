"""Pipelining and hazards: a five-stage cycle-count model.

Stages: IF, ID, EX, MEM, WB. One instruction enters per cycle. The register
file is written in the first half of a cycle and read in the second half, so an
instruction can read in ID during the same cycle its producer is in WB.

`Instr` and `parse` are given. Fill in the functions below them.
"""

from dataclasses import dataclass


@dataclass
class Instr:
    """One instruction: its text, the register it writes, the registers it reads."""

    text: str
    dest: str | None
    srcs: tuple
    is_load: bool = False


def parse(line):
    """Turn assembly text into an Instr. Register x0 is never a dependency.

    parse("add x3, x1, x2")  -> dest x3, srcs (x1, x2)
    parse("lw x5, 0(x1)")    -> dest x5, srcs (x1,), is_load
    parse("sw x5, 4(x1)")    -> dest None, srcs (x5, x1)
    parse("beq x1, x2, L")   -> dest None, srcs (x1, x2)
    """
    line = line.strip()
    op, _, rest = line.partition(" ")
    args = [a.strip() for a in rest.replace("(", ",").replace(")", "").split(",")]
    if op in ("add", "sub", "and", "or", "addi"):
        dest, srcs = args[0], [args[1]] + ([args[2]] if op != "addi" else [])
    elif op == "lw":
        dest, srcs = args[0], [args[2]]
    elif op == "sw":
        dest, srcs = None, [args[0], args[2]]
    elif op == "beq":
        dest, srcs = None, [args[0], args[1]]
    else:
        raise ValueError(f"unknown instruction {op!r}")
    regs = [r for r in srcs if r != "x0"]
    return Instr(line, None if dest in (None, "x0") else dest, tuple(regs), op == "lw")


def ideal_cycles(n):
    """Cycles for n independent instructions: the first takes 5, each later one adds 1.

    ideal_cycles(1) == 5, ideal_cycles(4) == 8, ideal_cycles(0) == 0.
    """
    raise NotImplementedError


def find_raw(program):
    """Read-after-write hazards as a sorted list of (producer, consumer) index pairs.

    A hazard is a consumer that reads a register written by one of the two
    instructions just before it. If both of those write the register, the
    nearer one is the producer. Each pair appears once.

    program = add x1,x2,x3 / add x4,x1,x5  ->  [(0, 1)]
    """
    raise NotImplementedError


def stalls_no_forwarding(program):
    """Stall cycles inserted before each instruction when there is no forwarding.

    Returns a list with one number per instruction. A consumer cannot leave ID
    until the cycle its producer is in WB.

    add x1,x2,x3 / add x4,x1,x5            -> [0, 2]
    add x1,x2,x3 / add x6,x7,x8 / add x4,x1,x5  -> [0, 0, 1]
    """
    raise NotImplementedError


def stalls_forwarding(program):
    """Stall cycles before each instruction when results are forwarded.

    Only a load followed immediately by a reader of its result stalls, by one cycle.

    lw x1,0(x2) / add x3,x1,x4  -> [0, 1]
    add x1,x2,x3 / add x4,x1,x5 -> [0, 0]
    """
    raise NotImplementedError


def total_cycles(program, forwarding=False):
    """Total cycles from the first IF to the last WB. 0 for an empty program.

    Two dependent adds: total_cycles(p) == 8 without forwarding, 6 with it.
    """
    raise NotImplementedError


def cpi(program, forwarding=False):
    """Cycles per instruction: total_cycles / number of instructions (a float)."""
    raise NotImplementedError


if __name__ == "__main__":
    program = [parse(line) for line in [
        "lw x1, 0(x2)",
        "lw x3, 4(x2)",
        "add x4, x1, x3",
        "sw x4, 8(x2)",
    ]]
    print("RAW hazards:", find_raw(program))
    for forwarding in (False, True):
        label = "with forwarding" if forwarding else "no forwarding  "
        print(label, "cycles:", total_cycles(program, forwarding), "CPI:", round(cpi(program, forwarding), 2))
