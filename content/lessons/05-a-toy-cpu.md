---
title: "A toy CPU: fetch, decode, execute"
slug: 05-a-toy-cpu
part: "Part 1 — How a CPU works"
summary: Build a small register machine in Python with memory, a program counter, and flags, then write programs for it.
minutes: 70
gpu: false
objectives:
  - Describe a CPU as registers, memory, a program counter, and flags driven by a fetch, decode, execute loop.
  - Implement an emulator for a small instruction set with arithmetic, memory access, and jumps.
  - Explain how a compare-and-jump pattern builds loops from a flag and a branch.
  - Write programs in the toy instruction set that sum a list and compute a factorial.
prereqs:
  - 04-logic-gates-and-adders
exercise: 05-a-toy-cpu
---

# A toy CPU: fetch, decode, execute

A program is a list of tiny steps, such as "add these two numbers" or "go back to step 4 if the result was zero". A *central processing unit*, or CPU, is the machine that carries those steps out, one after another, very fast.

Parts 2 to 5 of this course show real x86-64 code, and a reader who has never watched a CPU work will find it hard to see what each line does. So here you build the CPU. It is a toy, with nine instructions and a few dozen lines of Python, but it has the same moving parts as a real one. Once you have written the loop that runs it, an `add` or a `jmp` in assembly looks familiar.

You will also write programs for it by hand, in its own tiny instruction set. A program that sums a list, written in the toy's own language, shows you what a compiler has to produce.

## What you already know

- A Python class holds data in attributes and changes it through methods.
- A number lives in a fixed number of bits and wraps around when it overflows.
- An ALU adds and subtracts, and it sets flags such as zero and negative.
- A list is memory in miniature: a row of numbered slots, each holding one number.

## The parts of a CPU

Think of a cook working from a recipe card, with a few mixing bowls on the counter and a pantry across the room. The cook reads one step, does it with the bowls, and moves to the next step. A CPU works the same way.

- **Memory** is the pantry. It is a long row of numbered slots. Each slot has an *address*, which is its number, starting from 0. Memory holds data. It holds the program too, on a real machine.
- **Registers** are the bowls: a few named storage slots inside the CPU. They are much faster to use than memory, and almost every instruction reads or writes them. A real x86-64 CPU has 16 general-purpose registers. The toy has 8, named R0 to R7.
- The **program counter**, or PC, holds the position of the next instruction. It is the cook's finger on the recipe card.
- **Flags** are single bits that remember facts about the last result, such as "it was zero" or "it was negative". You built those in lesson 04.
- An **instruction** is one step. It names an operation, called the *opcode*, and the things it works on, called *operands*.
- The set of all instructions a CPU understands is its *instruction set*.

```text
        +--------------------------- CPU ---------------------------+
        |   PC: 3          flags: Z=0  N=0                          |
        |   registers:  R0=5  R1=2  R2=0  R3=0  R4=0 ... R7=0       |
        +------------------+----------------------------------------+
                           |
                           v
 program:   0: LOADI R0, 5          memory:   0: 10
            1: LOADI R1, 2                    1: 20
            2: ADD R0, R1                     2: 30
            3: HALT                           3:  0
```

> [!KEY]
> A CPU is registers, a program counter, and flags, connected to memory. Everything it does is a loop: read the instruction the PC points at, work out what it says, and do it.

## The fetch, decode, execute cycle

Every CPU repeats three phases forever. Each phase has a name.

1. **Fetch.** Read the instruction at the address in the program counter. Then advance the PC to the next instruction.
2. **Decode.** Work out what the instruction is: which opcode, and which operands.
3. **Execute.** Do it: compute a result, read or write memory, or change the PC.

Fetch, decode, and execute run for one instruction after another. Lesson 08 shows how real CPUs overlap them like an assembly line. Here you run them one after another.

The PC moves forward by one step on each fetch, so instructions run in order. A *jump* is an instruction that overwrites the PC, and that is how a loop or an `if` exists. A jump that only happens when a flag is set is a *conditional jump*.

