---
title: Pipelining and hazards
slug: 08-pipelining
part: "Part 1 — How a CPU works"
summary: Overlap the stages of instructions like an assembly line, then count the stalls that dependencies force and that forwarding removes.
minutes: 60
gpu: false
objectives:
  - Draw a five-stage pipeline timeline and explain why n instructions take n + 4 cycles.
  - Find read-after-write hazards in a short program.
  - Count stall cycles with and without forwarding, including the load-use bubble.
  - Compute CPI for a program and say what pushes it above 1.
prereqs:
  - 05-a-toy-cpu
  - 06-instruction-encoding
exercise: 08-pipelining
---

# Pipelining and hazards

The toy CPU of lesson 05 finishes one instruction before it starts the next. Fetch, decode, execute, store the result, and only then begin again. While the arithmetic circuits work, the fetch circuits sit idle, and the reverse.

Real CPUs avoid that waste with a **pipeline**. Think of a laundry: wash, dry, fold. You do not wait for load one to be folded before you start washing load two. While load one dries, load two washes. Every machine stays busy, and clothes come out faster, even though each load still takes the same three steps.

The catch is that instructions depend on each other, and a dependent instruction may need a result that is not ready yet. This lesson builds a model that counts cycles for a pipelined processor, finds those dependencies, and charges the cost. It is the model behind the words "CPI" and "stall".

## What you already know

- A CPU runs a loop: fetch an instruction, decode it, execute it, repeat (lesson 05).
- An instruction names destination and source registers, such as `add x3, x1, x2` (lesson 06).
- A **clock** ticks at a steady rate, and one tick is a **cycle**. A 3 GHz clock ticks three billion times a second.
- A register holds a value until something writes another value (lesson 05).
- A load reads memory into a register, and a store writes a register to memory (lesson 07).

## The five stages

Split each instruction's work into five steps, each small enough to fit in one clock cycle. This is the classic RISC pipeline:

| Stage | Name | Work |
|---|---|---|
| IF | Instruction fetch | Read the instruction at the program counter from memory. |
| ID | Instruction decode | Work out what it does and read its source registers. |
| EX | Execute | Do the arithmetic, or compute a memory address. |
| MEM | Memory access | A load reads memory. A store writes memory. Other instructions do nothing. |
| WB | Write back | Write the result into the destination register. |

Without a pipeline, each instruction takes five cycles and the next one waits. With a pipeline, as soon as instruction 1 moves from IF to ID, instruction 2 enters IF, so each stage works on a different instruction at the same time.

A **pipeline diagram** shows this. Rows are instructions, columns are cycles, and each cell says which stage the instruction is in. Here are four independent instructions:

```text
cycle:              1    2    3    4    5    6    7    8
addi x1, x0, 1      IF   ID   EX   MEM  WB
addi x2, x0, 2           IF   ID   EX   MEM  WB
addi x3, x0, 3                IF   ID   EX   MEM  WB
addi x4, x0, 4                     IF   ID   EX   MEM  WB
```

The first instruction needs 5 cycles. After that, one instruction completes every cycle. For `n` instructions with no delays, the total is:

$$
\text{cycles} = n + 4
$$

Four instructions take 8 cycles, and a hundred take 104. In the long run the machine finishes close to one instruction per cycle, though no single instruction got faster.

> [!KEY]
> A pipeline raises **throughput**, the number of instructions finished per cycle, and leaves **latency**, the time for one instruction, unchanged. A perfect five-stage pipeline approaches one instruction per cycle.

**CPI** (cycles per instruction) is total cycles divided by instructions. The ideal is 1. A hundred independent instructions give 104 / 100 = 1.04. Real programs sit above 1 on a simple pipeline because of the delays this lesson covers. Modern CPUs finish several instructions per cycle, so they quote the inverse, **IPC**, instructions per cycle.

## Hazards: when the assembly line stalls

A **hazard** is a situation where the next instruction cannot proceed in the next cycle. There are three kinds.

- A **structural hazard**: two instructions need the same hardware at once, such as IF and MEM both reading one memory. Separate instruction and data caches avoid it.
- A **data hazard**: an instruction needs a value an earlier instruction has not produced yet. This lesson models it.
- A **control hazard**: at a branch, the CPU does not yet know which instruction comes next. Lesson 10 covers it.

