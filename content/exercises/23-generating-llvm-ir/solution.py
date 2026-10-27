"""A code generator from a tiny language to LLVM IR text.

The language has 32-bit integer variables and these statements:

    let x = 1 + 2;          declare a variable and give it a value
    x = x * 3;              assign
    print x;                print the value and a newline
    if x < 10 { ... } else { ... }
    while x < 10 { ... }

Comparisons (< <= > >= == !=) give 1 or 0. In `if` and `while`, zero is false
and anything else is true. All values are `i32`. A variable that has been
declared but not yet given a value reads as 0.
"""

import re
from dataclasses import dataclass, field

import cputools

# ---------------------------------------------------------------------------
# Provided: errors, syntax tree, lexer, parser, and emitter helper.
# ---------------------------------------------------------------------------


class CompileError(Exception):
    """The source text or the program is invalid."""


@dataclass
class Num:
    value: int


@dataclass
class Var:
    name: str


@dataclass
class BinOp:
    op: str  # one of + - * / < <= > >= == !=
    left: object
    right: object


@dataclass
class Let:
    name: str
    value: object


@dataclass
class Assign:
    name: str
    value: object


@dataclass
class Print:
    value: object


@dataclass
class If:
    cond: object
    then: list
    orelse: list  # empty when there is no `else`


@dataclass
class While:
    cond: object
    body: list


@dataclass
class Program:
    body: list


_TOKEN = re.compile(
    r"""\s+|\#[^\n]*              # whitespace and comments
    |(?P<num>\d+)
    |(?P<name>[A-Za-z_]\w*)
    |(?P<op>==|!=|<=|>=|[-+*/<>=(){};])""",
    re.VERBOSE,
)
_KEYWORDS = {"let", "print", "if", "else", "while"}


def tokenize(source: str) -> list[tuple[str, str]]:
    """A list of (kind, text) pairs ending with ("eof", ""). Kinds: num, name, kw, op."""
    tokens, pos = [], 0
    while pos < len(source):
        m = _TOKEN.match(source, pos)
        if not m:
            raise CompileError(f"unexpected character {source[pos]!r}")
        pos = m.end()
        if m.lastgroup == "name" and m.group() in _KEYWORDS:
            tokens.append(("kw", m.group()))
        elif m.lastgroup:
            tokens.append((m.lastgroup, m.group()))
    tokens.append(("eof", ""))
    return tokens


class _Parser:
    def __init__(self, source: str):
        self.tokens = tokenize(source)
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos]

    def take(self, text=None, kind=None):
        tok = self.tokens[self.pos]
        if (text is not None and tok[1] != text) or (kind is not None and tok[0] != kind):
            want = text or kind
            raise CompileError(f"expected {want}, found {tok[1] or 'end of input'!r}")
        self.pos += 1
        return tok

    def at(self, text):
        return self.peek()[1] == text and self.peek()[0] in ("op", "kw")

    def program(self):
        body = []
        while self.peek()[0] != "eof":
            body.append(self.statement())
        return Program(body)

    def block(self):
        self.take("{")
        body = []
        while not self.at("}"):
            if self.peek()[0] == "eof":
                raise CompileError("missing }")
            body.append(self.statement())
        self.take("}")
        return body

    def statement(self):
        kind, text = self.peek()
        if text == "let" and kind == "kw":
            self.take()
            name = self.take(kind="name")[1]
            self.take("=")
            value = self.expr()
            self.take(";")
            return Let(name, value)
        if text == "print" and kind == "kw":
            self.take()
            value = self.expr()
            self.take(";")
            return Print(value)
        if text == "if" and kind == "kw":
            self.take()
            cond = self.expr()
            then = self.block()
            orelse = []
            if self.at("else"):
                self.take()
                orelse = self.block()
            return If(cond, then, orelse)
        if text == "while" and kind == "kw":
            self.take()
            cond = self.expr()
            return While(cond, self.block())
        if kind == "name":
            self.take()
            self.take("=")
            value = self.expr()
            self.take(";")
            return Assign(text, value)
        raise CompileError(f"unexpected {text or 'end of input'!r}")

    def _left_assoc(self, ops, operand):
        node = operand()
        while self.peek()[0] == "op" and self.peek()[1] in ops:
            op = self.take()[1]
            node = BinOp(op, node, operand())
        return node

    def expr(self):
        return self._left_assoc(("<", "<=", ">", ">=", "==", "!="), self.additive)

    def additive(self):
        return self._left_assoc(("+", "-"), self.term)

    def term(self):
        return self._left_assoc(("*", "/"), self.unary)

    def unary(self):
        if self.at("-"):
            self.take()
            return BinOp("-", Num(0), self.unary())
        return self.atom()

    def atom(self):
        kind, text = self.peek()
        if kind == "num":
            self.take()
            return Num(int(text))
        if kind == "name":
            self.take()
            return Var(text)
        if text == "(" and kind == "op":
            self.take()
            node = self.expr()
            self.take(")")
            return node
        raise CompileError(f"expected an expression, found {text or 'end of input'!r}")


