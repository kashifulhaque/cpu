---
title: "Control flow, basic blocks, and SSA"
slug: 20-control-flow-and-ssa
part: "Part 4 — Compilers and LLVM IR"
summary: Write branches and loops in LLVM IR with br and phi, and build a control-flow graph from IR text in Python.
minutes: 75
gpu: false
objectives:
  - Split a function into basic blocks and say what a terminator is.
  - Explain static single assignment and why a `phi` is needed where two paths meet.
  - Write an if/else and a loop in IR, with a `phi` for each value that changes.
  - Build a control-flow graph from IR text and check that each `phi` matches its block's predecessors.
prereqs:
  - 19-llvm-ir-basics
exercise: 20-control-flow-and-ssa
---

# Control flow, basic blocks, and SSA

Straight-line IR is easy: one instruction after another, then `ret`. Real programs branch and loop. In assembly you wrote that with `cmp` and a conditional jump, and a variable such as a loop counter lived in a register that each iteration overwrote.

LLVM IR does it differently, and the difference is one of the best ideas in compiler design. Every value in IR is assigned exactly once. A loop counter that changes on every iteration cannot be one name that is overwritten, so IR uses a special instruction, `phi`, to say "this value is one thing if we came from here and another thing if we came from there".

This lesson teaches blocks, branches, and `phi`. You will write `max`, `abs`, a summing loop, factorial, and `gcd` in IR, and then write Python that reads IR text and draws its control-flow graph.

## What you already know

- A conditional jump goes to a label when a condition holds, and falls through otherwise.
- A loop is a backward jump to an earlier label.
- An IR function is a list of typed instructions that ends in `ret`.
- `icmp` produces an `i1`, and `br` will consume it.
- A graph is a set of nodes and a set of edges, and Python can hold one as a dict of lists.

## Basic blocks

A **basic block** is a straight run of instructions with one way in (the top) and one way out (the bottom). Control enters at the first instruction, runs every instruction in order, and leaves at the last. No jumps land in the middle.

In IR, a block starts with a **label** such as `loop:` and ends with exactly one **terminator**: an instruction that says where control goes next. The terminators you need are these.

| Terminator | Meaning |
|---|---|
| `ret i32 %x` | Return from the function with a value. |
| `br label %next` | Jump to the block `next`, always. |
| `br i1 %c, label %yes, label %no` | Jump to `yes` if `%c` is 1, else to `no`. |

A block with no terminator is an error. So is a terminator in the middle of a block. You cannot "fall through" into the next block by leaving the terminator out; the verifier tells you so.

Take the C function `max`. A branch splits it into four blocks.

```text
        +--------+
        | entry  |   %gt = icmp sgt a, b
        +--------+   br %gt, then, else
         /      \
  +--------+  +--------+
  |  then  |  |  else  |   each one: br done
  +--------+  +--------+
         \      /
        +--------+
        |  done  |   %r = phi ...    ret %r
        +--------+
```

This picture is a **control-flow graph**, or **CFG**. Each box is a basic block and each arrow is a possible jump. The block at the top is the **entry**. The blocks an arrow starts from are **predecessors** of the block it points to, and the blocks it leaves toward are **successors**. Here `done` has two predecessors, `then` and `else`, and `entry` has two successors.

> [!KEY]
> A control-flow graph has one node per basic block and one edge per possible jump. Optimizers reason about the graph, not about line numbers.

## Static single assignment

Suppose you wanted to write `max` in a language where a variable can be assigned many times:

```text
r = b
if a > b: r = a
return r
```

The variable `r` is written twice. That is natural for people and a nuisance for compilers, because at the `return` you must ask which assignment's value `r` holds.

LLVM IR forbids it. Every name is defined by exactly one instruction. This rule is called **static single assignment**, or **SSA**: "single" because there is one definition, and "static" because it is about the text of the program, not about what happens when it runs. The verifier enforces it:

```text
<stdin>:6:3: error: multiple definition of local value named 'y'
  %y = add i32 %x, 2
  ^
```

SSA is not a restriction to work around. It is what makes optimization easy. When every name has one definition, "where did this value come from?" has one answer, and the optimizer can follow it without analyzing control flow. Constant propagation, dead-code removal, and common-subexpression elimination all become simple searches.

### The `phi` instruction

SSA has an obvious hole. In `max`, the result is `a` on one path and `b` on the other, so the join block needs a value that is "either". The instruction that makes one is **phi** (the Greek letter, pronounced "fie").

