"""A toy CPU: registers, memory, a program counter, flags, and nine instructions.

A program is a list of instructions. An instruction is a tuple whose first item
is the opcode, written in capitals:

  ("LOADI", rd, imm)   rd = imm
  ("LOAD",  rd, rb)    rd = memory[R[rb]]           (R[rb] holds an address)
  ("STORE", rs, rb)    memory[R[rb]] = R[rs]
  ("ADD",   rd, rs)    rd = rd + rs                 (sets flags)
  ("SUB",   rd, rs)    rd = rd - rs                 (sets flags)
  ("MUL",   rd, rs)    rd = rd * rs                 (sets flags)
  ("JMP",   target)    pc = target
  ("JZ",    target)    pc = target if the zero flag is set
  ("HALT",)            stop

`target` is an index into the program list. Registers are numbered 0 to 7 and
hold signed 32-bit numbers: results wrap around, as on real hardware.
"""

NUM_REGISTERS = 8


class CPUError(Exception):
    """The program did something the machine cannot do."""


class CPU:
    """The machine. Build it with a program and (optionally) starting memory.

    cpu = CPU([("LOADI", 0, 7), ("HALT",)])
    cpu.run()        -> 2   (the number of instructions executed, HALT included)
    cpu.regs[0]      -> 7

    Attributes: regs (list of 8 ints), memory (list of ints), pc (int),
    zero (bool, the Z flag), negative (bool, the N flag), halted (bool).
    """

    def __init__(self, program, memory=None, mem_size=64):
        """Copy the program. Use a copy of `memory` if given, else `mem_size` zeros.
        All registers start at 0, pc at 0, both flags False, halted False."""
        raise NotImplementedError

    def step(self):
        """Run one instruction: fetch program[pc], advance pc by one, decode the
        opcode, execute it. Raise CPUError if pc is outside the program, the
        opcode is unknown, or a memory address is outside memory."""
        raise NotImplementedError

    def run(self, max_steps=100_000):
        """Step until HALT. Return how many instructions ran, HALT included.
        Raise CPUError if max_steps is reached first."""
        raise NotImplementedError


def sum_list_program(base, n):
    """Return a program that adds up memory[base], memory[base+1], ... for n
    numbers, leaves the total in register 0, and halts. n may be 0 (total 0).
    It may use registers 0 to 7 and must not change memory.

    cpu = CPU(sum_list_program(0, 3), memory=[5, 6, 7]); cpu.run(); cpu.regs[0] -> 18
    """
    raise NotImplementedError


def factorial_program(n):
    """Return a program that computes n! (n is at least 1), leaves it in
    register 0, and halts. Results wrap to 32 bits like every other number.

    cpu = CPU(factorial_program(5)); cpu.run(); cpu.regs[0] -> 120
    """
    raise NotImplementedError


if __name__ == "__main__":
    add_program = [
        ("LOADI", 0, 2),
        ("LOADI", 1, 3),
        ("ADD", 0, 1),
        ("HALT",),
    ]
    cpu = CPU(add_program)
    steps = cpu.run()
    print(f"2 + 3 = {cpu.regs[0]} after {steps} instructions, pc = {cpu.pc}")
    cpu = CPU(sum_list_program(0, 4), memory=[10, 20, 30, 40])
    cpu.run()
    print("sum of [10, 20, 30, 40]:", cpu.regs[0])
    cpu = CPU(factorial_program(6))
    cpu.run()
    print("6! =", cpu.regs[0])
