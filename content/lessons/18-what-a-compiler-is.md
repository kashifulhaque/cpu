---
title: "What a compiler is: lexing and parsing"
slug: 18-what-a-compiler-is
part: "Part 4 — Compilers and LLVM IR"
summary: Build a lexer, a recursive-descent parser, and an interpreter for a tiny expression language with let bindings.
minutes: 65
gpu: false
objectives:
  - Name the stages of a compiler and say what each one takes in and hands on.
  - Split source text into tokens with a lexer.
  - Write a recursive-descent parser in which precedence comes from the grammar's layers and associativity from a loop.
  - Evaluate an abstract syntax tree with an environment for variables.
prereqs:
  - 17-object-files-linking-and-loading
exercise: 18-what-a-compiler-is
---

# What a compiler is: lexing and parsing

In lesson 16 you watched clang turn `x * 5` into `lea eax, [rdi + 4*rdi]`. Between the C text and the assembly text, clang did a great deal of work, and most of it happened to something that is not text at all. The first thing a compiler does is to read the source and build a tree that shows its structure. Everything after that works on the tree.

This lesson builds the front end of a small compiler. The language is arithmetic with names: `let x = 4 in x * (x + 1)`. You will write the code that reads it, and an interpreter that runs it. Lessons 19 to 23 will take the tree to LLVM IR and then to machine code.

The skills here are not only for compilers. Anyone who has parsed a config file, a query, or a math formula has used them. They show up in editors, linters, databases, and browsers.

## What you already know

- A string is a sequence of characters, and you can walk it with an index.
- A function can call itself, and each call has its own local variables.
- A class holds named fields, and a `dataclass` is a short way to write one.
- A dict maps names to values.
- Division in C truncates toward zero, and `int` arithmetic has a fixed width.

## The stages of a compiler

A compiler is a pipeline of stages. Each stage reads the output of the one before it and produces a different representation of the same program. The picture below shows the whole pipeline and which part of this course covers each stage.

```text
 source text      "let x = 4 in x * 2"
     │
     ▼  lexer             (this lesson)
 tokens           let  x  =  4  in  x  *  2
     │
     ▼  parser            (this lesson)
 syntax tree      Let(x, 4, x * 2)
     │
     ▼  code generator    (lesson 23)
 LLVM IR          %t = mul i32 %x, 2
     │
     ▼  optimizer         (lessons 21, 22)
 better IR
     │
     ▼  back end          (lesson 24)
 machine code     lea / imul / ret
```

The part up to the tree is the **front end**. The IR and optimizer are the **middle end**. Instruction selection and register allocation are the **back end**. This split is why LLVM works for many languages and many processors: each language needs only a front end, and each processor needs only a back end.

## Lexing: text to tokens

Source code is a long string of characters. The first stage groups them into **tokens**, the smallest pieces that have meaning: a number, a name, an operator, a parenthesis. The stage is called **lexing** or tokenizing, and the code is a **lexer**.

For `let x = 4 in x`, the characters are `l`, `e`, `t`, space, `x`, and so on. The tokens are these seven:

| Kind | Text |
|---|---|
| `kw` | `let` |
| `name` | `x` |
| `op` | `=` |
| `num` | `4` |
| `kw` | `in` |
| `name` | `x` |
| `eof` | (empty) |

The last token, `eof`, marks the end of the input. It saves every later stage from checking whether the text has ended.

The lexer walks the string with an index `i` and looks at one character at a time. The decision depends on what the character is.

- A space or newline is dropped.
- A digit starts a number. Keep reading while the next character is a digit.
- A letter or underscore starts a name. Keep reading while the next character is a letter, a digit, or an underscore. Afterward, check whether the word is a **keyword** (`let` or `in`), which has a reserved meaning.
- One of `+ - * / = ( )` is a one-character operator.
- Anything else is an error. Raise `ParseError`, and say which character and where.

Real compilers show you the token stream if you ask. Clang prints one token per line:

```text
int 'int'	 [StartOfLine]	Loc=</tmp/x.c:1:1>
identifier 'f'	 [LeadingSpace]	Loc=</tmp/x.c:1:5>
l_paren '('		Loc=</tmp/x.c:1:6>
...
plus '+'		Loc=</tmp/x.c:1:22>
numeric_constant '1'		Loc=</tmp/x.c:1:23>
```

Each token carries its line and column, so later error messages can point at the right place.

## The syntax tree

The structure that a program has is a tree, not a line. In `1 + 2 * 3`, the `*` happens first, so the tree has `+` at the root, with `1` on the left and the product `2 * 3` on the right.

```text
        +
       / \
      1   *
         / \
        2   3
```

This tree is the **abstract syntax tree**, or **AST**. It is "abstract" because it leaves out the punctuation: the parentheses and spaces are gone, because the shape of the tree already says what they said.

Four small classes cover the whole language. You will use them again in lesson 23.

```python
@dataclass
class Num:      value: int                    # 42
@dataclass
class Var:      name: str                     # x
@dataclass
class BinOp:    op: str; left: Node; right: Node   # left + right
@dataclass
class Let:      name: str; value: Node; body: Node  # let name = value in body
```

The starter gives you these classes. A `BinOp` holds two other nodes, which is what makes the structure a tree. To keep the set small, there is no unary minus node: `-x` is built as `BinOp("-", Num(0), x)`.

## The grammar

A **grammar** is a precise description of which texts are valid programs. Each line is a **rule**: a name on the left, and on the right what it can be made of. A quoted piece is a literal token. `|` means "or". `( ... )*` means "zero or more times".

```text
expr  := "let" NAME "=" expr "in" expr  |  sum
sum   := term (("+" | "-") term)*
term  := unary (("*" | "/") unary)*
unary := "-" unary  |  atom
atom  := NUMBER | NAME | "(" expr ")"
```

Read the rules from the bottom up. An `atom` is the tightest piece: a number, a name, or a parenthesized `expr`. A `unary` is an `atom` with any number of minus signs in front. A `term` is a chain of `unary` pieces joined with `*` or `/`. A `sum` is a chain of terms joined with `+` or `-`. An `expr` is a `sum` or a `let`.

The layers are the whole story of **precedence**, the rule that `*` binds tighter than `+`. The `+` rule is made of `term` pieces, so any `*` is already tucked inside a `term` before `+` sees it.

> [!KEY]
> A grammar with one rule per precedence level gives you precedence for free: tighter operators live in rules lower down.

## Recursive descent

A **recursive-descent parser** has one function for each rule. Each function reads tokens and calls the functions for the rules it contains. It "descends" through the layers and recurses wherever a rule mentions itself, such as parentheses around a whole `expr`.

The parser keeps a list of tokens and a position `pos`. Two helpers do the work: `peek()` returns the current token without consuming it, and `advance()` returns it and moves on.

```python
class Parser:
    def __init__(self, tokens):
        self.tokens, self.pos = tokens, 0

    def parse_atom(self):
        tok = self.advance()
        if tok.kind == "num":
            return Num(int(tok.text))
        ...
```

Trace `1 + 2 * 3`. The indentation shows calls, and each line is a function that is running.

```text
parse_expr
  parse_sum
    parse_term
      parse_unary -> parse_atom -> Num(1)
    peek is "+": not * or /, so parse_term returns Num(1)
    sees "+", consumes it
    parse_term
      parse_unary -> parse_atom -> Num(2)
      sees "*", consumes it
      parse_unary -> parse_atom -> Num(3)
      builds BinOp("*", Num(2), Num(3))
    builds BinOp("+", Num(1), BinOp("*", Num(2), Num(3)))
```

The `*` was absorbed inside the second `parse_term` call, before `parse_sum` could use it. That is how precedence falls out of the call structure.

### Associativity

