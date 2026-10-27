"""Optimization passes over a tiny three-address IR, and a comparison with LLVM."""

from dataclasses import dataclass

import cputools

# ---------------------------------------------------------------------------
# The IR (provided, and the same in the solution).
#
# A function is a straight line of instructions with no branches. Every name is
# assigned once. An operand is an int literal or the name of an earlier value.
#
#   const d n      d = n
#   copy  d a      d = a
#   add sub mul shl and   d = a OP b     (32-bit wrap-around arithmetic)
#   ret   a        return a
# ---------------------------------------------------------------------------

BINARY_OPS = ("add", "sub", "mul", "shl", "and")


def wrap32(n: int) -> int:
    """Wrap an int to a signed 32-bit value."""
    n &= 0xFFFFFFFF
    return n - (1 << 32) if n & 0x80000000 else n


def eval_op(op: str, a: int, b: int) -> int:
    """The value of `a OP b` for two ints, wrapped to 32 bits."""
    if op == "add":
        return wrap32(a + b)
    if op == "sub":
        return wrap32(a - b)
    if op == "mul":
        return wrap32(a * b)
    if op == "shl":
        return wrap32(a << (b & 31))
    if op == "and":
        return wrap32(a & b)
    raise ValueError(f"unknown op {op!r}")


@dataclass(frozen=True)
class Instr:
    op: str
    dest: str | None  # None for `ret`
    args: tuple  # each item is an int or a str (a name)


@dataclass(frozen=True)
class Function:
    name: str
    params: tuple
    body: tuple  # of Instr


def make(name: str, params: str, text: str) -> Function:
    """Build a Function from text: `make("f", "x y", "t = add x 1\\nret t")`."""

    def operand(word: str):
        return int(word) if word.lstrip("-").isdigit() else word

    body = []
    for line in text.strip().splitlines():
        words = line.replace("=", " ").split()
        if words[0] == "ret":
            body.append(Instr("ret", None, (operand(words[1]),)))
        else:
            dest, op, *args = words
            body.append(Instr(op, dest, tuple(operand(a) for a in args)))
    return Function(name, tuple(params.split()), tuple(body))


def format_function(func: Function) -> str:
    """Readable text, one instruction per line."""
    lines = [f"{func.name}({', '.join(func.params)}):"]
    for i in func.body:
        args = " ".join(str(a) for a in i.args)
        lines.append(f"  ret {args}" if i.op == "ret" else f"  {i.dest} = {i.op} {args}")
    return "\n".join(lines)


def evaluate(func: Function, args: list[int]) -> int:
    """Run a function on integer arguments."""
    env = dict(zip(func.params, (wrap32(a) for a in args)))

    def value(a):
        return a if isinstance(a, int) else env[a]

    for i in func.body:
        if i.op == "ret":
            return value(i.args[0])
        if i.op in ("const", "copy"):
            env[i.dest] = wrap32(value(i.args[0]))
        else:
            env[i.dest] = eval_op(i.op, value(i.args[0]), value(i.args[1]))
    raise ValueError("function has no ret")


