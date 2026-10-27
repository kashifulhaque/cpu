---
title: Branch prediction and out-of-order execution
slug: 10-branch-prediction-and-out-of-order
part: "Part 1 — How a CPU works"
summary: Guess branches with 1-bit, 2-bit, and gshare predictors, then see how out-of-order hardware finds work while slow instructions wait.
minutes: 60
gpu: false
objectives:
  - Explain why a branch is a control hazard and what a misprediction costs.
  - Implement static, 1-bit, 2-bit, and gshare predictors and compare their accuracy on loop, alternating, and random traces.
  - Say why a loop exit hurts a 1-bit predictor and why global history helps.
  - Compare in-order and out-of-order finish times with a dependency-chain latency model.
prereqs:
  - 08-pipelining
  - 09-caches
exercise: 10-branch-prediction-and-out-of-order
---

# Branch prediction and out-of-order execution

A pipeline keeps instructions flowing like an assembly line. A branch breaks the flow. After `beq x1, x2, done`, the CPU must fetch the next instruction, but it will not know whether the branch jumps until the branch reaches the execute stage, a few cycles later. Waiting wastes the cycles. Fetching the wrong instructions wastes them too.

CPUs solve this by **guessing**. A **branch predictor** looks at the branch, guesses the outcome, and the pipeline fetches down the guessed path. A right guess costs nothing. A wrong guess means throwing away the work and starting over. Good predictors guess right more than 95% of the time on typical code.

A second trick attacks a different waste: an instruction stuck waiting for a slow load holds up everything behind it. **Out-of-order execution** lets the CPU run later instructions whose inputs are ready. This lesson builds the predictors and a latency model that shows what out-of-order execution buys.

## What you already know

- A branch instruction compares values and either jumps or falls through to the next instruction (lessons 05 and 06).
- A pipeline fetches a new instruction every cycle, and a stalled instruction holds up the ones behind it (lesson 08).
- A dependent instruction waits for its producer, and a load takes longer than an add (lessons 08 and 09).
- A 2-bit number counts from 0 to 3.
- A bitwise XOR is 1 where two bits differ, and `x & mask` keeps the low bits of `x`.

## The cost of a branch

Branches are common, about one instruction in five. Every loop ends with one, and every `if` is one.

In the five-stage pipeline of lesson 08, a branch learns its outcome in EX, in the third stage. By then the pipeline has already fetched two more instructions behind it. If the branch jumps, those two instructions are wrong and must be thrown away, or **flushed**. The lost cycles are the **misprediction penalty**.

Real pipelines are deeper, and the penalty on an x86-64 core is roughly 15 to 20 cycles. If 20% of instructions are branches, 5% of those are mispredicted, and each costs 15 cycles:

```text
extra cycles per instruction = 0.20 * 0.05 * 15 = 0.15
```

A machine that could run at CPI 1.0 runs at 1.15. Halving the misprediction rate recovers half of that, which is why designers spend transistors on prediction.

> [!KEY]
> A branch predictor guesses each branch so the pipeline can keep fetching. A correct guess is free, and a wrong one costs the whole pipeline depth.

## A trace

A **trace** records what a program's branches did: a list of pairs `(pc, taken)`. The `pc` is the address of the branch instruction, which identifies it. `taken` is `True` when the branch jumped.

A loop that runs 10 iterations has a branch at its bottom that jumps back. It is taken 9 times and not taken on the tenth. If the loop runs ten times over, the trace for that one branch is:

```text
T T T T T T T T T N   T T T T T T T T T N   ...   (100 outcomes: 90 T and 10 N)
```

Each predictor is an object with two methods. `predict(pc)` returns the guess, and `update(pc, taken)` tells it the truth. To score a predictor, ask for each guess first, compare it with the outcome, and only then update.

## Static prediction

The simplest predictor ignores history. **Always taken** guesses `True` every time. On the loop trace it is right 90 times in 100. Loops are mostly taken, so this is a decent baseline, though it scores 0% on a branch that is never taken.

## The 1-bit predictor

A **1-bit predictor** remembers the last outcome of each branch and guesses it will repeat. It keeps a table of booleans, indexed by `pc % table_size`, all starting at "not taken".

Trace the loop. At the start the bit says not taken:

```text
outcome:   T    T    T  ...  T    N    T    T  ...  T    N
guess:     N    T    T  ...  T    T    N    T  ...  T    T
right?     no   yes  yes     yes  no   no   yes     yes  no
```

