"""Register allocation and x86-64 code generation for a tiny three-address IR."""

import ctypes
from dataclasses import dataclass

import cputools

# ---------------------------------------------------------------------------
# The IR (provided, and the same in the solution).
#
# A program is a list of instructions, with labels and jumps. Names may be
# assigned more than once (this is not SSA), so a loop can update a variable.
#
#   d = const n        d = n   (an int literal)
#   d = copy a         d = a
#   d = add a b        d = a + b     (also sub, mul; operands are names)
#   L:                 a label
#   jmp L              jump to L
#   jnz a L            jump to L if a is not zero, else fall through
#   ret a              return a
# ---------------------------------------------------------------------------

REGS = ["rcx", "r8", "r9", "r10", "r11"]  # the registers the allocator may hand out


@dataclass(frozen=True)
class Instr:
    op: str
    dest: str | None  # the name this instruction writes, if any
    args: tuple  # names, label names, or (for const) one int


@dataclass(frozen=True)
class Program:
    name: str
    params: tuple  # at most two names; they arrive in rdi and rsi
    code: tuple  # of Instr


def parse_program(name: str, params: str, text: str) -> Program:
    """Build a Program: parse_program("f", "a b", "t = add a b\\nret t")."""
    code = []
    for line in text.strip().splitlines():
        line = line.strip()
        if line.endswith(":"):
            code.append(Instr("label", None, (line[:-1],)))
            continue
        words = line.replace("=", " ").split()
        if words[0] in ("jmp", "jnz", "ret"):
            code.append(Instr(words[0], None, tuple(words[1:])))
        elif words[1] == "const":
            code.append(Instr("const", words[0], (int(words[2]),)))
        else:
            code.append(Instr(words[1], words[0], tuple(words[2:])))
    return Program(name, tuple(params.split()), tuple(code))


def uses(ins: Instr) -> list[str]:
    """The variable names an instruction reads."""
    if ins.op in ("copy", "ret"):
        return [ins.args[0]]
    if ins.op in ("add", "sub", "mul"):
        return list(ins.args)
    if ins.op == "jnz":
        return [ins.args[0]]
    return []


def defs(ins: Instr) -> str | None:
    """The variable name an instruction writes, or None."""
    return ins.dest


def successors(prog: Program, i: int) -> list[int]:
    """Indexes of the instructions that can run right after instruction i."""
    ins = prog.code[i]
    target = {j.args[0]: k for k, j in enumerate(prog.code) if j.op == "label"}
    if ins.op == "ret":
        return []
    if ins.op == "jmp":
        return [target[ins.args[0]]]
    nxt = [i + 1] if i + 1 < len(prog.code) else []
    if ins.op == "jnz":
        return nxt + [target[ins.args[1]]]
    return nxt


@dataclass
class Allocation:
    """Where every variable lives: a register name, or a stack slot number."""

    reg: dict  # name -> register, e.g. {"a": "rcx"}
    slot: dict  # name -> slot number 0, 1, 2, ... for spilled variables


# ---------------------------------------------------------------------------
# What you write
# ---------------------------------------------------------------------------


def liveness(prog: Program) -> tuple[list[set], list[set]]:
    """Return (live_in, live_out): one set of names per instruction, labels included.

    A name is live at a point if some path from there reads it before writing it.
        live_in[i]  = uses(i) | (live_out[i] - {defs(i)})
        live_out[i] = union of live_in[j] for j in successors(prog, i)
    Repeat until nothing changes, so that loops settle.

    For `t = add a b; ret t` with params a, b:
        live_in  = [{a, b}, {t}]       live_out = [{t}, set()]
    """
    raise NotImplementedError


def interference_graph(prog: Program) -> dict[str, set[str]]:
    """Map every variable to the set of variables it cannot share a register with.

    Every variable (parameters included) is a key, even with no neighbours.
    Two variables interfere when one is defined at a point where the other is
    live: for each instruction that defines d, add an edge from d to every other
    name in live_out[i]. Parameters all arrive at entry together, so add edges
    between every pair of parameters, whether or not the program reads them.
    The graph is symmetric: if b is in g["a"] then a is in g["b"].
    """
    raise NotImplementedError


def color_graph(graph: dict[str, set[str]], k: int) -> tuple[dict[str, int], list[str]]:
    """Color the graph with colors 0 .. k-1. Return (colors, spilled).

    Neighbours never share a color. A node that cannot be colored goes in
    `spilled`, sorted by name, and is not in `colors`.

    Simplify: with a working copy of the graph, repeatedly pick the node with
    the smallest degree if that degree is below k (ties: smallest name), else
    the node with the largest degree (ties: smallest name). Push it on a stack
    and remove it from the copy.
    Select: pop nodes. Give each the lowest color that no already-colored
    neighbour (in the original graph) uses. With none free, spill it.
    """
    raise NotImplementedError


def allocate(prog: Program, k: int) -> Allocation:
    """Choose where each variable lives, using at most k of REGS (k <= 5).

    Build the interference graph, color it, give color c the register
    REGS[c], and give each spilled variable a stack slot: 0, 1, 2, ... in
    order of name.
    """
    raise NotImplementedError


def emit_x86(prog: Program, alloc: Allocation) -> str:
    """x86-64 Intel assembly for `prog`, as a function named prog.name.

    Start with `.globl <name>` and `<name>:`. Arguments are 64-bit integers: the
    first parameter arrives in rdi, the second in rsi, and the result goes in rax.

    Every variable is in a register (alloc.reg) or in memory at
    `qword ptr [rsp + 8*slot]` (alloc.slot). If any slot exists, start with
    `sub rsp, 8*nslots` and run `add rsp, 8*nslots` before every `ret`.
    Move the parameters to their homes first.

    Select instructions, doing the work in rax so memory operands just work:
        const d n   mov <d>, n
        copy d a    mov rax, <a> ; mov <d>, rax
        add d a b   mov rax, <a> ; add rax, <b> ; mov <d>, rax   (sub; imul for mul)
        label L     .L<L>:
        jmp L       jmp .L<L>
        jnz a L     cmp <a>, 0 ; jne .L<L>
        ret a       mov rax, <a> ; (add rsp, ...) ; ret
    where <x> is the register or memory operand for x.
    """
    raise NotImplementedError


if __name__ == "__main__":
    prog = parse_program(
        "sum_to",
        "n",
        """
        s = const 0
        top:
        s = add s n
        one = const 1
        n = sub n one
        jnz n top
        ret s
        """,
    )
    live_in, live_out = liveness(prog)
    for i, ins in enumerate(prog.code):
        print(f"{i}: live_in={sorted(live_in[i])} live_out={sorted(live_out[i])}")
    print("interference:", {k: sorted(v) for k, v in sorted(interference_graph(prog).items())})
    asm = emit_x86(prog, allocate(prog, 3))
    print(asm)
    lib = cputools.assemble(asm)
    lib.sum_to.restype = ctypes.c_int64
    lib.sum_to.argtypes = [ctypes.c_int64]
    print("sum_to(10) =", lib.sum_to(10))
