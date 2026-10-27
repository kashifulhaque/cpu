---
title: "Generating LLVM IR from your own language"
slug: 23-generating-llvm-ir
part: "Part 4 — Compilers and LLVM IR"
summary: Write the code generator for a small language with variables, comparisons, if, and while, and run its programs on LLVM.
minutes: 70
gpu: false
objectives:
  - Translate expressions, variables, `if`, and `while` into LLVM IR text.
  - Place every variable in an `alloca` in the entry block and use `load` and `store` for access.
  - Build basic blocks and branches so that every block ends in a terminator.
  - Run generated programs with `cputools.run_ir` and check their output.
prereqs:
  - 22-optimization-passes
exercise: 23-generating-llvm-ir
---

# Generating LLVM IR from your own language

In lesson 18 you wrote the front of a compiler: a lexer that cuts text into tokens, and a parser that builds a tree. In lessons 19 to 22 you learned the middle: LLVM IR, memory, and optimization. This lesson connects the two. You take the tree and write the **code generator**, the part that walks it and emits IR.

That is the whole trick behind every LLVM-based language, from Rust to Swift to Julia. The front end turns source text into a tree. The code generator turns the tree into IR. LLVM does everything after that: it optimizes the IR and turns it into machine code for x86-64, ARM, or any other target. Writing a language no longer means writing a back end.

To make the language worth compiling, the lexer and parser in the starter are extended with comparisons, `if`, `while`, and assignment. They are given in full. You write the generator, about 100 lines of Python, and run real programs.

## What you already know

- A parser turns tokens into a tree of nodes such as `Num`, `Var`, and `BinOp`.
- IR has basic blocks, and each ends in a terminator: `br` or `ret`.
- `alloca`, `load`, and `store` give a variable a stack slot, and `mem2reg` turns slots into SSA values and `phi` nodes.
- `icmp` compares two integers and gives an `i1`, a one-bit value.
- `cputools.run_ir` runs a module's `@main` with `lli` and returns its output and exit code.

## The language

The language works on 32-bit integers. Here is a program:

```text
let n = 5;
let product = 1;
while n > 0 {
    product = product * n;
    n = n - 1;
}
print product;
```

It prints `120`. The statements are:

| Statement | Meaning |
|---|---|
| `let x = e;` | declare `x` and set it to `e` |
| `x = e;` | assign to an existing variable |
| `print e;` | print the value and a newline |
| `if e { ... } else { ... }` | run one branch; the `else` part is optional |
| `while e { ... }` | repeat the body while `e` is true |

Lesson 18 had `let x = e in e`, which binds a name inside one expression. A loop needs to change a variable that outlives one iteration, so this language uses statements instead. That is a real design choice: a language with assignment needs mutable variables, and mutable variables are why this lesson needs memory.

The comparison operators are `<`, `<=`, `>`, `>=`, `==`, and `!=`. A comparison gives `1` when it holds and `0` when it does not, so `(1 < 2) + (2 < 3)` is `2`. In `if` and `while`, `0` means false and every other value means true. All values are `i32`.

The starter gives you the tree. A `Program` holds a list of statements, and the statement classes are `Let`, `Assign`, `Print`, `If`, and `While`. Expressions are `Num`, `Var`, and `BinOp`. An `If` holds `cond`, `then`, and `orelse` (a list, empty without `else`). A `While` holds `cond` and `body`.

## How to give a variable a home

Here is the key decision. SSA says every name is assigned once, but `n = n - 1` assigns `n` again. Lesson 21 gave the answer: use the same trick clang uses at `-O0`.

Each variable gets one `alloca` in the entry block. A `let` or an assignment is a `store` to its slot. Every use is a `load`. The generator never thinks about `phi`, because it never has two values for one name: the value lives in memory.

```text
let x = 3;     ->   %x.slot = alloca i32        (once, in the entry block)
                    store i32 3, ptr %x.slot
print x + 1;   ->   %t0 = load i32, ptr %x.slot
                    %t1 = add i32 %t0, 1
```

The slot name is `%NAME.slot`. A dot can never appear in a temp name such as `%t0`, so a user variable can never collide with one.

