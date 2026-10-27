"""Checks for the lexer, parser, and interpreter exercise."""

import random

from cpucheck import check, equal, fail, has


def pairs(tokens):
    return [(t.kind, t.text) for t in tokens]


def expect_error(sub, exc_name, func, *args, label=""):
    exc = has(sub, exc_name)
    try:
        func(*args)
    except exc:
        return
    except NotImplementedError:
        raise
    except Exception as other:  # noqa: BLE001
        fail(f"{label}: expected {exc_name}, got {type(other).__name__}: {other}")
    fail(f"{label}: expected {exc_name}, but the call returned normally")


@check("tokenize splits numbers, names, keywords, and operators, and ends with eof")
def test_tokenize(sub):
    tokenize = has(sub, "tokenize")
    equal(
        pairs(tokenize("let x = 4 in x")),
        [("kw", "let"), ("name", "x"), ("op", "="), ("num", "4"), ("kw", "in"), ("name", "x"), ("eof", "")],
        label="let x = 4 in x",
    )
    equal(
        pairs(tokenize("12*(a_1+30)")),
        [("num", "12"), ("op", "*"), ("op", "("), ("name", "a_1"), ("op", "+"), ("num", "30"), ("op", ")"), ("eof", "")],
        label="no spaces between tokens",
    )
    equal(pairs(tokenize("")), [("eof", "")], label="empty input")
    equal(pairs(tokenize(" \n\t ")), [("eof", "")], label="only whitespace")
    equal(pairs(tokenize("letter inside")), [("name", "letter"), ("name", "inside")] + [("eof", "")], label="names that start with a keyword")


@check("tokenize raises ParseError on a character that starts no token")
def test_tokenize_errors(sub):
    tokenize = has(sub, "tokenize")
    expect_error(sub, "ParseError", tokenize, "1 + $", label="a dollar sign")
    expect_error(sub, "ParseError", tokenize, "3 % 2", label="a percent sign")


@check("parse builds the right AST for numbers, names, and one operation")
def test_parse_simple(sub):
    parse, Num, Var, BinOp = has(sub, "parse"), has(sub, "Num"), has(sub, "Var"), has(sub, "BinOp")
    equal(parse("42"), Num(42), label="42")
    equal(parse("  x_1 "), Var("x_1"), label="a name")
    equal(parse("7 - 2"), BinOp("-", Num(7), Num(2)), label="7 - 2")
    equal(parse("(5)"), Num(5), label="parentheses around one number")


@check("parse gives * and / higher precedence than + and -")
def test_precedence(sub):
    parse, to_sexpr = has(sub, "parse"), has(sub, "to_sexpr")
    equal(to_sexpr(parse("1 + 2 * 3")), "(+ 1 (* 2 3))", label="1 + 2 * 3")
    equal(to_sexpr(parse("1 * 2 + 3")), "(+ (* 1 2) 3)", label="1 * 2 + 3")
    equal(to_sexpr(parse("8 - 6 / 2")), "(- 8 (/ 6 2))", label="8 - 6 / 2")
    equal(to_sexpr(parse("(1 + 2) * 3")), "(* (+ 1 2) 3)", label="parentheses override precedence")


@check("parse groups equal-precedence operators from the left")
def test_associativity(sub):
    parse, to_sexpr = has(sub, "parse"), has(sub, "to_sexpr")
    equal(to_sexpr(parse("1 - 2 - 3")), "(- (- 1 2) 3)", label="1 - 2 - 3")
    equal(to_sexpr(parse("8 / 4 / 2")), "(/ (/ 8 4) 2)", label="8 / 4 / 2")
    equal(to_sexpr(parse("1 - 2 + 3 - 4")), "(- (+ (- 1 2) 3) 4)", label="mixed + and -")
    equal(to_sexpr(parse("2 * 3 / 4 * 5")), "(* (/ (* 2 3) 4) 5)", label="mixed * and /")
    equal(to_sexpr(parse("1 - (2 - 3)")), "(- 1 (- 2 3))", label="parentheses on the right")


