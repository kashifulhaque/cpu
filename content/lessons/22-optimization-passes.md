---
title: "Optimization passes"
slug: 22-optimization-passes
part: "Part 4 — Compilers and LLVM IR"
summary: Write constant folding, algebraic simplification, copy propagation, and dead-code elimination, then compare them with LLVM's passes.
minutes: 60
gpu: false
objectives:
  - Describe an optimization pass as a function from a program to an equivalent, cheaper program.
  - Implement constant folding, algebraic simplification, copy propagation, and dead-code elimination.
  - Explain why running passes in a loop reaches results that one run does not.
  - Run `instcombine`, `dce`, `gvn`, and `default<O2>` with `cputools.run_opt` and compare their output with yours.
prereqs:
  - 21-memory-in-ir
exercise: 22-optimization-passes
---

# Optimization passes

A compiler front end translates what you wrote, literally. If you wrote `x * 8 + 0`, the first version of the IR multiplies by 8 and adds 0, because that is what the source says. Nobody wants the program to do that work. The compiler's middle section exists to rewrite the program into a cheaper one that gives the same answers.

Each rewrite is small and specific. One replaces `2 + 3` with `5`. One replaces `x * 8` with a shift. One deletes a value nobody reads. Each is a **pass**: a function that takes a program and returns an equivalent program. A compiler is a pipeline of dozens of them.

In this lesson you build four passes over a tiny IR you can hold in your head, run them in a loop, and then see what LLVM's own passes do to the same function. Along the way you meet the rule that governs every optimization: the result must behave exactly like the original.

## What you already know

- LLVM IR is made of instructions that each define one SSA value.
- In SSA each name is assigned once, so one line tells you everything about a name.
- Constants such as `i32 5` can be operands directly.
- `mem2reg` is a pass: it takes IR and returns IR with fewer loads and stores.
- Python tuples and dataclasses: you build a new object rather than change one.

## A three-address IR in Python

LLVM IR is large. To write passes in an hour, you use a small IR with the same flavor. It is called **three-address code**, because each instruction has at most two operands and one result: three addresses in all.

A function is a straight line of instructions. There are no branches, so there is only one path through it. Every name is assigned exactly once. An operand is an integer literal or the name of an earlier value. The instruction set:

| Instruction | Meaning |
|---|---|
| `d = const n` | `d` is the integer `n` |
| `d = copy a` | `d` is the same value as `a` |
| `d = add a b` | `d` is `a + b` |
| `d = sub a b`, `d = mul a b` | subtraction and multiplication |
| `d = shl a b` | `a` shifted left by `b` bits |
| `d = and a b` | bitwise and |
| `ret a` | return `a` |

All arithmetic is 32-bit and wraps around, like `i32` in LLVM. In Python that is a helper `wrap32(n)`, which keeps the low 32 bits and reads them as a signed number. So `2147483647 + 1` is `-2147483648`.

In code, an instruction is a frozen dataclass `Instr(op, dest, args)`, and a function is `Function(name, params, body)` with the body a tuple of instructions. They are **frozen**, which means Python refuses attempts to change them. Every pass builds and returns a new `Function`. A pass that edits its input in place is a common bug, because the caller may want to compare before and after.

Here is a function the passes will work on, written with the starter's `make` helper:

```text
f(x, y):
  t0 = const 3
  t1 = const 4
  t2 = add t0 t1
  t3 = mul y t2
  t4 = mul x 8
  t5 = add t4 0
  t6 = add t3 t5
  t7 = mul y 1
  ret t6
```

It has nine instructions. After you finish the exercise, `optimize` turns it into four. Walk through it by hand first.

> [!KEY]
> A pass is a function from program to program that never changes what the program computes. Each pass in this lesson is simple. The power comes from running many of them, repeatedly.

## Pass 1: constant folding

If every operand of an instruction is known, the compiler can compute the result now and skip the work at run time. This is **constant folding**. Look at the first three lines of the function: `t0` is 3, `t1` is 4, so `t2 = add t0 t1` is `7`.

To fold, you must first know which names are constants. Walk the body once and keep a dictionary of the names defined by `const`. In each later instruction, replace a name found in the dictionary by its value. This is **constant propagation**. If an arithmetic instruction now has two integer operands, compute it with `eval_op` and replace the instruction with `const`.

