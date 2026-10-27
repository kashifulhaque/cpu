"""Checks for the LLVM IR code generator exercise."""

import random
import re

import cputools
from cpucheck import check, equal, fail, has


_DECLS = """\
@.fmt = private unnamed_addr constant [4 x i8] c"%d\\0A\\00"
declare i32 @printf(ptr, ...)
"""


def _values(sub, exprs, declared=(), setup="", cond=False):
    """Run gen_expr (or gen_cond) on each expression inside one @main that prints every result.

    One lli run covers all the expressions, which keeps the check fast.
    """
    em = sub.Emitter()
    for name in declared:
        em.declare(name)
    gen = has(sub, "gen_cond" if cond else "gen_expr")
    for k, expr in enumerate(exprs):
        operand = gen(expr, em)
        if not isinstance(operand, str):
            fail(f"{'gen_cond' if cond else 'gen_expr'} must return a string operand, not {operand!r}")
        if cond:
            # `select` accepts only an i1 condition, so this fails if gen_cond returns an i32.
            wide = em.temp()
            em.emit(f"{wide} = select i1 {operand}, i32 1, i32 0")
            operand = wide
        em.emit(f"{em.temp()} = call i32 (ptr, ...) @printf(ptr @.fmt, i32 {operand})")
    ir = _DECLS + "define i32 @main() {\nentry:\n" + setup + "\n".join(em.lines) + "\n  ret i32 0\n}\n"
    try:
        res = cputools.run_ir(ir)
    except cputools.ToolError as err:
        fail(f"the IR produced by your code is not valid:\n{ir}\n{err}")
    return [int(x) for x in res.stdout.split()]


def _expr(sub, text):
    return sub.parse(f"print {text};").body[0].value


def _run(sub, source):
    """Compile and run a program; return its printed lines as ints."""
    ir = has(sub, "compile_source")(source)
    res = cputools.run_ir(ir)
    if res.returncode != 0:
        fail(f"the program exited with code {res.returncode}, expected 0.\nstderr: {res.stderr}")
    return [int(line) for line in res.stdout.split()]


@check("collect_vars lists each `let` name once, in order, including names inside if and while")
def test_collect(sub):
    collect = has(sub, "collect_vars")
    p = sub.parse("let a = 1; while a < 3 { let b = 2; a = a + 1; } if a { let c = 1; } else { let d = 2; let a = 9; } let b = 4;")
    equal(collect(p), ["a", "b", "c", "d"])
    equal(collect(sub.parse("print 1;")), [])


@check("gen_expr turns arithmetic into add, sub, mul, and sdiv with the right precedence")
def test_arith(sub):
    cases = [
        ("42", 42),
        ("2 + 3 * 4", 14),       # * binds tighter
        ("(2 + 3) * 4", 20),
        ("10 - 4 - 3", 3),        # left to right: (10 - 4) - 3
        ("100 / 7", 14),          # integer division truncates
        ("(100 - 2) / (3 + 4) + 1", 15),  # 98 / 7 = 14, plus 1
    ]
    got = _values(sub, [_expr(sub, t) for t, _ in cases])
    for (text, want), g in zip(cases, got):
        equal(g, want, label=text)


@check("gen_expr: comparisons give 1 or 0 as an i32, and gen_cond gives an i1")
def test_compare(sub):
    cases = [("3 < 5", 1), ("5 < 3", 0), ("4 == 4", 1), ("4 != 4", 0), ("2 >= 3", 0),
             ("3 <= 3", 1), ("9 > 1", 1), ("(1 < 2) + (2 < 3)", 2), ("1 + 1 == 2", 1)]
    got = _values(sub, [_expr(sub, t) for t, _ in cases])
    for (text, want), g in zip(cases, got):
        equal(g, want, label=text)
    truth = [("0", 0), ("7", 1), ("3 - 3", 0), ("2 < 1", 0), ("5 > 1", 1)]
    got = _values(sub, [_expr(sub, t) for t, _ in truth], cond=True)
    for (text, want), g in zip(truth, got):
        equal(g, want, label=f"truth of {text}")


@check("gen_expr loads a variable from its slot, and rejects an undeclared one")
def test_var(sub):
    setup = "  %x.slot = alloca i32\n  store i32 9, ptr %x.slot\n"
    got = _values(sub, [_expr(sub, "x * 2 + x")], declared=["x"], setup=setup)
    equal(got, [27], label="x * 2 + x with x = 9")
    try:
        has(sub, "gen_expr")(sub.Var("nope"), sub.Emitter())
    except sub.CompileError:
        pass
    else:
        fail("gen_expr must raise CompileError for a variable that was never declared")


@check("let, assignment, and print: straight-line programs print the right values")
def test_straight(sub):
    equal(_run(sub, "let a = 6; let b = 7; print a * b;"), [42])
    equal(_run(sub, "let x = 1; x = x + 1; x = x * 10; print x; print x - 21;"), [20, -1])
    equal(_run(sub, "let x = 5; let y = x; x = 0; print y; print x;"), [5, 0])
    equal(_run(sub, "print 100 / 7; print (0 - 7) / 2; print -7 / 2; print -(3 + 4);"), [14, -3, -3, -7])
    equal(_run(sub, "# only a comment\nprint 2147483647 + 1;"), [-2147483648])  # i32 wraps
    equal(_run(sub, "if 0 { let z = 5; } print z;"), [0])  # a declared variable starts at 0