@check("parse handles unary minus and let, and a let body reaches as far right as it can")
def test_unary_let(sub):
    parse, to_sexpr = has(sub, "parse"), has(sub, "to_sexpr")
    equal(to_sexpr(parse("-5")), "(- 0 5)", label="-5")
    equal(to_sexpr(parse("--5")), "(- 0 (- 0 5))", label="--5")
    equal(to_sexpr(parse("-2 * 3")), "(* (- 0 2) 3)", label="unary minus binds tighter than *")
    equal(to_sexpr(parse("3 - -2")), "(- 3 (- 0 2))", label="3 - -2")
    equal(to_sexpr(parse("let x = 5 in x")), "(let x 5 x)", label="a simple let")
    equal(to_sexpr(parse("let x = 1 in x + 2 * 3")), "(let x 1 (+ x (* 2 3)))", label="the body takes the whole expression")
    equal(to_sexpr(parse("let a = 2 in let b = a * 3 in a + b")), "(let a 2 (let b (* a 3) (+ a b)))", label="nested lets")
    equal(to_sexpr(parse("(let x = 1 in x) + 2")), "(+ (let x 1 x) 2)", label="a let inside parentheses")


@check("parse raises ParseError for malformed programs")
def test_parse_errors(sub):
    parse = has(sub, "parse")
    for bad in ["", "   ", "1 +", "(1 + 2", "1 + 2)", "1 2", "* 3", "let = 1 in 2", "let x 1 in x", "let x = 1", "()", "let 5 = 1 in 2"]:
        expect_error(sub, "ParseError", parse, bad, label=f"parse({bad!r})")


@check("evaluate computes values with C-style truncating division")
def test_evaluate(sub):
    parse, evaluate = has(sub, "parse"), has(sub, "evaluate")
    cases = [
        ("1 + 2 * 3", 7),
        ("(1 + 2) * 3", 9),
        ("10 - 4 - 3", 3),  # (10 - 4) - 3
        ("7 / 2", 3),
        ("-7 / 2", -3),  # truncates toward zero, not -4
        ("7 / -2", -3),
        ("-7 / -2", 3),
        ("-(2 + 3)", -5),
        ("let x = 4 in x * (x + 1)", 20),  # 4 * 5
        ("let x = 2 in let y = x * 10 in y - x", 18),  # 20 - 2
        ("let x = 1 in (let x = 5 in x) + x", 6),  # the inner x is 5 only inside its body
    ]
    for src, want in cases:
        equal(evaluate(parse(src)), want, label=src)
    equal(evaluate(parse("x + 1"), {"x": 41}), 42, label="x + 1 with env x = 41")


@check("evaluate raises EvalError for division by zero and unbound names, and leaves env alone")
def test_eval_errors(sub):
    parse, evaluate = has(sub, "parse"), has(sub, "evaluate")
    expect_error(sub, "EvalError", lambda: evaluate(parse("1 / 0")), label="1 / 0")
    expect_error(sub, "EvalError", lambda: evaluate(parse("let x = 0 in 5 / x")), label="5 / x with x = 0")
    expect_error(sub, "EvalError", lambda: evaluate(parse("y + 1")), label="unbound y")
    expect_error(sub, "EvalError", lambda: evaluate(parse("(let z = 1 in z) + z")), label="z is not bound outside its let")
    env = {"a": 1}
    evaluate(parse("let b = 2 in a + b"), env)
    equal(env, {"a": 1}, label="env after evaluating a let")


@check("parse then evaluate agrees with Python on 200 random expressions")
def test_random(sub):
    parse, evaluate = has(sub, "parse"), has(sub, "evaluate")
    rng = random.Random(0)

    def gen(depth):
        # Parenthesise a side only sometimes, so precedence and associativity decide the rest.
        if depth == 0 or rng.random() < 0.25:
            return str(rng.randint(0, 20))
        if rng.random() < 0.15:
            return f"-({gen(depth - 1)})"
        left, right = gen(depth - 1), gen(depth - 1)
        if rng.random() < 0.5:
            left = f"({left})"
        if rng.random() < 0.5:
            right = f"({right})"
        return f"{left} {rng.choice('+-*')} {right}"

    # Each child is fully parenthesised when it matters, so Python computes the same value.
    def build(depth):
        if depth == 0 or rng.random() < 0.25:
            n = rng.randint(0, 20)
            return str(n)
        if rng.random() < 0.15:
            return f"-({build(depth - 1)})"
        return f"({build(depth - 1)}) {rng.choice('+-*')} ({build(depth - 1)})"

    for _ in range(100):
        text = gen(4)
        # Python parses the unparenthesised pieces with the same precedence and left associativity,
        # so eval is an independent reference for the text we generated.
        equal(evaluate(parse(text)), eval(text), label=text)
    for _ in range(100):
        text = build(4)
        equal(evaluate(parse(text)), eval(text), label=text)