Trace it:

```text
t0 = const 3          known: t0 = 3
t1 = const 4          known: t0 = 3, t1 = 4
t2 = add t0 t1   -->  t2 = add 3 4   -->  t2 = const 7     known: t2 = 7
t3 = mul y t2    -->  t3 = mul y 7        (y is a parameter: unknown)
```

The rule for wrap-around matters. `eval_op("add", 2147483647, 1)` must return `-2147483648`, not `2147483648`. Folding a program differently from how the hardware runs it is a miscompile: a wrong program from a correct one. LLVM folds with exactly the rules of the type, here `i32`.

The `const` instructions stay after folding. Nothing reads `t0` or `t1` any more, but removing unused code is a different pass's job.

## Pass 2: algebraic simplification

Some instructions can be simplified even when one operand is unknown, because of an identity that holds for every value of the unknown.

| Pattern | Replacement | Why |
|---|---|---|
| `x + 0`, `0 + x` | `copy x` | adding zero changes nothing |
| `x - 0` | `copy x` | the same |
| `x - x` | `const 0` | any value minus itself |
| `x * 1`, `1 * x` | `copy x` | multiplying by one |
| `x * 0`, `0 * x` | `const 0` | |
| `x * 2^k` | `shl x k` | a shift does the same, faster |
| `x << 0` | `copy x` | |
| `x & 0` | `const 0` | |
| `x & x` | `copy x` | |

The multiply-to-shift rule is the famous one. In binary, shifting left by one place doubles a number, so `x * 8` is `x << 3`. A shift is one cheap instruction; on many CPUs a multiply takes longer. Real compilers go further: you saw `lea` standing in for `a * 5` in lesson 16.

Notice the pattern for `x - x`: both operands are the same *name*. That is safe for any value of `x`. An instruction with two integer operands is not simplified here, because folding already handles it.

Each pass leaves its output in a form the next pass can use. Here, simplification turns `t4 = mul x 8` into `t4 = shl x 3`, `t5 = add t4 0` into `t5 = copy t4`, and `t7 = mul y 1` into `t7 = copy y`. It created copies, and copies are the next pass's food.

## Pass 3: copy propagation

`d = copy s` says that `d` and `s` are the same value. Anyone who reads `d` can read `s` instead. **Copy propagation** rewrites each later use of `d` into `s`, following chains: after `b = copy a; c = copy b`, a use of `c` becomes `a`.

```text
t5 = copy t4
t6 = add t3 t5     -->   t6 = add t3 t4
```

Because every name is assigned once, this is always safe: `t4` still holds the same value at `t6` as it did at `t5`. In IR with variables that change, you would have to check nobody reassigned `t4` in between. That is one reason SSA is so convenient.

The `copy` instructions stay for now. Nobody reads `t5` any more, which makes it dead.

## Pass 4: dead-code elimination

An instruction is **dead** when nothing uses its result. Removing it cannot change what the function returns, as long as the instruction has no other effect. Every instruction in this IR is a pure computation, so any with an unused result can go.

The pass works backward, from the end. Start with an empty set of needed names. `ret` is always kept, and its operands become needed. Go up the body. If an instruction's `dest` is in the needed set, keep it and add its operands to the set. If not, drop it.

```text
ret t6          needed: {t6}
t7 = copy y     t7 not needed: drop
t6 = add t3 t4  needed. needed: {t3, t4}
t5 = copy t4    t5 not needed: drop
t4 = shl x 3    needed. needed: {t3, x}
...
```

One backward walk is enough, because the needed set only grows as you go up, and a dead instruction can only have been fed by earlier ones.

> [!WARNING]
> Dead-code elimination is only valid for instructions without side effects. A `store` or a call that prints must stay even if its result is unused. In this lesson's IR every instruction is pure. In real LLVM IR, `dce` checks each instruction first.

## Running passes in a loop

Run them in order on the example. After the four passes the function is:

```text
f(x, y):
  t3 = mul y 7
  t4 = shl x 3
  t6 = add t3 t4
  ret t6
```

Four instructions, down from nine. One round was enough here, but not always. Take this function:

```text
a = mul x 0
b = add a 5
ret b
```

In round one, folding finds nothing: `x` is unknown. Simplification then turns `a` into `const 0`. Folding already ran, so `b` is untouched. In round two, folding sees that `a` is the constant 0, makes `b` the constant 5, and rewrites the return to `ret 5`. Dead-code elimination then removes `a` and `b`, and only `ret 5` remains. A pass can **enable** another, including one that already ran. So the compiler runs the pipeline until a round changes nothing. That state is a **fixed point**.

Your `optimize` does exactly this, with a limit on the number of rounds as a safety net. Real LLVM does not loop forever either. It runs a fixed sequence of passes, some more than once, and `instcombine` iterates internally.

## Comparing with LLVM

The starter includes `to_llvm`, which turns a `Function` into real LLVM IR text. `const` and `copy` have no LLVM instruction, so they become `add i32 0, n` and `add i32 a, 0`. The unoptimized module has these lines:

```llvm
  %t0 = add i32 0, 3
  %t1 = add i32 0, 4
  %t2 = add i32 %t0, %t1
  %t3 = mul i32 %y, %t2
  %t4 = mul i32 %x, 8
  %t5 = add i32 %t4, 0
  %t6 = add i32 %t3, %t5
  %t7 = mul i32 %y, 1
  ret i32 %t6
```

Run `cputools.run_opt(ir, "instcombine")`. **instcombine** is LLVM's peephole pass, a collection of hundreds of local rewrites like the ones you wrote. Real output:

```llvm
define i32 @f(i32 %x, i32 %y) {
entry:
  %t3 = mul i32 %y, 7
  %t4 = shl i32 %x, 3
  %t6 = add i32 %t3, %t4
  ret i32 %t6
}
```

It matches your result exactly, down to the names. One pass did the folding, the simplification, and the copy removal. It also erased the instructions that became unused along the way.

LLVM can do things your passes cannot. Take `a = mul x 7; b = mul x 8; c = add a b; ret c`. Under `default<O2>` the real output is:

```llvm
  %c = mul i32 %x, 15
  ret i32 %c
```

LLVM noticed that `7x + 8x` is `15x`. Your simplifier has no rule for that, and neither does a single copy of `instcombine` on the nine-line function: it matches patterns, and it has a very large collection of them.

Another pass handles a different problem. In this function, `%a` and `%b` compute the same thing:

```llvm
  %a = add i32 %x, %y
  %b = add i32 %x, %y
  %c = mul i32 %a, %b
```

Neither `instcombine` nor `dce` removes `%b`. But `gvn`, **global value numbering**, gives every expression a number and notices that two instructions have the same one. Real output of `gvn`:

```llvm
  %a = add i32 %x, %y
  %c = mul i32 %a, %a
```

That optimization is called **common subexpression elimination**. The `default<O2>` pipeline runs `instcombine`, `gvn`, and many more in an order tuned over many years.

| Pass | What it does | Does it remove `%b` above? |
|---|---|---|
| `dce` | removes instructions whose result is unused | no, `%b` is used |
| `instcombine` | local algebraic rewrites | no |
| `gvn` | removes repeated computations | yes |
| `default<O2>` | the whole pipeline | yes |

> [!KEY]
> Passes are small and specialized, and each can expose work for another. An optimizing compiler is many simple passes in a good order, not one clever algorithm.

## Try it on your own machine

Each command works on Linux or macOS with LLVM installed.

1. Write `f.ll` containing a function with `%t5 = add i32 %t4, 0` and `%t7 = mul i32 %y, 1`, then run `opt -S -passes=instcombine f.ll`. Look for the lines that vanish.
2. Run `opt -S -passes=dce f.ll`. It removes only the unused `%t7`, because `dce` knows nothing about identities such as `x + 0`. The result still has the `add` with 0.
3. Run `opt -S -passes='default<O2>' f.ll`. Compare the result with the `instcombine` output.
4. Run `opt -passes='default<O2>' -print-pipeline-passes -disable-output f.ll` to print the list of passes `-O2` runs. Count them.