Why the entry block and not the place of the `let`? A `let` inside a loop body runs once per iteration. An `alloca` runs each time it executes and grows the stack each time. Put in the entry block, it runs once. So `generate` first walks the whole tree with `collect_vars` to find the names, emits all the allocas up front, and gives each a `store i32 0`. That is also why a declared variable reads as `0` until the program assigns it.

> [!KEY]
> A code generator does not need SSA. It gives each variable an `alloca` in the entry block, writes with `store`, reads with `load`, and leaves the conversion to SSA to `mem2reg`.

## Generating expressions

`gen_expr(expr, em)` emits instructions and returns the **operand** that holds the result: a string you can paste into the next instruction. The `Emitter` `em` keeps the list of emitted lines and creates fresh temp names, `%t0`, `%t1`, and so on.

- A `Num` needs no instruction. The operand is the literal, such as `"5"`.
- A `Var` emits `%t3 = load i32, ptr %x.slot` and returns `"%t3"`. If the name is not declared yet, raise `CompileError`.
- A `BinOp` generates its left side, then its right side, then one instruction. `+ - * /` become `add`, `sub`, `mul`, and `sdiv`. `sdiv` is signed division, which rounds toward zero, like C.

Take `(2 + 3) * x`. The generator works from the leaves up:

```text
gen_expr(BinOp(*, BinOp(+, 2, 3), Var x))
  left:  gen_expr(BinOp(+, 2, 3))   emits  %t0 = add i32 2, 3     returns "%t0"
  right: gen_expr(Var x)            emits  %t1 = load i32, ptr %x.slot   returns "%t1"
  emits  %t2 = mul i32 %t0, %t1     returns "%t2"
```

Order matters. Generating the right side before the left changes which temp is which, but not the result. In a language with side effects in expressions it would change the result, so the habit is: left first.

### Comparisons

`icmp slt i32 %a, %b` compares two `i32` values with a signed "less than" and gives an `i1`. The predicates for this language are:

| Source | `icmp` predicate |
|---|---|
| `<` | `slt` |
| `<=` | `sle` |
| `>` | `sgt` |
| `>=` | `sge` |
| `==` | `eq` |
| `!=` | `ne` |

The `s` stands for signed. Lesson 12 showed that `jl` and `jb` disagree on negative numbers, and IR makes you say which one you mean in the name of the predicate.

An `i1` is a different type from `i32`. You cannot add it to an integer. Since every value of the language is an `i32`, the generator widens the result: `%w = zext i1 %c to i32` gives `1` or `0`. That is what lets `(1 < 2) + (2 < 3)` work.

### Conditions

A branch needs an `i1`, not an `i32`. `gen_cond(expr, em)` generates the expression and tests it against zero:

```llvm
%t5 = icmp ne i32 %t4, 0
```

For `if x > 1`, the generator makes an `i1`, widens it to `i32`, then narrows it again with `icmp ne`. A human would skip both steps. LLVM's `instcombine` does the same, so the redundancy costs nothing in the final code. A simple, uniform generator that relies on the optimizer is the standard way to build a compiler.

## Basic blocks and branches

Each `if` and `while` splits a function into several basic blocks. The rule from lesson 20 is strict: a block has exactly one terminator, at its end, and no instruction may follow it. In a generator, that rule becomes a habit: **every time you finish writing a block, write its `br`**.

### If

```text
         +--------+
         |  test  |   br i1 %cond, label %if.then, label %if.else
         +--------+
          /      \
   +---------+  +---------+
   | if.then |  | if.else |     each ends with: br label %if.end
   +---------+  +---------+
          \      /
         +---------+
         | if.end  |    later statements continue here
         +---------+
```

The code for `if x > 1 { print x; } else { x = 0; }` with `x` equal to 3 is this real output of the reference generator, with the module prelude left out:

```llvm
define i32 @main() {
entry:
  %x.slot = alloca i32
  store i32 0, ptr %x.slot
  store i32 3, ptr %x.slot
  %t0 = load i32, ptr %x.slot
  %t1 = icmp sgt i32 %t0, 1
  %t2 = zext i1 %t1 to i32
  %t3 = icmp ne i32 %t2, 0
  br i1 %t3, label %if.then.0, label %if.else.1
if.then.0:
  %t4 = load i32, ptr %x.slot
  %t5 = call i32 (ptr, ...) @printf(ptr @.fmt, i32 %t4)
  br label %if.end.2
if.else.1:
  store i32 0, ptr %x.slot
  br label %if.end.2
if.end.2:
  ret i32 0
}
```

Labels get unique numbers from `em.label("if.then")`. Two `if` statements in one function cannot both define a label called `if.then`. Ask the emitter for each label once, keep the string, and use it in both the `br` and the `start_block`.

Even a missing `else` gets an `if.else` block that only branches to `if.end`. That keeps the shape the same for every `if`. It also means a nested `if` inside a branch works without any special case: it creates its own blocks and ends in its own `if.end`, which then gets this branch's closing `br`.

### While

```text
        br label %while.cond
             |
             v
   +--------------------+ <-----------------+
   | while.cond         |                   |
   |  br i1 %c, body, end                   |
   +--------------------+                   |
        |          |                        |
        v          |                 br label %while.cond
   +------------+  |                        |
   | while.body | -+------------------------+
   +------------+  |
                   v
              +-----------+
              | while.end |
              +-----------+
```

The block that was open must first branch into `while.cond`, because a block cannot flow into the next one without a terminator. The test sits in its own block so the back edge from the body has somewhere to land. When the body finishes, it branches back to `while.cond`. Control reaches `while.end` only when the test fails, and generation continues there.

Here is the loop body of the factorial program, from the real output:

```llvm
while.cond.0:
  %t0 = load i32, ptr %n.slot
  %t1 = icmp sgt i32 %t0, 0
  %t2 = zext i1 %t1 to i32
  %t3 = icmp ne i32 %t2, 0
  br i1 %t3, label %while.body.1, label %while.end.2
while.body.1:
  %t4 = load i32, ptr %p.slot
  %t5 = load i32, ptr %n.slot
  %t6 = mul i32 %t4, %t5
  store i32 %t6, ptr %p.slot
  %t7 = load i32, ptr %n.slot
  %t8 = sub i32 %t7, 1
  store i32 %t8, ptr %n.slot
  br label %while.cond.0
```

> [!KEY]
> Control flow in a generator is blocks and branches: finish the current block with a `br`, start a new labelled block, and remember that every block needs a terminator.

## Print and the whole module

`print` calls the C library's `printf`. The module needs two declarations, which the starter gives as `PRELUDE`: a constant string `"%d\n"`, and `declare i32 @printf(ptr, ...)`. The `...` means printf takes any number of extra arguments. A call to such a function names its full type:

```llvm
%t5 = call i32 (ptr, ...) @printf(ptr @.fmt, i32 %t4)
```

`generate(program)` assembles the module: the prelude, then `define i32 @main() {`, then `entry:`, the allocas, the statements, `ret i32 0`, and `}`. `lli` finds `@main` and runs it, so a program's output appears in `cputools.run_ir(ir).stdout`.

## Try it on your own machine

Each command works on Linux or macOS with LLVM installed.

1. Save the generated IR of a program as `p.ll` (call `print(compile_source(src))` in the starter) and run `lli p.ll`. You see the program's output.
2. Run `opt -S -passes=mem2reg p.ll`. Every `alloca` disappears and `phi` nodes appear at each loop header.
3. Run `opt -S -passes='default<O2>' p.ll`. The factorial program becomes a single `printf` call with the constant `120`, because LLVM evaluates the whole loop at compile time.
4. Run `llc -O2 p.ll -o - --x86-asm-syntax=intel`. Find the `imul` of your language's `*`.
5. Run `clang p.ll -o p && ./p`. The same IR becomes a native executable.

> [!RECAP]
> - The code generator walks the tree and emits IR text; LLVM does the rest.
> - Each variable gets an `alloca` in the entry block, `store` writes it, and `load` reads it.
> - A comparison is `icmp` plus `zext`, and a branch condition is `icmp ne ..., 0`.
> - `if` and `while` are labelled blocks, and every block ends with a `br`.