```llvm
%r = phi i32 [ %a, %then ], [ %b, %else ]
```

Read it as: "the value of `%r` is `%a` if control arrived from the block `then`, and `%b` if it arrived from `else`". A `phi` has one pair, `[ value, %block ]`, for each predecessor of its block.

A `phi` is not an instruction the CPU runs. It is a notation for "pick by the edge you came in on". The back end later turns it into register copies on each incoming edge, as lesson 24 shows.

Three rules apply to `phi`:

1. It must be at the top of its block, before any other instruction.
2. It needs exactly one pair for each predecessor: no missing ones, and none naming a block that is not a predecessor.
3. A value in a pair only has to be available at the *end* of the predecessor it is paired with. That is why a loop's phi can name a value defined further down in the text.

## Writing `max`

Here is `max` in full.

```llvm
define i32 @imax(i32 %a, i32 %b) {
entry:
  %gt = icmp sgt i32 %a, %b
  br i1 %gt, label %then, label %else
then:
  br label %done
else:
  br label %done
done:
  %r = phi i32 [ %a, %then ], [ %b, %else ]
  ret i32 %r
}
```

Trace `imax(3, 7)`. `%gt` is `3 > 7`, false, so control goes to `else`, then to `done`. There, the `phi` sees that it came from `else` and takes `%b`, which is 7. For `imax(9, 2)`, it goes through `then`, and `%r` is `%a`, 9.

The blocks `then` and `else` here contain only a `br`. That is legal and common. They exist so `done` has two distinct predecessors that the `phi` can name.

You may recognize this shape. Clang makes it for the C expression `a > b ? a : b`. At `-O0`, clang first stores the arguments in stack slots. Here is its real output for the conditional, with the stack traffic in place:

```llvm
cond.true:                                        ; preds = %entry
  %2 = load i32, ptr %a.addr, align 4
  br label %cond.end

cond.false:                                       ; preds = %entry
  %3 = load i32, ptr %b.addr, align 4
  br label %cond.end

cond.end:                                         ; preds = %cond.false, %cond.true
  %cond = phi i32 [ %2, %cond.true ], [ %3, %cond.false ]
  ret i32 %cond
```

The comments after the semicolons list each block's predecessors. Clang writes them for you, and your Python code will compute the same list.

## Loops

A loop is a block that is its own ancestor: a branch leads back to it. The variables that change from one iteration to the next become `phi` nodes at the loop's top.

Here is the sum of 1 through `n`, in C and in IR.

```c
long sum_to(long n) { long s = 0; for (long i = 1; i <= n; i++) s += i; return s; }
```

```llvm
define i64 @sum_to(i64 %n) {
entry:
  br label %loop
loop:
  %i = phi i64 [ 1, %entry ], [ %i.next, %body ]
  %s = phi i64 [ 0, %entry ], [ %s.next, %body ]
  %done = icmp sgt i64 %i, %n
  br i1 %done, label %exit, label %body
body:
  %s.next = add i64 %s, %i
  %i.next = add i64 %i, 1
  br label %loop
exit:
  ret i64 %s
}
```

The graph has a cycle.

```text
   +-------+
   | entry |
   +-------+
       |
       v
   +--------+    i > n     +------+
   |  loop  | -----------> | exit |
   +--------+              +------+
     ^    |
     |    | i <= n
     |    v
     |  +------+
     +--| body |
        +------+
```

Each `phi` has two pairs, because `loop` has two predecessors: `entry` (the first time) and `body` (every later time). On entry, `%i` is 1 and `%s` is 0. After the body, `%i.next` and `%s.next` feed the next round.

Trace `sum_to(4)`, one row per time control reaches the top of `loop`.

| Visit | `%i` | `%s` | `%i > 4`? | Next |
|---|---|---|---|---|
| 1 | 1 | 0 | no | `body` computes `%s.next = 1`, `%i.next = 2` |
| 2 | 2 | 1 | no | `%s.next = 3`, `%i.next = 3` |
| 3 | 3 | 3 | no | `%s.next = 6`, `%i.next = 4` |
| 4 | 4 | 6 | no | `%s.next = 10`, `%i.next = 5` |
| 5 | 5 | 10 | yes | `exit` returns 10 |

SSA is not violated: `%i` is defined once, by the `phi`, and on each visit it gets a fresh value, as if each round had its own copy of the variable. "Single assignment" is about the text, not about the run.

The test for the loop is at the top, in `loop`, so `sum_to(0)` and `sum_to(-3)` skip the body and return 0.

