"""Checks for the optimization passes exercise."""

import random

import cputools
from cpucheck import check, equal, fail, has


def _wrap(n):
    n &= 0xFFFFFFFF
    return n - (1 << 32) if n & 0x80000000 else n


def _ref_eval(func, args):
    """An independent evaluator, so the checks do not trust the starter's."""
    env = dict(zip(func.params, args))
    val = lambda a: a if isinstance(a, int) else env[a]  # noqa: E731
    for i in func.body:
        if i.op == "ret":
            return val(i.args[0])
        if i.op in ("const", "copy"):
            env[i.dest] = _wrap(val(i.args[0]))
        else:
            a, b = val(i.args[0]), val(i.args[1])
            env[i.dest] = _wrap(
                {"add": a + b, "sub": a - b, "mul": a * b, "shl": a << (b & 31), "and": a & b}[i.op]
            )
    raise AssertionError("no ret")


def _same_behaviour(before, after, rng, label):
    for _ in range(12):
        args = [rng.choice([0, 1, -1, 2, 7, -9, 100, 2**31 - 1, -(2**31), rng.randint(-10**6, 10**6)]) for _ in before.params]
        want, got = _ref_eval(before, args), _ref_eval(after, args)
        if got != want:
            fail(f"{label}: the optimized function returns {got} for args {args}, the original returns {want}.\n{_fmt(after)}")


def _fmt(func):
    return "\n".join(f"  {i.dest or ''} {i.op} {i.args}" for i in func.body)


def _random_function(sub, rng, n=14):
    names = ["x", "y"]
    lines = []
    for k in range(n):
        op = rng.choice(["add", "sub", "mul", "shl", "and", "const", "copy"])
        d = f"t{k}"

        def pick():
            if rng.random() < 0.35:
                return rng.choice([0, 1, 2, 4, 8, 3, -2, 5])
            return rng.choice(names)

        if op == "const":
            lines.append(f"{d} = const {rng.choice([0, 1, 2, 5, -3, 16])}")
        elif op == "copy":
            lines.append(f"{d} = copy {pick()}")
        elif op == "shl":
            lines.append(f"{d} = shl {rng.choice(names)} {rng.choice([0, 1, 2, 3])}")
        else:
            lines.append(f"{d} = {op} {pick()} {pick()}")
        names.append(d)
    lines.append(f"ret {rng.choice(names[2:])}")
    return sub.make("g", "x y", "\n".join(lines))


@check("fold_constants folds const arithmetic and wraps to 32 bits")
def test_fold(sub):
    fold = has(sub, "fold_constants")
    f = sub.make("f", "", "a = const 2\nb = const 3\nc = add a b\nd = mul c 4\nret d")
    g = fold(f)
    by = {i.dest: i for i in g.body if i.dest}
    equal(by["c"].op, "const", label="c = add a b")
    equal(by["c"].args, (5,), label="c's value")
    equal(by["d"].op, "const", label="d = mul c 4")
    equal(by["d"].args, (20,), label="d's value (5 * 4)")
    equal(g.body[-1].args, (20,), label="ret operand is the folded constant")
    # 2^31 - 1 plus 1 wraps to -2^31; 65536 * 65536 wraps to 0.
    h = fold(sub.make("h", "", "a = add 2147483647 1\nb = mul 65536 65536\nret a"))
    equal(h.body[0].args, (-(2**31),), label="2147483647 + 1")
    equal(h.body[1].args, (0,), label="65536 * 65536")


@check("fold_constants leaves unknown values alone and does not change its input")
def test_fold_keeps(sub):
    fold = has(sub, "fold_constants")
    f = sub.make("f", "x", "a = const 5\nb = add x a\nc = copy 7\nret b")
    g = fold(f)
    equal(g.body[1].op, "add", label="b still an add")
    equal(g.body[1].args, ("x", 5), label="b's args: x stays, a becomes 5")
    equal(g.body[2].op, "const", label="a copy of an int becomes a const")
    equal(f.body[1].args, ("x", "a"), label="the input function must not change")


@check("simplify_algebra: x+0, x*1, x*0, x-x, and x*2^k become copy, const, or shl")
def test_simplify(sub):
    simp = has(sub, "simplify_algebra")
    f = sub.make(
        "f", "x y",
        "a = add x 0\nb = add 0 y\nc = mul x 1\nd = mul 1 y\ne = mul x 0\n"
        "f1 = sub x x\ng = sub y 0\nh = mul x 8\ni = mul 2 y\nj = shl x 0\nk = and x 0\nl = and y y\nret a",
    )
    got = {i.dest: (i.op, i.args) for i in simp(f).body if i.dest}
    want = {
        "a": ("copy", ("x",)), "b": ("copy", ("y",)), "c": ("copy", ("x",)), "d": ("copy", ("y",)),
        "e": ("const", (0,)), "f1": ("const", (0,)), "g": ("copy", ("y",)),
        "h": ("shl", ("x", 3)), "i": ("shl", ("y", 1)), "j": ("copy", ("x",)),
        "k": ("const", (0,)), "l": ("copy", ("y",)),
    }
    for name, expected in want.items():
        equal(got[name], expected, label=f"rewrite of {name}")