def parse(source: str) -> Program:
    """Parse source text into a Program, or raise CompileError."""
    return _Parser(source).program()


@dataclass
class Emitter:
    """Collects IR lines and hands out fresh names.

    em.temp()            -> "%t0", "%t1", ...      a fresh SSA value name
    em.label("if.then")  -> "if.then.0", ...       a fresh block label (no %)
    em.emit("%t0 = ...") appends one indented instruction line
    em.start_block(name) appends the line `name:`
    em.slot("x")         -> "%x.slot"              the alloca that holds variable x
    em.declare("x")      records that x has been declared; em.declared is the set
    """

    lines: list = field(default_factory=list)
    declared: set = field(default_factory=set)
    _temps: int = 0
    _labels: int = 0

    def temp(self) -> str:
        self._temps += 1
        return f"%t{self._temps - 1}"

    def label(self, hint: str) -> str:
        self._labels += 1
        return f"{hint}.{self._labels - 1}"

    def emit(self, text: str) -> None:
        self.lines.append("  " + text)

    def start_block(self, name: str) -> None:
        self.lines.append(f"{name}:")

    def slot(self, name: str) -> str:
        return f"%{name}.slot"

    def declare(self, name: str) -> None:
        self.declared.add(name)


# Declarations every generated module starts with: the C library's printf and
# the format string "%d\n" that `print` uses.
PRELUDE = """\
@.fmt = private unnamed_addr constant [4 x i8] c"%d\\0A\\00"
declare i32 @printf(ptr, ...)

"""

# ---------------------------------------------------------------------------
# What you write
# ---------------------------------------------------------------------------


def collect_vars(program: Program) -> list[str]:
    """The distinct names declared by `let`, in order of first appearance."""
    names: list[str] = []

    def walk(stmts):
        for s in stmts:
            if isinstance(s, Let) and s.name not in names:
                names.append(s.name)
            elif isinstance(s, If):
                walk(s.then)
                walk(s.orelse)
            elif isinstance(s, While):
                walk(s.body)

    walk(program.body)
    return names


_ARITH = {"+": "add", "-": "sub", "*": "mul", "/": "sdiv"}
_COMPARE = {"<": "slt", "<=": "sle", ">": "sgt", ">=": "sge", "==": "eq", "!=": "ne"}