The most common data hazard is **read after write** (RAW): an instruction reads a register that an earlier instruction writes.

```text
add x1, x2, x3     # writes x1
add x4, x1, x5     # reads x1, needs the result of the line above
```

The second `add` needs `x1` in its ID stage, where it reads registers. The first `add` does not write `x1` until its WB stage, three cycles after its own ID. The second instruction must wait.

One detail makes the wait shorter. The register file writes in the first half of a clock cycle and reads in the second half. An instruction in ID can therefore read a register in the same cycle another instruction writes it in WB. This model uses that rule: a consumer can leave ID in the cycle its producer is in WB.

## Stalls

To wait, the pipeline **stalls**: the dependent instruction stays in ID, repeating the stage, and everything behind it waits too. Each cycle of waiting is a **bubble**, a stage doing no useful work. Here is the pair above with no forwarding:

```text
cycle:              1    2    3    4    5    6    7    8
add x1, x2, x3      IF   ID   EX   MEM  WB
add x4, x1, x5           IF   ID   ID   ID   EX   MEM  WB
                                   stall stall
```

The first `add` is in WB in cycle 5. The second can leave ID in cycle 5, reading `x1` in the second half. Its two extra cycles in ID, 3 and 4, are stalls. Two instructions take 8 cycles instead of 6.

The distance between producer and consumer sets the cost:

| Distance | Example | Stall cycles (no forwarding) |
|---|---|---|
| 1 (adjacent) | producer, then consumer | 2 |
| 2 (one instruction between) | producer, other, consumer | 1 |
| 3 or more | | 0 |

An independent instruction between the two fills what would have been a bubble, and compilers try to find one.

### The model, as arithmetic

Give each instruction `i` a number `id[i]`, the cycle in which it leaves ID. The first is at cycle 2, after IF in cycle 1. Instructions enter ID in order, one per cycle at best, so:

```text
id[i] = max( id[i-1] + 1,
             id[p] + 3  for each producer p of a register i reads )
```

The term `id[p] + 3` is the producer's WB cycle: EX is `id + 1`, MEM is `id + 2`, WB is `id + 3`. Stalls before instruction `i` are `id[i] - (id[i-1] + 1)`. The last instruction finishes its WB at `id[last] + 3`.

Check the pair: `id[0] = 2`, and `id[1] = max(3, 2 + 3) = 5`, so 2 stalls, and the total is `5 + 3 = 8`. ✓

Take a chain of three: `add x1,x2,x3`, `add x4,x1,x1`, `add x5,x4,x1`.

```text
id[0] = 2
id[1] = max(3, id[0] + 3) = 5          stalls 2
id[2] = max(6, id[1] + 3 = 8, id[0] + 3 = 5) = 8   stalls 2
total = 8 + 3 = 11   (7 ideal + 4 stalls)
```

The producer of a register is its nearest earlier writer. If two earlier instructions write `x1`, the reader waits for the nearer one.

## Forwarding

The wait is wasteful. The first `add` computes its answer at the end of EX. The value is ready then, three stages before it reaches the register file. **Forwarding**, also called **bypassing**, adds wires that carry a result straight from the end of EX (or MEM) to the input of the ALU for the next instruction. The consumer no longer waits for WB.

```text
cycle:              1    2    3    4    5    6
add x1, x2, x3      IF   ID   EX   MEM  WB
add x4, x1, x5           IF   ID   EX   MEM  WB
                                  ^
                  result forwarded from the end of EX
```

With forwarding, the dependent pair takes 6 cycles and no stall. For arithmetic, forwarding removes every stall.

### The load-use bubble

A load is different. Its data comes from memory, so it is ready only at the end of MEM. The next instruction needs it at the start of its EX, which is the same cycle as the load's MEM. Forwarding cannot reach back in time. The consumer must wait one cycle:

```text
cycle:              1    2    3    4    5    6    7
lw  x1, 0(x2)       IF   ID   EX   MEM  WB
add x3, x1, x4           IF   ID   ID   EX   MEM  WB
                                  stall
```

This is the **load-use hazard**, and its cost is one bubble. A load two instructions before its user costs nothing, because the data has arrived by then. A compiler can move an unrelated instruction into the gap, a trick called **instruction scheduling**.

