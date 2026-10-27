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
    """Return (live_in, live_out): one set of names per instruction, labels included."""
    n = len(prog.code)
    live_in = [set() for _ in range(n)]
    live_out = [set() for _ in range(n)]
    changed = True
    while changed:  # a loop's back edge feeds later instructions into earlier ones
        changed = False
        for i in reversed(range(n)):  # backwards converges fastest, but any order works
            ins = prog.code[i]
            out = set()
            for j in successors(prog, i):
                out |= live_in[j]
            new_in = set(uses(ins)) | (out - {defs(ins)})
            if out != live_out[i] or new_in != live_in[i]:
                live_out[i], live_in[i] = out, new_in
                changed = True
    return live_in, live_out


def interference_graph(prog: Program) -> dict[str, set[str]]:
    """Map every variable to the set of variables it cannot share a register with."""
    _, live_out = liveness(prog)
    graph: dict[str, set[str]] = {p: set() for p in prog.params}

    def add_edge(a, b):
        graph.setdefault(a, set())
        graph.setdefault(b, set())
        if a != b:
            graph[a].add(b)
            graph[b].add(a)

    for i, ins in enumerate(prog.code):
        for name in uses(ins):
            graph.setdefault(name, set())
        d = defs(ins)
        if d is not None:
            graph.setdefault(d, set())
            for v in live_out[i]:
                add_edge(d, v)  # writing d must not clobber anything still needed
    for a in prog.params:  # parameters all arrive at the same moment
        for b in prog.params:
            add_edge(a, b)
    return graph


def color_graph(graph: dict[str, set[str]], k: int) -> tuple[dict[str, int], list[str]]:
    """Color the graph with colors 0 .. k-1. Return (colors, spilled)."""
    work = {v: set(nb) for v, nb in graph.items()}
    stack = []
    while work:
        easy = [v for v in work if len(work[v]) < k]
        if easy:
            pick = min(easy, key=lambda v: (len(work[v]), v))
        else:  # stuck: optimistically push the most constrained node
            pick = min(work, key=lambda v: (-len(work[v]), v))
        stack.append(pick)
        for nb in work.pop(pick):
            work[nb].discard(pick)

    colors: dict[str, int] = {}
    spilled: list[str] = []
    while stack:
        v = stack.pop()
        taken = {colors[nb] for nb in graph[v] if nb in colors}
        free = [c for c in range(k) if c not in taken]
        if free:
            colors[v] = free[0]
        else:
            spilled.append(v)
    return colors, sorted(spilled)


def allocate(prog: Program, k: int) -> Allocation:
    """Choose where each variable lives, using at most k of REGS."""
    colors, spilled = color_graph(interference_graph(prog), k)
    reg = {v: REGS[c] for v, c in colors.items()}
    slot = {v: n for n, v in enumerate(spilled)}
    return Allocation(reg, slot)


_OPS = {"add": "add", "sub": "sub", "mul": "imul"}


def emit_x86(prog: Program, alloc: Allocation) -> str:
    """x86-64 Intel assembly for `prog`, as a function named prog.name."""
    nbytes = 8 * len(alloc.slot)

    def loc(name: str) -> str:
        if name in alloc.reg:
            return alloc.reg[name]
        return f"qword ptr [rsp + {8 * alloc.slot[name]}]"

    out = [f".globl {prog.name}", f"{prog.name}:"]
    if nbytes:
        out.append(f"  sub rsp, {nbytes}")
    for param, source in zip(prog.params, ("rdi", "rsi")):
        out.append(f"  mov {loc(param)}, {source}")
    for ins in prog.code:
        op = ins.op
        if op == "const":
            out.append(f"  mov {loc(ins.dest)}, {ins.args[0]}")
        elif op == "copy":
            out += [f"  mov rax, {loc(ins.args[0])}", f"  mov {loc(ins.dest)}, rax"]
        elif op in _OPS:
            a, b = ins.args
            out += [
                f"  mov rax, {loc(a)}",
                f"  {_OPS[op]} rax, {loc(b)}",
                f"  mov {loc(ins.dest)}, rax",
            ]
        elif op == "label":
            out.append(f".L{ins.args[0]}:")
        elif op == "jmp":
            out.append(f"  jmp .L{ins.args[0]}")
        elif op == "jnz":
            out += [f"  cmp {loc(ins.args[0])}, 0", f"  jne .L{ins.args[1]}"]
        elif op == "ret":
            out.append(f"  mov rax, {loc(ins.args[0])}")
            if nbytes:
                out.append(f"  add rsp, {nbytes}")
            out.append("  ret")
        else:
            raise ValueError(f"unknown instruction {op!r}")
    return "\n".join(out) + "\n"


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