def gen_expr(expr, em: Emitter) -> str:
    """Emit instructions for `expr` and return the operand that holds its value."""
    if isinstance(expr, Num):
        return str(expr.value)
    if isinstance(expr, Var):
        if expr.name not in em.declared:
            raise CompileError(f"variable {expr.name!r} is used before its `let`")
        t = em.temp()
        em.emit(f"{t} = load i32, ptr {em.slot(expr.name)}")
        return t
    if isinstance(expr, BinOp):
        left = gen_expr(expr.left, em)  # left first, then right
        right = gen_expr(expr.right, em)
        t = em.temp()
        if expr.op in _ARITH:
            em.emit(f"{t} = {_ARITH[expr.op]} i32 {left}, {right}")
            return t
        # A comparison is an i1; widen it so every value in the language is an i32.
        em.emit(f"{t} = icmp {_COMPARE[expr.op]} i32 {left}, {right}")
        wide = em.temp()
        em.emit(f"{wide} = zext i1 {t} to i32")
        return wide
    raise CompileError(f"cannot generate code for {expr!r}")


def gen_cond(expr, em: Emitter) -> str:
    """Emit instructions that test `expr` and return an operand of type i1."""
    value = gen_expr(expr, em)
    t = em.temp()
    em.emit(f"{t} = icmp ne i32 {value}, 0")
    return t


def gen_stmt(stmt, em: Emitter) -> None:
    """Emit instructions for one statement."""
    if isinstance(stmt, (Let, Assign)):
        value = gen_expr(stmt.value, em)  # evaluate first: `let x = x + 1` reads the old x
        if isinstance(stmt, Let):
            em.declare(stmt.name)
        elif stmt.name not in em.declared:
            raise CompileError(f"assignment to undeclared variable {stmt.name!r}")
        em.emit(f"store i32 {value}, ptr {em.slot(stmt.name)}")
    elif isinstance(stmt, Print):
        value = gen_expr(stmt.value, em)
        em.emit(f"{em.temp()} = call i32 (ptr, ...) @printf(ptr @.fmt, i32 {value})")
    elif isinstance(stmt, If):
        cond = gen_cond(stmt.cond, em)
        then_l, else_l, end_l = em.label("if.then"), em.label("if.else"), em.label("if.end")
        em.emit(f"br i1 {cond}, label %{then_l}, label %{else_l}")
        em.start_block(then_l)
        for s in stmt.then:
            gen_stmt(s, em)
        em.emit(f"br label %{end_l}")
        em.start_block(else_l)
        for s in stmt.orelse:
            gen_stmt(s, em)
        em.emit(f"br label %{end_l}")
        em.start_block(end_l)
    elif isinstance(stmt, While):
        cond_l, body_l, end_l = em.label("while.cond"), em.label("while.body"), em.label("while.end")
        em.emit(f"br label %{cond_l}")  # the current block falls into the test
        em.start_block(cond_l)
        cond = gen_cond(stmt.cond, em)
        em.emit(f"br i1 {cond}, label %{body_l}, label %{end_l}")
        em.start_block(body_l)
        for s in stmt.body:
            gen_stmt(s, em)
        em.emit(f"br label %{cond_l}")  # back edge
        em.start_block(end_l)
    else:
        raise CompileError(f"cannot generate code for {stmt!r}")


def generate(program: Program) -> str:
    """The complete IR module for a program: PRELUDE and a `@main` returning 0."""
    em = Emitter()
    for name in collect_vars(program):
        em.emit(f"{em.slot(name)} = alloca i32")
        em.emit(f"store i32 0, ptr {em.slot(name)}")
    for stmt in program.body:
        gen_stmt(stmt, em)
    em.emit("ret i32 0")
    body = "\n".join(em.lines)
    return PRELUDE + "define i32 @main() {\nentry:\n" + body + "\n}\n"


def compile_source(source: str) -> str:
    """Parse and generate. Provided: it calls your `generate`."""
    return generate(parse(source))


if __name__ == "__main__":
    source = """
    let n = 5;
    let product = 1;
    while n > 0 {
        product = product * n;
        n = n - 1;
    }
    print product;
    """
    ir = compile_source(source)
    print(ir)
    result = cputools.run_ir(ir)
    print("program printed:", result.stdout.strip())