@check("if and else: branches run only when the condition holds, and any non-zero value is true")
def test_if(sub):
    equal(_run(sub, "let n = 5; if n > 3 { print 1; } else { print 2; } if n == 0 { print 3; } print 4;"), [1, 4])
    equal(_run(sub, "if 7 { print 1; } if 0 { print 2; } else { print 3; } if 3 - 3 { print 4; } else { print 5; }"), [1, 3, 5])
    # Nested ifs: a classify function over several values (negative, zero, small, large).
    src = """
    let i = 0 - 2;
    while i < 12 {
        if i < 0 { print 0 - 1; }
        else { if i == 0 { print 0; } else { if i < 10 { print 1; } else { print 2; } } }
        i = i + 5;
    }
    """
    equal(_run(sub, src), [-1, 1, 1])  # i = -2, 3, 8, then 13 stops the loop; 8 < 10 prints 1


@check("while: sums, factorials, Fibonacci numbers, nested loops, and gcd")
def test_while(sub):
    equal(_run(sub, "let i = 1; let s = 0; while i <= 10 { s = s + i; i = i + 1; } print s;"), [55])
    equal(_run(sub, "let n = 10; let f = 1; while n > 1 { f = f * n; n = n - 1; } print f;"), [3628800])
    equal(_run(sub, "let a = 0; let b = 1; let k = 0; while k < 10 { let t = a + b; a = b; b = t; k = k + 1; } print a;"), [55])
    equal(_run(sub, "let i = 0; let c = 0; while i < 4 { let j = 0; while j < 3 { c = c + 1; j = j + 1; } i = i + 1; } print c;"), [12])
    gcd = "let a = 48; let b = 18; while a != b { if a > b { a = a - b; } else { b = b - a; } } print a;"
    equal(_run(sub, gcd), [6])
    equal(_run(sub, "let i = 5; while i < 3 { print 9; } print i;"), [5])  # the body may run zero times


def _to_source(e):
    if isinstance(e, int):
        return str(e)
    op, a, b = e
    return f"({_to_source(a)} {op} {_to_source(b)})"


def _wrap(n):
    n &= 0xFFFFFFFF
    return n - (1 << 32) if n & 0x80000000 else n


def _ref(e):
    if isinstance(e, int):
        return e
    op, a, b = e
    x, y = _ref(a), _ref(b)
    if op == "+":
        return _wrap(x + y)
    if op == "-":
        return _wrap(x - y)
    if op == "*":
        return _wrap(x * y)
    if op == "/":
        q = abs(x) // y  # the divisor is a positive literal; C truncates toward zero
        return q if x >= 0 else -q
    return int({"<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y, "==": x == y, "!=": x != y}[op])


def _random_expr(rng, depth):
    if depth == 0 or rng.random() < 0.2:
        return rng.choice([0, 1, 2, 3, 7, 10, 100, 12345])
    op = rng.choice(["+", "-", "*", "/", "<", "<=", ">", ">=", "==", "!="])
    if op == "/":
        return (op, _random_expr(rng, depth - 1), rng.randint(1, 9))
    return (op, _random_expr(rng, depth - 1), _random_expr(rng, depth - 1))


@check("sixty random expressions, evaluated by the compiled program, match a Python reference")
def test_random(sub):
    rng = random.Random(0)
    exprs = [_random_expr(rng, 3) for _ in range(60)]
    source = "".join(f"print {_to_source(e)};\n" for e in exprs)
    got = _run(sub, source)
    equal(got, [_ref(e) for e in exprs])


@check("generated IR keeps every alloca in the entry block (checked in your IR text), and mem2reg removes them all")
def test_layout(sub):
    src = "let i = 0; let s = 0; while i < 5 { let t = i * i; s = s + t; i = i + 1; } if s > 10 { print s; }"
    ir = sub.compile_source(src)
    lines = [ln.strip() for ln in ir.splitlines()]
    allocas = [k for k, ln in enumerate(lines) if "= alloca" in ln]
    equal(len(allocas), 3, label="one alloca per distinct variable (i, s, t)")
    first_br = min(k for k, ln in enumerate(lines) if ln.startswith("br "))
    if max(allocas) > first_br:
        fail("an alloca appears after the first `br`: it is outside the entry block, so a loop would grow the stack")
    cputools.verify_ir(ir)
    want = _run(sub, src)
    equal(want, [30], label="0 + 1 + 4 + 9 + 16")
    promoted = cputools.run_opt(ir, "mem2reg")
    if "alloca" in promoted:
        fail("mem2reg left an alloca behind; every slot should be promotable")
    if "phi" not in promoted:
        fail("expected phi nodes after mem2reg, because the loop changes i and s")
    equal([int(x) for x in cputools.run_ir(promoted).stdout.split()], want, label="output after mem2reg")


@check("using or assigning an undeclared variable raises CompileError")
def test_undeclared(sub):
    for source in ["print y;", "y = 1;", "let a = b + 1;", "while k < 3 { print 1; }"]:
        try:
            sub.compile_source(source)
        except sub.CompileError:
            continue
        fail(f"compile_source({source!r}) should raise CompileError")
