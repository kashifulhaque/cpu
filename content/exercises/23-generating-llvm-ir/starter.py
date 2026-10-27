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
    """The distinct names declared by `let`, in order of first appearance.

    Look inside `if` and `while` bodies too, because a `let` there still needs
    a slot. `let a = 1; while a < 3 { let b = 2; a = a + 1; } let a = 5;`
    gives ["a", "b"].
    """
    raise NotImplementedError


def gen_expr(expr, em: Emitter) -> str:
    """Emit instructions for `expr` and return the operand that holds its value.

    The operand is a string of type i32: an integer literal such as "5" for a
    Num (emitting nothing), or a fresh temp such as "%t3".

      Var: `load i32, ptr <slot>`. Raise CompileError if the name is not in
           em.declared.
      + - * /: `add`, `sub`, `mul`, `sdiv` on i32.
      comparison: `icmp slt|sle|sgt|sge|eq|ne` gives an i1; `zext` it to i32.

    Evaluate the left operand before the right one.
    """
    raise NotImplementedError


def gen_cond(expr, em: Emitter) -> str:
    """Emit instructions that test `expr` and return an operand of type i1.

    The condition is true when the value of `expr` is not zero:
    `icmp ne i32 <value>, 0`.
    """
    raise NotImplementedError


def gen_stmt(stmt, em: Emitter) -> None:
    """Emit instructions for one statement.

      Let / Assign: evaluate the value, `store i32` into the variable's slot.
                    A `let` also calls em.declare(name); an Assign to a name
                    that is not declared raises CompileError.
      Print: evaluate, then
             `call i32 (ptr, ...) @printf(ptr @.fmt, i32 <value>)`.
      If: branch on gen_cond to a `then` block and an `else` block, then
          continue in an `end` block. Every block ends with a `br`.
      While: a `cond` block that tests and branches to `body` or `end`; the body
          ends by branching back to `cond`.
    """
    raise NotImplementedError


def generate(program: Program) -> str:
    """The complete IR module for a program: PRELUDE and a `@main` returning 0.

    All `alloca` instructions go in the `entry` block, each followed by a
    `store i32 0`, so a variable reads as 0 until it is assigned.
    """
    raise NotImplementedError


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