Every iteration costs two mistakes. The exit is a surprise, since the predictor expects `T`. And after the exit, the stored bit says "not taken", so the first iteration of the next run is also guessed wrong. Over the 100-outcome trace that is 20 mistakes: 80 correct, which is worse than always taken.

## The 2-bit predictor

The fix is to need two surprises before changing the guess. A **2-bit saturating counter** counts from 0 to 3:

```text
0 strongly not taken    1 weakly not taken    2 weakly taken    3 strongly taken
```

It guesses taken when the counter is 2 or 3. A taken outcome adds 1, a not-taken outcome subtracts 1, and the counter **saturates**: it stays at 3 when it would go above, and at 0 when it would go below. Each branch starts at 1.

Trace the loop again:

```text
step              counter   guess   outcome   right?   counter after
first T           1         N       T         no       2
second T          2         T       T         yes      3
... (7 more T)    3         T       T         yes      3
exit              3         T       N         no       2
next first T      2         T       T         yes      3     <- no surprise this time
```

After the first run through, the exit pulls the counter from 3 to 2 only, so it still guesses "taken" at the start of the next run. Each loop pass costs one mistake, at the exit. Over 100 outcomes there are 11 mistakes: the first outcome and the 10 exits. That is **89 correct**.

On a branch that is 90% taken but irregular, the 2-bit counter does better than the 1-bit one. The exercise uses a seeded trace of 1000 outcomes, 896 of them taken:

| Predictor | Correct out of 1000 |
|---|---|
| Always taken | 896 |
| 1-bit | 823 |
| 2-bit | 882 |

One rare not-taken outcome costs a 1-bit predictor two mistakes and a 2-bit one a single mistake.

> [!KEY]
> A 2-bit counter has hysteresis: one unusual outcome does not change its mind. That makes it better than a 1-bit predictor on loops and on strongly biased branches.

### Aliasing

The table is small and indexed by `pc % table_size`. Two different branches with the same remainder share an entry, which is called **aliasing**. Suppose branch 0 is always taken and branch 4 is never taken, and they alternate:

```text
table_size = 4: both map to entry 0. They overwrite each other's state: 0 of 20 correct.
table_size = 8: separate entries. Only the very first guess is wrong: 19 of 20 correct.
```

Real hardware aliases too, and a bigger table reduces the damage.

## Patterns that counters cannot learn

Consider a branch that alternates `T N T N T N ...`. The 1-bit predictor is always one step behind and scores 0 of 100. The 2-bit counter, starting at 1, goes 1 to 2 on `T`, then back to 1 on `N`. It always guesses `N` when the outcome is `T`, and `T` when the outcome is `N`. It also scores 0 of 100.

A human sees the pattern at once: the opposite of last time happens next. A per-branch counter cannot, because it keeps only its own count. It needs **history**.

## Gshare: global history

A **gshare** predictor adds a **global history register**: a short bit string holding the last few branch outcomes, newest in the lowest bit. It then indexes its table by the address XOR-ed with the history:

```python
index = (pc ^ history) & (table_size - 1)
```

The same branch now uses a different counter depending on what happened just before. After a `T` it reads one counter, and after an `N` another. Each counter learns what tends to follow that history.

The table holds 2-bit counters, starting at 1. The order of operations matters. `predict` uses the history as it is. `update` adjusts the counter at the same index, and only then shifts the new outcome into the history:

```python
history = ((history << 1) | taken) & mask
```

Trace the alternating branch with `index_bits = 2`. The branch is at `pc = 0x40`, and `0x40 & 3 = 0`, so the index equals the history. All four counters start at 1:

```text
step  history  index  counter  guess  outcome  right?  counter after  history after
1     00       0      1        N      T        no      2              01
2     01       1      1        N      N        yes     0              10
3     10       2      1        N      T        no      2              01
4     01       1      0        N      N        yes     0              10
5     10       2      2        T      T        yes     3              01
6     01       1      0        N      N        yes     0              10
```

From step 4 on, the history after a `T` is `01` and the history after an `N` is `10`. Entry 1 learns "not taken" and entry 2 learns "taken". Only steps 1 and 3 are wrong, so gshare scores **98 of 100**.

Gshare also learns loop exits, if the history is long enough to see them. A loop with a trip count of 4 (taken three times, then not taken, 100 times over) gives:

Always taken scores 300 of 400, a 1-bit predictor 200, a 2-bit predictor 299, and gshare with 4 history bits **394**. The 4-bit history `0111` (an exit, then three taken) always means "the exit comes next".