> [!KEY]
> Forwarding removes the stalls for results computed by the ALU. A load followed immediately by an instruction that uses it still costs one cycle.

The model treats every reader of a loaded register the same way. A real pipeline can forward a loaded value into a store's data input without a bubble. This model keeps one rule.

## A whole program

Here is a four-instruction program, with the stall counts under both designs. It loads two array elements, adds them, and stores the sum.

```text
lw  x1, 0(x2)
lw  x3, 4(x2)
add x4, x1, x3
sw  x4, 8(x2)
```

Without forwarding, `id` is 2, 3, 6, 9:

```text
cycle:          1   2   3   4   5   6   7   8   9   10  11  12
lw  x1, 0(x2)   IF  ID  EX  MEM WB
lw  x3, 4(x2)       IF  ID  EX  MEM WB
add x4, x1, x3          IF  ID  ID  ID  EX  MEM WB
sw  x4, 8(x2)               IF  IF  IF  ID  ID  ID  EX  MEM WB
```

The `add` waits for the second load's WB in cycle 6, which is 2 stalls. The `sw` waits for the `add`'s WB in cycle 9, another 2. The program takes 8 ideal cycles plus 4 stalls: **12 cycles**, CPI 12 / 4 = **3.0**.

With forwarding, only the second `lw` and the `add` form a load-use pair:

```text
cycle:          1   2   3   4   5   6   7   8   9
lw  x1, 0(x2)   IF  ID  EX  MEM WB
lw  x3, 4(x2)       IF  ID  EX  MEM WB
add x4, x1, x3          IF  ID  ID  EX  MEM WB
sw  x4, 8(x2)               IF  IF  ID  EX  MEM WB
```

One stall, so **9 cycles**, CPI **2.25**. The `sw` reads `x4` straight from the `add`'s forwarded result.

## Connect to the real machine

Real pipelines are longer and wider. Modern x86-64 cores have roughly 14 to 20 stages, and they are **superscalar**: they start up to four to six instructions in every cycle. A well-tuned program can reach an IPC of 3 or 4.

Common latencies (the cycles before a result can feed a dependent instruction) are close to these on recent Intel and AMD cores. The exact numbers depend on the CPU model, and Agner Fog's tables list them:

| Operation | Typical latency |
|---|---|
| Integer add, `lea`, logic | 1 cycle |
| Integer multiply (`imul`) | 3 cycles |
| Load that hits the L1 cache | 4 to 5 cycles |
| Floating-point add | 3 to 4 cycles |

The load row is the load-use bubble, stretched: on a real machine a dependent instruction waits 4 or 5 cycles for a load, not 1, because the data comes through the cache.

You can see the effect. Summing doubles into one variable makes each add wait for the one before. Summing into four variables lets four adds overlap:

```c
double sum1(const double *a, long n) {
    double s = 0;
    for (long i = 0; i < n; i++) s += a[i];        /* one chain of dependent adds */
    return s;
}

double sum4(const double *a, long n) {
    double s0 = 0, s1 = 0, s2 = 0, s3 = 0;
    for (long i = 0; i < n; i += 4) {              /* four independent chains */
        s0 += a[i]; s1 += a[i + 1]; s2 += a[i + 2]; s3 += a[i + 3];
    }
    return s0 + s1 + s2 + s3;
}
```

Compiled at `-O2` without `-ffast-math`, the compiler may not reorder floating-point additions, since that changes the rounding. `sum1` stays a single dependent chain, and `sum4` is typically three times faster or more. The ratio depends on your processor.

> [!TIP]
> Latency and throughput are different numbers. When a loop is slow, ask first whether each step waits for the previous one (a dependency chain), or whether the machine is short of execution units.

## Try it on your own machine

1. Count cycles and instructions for a real program (Linux, needs the `perf` tool, which is a separate package):

   ```bash
   perf stat -e cycles,instructions ls > /dev/null
   ```

   Expect a line such as `insn per cycle`. Values between 0.5 and 3 are normal. A program stuck on memory scores low.

2. Read your CPU's model and cache sizes (Linux):

   ```bash
   lscpu | head -20
   ```

   Look up the model name in Agner Fog's tables to find its real latencies.