## Build it step by step

The lexer, parser, tree classes, and `Emitter` are in the starter. You write five functions.

1. `collect_vars(program)` returns the distinct `let` names in order of first appearance. Recurse into `then`, `orelse`, and `body` lists. The mistake to avoid is looking only at the top-level statements, which leaves a `let` inside a loop without a slot.

2. `gen_expr(expr, em)` returns an operand string. `Num` gives the literal, `Var` loads from `em.slot(name)`, and `BinOp` generates left then right. Arithmetic uses `add`, `sub`, `mul`, `sdiv`. Comparisons use `icmp` plus `zext`. The common mistake is returning the `i1` from a comparison, which the verifier rejects the first time it meets an `i32` operation.

3. `gen_cond(expr, em)` calls `gen_expr` and emits `icmp ne i32 V, 0`. Return the temp. The mistake is branching on the `i32` directly: `br` needs an `i1`.

4. `gen_stmt(stmt, em)` handles `Let`, `Assign`, `Print`, `If`, and `While`. For `Let`, generate the value before you call `em.declare(name)`, so `let x = x + 1;` with no earlier `x` raises an error. For an `Assign` to an undeclared name, raise `CompileError`. For `If` and `While`, create the labels once and end every block with `br`. The common mistake is forgetting the closing `br label %end` at the end of the `then` branch.

5. `generate(program)` puts it together: `PRELUDE`, `define i32 @main() {`, `entry:`, an `alloca` and a `store i32 0` for each variable, the statements, `ret i32 0`, and `}`. Join `em.lines` with newlines.

## Where this breaks

- **Division by zero and overflow are undefined.** `sdiv` by zero has no defined result in IR, and `INT_MIN / -1` overflows. A real language adds a check, or defines the behavior, before it emits the instruction. This generator does neither.
- **One scope.** There is a single flat namespace. A `let` inside a loop makes a variable visible after the loop. Real languages keep a stack of scopes in the generator and give shadowed names different slots.
- **One type.** Everything is `i32`. Adding `bool`, `i64`, or floating point means each node needs a type, usually found by a separate pass over the tree called type checking.
- **No functions.** A real front end also emits one `define` per function, handles calls and returns, and often needs `phi` nodes of its own when it wants to avoid the memory round trip.
- **Slow without the optimizer.** The IR you generate is full of loads, stores, and redundant compares. It is correct but would run slowly if compiled with no optimization. Run `mem2reg` and `default<O2>` over it, and most of the cost goes away.

## Further reading

- [Kaleidoscope: code generation to LLVM IR](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/LangImpl03.html) — the LLVM project's own tutorial, which builds the same pipeline for a toy language.
- [Kaleidoscope: extending the language with control flow](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/LangImpl05.html) — `if` and `for` emitted as blocks with `phi`.
- [Kaleidoscope: mutable variables](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/LangImpl07.html) — the alloca-per-variable method of this lesson, and why it is the standard choice.
- [LLVM Language Reference](https://llvm.org/docs/LangRef.html) — every instruction used here: `icmp`, `zext`, `br`, `sdiv`, `call`.
- [Crafting Interpreters](https://craftinginterpreters.com) — a free book that builds a full language, with scopes, functions, and classes, in two ways.

## The exercise

In `starter.py` you write `collect_vars`, `gen_expr`, `gen_cond`, `gen_stmt`, and `generate`. `compile_source` and everything before it are provided. The language is the one on this page. The checks run your code in layers: `gen_expr` and `gen_cond` are wrapped in a tiny `@main` and run with `cputools.run_ir`, then whole programs run and their printed output is compared with hand-computed values: sums, factorials, Fibonacci numbers, nested loops, and gcd.

A check generates sixty random expressions from a seeded generator and compares the program's output with a Python reference that follows 32-bit wrap-around and C-style division. Another reads your IR text to confirm that every `alloca` is in the entry block, then runs `mem2reg` over the module and requires that no `alloca` is left and that the output is the same.