In Python, the loop looks like this:

```python
def step(self):
    instruction = self.program[self.pc]    # fetch
    self.pc += 1
    opcode, *operands = instruction        # decode
    if opcode == "ADD":                    # execute
        ...
```

The `*operands` syntax collects the rest of the tuple into a list. The advance of `self.pc` happens before the execute step. A jump then sets `self.pc` to its target, replacing the advanced value.

## The instruction set

The toy's instruction set has nine instructions. A program is a Python list of tuples. The first item of each tuple is the opcode, and the rest are operands. A register operand is a number from 0 to 7. A *target* is the position of an instruction in the list, counting from 0.

| Instruction | Does | Flags |
|---|---|---|
| `("LOADI", rd, imm)` | `R[rd] = imm`, a number written into the instruction | unchanged |
| `("LOAD", rd, rb)` | `R[rd] = memory[R[rb]]` | unchanged |
| `("STORE", rs, rb)` | `memory[R[rb]] = R[rs]` | unchanged |
| `("ADD", rd, rs)` | `R[rd] = R[rd] + R[rs]` | set from result |
| `("SUB", rd, rs)` | `R[rd] = R[rd] - R[rs]` | set from result |
| `("MUL", rd, rs)` | `R[rd] = R[rd] * R[rs]` | set from result |
| `("JMP", target)` | `pc = target` | unchanged |
| `("JZ", target)` | `pc = target` if the Z flag is set | unchanged |
| `("HALT",)` | stop the machine | unchanged |

A few choices are worth explaining.

*Immediate* means a constant that sits inside the instruction. `LOADI` is how a program puts a number into a register in the first place.

`LOAD` and `STORE` take the address from a *register*, not from a constant. Reading `memory[R[rb]]` means: look at the register `rb`, take the number in it, and treat that number as an address. This is called *register-indirect* addressing. It lets a loop walk along a list by adding 1 to a register each time.

The three arithmetic instructions overwrite their first operand and set the flags from the result. `Z` is true when the result is 0, and `N` is true when it is negative. Real x86-64 sets its flags in a similar way. The multiply is a convenience: without it, a factorial would need a nested loop, and a real CPU has an `imul` instruction for the same reason.

The registers hold signed 32-bit numbers. Every result wraps, as in lesson 03, so `2147483647 + 1` is `-2147483648`. A helper does the wrapping: `((x + 2**31) % 2**32) - 2**31`.

A program is not stored in the memory of the toy. It is a separate list. Real machines keep code and data in the same memory. Lesson 06 shows how an instruction becomes a number that fits in a memory slot.

## Tracing a program by hand

Start with a program that adds 2 and 3.

```python
add_program = [
    ("LOADI", 0, 2),    # 0: R0 = 2
    ("LOADI", 1, 3),    # 1: R1 = 3
    ("ADD", 0, 1),      # 2: R0 = R0 + R1
    ("HALT",),          # 3: stop
]
```

Trace it. Each row shows the state after the instruction has run:

```text
step   pc before   instruction      R0   R1   Z    pc after
1      0           LOADI R0, 2       2    0   no   1
2      1           LOADI R1, 3       2    3   no   2
3      2           ADD R0, R1        5    3   no   3
4      3           HALT              5    3   no   4
```

`run` returns 4, the number of instructions executed, including `HALT`. The answer is in R0.

### A loop built from a flag and a jump

A loop on a CPU is a conditional jump that goes backwards. Here is a program that counts R0 down from 3 to 0:

```python
countdown = [
    ("LOADI", 0, 3),    # 0: R0 = 3
    ("LOADI", 1, 1),    # 1: R1 = 1
    ("SUB", 0, 1),      # 2: R0 = R0 - 1, and set the Z flag if it is 0 after the subtraction
    ("JZ", 5),          # 3: if R0 is 0, leave the loop
    ("JMP", 2),         # 4: otherwise go round again
    ("HALT",),          # 5
]
```

The trace shows the loop on the second to fourth line and the exit:

```text
pc  instruction     R0  Z      what happens
0   LOADI R0, 3      3  no
1   LOADI R1, 1      3  no
2   SUB R0, R1       2  no     R0 becomes 2
3   JZ 5             2  no     Z is not set, so pc moves on to 4
4   JMP 2            2  no     pc = 2
2   SUB R0, R1       1  no
3   JZ 5             1  no
4   JMP 2            1  no
2   SUB R0, R1       0  yes    Z is set
3   JZ 5             0  yes    pc = 5
5   HALT             0  yes
```

The program ran 11 instructions. The `SUB` sets the flag, the `JZ` reads it, and the `JMP` at the bottom makes the code repeat. Every `while` loop you have ever written becomes a pattern like this in machine code. In lesson 12 you will write exactly this shape in x86-64.

> [!KEY]
> A loop is a jump backwards. A branch is a jump that reads a flag. With those two ideas, a machine that only knows how to add and subtract can compute anything a program can.

### Writing your own programs

The exercise asks for two programs, and both use this pattern.

`sum_list_program(base, n)` must add up `n` numbers in memory, starting at address `base`, and leave the total in R0. Think about which registers it needs: a total, a pointer that starts at `base` and goes up by 1 each time, a counter that starts at `n` and goes down by 1, and a register holding the constant 1. The loop does `LOAD`, `ADD`, move the pointer, decrement the counter, and jump back until the counter hits zero.

Watch for an empty list. If `n` is 0, the loop must not run. The flags come only from `ADD`, `SUB`, and `MUL`, so you need to run one of them on the counter once before the loop starts. Adding a register that holds 0 to the counter does it without changing the counter.

`factorial_program(n)` leaves $n!$ in R0, with $n! = n \times (n-1) \times \dots \times 1$. Use `MUL` to multiply a running result by a counter. Use the same count-down loop to walk the counter from `n` to 1.

## Errors the machine must catch

A real CPU can hit faults too. If the PC points outside the program, the toy has nothing to fetch. If an opcode does not exist, it cannot decode. If a `LOAD` or `STORE` uses an address outside memory, it cannot execute. The toy raises a `CPUError` in each case.

A program that never halts is a fault of its own. `run` takes a `max_steps` limit and raises `CPUError` when the program uses it up, so an infinite loop becomes an error instead of a hang.

Python lists accept negative indexes, so `memory[-1]` quietly reads the last slot. A real machine has no such feature, so the toy must test addresses itself.

## Try it on your own machine

1. Watch a real program counter. On x86-64 it is the register `rip`. Run `objdump -d -M intel /bin/true | head -40` (this needs `objdump` from binutils, or use `llvm-objdump -d --x86-asm-syntax=intel`). Look at the column of addresses on the left. Each instruction has an address, and the addresses go up by different amounts, because x86 instructions have different lengths.
2. Count the real registers. `python3 -c "print(['rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp'] + [f'r{i}' for i in range(8, 16)])"` lists the 16 general-purpose registers of x86-64. The toy has 8.
3. Run the toy's trace yourself. After you have filled in the `CPU` class, add `print(cpu.pc, cpu.regs, cpu.zero)` after each `cpu.step()` in a loop, and compare with the 11-line trace above.
4. Count how fast a real CPU steps. Run `lscpu | grep -i 'model name'` on Linux. A clock of 3 GHz is three billion cycles a second, and a modern core can finish several instructions per cycle, so one core runs billions of toy-sized steps each second.

## Build it step by step

The starter has the instruction table in its docstring and a `__main__` block that runs three programs. Build the pieces in this order.