3. Compare the two sums above: add a `main` that fills a 100,000-element array and calls one function 10,000 times, build with `clang -O2`, and time each version with `time`. Expect `sum4` to win.

4. Disassemble the loop with `clang -O2 -S -masm=intel sum.c -o -`. In `sum1`, look for an `addsd` that reads and writes the same register on every iteration: that is the dependency chain.

> [!RECAP]
> - Five stages (IF, ID, EX, MEM, WB) overlap, so `n` independent instructions take `n + 4` cycles.
> - A RAW hazard stalls a consumer until its producer's WB: 2 cycles at distance 1, 1 at distance 2.
> - Forwarding removes ALU stalls, but a load followed by its user still loses 1 cycle.
> - CPI is total cycles divided by instructions, and stalls push it above 1.

## Build it step by step

Open `starter.py`. The `Instr` dataclass and `parse(line)` are given in full: `parse("add x3, x1, x2")` returns an `Instr` with `dest` `"x3"` and `srcs` `("x1", "x2")`, a load has `is_load=True`, and register `x0` never appears as a dependency. You write six functions, in this order.

1. `ideal_cycles(n)` returns `n + 4`, or 0 for an empty program.

2. `find_raw(program)` returns a sorted list of `(producer, consumer)` index pairs. For each consumer and each register it reads, look back at the instructions at distance 1 and 2, nearest first, and stop at the first whose `dest` matches. The common mistake is to report both writers of the same register. Only the nearest counts.

3. `stalls_no_forwarding(program)` returns one stall count per instruction. Track `id[i]` with the formula above. The producer of a register is the nearest earlier writer at any distance, so look all the way back.

4. `stalls_forwarding(program)` returns 1 for an instruction whose predecessor is a load that writes a register it reads, and 0 otherwise.

5. `total_cycles(program, forwarding=False)` is `ideal_cycles(len(program)) + sum(stalls)`.

6. `cpi(program, forwarding=False)` is the total divided by the instruction count, as a float.

## Where this breaks

- **Branches.** The pipeline must fetch the next instruction before a branch has been decided. A wrong guess wastes the stages already filled, and a deep pipeline wastes many. The next lesson covers prediction.
- **Memory.** A load that misses the cache takes tens or hundreds of cycles, not 1. The pipeline stalls for it unless the CPU can run other instructions meanwhile. Lesson 09 covers the cache, and lesson 10 the machinery for running later instructions early.
- **Out-of-order machines.** Real cores run any instruction whose inputs are ready and rename registers to remove false dependencies. The model changes from "stall" to "find other work".
- **Other hazards.** Write after read (WAR) and write after write (WAW) cannot occur in a simple in-order pipeline, so this lesson ignores them. They matter once instructions finish out of order.
- **Some instructions take many cycles.** Division stalls the pipeline or runs alongside it.

## Further reading

- [Classic RISC pipeline](https://en.wikipedia.org/wiki/Classic_RISC_pipeline) on Wikipedia describes the five stages, the hazards, and forwarding paths in detail.
- [Agner Fog's microarchitecture manual](https://www.agner.org/optimize/microarchitecture.pdf) explains the pipelines of real Intel and AMD cores.
- [Agner Fog's instruction tables](https://www.agner.org/optimize/instruction_tables.pdf) list the latency and throughput of every x86 instruction on each core.
- [uops.info](https://uops.info/table.html) provides measured latency and throughput for x86 instructions on recent CPUs.
- Hennessy and Patterson, *Computer Architecture: A Quantitative Approach*, has the standard treatment of pipelines and hazards in its appendix on pipelining.

## The exercise

You write the cycle-counting model for a five-stage pipeline. `find_raw` locates read-after-write dependencies. `stalls_no_forwarding` and `stalls_forwarding` return the stalls each instruction suffers under the two designs, and `total_cycles` and `cpi` turn them into the numbers a performance engineer quotes.

The checks use the hand-worked programs in this lesson: two dependent adds (8 cycles, then 6), a load followed by its user (8, then 7), the three-add chain (11 cycles, then 7), and the four-instruction array example (12 cycles and CPI 3.0, then 9 cycles and CPI 2.25). They also check `x0` handling, the nearest-writer rule, and a ten-times unrolled loop body.
