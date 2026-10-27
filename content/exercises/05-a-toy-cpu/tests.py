"""Checks for the toy CPU exercise."""

import math

from cpucheck import check, equal, fail, has


def expect_cpu_error(sub, action, what):
    CPUError = has(sub, "CPUError")
    try:
        action()
    except CPUError:
        return
    except NotImplementedError:
        raise
    except Exception as exc:  # noqa: BLE001
        fail(f"{what}: raised {type(exc).__name__}, expected CPUError")
    fail(f"{what}: expected CPUError, but nothing was raised")


def run(sub, program, memory=None, **kw):
    cpu = has(sub, "CPU")(program, memory, **kw)
    steps = cpu.run()
    return cpu, steps


def wrap32(x):
    return ((x + 2**31) % 2**32) - 2**31


@check("a new CPU starts clean, and LOADI plus HALT run and count instructions")
def test_basic(sub):
    CPU = has(sub, "CPU")
    cpu = CPU([("LOADI", 0, 7), ("LOADI", 3, -2), ("HALT",)])
    equal(list(cpu.regs), [0] * 8, label="registers before running")
    equal((cpu.pc, cpu.zero, cpu.negative, cpu.halted), (0, False, False, False), label="pc, flags, halted at start")
    equal(len(cpu.memory), 64, label="default memory size")
    steps = cpu.run()
    equal(steps, 3, label="instructions executed, HALT included")
    equal(cpu.regs[0], 7, label="R0 after LOADI 7")
    equal(cpu.regs[3], -2, label="R3 after LOADI -2")
    equal((cpu.pc, cpu.halted), (3, True), label="pc after HALT, and halted")


@check("step fetches one instruction and advances pc before executing it")
def test_step(sub):
    CPU = has(sub, "CPU")
    cpu = CPU([("LOADI", 1, 5), ("JMP", 0)])
    cpu.step()
    equal((cpu.pc, cpu.regs[1]), (1, 5), label="after one step of LOADI")
    cpu.step()
    equal(cpu.pc, 0, label="a JMP to 0 sets pc to 0")
    cpu = CPU([("HALT",)])
    cpu.step()
    equal(cpu.halted, True, label="halted after stepping a HALT")


@check("ADD, SUB, and MUL update the destination register and the Z and N flags")
def test_alu(sub):
    cpu, _ = run(sub, [("LOADI", 0, 6), ("LOADI", 1, 4), ("ADD", 0, 1), ("HALT",)])
    equal((cpu.regs[0], cpu.zero, cpu.negative), (10, False, False), label="6 + 4")
    cpu, _ = run(sub, [("LOADI", 0, 6), ("LOADI", 1, 6), ("SUB", 0, 1), ("HALT",)])
    equal((cpu.regs[0], cpu.zero, cpu.negative), (0, True, False), label="6 - 6 sets Z")
    cpu, _ = run(sub, [("LOADI", 0, 2), ("LOADI", 1, 5), ("SUB", 0, 1), ("HALT",)])
    equal((cpu.regs[0], cpu.zero, cpu.negative), (-3, False, True), label="2 - 5 sets N")
    cpu, _ = run(sub, [("LOADI", 0, 7), ("LOADI", 1, -6), ("MUL", 0, 1), ("HALT",)])
    equal((cpu.regs[0], cpu.zero, cpu.negative), (-42, False, True), label="7 * -6")
    # LOADI does not touch the flags: Z stays set from the SUB.
    cpu, _ = run(sub, [("LOADI", 0, 1), ("SUB", 0, 0), ("LOADI", 1, 9), ("HALT",)])
    equal((cpu.zero, cpu.regs[1]), (True, 9), label="LOADI leaves the flags alone")
    cpu, _ = run(sub, [("LOADI", 0, 3), ("ADD", 0, 0), ("ADD", 0, 0), ("HALT",)])
    equal(cpu.regs[0], 12, label="a register can be both operands")


@check("results wrap around like 32-bit signed numbers")
def test_wrap(sub):
    cpu, _ = run(sub, [("LOADI", 0, 2**31 - 1), ("LOADI", 1, 1), ("ADD", 0, 1), ("HALT",)])
    equal((cpu.regs[0], cpu.negative), (-(2**31), True), label="2147483647 + 1")
    cpu, _ = run(sub, [("LOADI", 0, -(2**31)), ("LOADI", 1, 1), ("SUB", 0, 1), ("HALT",)])
    equal(cpu.regs[0], 2**31 - 1, label="-2147483648 - 1")
    cpu, _ = run(sub, [("LOADI", 0, 65536), ("LOADI", 1, 65536), ("MUL", 0, 1), ("HALT",)])
    equal((cpu.regs[0], cpu.zero), (0, True), label="65536 * 65536 wraps to 0")