A trip count of 10 needs at least 9 bits of history to see nine taken outcomes before the exit. Over 1000 outcomes of that loop:

| Predictor | Correct out of 1000 |
|---|---|
| Always taken | 900 |
| 1-bit | 800 |
| 2-bit | 899 |
| Gshare, 4 history bits | 892 |
| Gshare, 10 history bits | 982 |

> [!KEY]
> Gshare indexes its counters by recent history, so a branch can predict differently depending on what came just before. It learns repeating patterns that a lone counter cannot.

No predictor wins on truly random outcomes. On a seeded 50% trace of 1000 outcomes, every one scores near 50%: 477, 503, and 503 correct for the 1-bit, 2-bit, and gshare predictors. If the data decides the branch, no pattern exists to find.

## Out-of-order execution

A different waste: in the pipeline of lesson 08, an instruction that must wait stalls everything behind it, even instructions that do not depend on it. A slow load stalls an unrelated add.

An **out-of-order** (OoO) CPU keeps a window of upcoming instructions, a few hundred of them in modern cores, and runs any whose inputs are ready. Results are committed in the original program order, so the program behaves as if each instruction ran in turn. Two pieces of hardware make it work:

- **Register renaming** gives each result a fresh internal register. Two instructions that reuse the name `x1` no longer conflict, which removes the write-after-read and write-after-write hazards of lesson 08. Only real dependencies, RAW, remain.
- A **reorder buffer** holds instructions in program order until they finish, then retires them in order.

**Speculation** ties it to branches. The CPU predicts a branch and keeps executing past it, tentatively. If the prediction was right, the results become real. If it was wrong, the CPU discards everything after the branch: the misprediction penalty.

### A dependency-chain model

To see the benefit, model each instruction as a pair: a **latency** (cycles to finish) and a list of earlier instructions it **depends on**. An instruction can start only once everything it depends on has finished.

Here are two loads, each followed by an add that uses it, and a final add of both results:

```text
op 0  load a      latency 4   deps: none
op 1  add  (a)    latency 1   deps: 0
op 2  load b      latency 4   deps: none
op 3  add  (b)    latency 1   deps: 2
op 4  add  both   latency 1   deps: 1, 3
```

In the model of the exercise, an **in-order** machine starts instructions in program order, at most one per cycle, and a later instruction never starts before an earlier one:

```text
op 0 starts 0, finishes 4
op 1 starts 4 (waits for op 0), finishes 5
op 2 starts 5 (cannot start before op 1 started, plus 1), finishes 9
op 3 starts 9, finishes 10
op 4 starts 10, finishes 11          -> 11 cycles
```

An **out-of-order** machine with unlimited resources starts each op as soon as its dependencies finish:

```text
op 0 starts 0, finishes 4      op 2 starts 0, finishes 4     (both loads at once)
op 1 starts 4, finishes 5      op 3 starts 4, finishes 5
op 4 starts 5, finishes 6                                    -> 6 cycles
```

The OoO time is the **critical path**: the longest chain of dependent latencies. Here it is load, add, final add: 4 + 1 + 1 = 6. No amount of hardware can finish sooner, because each step on that path needs the one before. In-order hardware took 11, almost twice as long.

The independent work a core can overlap is called **instruction-level parallelism** (ILP). A dependent chain has none: three ops of latency 1 take 3 cycles either way.

## Connect to the real machine

Branch predictors on a real CPU are far more sophisticated than gshare. Modern designs combine several predictors with different history lengths (the best known family is called TAGE), and they track hundreds of bits of history.

The classic experiment sums the elements of an array that are at least 128. With random data the branch is unpredictable. With sorted data it is long runs of one outcome. The C code is:

```c
for (int i = 0; i < n; i++)
    if (a[i] >= 128) sum += a[i];
```

Build the program at `-O0`, where clang keeps the branch. On the machine we tried, 100 passes over a million random values below 256 took 1.5 to 1.9 seconds unsorted and 0.35 to 0.5 seconds sorted, a gap of three to four times. Your numbers will differ.

At `-O2`, clang rewrites the loop with a conditional move or SIMD instructions. The branch disappears, and so does the gap.

Real out-of-order cores have reorder buffers of roughly 200 to 500 entries. A longer window finds more independent work.

> [!WARNING]
> Speculation leaves traces. Wrong-path instructions are squashed, but the data they loaded stays in the cache. The Spectre attacks measure those traces to read data a program should not see. The defences cost some speed.

## Try it on your own machine