### Clang's view

Clang does not write `phi` for loops at `-O0`. It keeps `i` and `s` in stack slots and reads and writes them, which is why `-O0` code is slow. The pass `mem2reg` rewrites the slots as `phi` nodes. Run it through `cputools.run_opt(ir, "mem2reg")` on the `-O0` IR of the C loop above, and you get this, which is the shape you wrote by hand:

```llvm
for.cond:                                         ; preds = %for.inc, %entry
  %s.0 = phi i32 [ 0, %entry ], [ %add, %for.inc ]
  %i.0 = phi i32 [ 1, %entry ], [ %inc, %for.inc ]
  %cmp = icmp sle i32 %i.0, %n
  br i1 %cmp, label %for.body, label %for.end
```

Clang's version has more blocks (`for.body`, `for.inc`, `for.end`) because it translates the three parts of a `for` into three places. The idea is the same. Lesson 21 explains `mem2reg`.

## Reading IR with Python: the control-flow graph

The second half of the exercise builds a CFG from IR text. You do not need LLVM for this, only string handling.

Scan the lines of the function. After you cut off `;` comments and strip spaces:

- A line that ends in `:` starts a block. Its name is the text before the colon.
- A line that starts with `br` or `switch` is a terminator that names successors. Each `label %name` on it is a successor.
- A line that starts with `ret` or `unreachable` ends a block with no successors.

Keep the current block in a variable and add each successor to it. When you have scanned everything, fill in the predecessors by walking every block's successors: if `a` jumps to `b`, then `a` is a predecessor of `b`.

For `sum_to`, the result is:

| Block | Successors | Predecessors |
|---|---|---|
| `entry` | `loop` | (none) |
| `loop` | `exit`, `body` | `entry`, `body` |
| `body` | `loop` | `loop` |
| `exit` | (none) | `loop` |

With the CFG in hand, two more checks are short.

**Does every `phi` match?** For each `phi`, collect the block names in its `[ value, %block ]` pairs and compare them with the predecessors of its block. Any difference is a bug. The verifier reports it too, in its own words:

```text
PHINode should have one entry for each predecessor of its parent basic block!
  %q = phi i32 [ 0, %a ], [ 1, %entry ]
```

Your function returns the same information as a list of strings, such as `"block loop: phi %i has no incoming value for body"`.

**Where are the loops?** Walk the graph depth first from the entry, keeping the set of blocks that are on the current path. An edge that leads to a block on the current path is a **back edge**, and each back edge closes a loop. In `sum_to`, `body -> loop` is the back edge. A block that jumps to itself is also a back edge.

## Try it on your own machine

1. Draw the CFG of a real function. LLVM can print a graph in DOT format with `opt`. You need Graphviz (`dot`) to turn it into an image, so skip this one if you do not have it.

   ```bash
   printf 'int f(int n) { int s = 0; for (int i = 0; i < n; i++) s += i; return s; }\n' > f.c
   clang -S -emit-llvm -O0 -Xclang -disable-O0-optnone f.c -o f.ll
   opt -passes=dot-cfg -disable-output f.ll && ls .*.dot
   ```

2. Run `mem2reg` on the same IR, and compare the `-O0` and promoted versions. Count how many `alloca` instructions remain.

   ```bash
   opt -S -passes=mem2reg f.ll
   ```

3. See what the loop looks like once the optimizer has finished with it. Look for the loop in the IR, and ask whether it is still a loop.

   ```bash
   clang -S -emit-llvm -O2 f.c -o -
   ```

4. Write `sum_to` by hand into a file and lower it with `llc -O0`. The output has many spills (`8-byte Spill`) because `-O0` does no register allocation worth the name. Try `-O2`, and the spills disappear.

   ```bash
   llc -O0 -x86-asm-syntax=intel sum_to.ll -o -
   ```

## Build it step by step

The checks go from the graph tools to the IR functions and end with a test that ties both together.

