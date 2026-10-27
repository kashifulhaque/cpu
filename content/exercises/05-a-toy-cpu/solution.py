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


def _wrap(x):
    """Wrap an int to a signed 32-bit number."""
    return ((x + 2**31) % 2**32) - 2**31


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
        self.program = list(program)
        self.memory = list(memory) if memory is not None else [0] * mem_size
        self.regs = [0] * NUM_REGISTERS
        self.pc = 0
        self.zero = False
        self.negative = False
        self.halted = False

    def _address(self, reg):
        """The memory address held in a register, checked against memory."""
        addr = self.regs[reg]
        if not 0 <= addr < len(self.memory):
            raise CPUError(f"memory address {addr} is outside 0..{len(self.memory) - 1}")
        return addr

    def _set_flags(self, result):
        self.zero = result == 0
        self.negative = result < 0

    def step(self):
        """Run one instruction: fetch program[pc], advance pc by one, decode the
        opcode, execute it. Raise CPUError if pc is outside the program, the
        opcode is unknown, or a memory address is outside memory."""
        # Fetch: read the instruction the program counter points at.
        if not 0 <= self.pc < len(self.program):
            raise CPUError(f"pc {self.pc} is outside the program")
        instruction = self.program[self.pc]
        self.pc += 1  # point at the next instruction before executing this one

        # Decode: split the tuple into an opcode and its operands.
        opcode, *operands = instruction

        # Execute.
        if opcode == "LOADI":
            rd, imm = operands
            self.regs[rd] = _wrap(imm)
        elif opcode == "LOAD":
            rd, rb = operands
            self.regs[rd] = self.memory[self._address(rb)]
        elif opcode == "STORE":
            rs, rb = operands
            self.memory[self._address(rb)] = self.regs[rs]
        elif opcode in ("ADD", "SUB", "MUL"):
            rd, rs = operands
            a, b = self.regs[rd], self.regs[rs]
            raw = a + b if opcode == "ADD" else a - b if opcode == "SUB" else a * b
            self.regs[rd] = _wrap(raw)
            self._set_flags(self.regs[rd])
        elif opcode == "JMP":
            (target,) = operands
            self.pc = target
        elif opcode == "JZ":
            (target,) = operands
            if self.zero:
                self.pc = target
        elif opcode == "HALT":
            self.halted = True
        else:
            raise CPUError(f"unknown opcode {opcode!r}")

    def run(self, max_steps=100_000):
        """Step until HALT. Return how many instructions ran, HALT included.
        Raise CPUError if max_steps is reached first."""
        steps = 0
        while not self.halted:
            if steps >= max_steps:
                raise CPUError(f"no HALT after {max_steps} steps")
            self.step()
            steps += 1
        return steps


def sum_list_program(base, n):
    """Return a program that adds up memory[base], memory[base+1], ... for n
    numbers, leaves the total in register 0, and halts. n may be 0 (total 0).
    It may use registers 0 to 7 and must not change memory.

    cpu = CPU(sum_list_program(0, 3), memory=[5, 6, 7]); cpu.run(); cpu.regs[0] -> 18
    """
    return [
        ("LOADI", 0, 0),      # 0: R0 = total
        ("LOADI", 1, base),   # 1: R1 = pointer to the next number
        ("LOADI", 2, n),      # 2: R2 = numbers left
        ("LOADI", 3, 1),      # 3: R3 = 1
        ("LOADI", 4, 0),      # 4: R4 = 0
        ("ADD", 2, 4),        # 5: R2 + 0 sets the flags from R2, so n = 0 is caught
        ("JZ", 13),           # 6: nothing to add
        ("LOAD", 5, 1),       # 7: R5 = memory[R1]
        ("ADD", 0, 5),        # 8: total += R5
        ("ADD", 1, 3),        # 9: pointer += 1
        ("SUB", 2, 3),        # 10: left -= 1, and Z is set when it reaches 0
        ("JZ", 13),           # 11: done
        ("JMP", 7),           # 12: next number
        ("HALT",),            # 13
    ]


def factorial_program(n):
    """Return a program that computes n! (n is at least 1), leaves it in
    register 0, and halts. Results wrap to 32 bits like every other number.

    cpu = CPU(factorial_program(5)); cpu.run(); cpu.regs[0] -> 120
    """
    return [
        ("LOADI", 0, 1),      # 0: R0 = result so far
        ("LOADI", 1, n),      # 1: R1 = counter, counting down
        ("LOADI", 2, 1),      # 2: R2 = 1
        ("MUL", 0, 1),        # 3: result *= counter
        ("SUB", 1, 2),        # 4: counter -= 1, and Z is set at 0
        ("JZ", 7),            # 5: finished
        ("JMP", 3),           # 6: multiply again
        ("HALT",),            # 7
    ]


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