**Associativity** decides how a chain of the same operator groups. In `1 - 2 - 3`, C and Python read it left to right: `(1 - 2) - 3 = -4`. The other grouping, `1 - (2 - 3)`, gives 2. The two answers differ, so the parser must choose.

A loop gives left associativity. Parse one `term`. While the next token is `+` or `-`, parse another `term` and wrap what you have so far with it as the left child.

```python
def parse_sum(self):
    node = self.parse_term()
    while self.peek() is + or -:
        op = self.advance().text
        node = BinOp(op, node, self.parse_term())   # node becomes the left child
    return node
```

Trace `1 - 2 - 3`: `node = 1`. First pass: `node = BinOp("-", 1, 2)`. Second pass: `node = BinOp("-", BinOp("-", 1, 2), 3)`. The tree leans left, which is `(1 - 2) - 3`. If instead you recursed (`BinOp(op, node, self.parse_sum())`), the tree would lean right, and `1 - 2 - 3` would evaluate to 2. Recursion is the right tool for right-associative operators such as exponentiation.

### Unary minus and `let`

`parse_unary` handles the minus sign. If the next token is `-`, consume it and return `BinOp("-", Num(0), self.parse_unary())`. It calls itself, so `--5` works.

`parse_expr` handles `let`. When the next token is the keyword `let`, read a name, expect `=`, parse an expression for the value, expect `in`, and parse another expression for the body. The body is parsed by `parse_expr`, so it reaches as far to the right as it can: in `let x = 1 in x + 2 * 3`, the body is `x + 2 * 3`, not just `x`.

### Errors

A parser must reject text that is not a program. Three situations cover most cases. A token appears where none is allowed (`* 3`). A required token is missing (`(1 + 2`, with no `)`). Or the expression ends but tokens remain (`1 2`). After `parse_expr` returns, check that the next token is `eof`; if not, raise `ParseError`.

## Evaluating the tree

An **interpreter** runs a program directly from its tree. The function `evaluate(node, env)` walks the tree. `env` is the **environment**, a dict from names to values.

- `Num` returns its value.
- `Var` looks the name up in `env`. If it is not there, raise `EvalError`.
- `BinOp` evaluates its left and right children, then combines the results.
- `Let` evaluates the value, adds `name: value` to a copy of `env`, and evaluates the body with the copy.

The copy matters. A `let` binding lasts only for its body, so `(let x = 1 in x) + x` must fail, because the second `x` is outside. Copying the dict makes the binding vanish when the body is done. This idea, a name that exists only in a region of the program, is called **scope**.

Division follows C. `7 / 2` is 3 and `-7 / 2` is -3, because C truncates toward zero. Python's `//` rounds down and gives -4 for `-7 // 2`, so do the arithmetic on absolute values and put the sign back. Division by zero raises `EvalError`.

A worked example, `let x = 4 in x * (x + 1)`, shows the tree and the evaluation together.

```text
Let x
├─ value: Num(4)
└─ body:  BinOp *
          ├─ Var x
          └─ BinOp +
             ├─ Var x
             └─ Num(1)

evaluate with env {}:
  value = 4, env becomes {x: 4}
  body: x * (x + 1) = 4 * (4 + 1) = 4 * 5 = 20
```

Lesson 23 will compile the same tree to IR instead of running it.

## Try it on your own machine

1. Ask Python to show you its own AST for an expression. Look for `Mult` nested inside `Add`: it is the same tree you will build.

   ```bash
   python3 -c "import ast; print(ast.dump(ast.parse('1+2*3', mode='eval').body))"
   ```

2. Dump clang's token stream for a one-line C file. Count the tokens, and find the line and column of each.

   ```bash
   printf 'int f(int x){return x+1;}\n' > x.c
   clang -fsyntax-only -Xclang -dump-tokens x.c
   ```

3. Dump clang's AST for the same file. The tree is far bigger than yours, but the root-to-leaf structure is the same idea.

   ```bash
   clang -fsyntax-only -Xclang -ast-dump x.c
   ```

## Build it step by step