@check("simplify_algebra leaves non-powers of two, other operations, and int-only operands alone")
def test_simplify_keeps(sub):
    simp = has(sub, "simplify_algebra")
    f = sub.make("f", "x y", "a = mul x 6\nb = add x y\nc = sub x y\nd = add 2 3\ne = mul x 1\nret a")
    g = simp(f)
    for i in range(4):
        equal(g.body[i], f.body[i], label=f"instruction {i} unchanged")
    equal(g.body[4].op, "copy", label="x * 1 still rewrites")


@check("propagate_copies replaces uses of a copy with its source, following chains")
def test_copies(sub):
    prop = has(sub, "propagate_copies")
    f = sub.make("f", "x", "a = copy x\nb = copy a\nc = add b a\nd = mul c b\nret d")
    g = prop(f)
    equal(g.body[2].args, ("x", "x"), label="c = add b a")
    equal(g.body[3].args, ("c", "x"), label="d = mul c b")
    g2 = prop(sub.make("f", "x", "a = copy x\nret a"))
    equal(g2.body[-1].args, ("x",), label="ret uses the source")


@check("eliminate_dead_code removes unused instructions, even chains of them, and keeps ret")
def test_dce(sub):
    dce = has(sub, "eliminate_dead_code")
    f = sub.make("f", "x y", "a = add x 1\nb = mul a 2\nc = sub b a\nd = add y 5\ne = mul x x\nret d")
    g = dce(f)
    equal([i.dest for i in g.body], ["d", None], label="what remains (a, b, c feed only the dead c; e is unused)")
    equal(g.body[-1].op, "ret")
    h = dce(sub.make("h", "x", "a = add x 1\nb = mul a a\nret b"))
    equal(len(h.body), 3, label="a live chain is kept whole")


@check("every pass preserves behaviour on random programs (32-bit wrap-around, negative and edge inputs)")
def test_random_semantics(sub):
    passes = {n: has(sub, n) for n in ("fold_constants", "simplify_algebra", "propagate_copies", "eliminate_dead_code", "optimize")}
    rng = random.Random(0)
    for k in range(40):
        f = _random_function(sub, rng)
        for name, p in passes.items():
            g = p(f)
            _same_behaviour(f, g, rng, f"{name} on random program {k}")


@check("optimize reaches a fixed point: a fully constant function collapses to one ret, and the result is stable")
def test_optimize(sub):
    opt = has(sub, "optimize")
    f = sub.make("f", "x", "a = const 6\nb = const 7\nc = mul a b\nd = add c 0\ne = copy d\nf1 = mul x 0\nret e")
    g = opt(f)
    equal(len(g.body), 1, label="instructions left")
    equal(g.body[0].args, (42,), label="ret operand")
    h = sub.make(
        "h", "x y",
        "t0 = const 3\nt1 = const 4\nt2 = add t0 t1\nt3 = mul y t2\nt4 = mul x 8\nt5 = add t4 0\nt6 = add t3 t5\nt7 = mul y 1\nret t6",
    )
    o = opt(h)
    equal([i.op for i in o.body], ["mul", "shl", "add", "ret"], label="demo function after optimize")
    equal(opt(o), o, label="optimizing twice changes nothing")


@check("llvm_instruction_count: instcombine and default<O2> shrink the same functions, and O2 agrees with your optimize")
def test_llvm(sub):
    count = has(sub, "llvm_instruction_count")
    opt = has(sub, "optimize")
    f = sub.make("f", "x", "a = add x 0\nb = mul a 1\nc = copy b\nret c")
    equal(count(f, "verify"), 4, label="unoptimized count (verify changes nothing)")
    equal(count(f, "instcombine"), 1, label="instcombine leaves only ret")
    programs = [
        sub.make("f", "x y", "t0 = const 3\nt1 = const 4\nt2 = add t0 t1\nt3 = mul y t2\nt4 = mul x 8\nt5 = add t4 0\nt6 = add t3 t5\nt7 = mul y 1\nret t6"),
        sub.make("f", "x", "a = add x 0\nb = mul a 1\nc = copy b\nret c"),
        sub.make("f", "x y", "a = sub x x\nb = and y y\nc = add a b\nd = mul c 16\nret d"),
        sub.make("f", "x", "a = const 6\nb = const 7\nc = mul a b\nd = mul x 0\nret c"),
    ]
    for k, p in enumerate(programs):
        mine = len(opt(p).body)
        theirs = count(p, "default<O2>")
        equal(mine, theirs, label=f"program {k}: your optimize versus LLVM's default<O2> (instructions)")
        if count(p, "instcombine") > len(p.body):
            fail("instcombine made the function longer")