1. `build_cfg(ir)` returns a dict from block label to `Block`, in the order the blocks appear. Strip comments with `line.split(";", 1)[0]` first. Collect successors with `re.findall(r"label %([\w.$-]+)", line)` on `br` lines, without duplicates. Then fill predecessors in a second pass. The common mistake is to fill predecessors in the same pass, and miss a jump to a block that appears later.
2. `phi_problems(ir)` uses `build_cfg`, and then re-scans the lines to find each `phi`. Parse the incoming blocks with a regular expression for `[ value, %block ]`. Compare the set of incoming labels with the set of predecessors, and describe each difference. Return an empty list when all is right.
3. `back_edges(cfg)` runs a depth-first search from the first block. Keep a `visiting` set for blocks on the current path and a `done` set for finished blocks. An edge to a block in `visiting` goes in the result, and the result is sorted. The common mistake is to treat an edge to any visited block as a back edge: in a diamond, `then` and `else` both reach `done`, and the second one is not a loop.
4. `max_ir()` writes `@imax` as in this lesson.
5. `abs_ir()` writes `@iabs`. Compare with 0, and branch to a block that computes `sub i32 0, %x` or to one that keeps `%x`. The `phi` joins the two. For `INT_MIN`, `0 - x` wraps back to `INT_MIN`, as in C.
6. `sum_to_ir()` writes `@sum_to` with `i64`, as in this lesson. Check `phi` order: `entry` first and `body` second in each.
7. `factorial_ir()` writes `@fact`. The loop is like `sum_to`, with the accumulator starting at 1 and multiplying, and the counter starting at 2. It returns 1 for any `n <= 1`. 20! fits in an `i64`, but 21! does not.
8. `gcd_ir()` writes `@gcd` with Euclid's algorithm: while `b != 0`, replace `(a, b)` with `(b, a mod b)`. Use `srem`, and two `phi` nodes. Both `phi` nodes read the values from the start of the round, so the next `a` is the current `b`. A `phi` may name another `phi` of the same block as an incoming value, and the usual mistake is to name the wrong round's value.

## Where this breaks

**Critical edges.** An edge from a block with several successors to a block with several predecessors is a critical edge. A back end that turns `phi` nodes into copies has no good block to put the copy in, so it splits the edge by adding an empty block. Your `then` and `else` blocks are not wasted: they do the same job.

**`phi` nodes make register allocation harder.** The copies they turn into can form cycles, such as two variables that swap on each iteration, and the back end must break the cycles with a temporary. Lesson 24 returns to this.

**Not all control flow is a branch.** `switch` jumps to one of many blocks. Exceptions add edges that no `br` shows (`invoke`). Your CFG parser handles `br` and `switch` only.

**Irreducible loops.** Some graphs have loops with more than one entry, which `goto` can create. A back-edge search finds cycles in them, but they do not have the clean "loop header" shape that many optimizations assume, so LLVM treats them with care.

**Text is a fragile input.** Your parser reads IR with regular expressions. Quoted names, `callbr`, and unnamed blocks (the entry block can have no label, and LLVM calls it `%0`) would break it. LLVM's own parser handles all of these.

## Further reading

- [LLVM Language Reference: terminator instructions](https://llvm.org/docs/LangRef.html#terminator-instructions) describes `br`, `ret`, `switch`, and the other ways a block ends.
- [LLVM Language Reference: the `phi` instruction](https://llvm.org/docs/LangRef.html#phi-instruction) states the exact rules for `phi` nodes.
- [Kaleidoscope chapter 5](https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/LangImpl05.html) shows how an `if` and a `for` loop turn into blocks and `phi` nodes, with the C++ API.
- [LLVM's `mem2reg` documentation](https://llvm.org/docs/Passes.html#mem2reg-promote-memory-to-register) describes how stack slots become `phi` nodes.
- [Compiler Explorer](https://godbolt.org) can draw the control-flow graph of the assembly it shows, which makes branches and loops easy to see.

## The exercise

You write five functions that return IR text: `max_ir` (`@imax`), `abs_ir` (`@iabs`), `sum_to_ir` (`@sum_to`), `factorial_ir` (`@fact`), and `gcd_ir` (`@gcd`). You also write three Python functions over IR text: `build_cfg`, `phi_problems`, and `back_edges`. The class `Block` is given.

The checks for the graph functions run first. They test an if/else diamond and a loop for exact successors and predecessors, test that the graph is consistent on IR clang generates for four C functions, and test `phi_problems` on correct IR and on IR with a missing and a wrong incoming block. `back_edges` is tested on a diamond, a loop, and nested loops.

The IR checks verify your text with `cputools.verify_ir` and show you LLVM's own error message when it rejects it. They compile each function with `cputools.ir_to_lib` at `-O0`, call it in a child process with a time limit, so that a loop that never ends fails one check, and compare against Python's `max`, `abs`, `math.factorial`, and `math.gcd` over edge cases that include `INT_MIN` and large 64-bit values. The last check runs your CFG tools on your own `sum_to_ir` and expects exactly one back edge and no `phi` problems.