1. `CPU.__init__(program, memory=None, mem_size=64)` copies the program, copies `memory` if you pass one, and otherwise makes `mem_size` zeros. It sets 8 registers to 0, `pc` to 0, `zero` and `negative` to `False`, and `halted` to `False`. The usual mistake is to keep a reference to the caller's list instead of a copy, so the program changes memory the test still holds.
2. `CPU.step()` runs one instruction. Fetch with `self.program[self.pc]` after checking that `pc` is in range. Advance `pc` by 1. Split the tuple with `opcode, *operands = instruction`. Then use an `if` chain on the opcode. A common mistake is to advance `pc` after executing, which breaks every jump.
3. Handle the arithmetic in one branch for `ADD`, `SUB`, and `MUL`. Compute the raw result, wrap it to a signed 32-bit number, store it, then set `zero` from `result == 0` and `negative` from `result < 0`. `LOADI`, `LOAD`, and `STORE` do not touch flags. `LOADI` wraps its immediate too.
4. For `LOAD` and `STORE`, read the address from the register, and raise `CPUError` unless it is in `0 .. len(memory) - 1`. For `JZ`, jump only when `self.zero` is true. For `HALT`, set `halted`. Raise `CPUError` for any other opcode.
5. `CPU.run(max_steps=100_000)` calls `step` until `halted` is true. It returns the number of steps, `HALT` included. If it reaches `max_steps` first, it raises `CPUError`.
6. `sum_list_program(base, n)` returns a list of instructions. Number them as you write them, because every jump target is an index into this list. Test it by hand on `memory = [5, 6, 7]` before you run the checks.
7. `factorial_program(n)` returns a list that leaves $n!$ in R0, for $n$ at least 1. The check also runs 13!, where the result wraps around to 1,932,053,504, because $13! = 6{,}227{,}020{,}800$ is too big for 32 bits.

If a program check fails, the message names the list and the value it expected. Trace the program on paper, using the table format above, and look for the row where your register differs from what you meant.

## Where this breaks

The toy leaves out most of what makes real CPUs hard.

- **Variable instruction length.** Each toy instruction takes one slot. x86-64 instructions are 1 to 15 bytes, so the PC moves by different amounts. RISC-V, which lesson 06 uses, uses 4 bytes for every instruction.
- **Code and data in one memory.** Real programs live in memory next to their data, and the PC is an address. That allows self-modifying code and exploits. Lesson 07 puts a stack and function calls into the same memory.
- **One instruction at a time.** A real CPU overlaps the phases of many instructions in a *pipeline*. Lesson 08 shows the cost when they depend on each other. Lesson 10 shows out-of-order execution, where the CPU reorders work.
- **No interrupts or privilege.** A real CPU can be interrupted by a timer or a device, and it runs the operating system in a privileged mode. A toy program owns the machine.
- **Few flags and few instructions.** x86-64 has hundreds of instructions, flags for carry, overflow, parity, and more, and a `cmp` instruction that sets flags without storing a result. The toy sets flags from `ADD`, `SUB`, and `MUL`, so every comparison costs an instruction that overwrites a register.

## Further reading

- [Von Neumann architecture on Wikipedia](https://en.wikipedia.org/wiki/Von_Neumann_architecture) describes the stored-program design that nearly every CPU follows.
- [Instruction cycle on Wikipedia](https://en.wikipedia.org/wiki/Instruction_cycle) explains fetch, decode, and execute, and the variations real CPUs use.
- [Nand2Tetris, part 2](https://www.nand2tetris.org/) builds a full computer, from the ALU to an assembler, and its Hack machine is a sibling of this toy.
- [Little Man Computer on Wikipedia](https://en.wikipedia.org/wiki/Little_man_computer) is a classic teaching CPU with a tiny instruction set, close in spirit to this one.
- [The RISC-V specifications](https://riscv.org/technical/specifications/) define a clean, real instruction set. Lesson 06 encodes a subset of it.

## The exercise

You write the machine and two programs for it. The class `CPU` has `__init__`, `step`, and `run`. The exception `CPUError` is provided. The functions `sum_list_program(base, n)` and `factorial_program(n)` return programs as lists of tuples.

The checks go from small to large. They test `LOADI` and `HALT`, a single `step`, the arithmetic instructions with their flags, 32-bit wrap-around, `LOAD` and `STORE` through registers, and the two jumps. Then they check that bad programs raise `CPUError`. The last two checks run your programs on your CPU: the list sums, including an empty list, a negative list, and a 50-item list, and the factorials of 1 through 13.
