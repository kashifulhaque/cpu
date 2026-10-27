"""A lexer, a recursive-descent parser, and an interpreter for a tiny language.

    let x = 4 in x * (x + 1)       # 20

The grammar, from loosest to tightest binding:

    expr  := "let" NAME "=" expr "in" expr  |  sum
    sum   := term (("+" | "-") term)*
    term  := unary (("*" | "/") unary)*
    unary := "-" unary  |  atom
    atom  := NUMBER | NAME | "(" expr ")"

The AST classes, Token, and the error types are given. You write tokenize,
parse, evaluate, and to_sexpr.
"""

from dataclasses import dataclass


class ParseError(Exception):
    """The text is not a valid program."""


class EvalError(Exception):
    """A valid program failed while running (division by zero, unbound name)."""


@dataclass
class Token:
    kind: str  # "num", "name", "kw" (let, in), "op" (+ - * / = ( )), or "eof"
    text: str


@dataclass
class Num:
    value: int


@dataclass
class Var:
    name: str


@dataclass
class BinOp:
    op: str  # "+", "-", "*", or "/"
    left: object
    right: object


@dataclass
class Let:
    name: str
    value: object
    body: object


def tokenize(src: str) -> list:
    """Split `src` into tokens. The list always ends with Token("eof", "").

    >>> tokenize("let x = 4 in x")   # shown here as (kind, text) pairs
    [('kw', 'let'), ('name', 'x'), ('op', '='), ('num', '4'), ('kw', 'in'), ('name', 'x'), ('eof', '')]

    Spaces and newlines separate tokens and are dropped. Raise ParseError for
    any character that starts no token, such as `$`.
    """
    kinds_kw = {"let", "in"}
    tokens = []
    i = 0
    while i < len(src):
        ch = src[i]
        if ch.isspace():
            i += 1
        elif ch.isdigit():
            start = i
            while i < len(src) and src[i].isdigit():
                i += 1
            tokens.append(Token("num", src[start:i]))
        elif ch.isalpha() or ch == "_":
            start = i
            while i < len(src) and (src[i].isalnum() or src[i] == "_"):
                i += 1
            word = src[start:i]
            tokens.append(Token("kw" if word in kinds_kw else "name", word))
        elif ch in "+-*/=()":
            tokens.append(Token("op", ch))
            i += 1
        else:
            raise ParseError(f"unexpected character {ch!r} at position {i}")
    tokens.append(Token("eof", ""))
    return tokens


class Parser:
    """One method per grammar rule; `pos` is the index of the next token."""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos]

    def advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, kind, text):
        tok = self.advance()
        if (tok.kind, tok.text) != (kind, text):
            raise ParseError(f"expected {text!r}, found {tok.text or 'end of input'!r}")

    def parse_program(self):
        node = self.parse_expr()
        if self.peek().kind != "eof":
            raise ParseError(f"unexpected {self.peek().text!r} after the expression")
        return node

    def parse_expr(self):
        if self.peek() == Token("kw", "let"):
            self.advance()
            name = self.advance()
            if name.kind != "name":
                raise ParseError("expected a name after let")
            self.expect("op", "=")
            value = self.parse_expr()
            self.expect("kw", "in")
            return Let(name.text, value, self.parse_expr())
        return self.parse_sum()

    def parse_sum(self):
        node = self.parse_term()
        while self.peek().kind == "op" and self.peek().text in "+-":
            op = self.advance().text
            node = BinOp(op, node, self.parse_term())  # a loop leans left: 1-2-3 is (1-2)-3
        return node

    def parse_term(self):
        node = self.parse_unary()
        while self.peek().kind == "op" and self.peek().text in "*/":
            op = self.advance().text
            node = BinOp(op, node, self.parse_unary())
        return node

    def parse_unary(self):
        if self.peek() == Token("op", "-"):
            self.advance()
            return BinOp("-", Num(0), self.parse_unary())
        return self.parse_atom()

    def parse_atom(self):
        tok = self.advance()
        if tok.kind == "num":
            return Num(int(tok.text))
        if tok.kind == "name":
            return Var(tok.text)
        if tok == Token("op", "("):
            node = self.parse_expr()
            self.expect("op", ")")
            return node
        raise ParseError(f"unexpected {tok.text or 'end of input'!r}")


def parse(src: str):
    """Parse a program into an AST (a Num, Var, BinOp, or Let).

    >>> parse("1 + 2 * 3")
    BinOp(op='+', left=Num(value=1), right=BinOp(op='*', left=Num(value=2), right=Num(value=3)))

    `-x` parses as BinOp("-", Num(0), x). Raise ParseError for an empty
    program, a missing `)`, or tokens left over after a complete expression.
    """
    return Parser(tokenize(src)).parse_program()


def evaluate(node, env=None) -> int:
    """Run an AST and return an int. `env` maps names to ints.

    `/` truncates toward zero, as in C: 7 / 2 is 3 and -7 / 2 is -3.
    Raise EvalError for division by zero and for a name that is not bound.
    A `let` binds its name only inside its body, and does not change `env`.
    """
    env = env or {}
    if isinstance(node, Num):
        return node.value
    if isinstance(node, Var):
        if node.name not in env:
            raise EvalError(f"unbound name {node.name}")
        return env[node.name]
    if isinstance(node, Let):
        inner = dict(env)  # a copy, so the binding vanishes after the body
        inner[node.name] = evaluate(node.value, env)
        return evaluate(node.body, inner)
    left, right = evaluate(node.left, env), evaluate(node.right, env)
    if node.op == "+":
        return left + right
    if node.op == "-":
        return left - right
    if node.op == "*":
        return left * right
    if right == 0:
        raise EvalError("division by zero")
    quotient = abs(left) // abs(right)  # truncate toward zero
    return quotient if (left < 0) == (right < 0) else -quotient


def to_sexpr(node) -> str:
    """Print an AST with every operation in parentheses, operator first.

    >>> to_sexpr(parse("1 - 2 - 3"))
    '(- (- 1 2) 3)'
    >>> to_sexpr(parse("let x = 5 in x"))
    '(let x 5 x)'
    """
    if isinstance(node, Num):
        return str(node.value)
    if isinstance(node, Var):
        return node.name
    if isinstance(node, Let):
        return f"(let {node.name} {to_sexpr(node.value)} {to_sexpr(node.body)})"
    return f"({node.op} {to_sexpr(node.left)} {to_sexpr(node.right)})"


if __name__ == "__main__":
    program = "let x = 4 in x * (x + 1)"
    print("tokens:", [(t.kind, t.text) for t in tokenize(program)])
    tree = parse(program)
    print("tree:  ", tree)
    print("sexpr: ", to_sexpr(tree))
    print("value: ", evaluate(tree))
