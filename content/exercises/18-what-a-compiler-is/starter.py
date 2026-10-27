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
    raise NotImplementedError


def parse(src: str):
    """Parse a program into an AST (a Num, Var, BinOp, or Let).

    >>> parse("1 + 2 * 3")
    BinOp(op='+', left=Num(value=1), right=BinOp(op='*', left=Num(value=2), right=Num(value=3)))

    `-x` parses as BinOp("-", Num(0), x). Raise ParseError for an empty
    program, a missing `)`, or tokens left over after a complete expression.
    """
    raise NotImplementedError


def evaluate(node, env=None) -> int:
    """Run an AST and return an int. `env` maps names to ints.

    `/` truncates toward zero, as in C: 7 / 2 is 3 and -7 / 2 is -3.
    Raise EvalError for division by zero and for a name that is not bound.
    A `let` binds its name only inside its body, and does not change `env`.
    """
    raise NotImplementedError


def to_sexpr(node) -> str:
    """Print an AST with every operation in parentheses, operator first.

    >>> to_sexpr(parse("1 - 2 - 3"))
    '(- (- 1 2) 3)'
    >>> to_sexpr(parse("let x = 5 in x"))
    '(let x 5 x)'
    """
    raise NotImplementedError


if __name__ == "__main__":
    program = "let x = 4 in x * (x + 1)"
    print("tokens:", [(t.kind, t.text) for t in tokenize(program)])
    tree = parse(program)
    print("tree:  ", tree)
    print("sexpr: ", to_sexpr(tree))
    print("value: ", evaluate(tree))