@check("LOAD and STORE use a register as the address")
def test_memory(sub):
    program = [
        ("LOADI", 1, 2),       # R1 = address 2
        ("LOAD", 0, 1),        # R0 = memory[2]
        ("LOADI", 2, 5),       # R2 = address 5
        ("STORE", 0, 2),       # memory[5] = R0
        ("LOADI", 3, 99),
        ("LOADI", 4, 0),       # R4 = address 0
        ("STORE", 3, 4),       # memory[0] = 99
        ("HALT",),
    ]
    cpu, _ = run(sub, program, memory=[1, 2, 33, 4, 5, 6, 7, 8])
    equal(cpu.regs[0], 33, label="R0 loaded from memory[2]")
    equal(cpu.memory, [99, 2, 33, 4, 5, 33, 7, 8], label="memory after two STOREs")
    original = [1, 2, 3]
    run(sub, [("LOADI", 0, 9), ("LOADI", 1, 0), ("STORE", 0, 1), ("HALT",)], memory=original)
    equal(original, [1, 2, 3], label="the memory list you pass in is copied, not changed")


@check("JMP always jumps and JZ jumps only when the zero flag is set")
def test_jumps(sub):
    program = [
        ("LOADI", 0, 1),
        ("JMP", 3),
        ("LOADI", 0, 111),     # skipped
        ("LOADI", 1, 5),
        ("LOADI", 2, 5),
        ("SUB", 1, 2),         # R1 = 0, Z set
        ("JZ", 8),             # taken
        ("LOADI", 0, 222),     # skipped
        ("LOADI", 3, 1),
        ("SUB", 3, 0),         # R3 = 0, Z set
        ("LOADI", 4, 7),
        ("ADD", 4, 0),         # R4 = 8, Z clear
        ("JZ", 15),            # not taken
        ("LOADI", 5, 42),      # runs
        ("HALT",),
        ("HALT",),
    ]
    cpu, steps = run(sub, program)
    equal((cpu.regs[0], cpu.regs[5]), (1, 42), label="R0 untouched by skipped code, R5 set by fall-through")
    equal(steps, 13, label="instructions executed")


@check("the CPU raises CPUError for a bad pc, a bad opcode, a bad address, and a runaway loop")
def test_errors(sub):
    CPU = has(sub, "CPU")
    expect_cpu_error(sub, lambda: CPU([("LOADI", 0, 1)]).run(), "running off the end of the program")
    expect_cpu_error(sub, lambda: CPU([("JMP", 5)]).run(), "jumping outside the program")
    expect_cpu_error(sub, lambda: CPU([("JMP", -1)]).run(), "jumping to a negative target")
    expect_cpu_error(sub, lambda: CPU([("NOP",), ("HALT",)]).run(), "unknown opcode NOP")
    expect_cpu_error(sub, lambda: CPU([("LOADI", 1, 64), ("LOAD", 0, 1), ("HALT",)]).run(), "LOAD at address 64")
    expect_cpu_error(sub, lambda: CPU([("LOADI", 1, -1), ("STORE", 0, 1), ("HALT",)]).run(), "STORE at address -1")
    expect_cpu_error(sub, lambda: CPU([("JMP", 0)]).run(max_steps=50), "a loop that never halts")
    cpu = CPU([("JMP", 0)])
    try:
        cpu.run(max_steps=50)
    except has(sub, "CPUError"):
        pass
    equal(cpu.pc, 0, label="pc after 50 JMPs to 0")


@check("sum_list_program adds up lists in memory, including empty and negative ones")
def test_sum_program(sub):
    sum_list_program = has(sub, "sum_list_program")
    cases = [
        (0, [5, 6, 7]),
        (0, [10, 20, 30, 40]),
        (0, [42]),
        (0, []),
        (3, [1, 2, 3, 4, 5, 6]),
        (0, [-5, 5, -10, 20]),
        (0, list(range(1, 51))),
    ]
    for base, numbers in cases:
        memory = [100] * base + numbers + [100, 100]
        cpu, _ = run(sub, sum_list_program(base, len(numbers)), memory=list(memory))
        equal(cpu.regs[0], sum(numbers), label=f"sum of {numbers[:6]} at base {base}")
        equal(cpu.memory, memory, label="memory is left unchanged")


@check("factorial_program computes n! for n = 1 to 12, and wraps for 13")
def test_factorial_program(sub):
    factorial_program = has(sub, "factorial_program")
    for n in range(1, 14):
        cpu, steps = run(sub, factorial_program(n))
        equal(cpu.regs[0], wrap32(math.factorial(n)), label=f"{n}!")  # 13! = 6227020800 wraps to 1932053504
        if steps > 20 + 6 * n:
            fail(f"{n}! took {steps} instructions; a simple loop needs about {4 * n + 5}")