def to_llvm(func: Function) -> str:
    """LLVM IR text for a function, with every value an i32.

    `const` and `copy` have no LLVM instruction, so they become `add 0, n` and
    `add a, 0`. Optimizing LLVM removes them, which makes the instruction counts
    before and after easy to compare with yours.
    """

    def arg(a):
        return str(a) if isinstance(a, int) else f"%{a}"

    params = ", ".join(f"i32 %{p}" for p in func.params)
    lines = [f"define i32 @{func.name}({params}) {{", "entry:"]
    for i in func.body:
        if i.op == "ret":
            lines.append(f"  ret i32 {arg(i.args[0])}")
        elif i.op == "const":
            lines.append(f"  %{i.dest} = add i32 0, {i.args[0]}")
        elif i.op == "copy":
            lines.append(f"  %{i.dest} = add i32 {arg(i.args[0])}, 0")
        else:
            lines.append(f"  %{i.dest} = {i.op} i32 {arg(i.args[0])}, {arg(i.args[1])}")
    lines.append("}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# What you write
# ---------------------------------------------------------------------------


def _subst(args: tuple, known: dict) -> tuple:
    """Replace each name in `args` that `known` maps to a value."""
    return tuple(known.get(a, a) if isinstance(a, str) else a for a in args)


def _is_int(a) -> bool:
    return isinstance(a, int)


def fold_constants(func: Function) -> Function:
    """Constant propagation and folding in one forward walk."""
    consts: dict[str, int] = {}
    out = []
    for ins in func.body:
        args = _subst(ins.args, consts)
        if ins.op in BINARY_OPS and _is_int(args[0]) and _is_int(args[1]):
            ins = Instr("const", ins.dest, (eval_op(ins.op, args[0], args[1]),))
        elif ins.op == "copy" and _is_int(args[0]):
            ins = Instr("const", ins.dest, (wrap32(args[0]),))
        else:
            ins = Instr(ins.op, ins.dest, args)
        if ins.op == "const":
            consts[ins.dest] = ins.args[0]
        out.append(ins)
    return Function(func.name, func.params, tuple(out))


def _is_pow2(n) -> bool:
    return _is_int(n) and n > 1 and n & (n - 1) == 0


def _simplify(ins: Instr) -> Instr:
    if ins.op not in BINARY_OPS:
        return ins
    a, b = ins.args
    if _is_int(a) and _is_int(b):
        return ins  # folding's job
    d = ins.dest
    copy = lambda x: Instr("copy", d, (x,))  # noqa: E731
    zero = Instr("const", d, (0,))
    if ins.op == "add":
        if a == 0:
            return copy(b)
        if b == 0:
            return copy(a)
    elif ins.op == "sub":
        if b == 0:
            return copy(a)
        if a == b:  # the same name (ints were handled above)
            return zero
    elif ins.op == "mul":
        if b == 1:
            return copy(a)
        if a == 1:
            return copy(b)
        if a == 0 or b == 0:
            return zero
        if _is_pow2(b):
            return Instr("shl", d, (a, b.bit_length() - 1))
        if _is_pow2(a):
            return Instr("shl", d, (b, a.bit_length() - 1))
    elif ins.op == "shl":
        if b == 0:
            return copy(a)
        if a == 0:
            return zero
    elif ins.op == "and":
        if a == 0 or b == 0:
            return zero
        if a == b:
            return copy(a)
    return ins


def simplify_algebra(func: Function) -> Function:
    """Rewrite instructions that have an algebraic identity."""
    return Function(func.name, func.params, tuple(_simplify(i) for i in func.body))


def propagate_copies(func: Function) -> Function:
    """Replace every use of a `copy d s` (s a name) with s, following chains."""
    alias: dict[str, str] = {}
    out = []
    for ins in func.body:
        args = _subst(ins.args, alias)  # earlier aliases are already resolved
        if ins.op == "copy" and isinstance(args[0], str):
            alias[ins.dest] = args[0]
        out.append(Instr(ins.op, ins.dest, args))
    return Function(func.name, func.params, tuple(out))


def eliminate_dead_code(func: Function) -> Function:
    """Remove every instruction whose result is never used."""
    needed: set[str] = set()
    kept = []
    for ins in reversed(func.body):
        if ins.op == "ret" or ins.dest in needed:
            kept.append(ins)
            needed.update(a for a in ins.args if isinstance(a, str))
    kept.reverse()
    return Function(func.name, func.params, tuple(kept))


def optimize(func: Function, max_rounds: int = 10) -> Function:
    """Run the four passes until a round changes nothing."""
    for _ in range(max_rounds):
        before = func
        for run_pass in (fold_constants, simplify_algebra, propagate_copies, eliminate_dead_code):
            func = run_pass(func)
        if func == before:
            break
    return func


def llvm_instruction_count(func: Function, passes: str) -> int:
    """How many instructions (`ret` included) are left after LLVM runs `passes`."""
    ir = cputools.run_opt(to_llvm(func), passes)
    lines = ir.splitlines()
    start = lines.index("entry:") + 1
    end = lines.index("}", start)
    return sum(1 for line in lines[start:end] if line.strip())


if __name__ == "__main__":
    demo = make(
        "f",
        "x y",
        """
        t0 = const 3
        t1 = const 4
        t2 = add t0 t1
        t3 = mul y t2
        t4 = mul x 8
        t5 = add t4 0
        t6 = add t3 t5
        t7 = mul y 1
        ret t6
        """,
    )
    print("before:", len(demo.body), "instructions")
    print(format_function(demo))
    best = optimize(demo)
    print("\nafter your passes:", len(best.body), "instructions")
    print(format_function(best))
    print("\nLLVM instruction counts:")
    for passes in ("instcombine", "default<O2>"):
        print(f"  {passes}: {llvm_instruction_count(demo, passes)}")
