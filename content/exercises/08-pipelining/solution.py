"""Pipelining and hazards: a five-stage cycle-count model.

Reference solution.

Stages: IF, ID, EX, MEM, WB. One instruction enters per cycle. The register
file is written in the first half of a cycle and read in the second half, so an
instruction can read in ID during the same cycle its producer is in WB.
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
    """Cycles for n independent instructions: the first takes 5, each later one adds 1."""
    return 0 if n == 0 else n + 4


def _producer(program, j, reg):
    """Index of the latest instruction before j that writes reg, or None."""
    for i in range(j - 1, -1, -1):
        if program[i].dest == reg:
            return i
    return None


def find_raw(program):
    """Read-after-write hazards as sorted (producer, consumer) pairs.

    A hazard is a consumer that reads a register written by one of the two
    instructions just before it (the nearest writer within distance 2).
    """
    pairs = set()
    for j, instr in enumerate(program):
        for reg in instr.srcs:
            for i in range(j - 1, max(j - 3, -1), -1):      # distance 1, then 2
                if program[i].dest == reg:
                    pairs.add((i, j))
                    break                                   # only the nearest writer counts
    return sorted(pairs)


def stalls_no_forwarding(program):
    """Stall cycles inserted before each instruction when there is no forwarding."""
    stalls, id_cycle = [], []
    for j, instr in enumerate(program):
        earliest = 2 if j == 0 else id_cycle[j - 1] + 1     # in order, one per cycle
        for reg in instr.srcs:
            p = _producer(program, j, reg)
            if p is not None:
                earliest = max(earliest, id_cycle[p] + 3)   # wait for the producer's WB
        stalls.append(0 if j == 0 else earliest - (id_cycle[j - 1] + 1))
        id_cycle.append(earliest)
    return stalls


def stalls_forwarding(program):
    """Stall cycles inserted before each instruction when results are forwarded.

    Only a load followed immediately by an instruction that reads its result
    needs a bubble: one cycle.
    """
    stalls = []
    for j, instr in enumerate(program):
        prev = program[j - 1] if j else None
        hit = prev is not None and prev.is_load and prev.dest in instr.srcs
        stalls.append(1 if hit else 0)
    return stalls


def total_cycles(program, forwarding=False):
    """Total cycles to run the program, from the first IF to the last WB."""
    if not program:
        return 0
    stalls = stalls_forwarding(program) if forwarding else stalls_no_forwarding(program)
    return ideal_cycles(len(program)) + sum(stalls)


def cpi(program, forwarding=False):
    """Cycles per instruction."""
    return total_cycles(program, forwarding) / len(program)


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