> [!RECAP]
> - A pass maps a program to an equivalent program, and each pass here is a few lines of Python.
> - Folding computes known values, simplification applies identities, copy propagation removes aliases, and dead-code elimination deletes unused results.
> - Passes enable each other, so you run them until a round changes nothing.
> - LLVM's `instcombine` matches your rewrites and many more, and `gvn` removes repeated computations.

## Build it step by step

The starter holds the IR in full: `Instr`, `Function`, `make`, `evaluate`, `eval_op`, `wrap32`, and `to_llvm`. You write six functions.

1. `fold_constants(func)` takes a `Function` and returns a new one. Keep a dict of names known to be constants, replace known names in each instruction's args, then fold arithmetic with two ints into `const`, and a `copy` of an int into `const`. The common mistake is forgetting to record the newly created `const` in the dict, so the chain `t0, t1, t2` stops after one step.

2. `simplify_algebra(func)` rewrites the identities in the table above. Write one helper that maps an `Instr` to a replacement, and apply it to each. The common mistake is simplifying an instruction whose operands are both ints. The checks leave those to folding, and `0 + 0` as a `copy 0` is not what they expect.

3. `propagate_copies(func)` keeps a dict `alias` from a copy's dest to its source. Substitute before you record, so chains resolve in one step. The common mistake is substituting into the `copy` instruction itself last, which leaves a chain of length two.

4. `eliminate_dead_code(func)` walks the body in reverse with a set of needed names, as in the trace above. Reverse the result at the end. The common mistake is dropping `ret`, which has no `dest`.

5. `optimize(func, max_rounds=10)` runs the four passes in order inside a loop and stops when a round returns an equal function. `Function` is a dataclass, so `==` compares by value.

6. `llvm_instruction_count(func, passes)` converts with `to_llvm`, runs `cputools.run_opt(ir, passes)`, and counts the non-blank lines between `entry:` and the closing `}`. This is how you compare with LLVM without trusting your eyes.

## Where this breaks

- **Undefined behavior limits folding.** In C, signed overflow is undefined, so a real compiler may assume `x + 1 > x`. LLVM records this with the `nsw` flag on `add`. Your IR wraps always, so you cannot make that assumption. Optimizing with flags makes code faster and gives surprising results when the program breaks its own promise.
- **Branches and loops break the single-pass method.** With control flow, a name may hold different values on different paths, and passes need analyses such as dominators or dataflow. Lesson 24 uses one of them, liveness, to allocate registers.
- **Memory and calls have side effects.** A `store` is never dead just because no later instruction reads the value: another function might. Real compilers use alias analysis to decide what is safe to remove.
- **Pass ordering is a heuristic.** No ordering is best for every program. LLVM's `-O2` pipeline is a compromise, and the passes can cost compile time that grows with program size.
- **A miscompile is worse than a missed optimization.** A pass that returns a wrong program silently corrupts every program it touches. Compiler teams test passes with huge suites, and LLVM ships a tool, Alive2, that proves small rewrites correct.

## Further reading

- [LLVM Passes](https://llvm.org/docs/Passes.html) — a short description of every analysis and transform pass, including `instcombine`, `dce`, and `gvn`.
- [LLVM Language Reference](https://llvm.org/docs/LangRef.html) — the meaning of `nsw`, `nuw`, and poison, which decide what an optimizer may assume.
- [Kaleidoscope tutorial, chapter 4: optimizer and JIT](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/LangImpl04.html) — adds optimization passes to a toy language's compiler.
- [Compiler Explorer](https://godbolt.org) — change the optimization level and watch the same function shrink.
- [Alive2](https://alive2.llvm.org) — an online tool that checks whether an optimization is a valid rewrite.

## The exercise

In `starter.py` you write `fold_constants`, `simplify_algebra`, `propagate_copies`, `eliminate_dead_code`, `optimize`, and `llvm_instruction_count`. The checks run each pass on hand-written functions and compare the result with hand-computed answers. They also generate random programs with a seeded generator and check that every pass, and `optimize`, returns a function that gives the same answers as the original on many inputs, including negative numbers and the extremes of 32-bit values.

The last check asks LLVM to optimize the same functions. It requires that `default<O2>` leaves the same number of instructions as your `optimize` on four functions where a pattern-matching optimizer cannot do better than your four passes. The checks never compare run times.
