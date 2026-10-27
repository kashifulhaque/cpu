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


def fold_constants(func: Function) -> Function:
    """Constant propagation and folding.

    Walk the body once. Keep the names defined by `const`. In each instruction,
    replace a name that is a known constant by its int. Then:
      * a binary op with two int operands becomes `const` of its value
        (use eval_op, which wraps to 32 bits);
      * a `copy` of an int becomes `const`.
    The `const` instructions stay; dead-code elimination removes them later.

    `t0 = const 2; t1 = add t0 3; ret t1` becomes
    `t0 = const 2; t1 = const 5; ret 5`.
    """
    raise NotImplementedError


def simplify_algebra(func: Function) -> Function:
    """Rewrite instructions that have an algebraic identity. An instruction
    whose two operands are both ints is left alone (folding handles it).

      add:  x + 0, 0 + x   -> copy x
      sub:  x - 0          -> copy x;   x - x (the same name) -> const 0
      mul:  x * 1, 1 * x   -> copy x;   x * 0, 0 * x -> const 0
            x * 2^k, 2^k * x (k >= 1)  -> shl x k
      shl:  x << 0         -> copy x;   0 << x -> const 0
      and:  x & 0, 0 & x   -> const 0;  x & x (the same name) -> copy x

    `t = mul x 8` becomes `t = shl x 3`.
    """
    raise NotImplementedError


def propagate_copies(func: Function) -> Function:
    """Replace every use of a `copy d s` (where s is a name) with s.

    Follow chains: after `b = copy a; c = copy b`, a use of `c` becomes `a`.
    The `copy` instructions stay; dead-code elimination removes them later.

    `t = copy x; u = add t 1; ret u` becomes `t = copy x; u = add x 1; ret u`.
    """
    raise NotImplementedError


def eliminate_dead_code(func: Function) -> Function:
    """Remove every instruction whose result is never used.

    Walk the body from the end. `ret` is always kept. Every instruction is free
    of side effects, so one whose `dest` nobody needs can go. Dropping an
    instruction can make the ones before it dead, and a single backward walk
    finds them all.
    """
    raise NotImplementedError


def optimize(func: Function, max_rounds: int = 10) -> Function:
    """Run fold_constants, simplify_algebra, propagate_copies, and
    eliminate_dead_code in that order, over and over, until a whole round
    changes nothing (or `max_rounds` rounds have run). Return the result.
    """
    raise NotImplementedError


def llvm_instruction_count(func: Function, passes: str) -> int:
    """How many instructions (`ret` included) are left after LLVM runs `passes`.

    Convert with to_llvm, run cputools.run_opt(ir, passes), and count the
    non-blank lines between the `entry:` label and the closing `}`.
    `passes` is a pass-pipeline string such as "instcombine" or "default<O2>".
    """
    raise NotImplementedError


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