The functions are tested in this order. The classes `Token`, `Num`, `Var`, `BinOp`, `Let`, and the errors `ParseError` and `EvalError` are given.

1. `tokenize(src)` takes a string and returns a list of `Token` ending in `Token("eof", "")`. Use a `while i < len(src)` loop. The common mistake is to forget the inner loops that consume a whole number or name, which splits `42` into `4` and `2`. Another is to treat `letter` as the keyword `let`: read the whole word first, then compare.
2. `parse(src)` calls `tokenize` and runs your recursive-descent parser. You decide how to organize it. A small `Parser` class with `peek`, `advance`, and one method per rule works well. The common mistake is to skip the final `eof` check, which makes `1 2` parse as `1`.
3. Precedence and associativity live in `parse_sum` and `parse_term`. Use a `while` loop in each. The common mistake is to recurse for the right operand of `-`, which makes `1 - 2 - 3` lean right.
4. `evaluate(node, env=None)` dispatches on the node type with `isinstance`. For `Let`, evaluate the value in the current environment, copy the environment, add the binding, and evaluate the body in the copy. The common mistake is to write into the caller's `env`, which leaks the binding.
5. `to_sexpr(node)` prints the tree with every operation parenthesized and the operator first: `(- (- 1 2) 3)`. A `Let` prints as `(let x value body)`. The checks use this form to see the exact shape of your tree.

## Where this breaks

**Error messages.** Your parser stops at the first problem and says little. A production compiler reports a line and column, and keeps going, so one run shows many errors. That needs token positions and a plan for resuming after an error.

**Many precedence levels.** C has 15 levels of operators. Writing one function per level is tedious. **Precedence climbing** and **Pratt parsing** replace the chain of functions with one loop and a table of binding strengths.

**Left recursion.** A rule like `sum := sum "+" term` looks natural but makes a recursive-descent parser call itself forever without consuming a token. The loop form in this lesson is the standard fix.

**Ambiguity.** Some grammars have texts with two valid trees. The classic case is `if a then if b then c else d`: which `if` owns the `else`? A grammar needs a rule to decide. C resolves it by attaching `else` to the nearest `if`.

**Context.** C cannot be parsed with a pure grammar. In `a * b;` the meaning depends on whether `a` is a type, so the parser needs a table of names it has seen. This is why real C front ends are large.

**Deep nesting.** Each level of parentheses is a Python call. A text with a thousand nested parentheses can hit Python's recursion limit of about 1000 frames, which surfaces as a `RecursionError`, not a `ParseError`.

## Further reading

- [Crafting Interpreters](https://craftinginterpreters.com) is a free book that builds two complete interpreters. Its chapters on scanning and parsing expressions cover this lesson in depth.
- [Pratt Parsers: Expression Parsing Made Easy](https://journal.stuffwithstuff.com/2011/03/19/pratt-parsers-expression-parsing-made-easy/) shows the table-driven alternative to one function per level.
- [The LLVM Kaleidoscope tutorial](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/index.html) builds a lexer and parser and then generates LLVM IR, which is where this course goes next.
- [The Python `ast` module](https://docs.python.org/3/library/ast.html) is a real AST you can inspect for any Python program.

## The exercise

You write `tokenize`, `parse`, `evaluate`, and `to_sexpr`, in the file's order. The AST classes `Num`, `Var`, `BinOp`, and `Let`, the `Token` class, and the exceptions are given, and your parser should stay a plain recursive-descent parser over them, because lesson 23 extends it.

The checks test the lexer on inputs with and without spaces, and on names that start with a keyword. They check the tree shape through `to_sexpr` for precedence, left associativity, unary minus, nested `let`, and parenthesized `let`. They test that malformed programs raise `ParseError`, that evaluation truncates toward zero and raises `EvalError` for division by zero and unbound names, and that `evaluate` leaves the caller's `env` alone. A final check generates 200 random expressions with a seeded generator and compares your result with Python's own `eval`.