1. Count branches and mispredictions (Linux, needs the `perf` package):

   ```bash
   perf stat -e branches,branch-misses ls > /dev/null
   ```

   Expect a miss rate of 1% to 5%. Some virtual machines hide the counters, and `perf` then prints `<not supported>`.

2. Wrap the loop in a program that fills 1,048,576 values with `rand() % 256`, optionally sorts them with `qsort`, and times 100 passes with `clock_gettime`. Compare sorted and unsorted at `clang -O0`, then at `clang -O2`, where the gap shrinks or vanishes.

3. Look for the conditional move with `clang -O2 -S -masm=intel branch.c -o -`. Expect `cmov` or vector instructions in place of the jump.

> [!RECAP]
> - A branch is a control hazard, and a misprediction flushes the pipeline: roughly 15 to 20 cycles on a modern core.
> - A 2-bit counter needs two surprises to change its guess, so it beats a 1-bit predictor on loops.
> - Gshare indexes counters by `pc ^ history`, which lets it learn repeating patterns.
> - Out-of-order hardware finishes in the length of the critical path, not the sum of the latencies.

## Build it step by step

Open `starter.py`. `StaticPredictor` is given in full. Every predictor has `predict(pc)` and `update(pc, taken)`. You write these in order.

1. `OneBitPredictor(table_size=64)` keeps `table`, a list of booleans, all `False`. It reads and writes the entry `pc % table_size`.

2. `TwoBitPredictor(table_size=64)` keeps counters, all starting at 1. `predict` is `counter >= 2`. `update` adds 1 or subtracts 1 and clamps to the range 0 to 3. The common mistake is to let the counter run past 3 or below 0.

3. `GsharePredictor(index_bits=8)` has `2 ** index_bits` counters starting at 1 and a `history` starting at 0. The index is `(pc ^ history) & mask`. In `update`, adjust the counter at the same index `predict` used, then shift the outcome into `history`. The common mistake is to shift the history first, which changes the index.

4. `run_predictor(predictor, trace)` returns the number of correct predictions. Predict, compare, then update.

5. `ooo_time(ops)` takes `(latency, deps)` pairs, where `deps` is a tuple of earlier indexes. Each start is the latest finish among its dependencies (0 with none). Return the largest finish, or 0 for an empty list.

6. `in_order_time(ops)` is the same, except an op cannot start before the previous op started plus 1. Keep the previous start in a variable, beginning at -1.

## Where this breaks

- **History needs room.** Gshare with `h` history bits cannot see a pattern longer than `h` outcomes, and the table grows with the history.
- **Data-dependent branches are unpredictable.** Branches on random data stay near 50% for any predictor. Compilers remove them with conditional moves.
- **Out-of-order windows are finite.** A load that misses every cache takes hundreds of cycles, and the window fills before it returns.
- **Power.** Renaming, a reorder buffer, and speculation consume energy, so small low-power cores are often in-order.
- **The model has no width limit.** `ooo_time` lets every ready op start at once. A real core issues four to six ops a cycle.

## Further reading

- [Branch predictor](https://en.wikipedia.org/wiki/Branch_predictor) on Wikipedia covers static, saturating-counter, two-level, and gshare predictors, with diagrams.
- [Dan Luu, "Branch prediction"](https://danluu.com/branch-prediction/) walks through how real predictors work and why they matter.
- [Agner Fog's microarchitecture manual](https://www.agner.org/optimize/microarchitecture.pdf) documents the predictors and pipelines of real Intel and AMD cores.
- [Why is processing a sorted array faster than processing an unsorted array?](https://stackoverflow.com/questions/11227809/why-is-processing-a-sorted-array-faster-than-processing-an-unsorted-array) is the best-known question about branch prediction, with a thorough answer.
- [Spectre Attacks: Exploiting Speculative Execution](https://spectreattack.com/spectre.pdf) explains how speculation can leak data.

## The exercise

You write four branch predictors and two timing models. `OneBitPredictor`, `TwoBitPredictor`, and `GsharePredictor` each guess a branch and learn from its outcome, and `run_predictor` scores a predictor over a trace of `(pc, taken)` pairs. `ooo_time` and `in_order_time` compute how long a list of `(latency, deps)` operations takes with and without out-of-order execution.

The checks use seeded traces and the exact counts from this lesson: 90, 80, and 89 correct for always-taken, 1-bit, and 2-bit on the loop trace; 0, 0, and 98 on the alternating trace; 896, 823, and 882 on the biased trace; and 6 versus 11 cycles for the two-load example. They also check aliasing and that random outcomes stay near 50%.
