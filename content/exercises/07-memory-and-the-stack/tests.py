"""Checks for the memory, stack, and endianness exercise."""

import random

from cpucheck import check, equal, fail, has


def _raises(exc, fn, *args, **kwargs):
    try:
        got = fn(*args, **kwargs)
    except exc:
        return
    fail(f"expected {exc.__name__}, but {fn.__name__}{args!r} returned {got!r}")


@check("to_le_bytes puts the least significant byte first")
def test_to_le(sub):
    to_le_bytes = has(sub, "to_le_bytes")
    equal(to_le_bytes(0x11223344, 4), b"\x44\x33\x22\x11", label="to_le_bytes(0x11223344, 4)")
    equal(to_le_bytes(0x0102, 2), b"\x02\x01", label="to_le_bytes(0x0102, 2)")
    equal(to_le_bytes(1, 8), b"\x01" + b"\x00" * 7, label="to_le_bytes(1, 8)")
    # -1 wrapped to 2 bytes is 0xFFFF; -2 wrapped to 1 byte is 0xFE (256 - 2).
    equal(to_le_bytes(-1, 2), b"\xff\xff", label="to_le_bytes(-1, 2)")
    equal(to_le_bytes(-2, 1), b"\xfe", label="to_le_bytes(-2, 1)")
    # A value too big is cut to its low bytes: 0x1_2345 in 2 bytes is 0x2345.
    equal(to_le_bytes(0x12345, 2), b"\x45\x23", label="to_le_bytes(0x12345, 2)")


@check("from_le_bytes reads unsigned and signed values")
def test_from_le(sub):
    from_le_bytes = has(sub, "from_le_bytes")
    equal(from_le_bytes(b"\x44\x33\x22\x11"), 0x11223344, label="unsigned 4 bytes")
    equal(from_le_bytes(b"\xff\xff"), 65535, label="ff ff unsigned")
    equal(from_le_bytes(b"\xff\xff", signed=True), -1, label="ff ff signed")
    equal(from_le_bytes(b"\x80", signed=True), -128, label="80 signed")
    equal(from_le_bytes(b"\x7f", signed=True), 127, label="7f signed")
    equal(from_le_bytes(bytearray(b"\x00\x00\x00\x80"), signed=True), -(2 ** 31), label="INT_MIN")
    rng = random.Random(0)
    to_le_bytes = has(sub, "to_le_bytes")
    for size in (1, 2, 4, 8):
        for _ in range(20):
            v = rng.randrange(1 << (8 * size))
            equal(from_le_bytes(to_le_bytes(v, size)), v, label=f"round trip {v:#x} in {size} bytes")


@check("Memory.store lays bytes out little-endian; load reads them back")
def test_memory_basic(sub):
    Memory = has(sub, "Memory")
    mem = Memory(32)
    mem.store(4, 0x11223344, 4)
    equal(bytes(mem.data[4:8]), b"\x44\x33\x22\x11", label="bytes in memory")
    equal(mem.load(4, 4), 0x11223344, label="load 4")
    equal(mem.load(4, 1), 0x44, label="load 1 at the low address")
    equal(mem.load(7, 1), 0x11, label="load 1 at the high address")
    equal(mem.load(4, 2), 0x3344, label="load 2 at 4")
    equal(mem.load(6, 2), 0x1122, label="load 2 at 6")
    mem.store(16, 0x0102030405060708, 8)
    equal(mem.load(16, 8), 0x0102030405060708, label="load 8")
    equal(mem.load(16, 4), 0x05060708, label="low half of the 8-byte value")
    equal(mem.load(20, 4), 0x01020304, label="high half of the 8-byte value")
    equal(mem.load(24, 8), 0, label="untouched memory is zero")


@check("Memory handles negative values, signed loads, and overwrites")
def test_memory_signed(sub):
    Memory = has(sub, "Memory")
    mem = Memory(16)
    mem.store(0, -1, 4)
    equal(bytes(mem.data[0:4]), b"\xff\xff\xff\xff", label="-1 stored in 4 bytes")
    equal(mem.load(0, 4), 0xFFFFFFFF, label="unsigned load of -1")
    equal(mem.load(0, 4, signed=True), -1, label="signed load of -1")
    mem.store(8, 200, 1)
    equal(mem.load(8, 1, signed=True), -56, label="200 as a signed byte (200 - 256)")
    # Storing 1 byte must not disturb its neighbours.
    mem.store(4, 0x7F, 1)
    equal(bytes(mem.data[3:6]), b"\xff\x7f\x00", label="neighbours untouched")
    # Storing a too-wide value keeps only the low bytes.
    mem.store(12, 0x1_2345_6789, 4)
    equal(mem.load(12, 4), 0x23456789, label="value wrapped to 4 bytes")


@check("Memory faults outside its range and rejects odd sizes")
def test_memory_faults(sub):
    Memory, MemoryFault = has(sub, "Memory"), has(sub, "MemoryFault")
    mem = Memory(16)
    _raises(MemoryFault, mem.load, 16, 1)         # one past the end
    _raises(MemoryFault, mem.load, 13, 4)         # last byte at 16: out
    _raises(MemoryFault, mem.store, 100, 1, 1)
    _raises(MemoryFault, mem.load, -1, 1)         # negative address
    _raises(MemoryFault, mem.store, -4, 1, 4)
    mem.store(12, 5, 4)                           # the last 4 bytes are fine
    equal(mem.load(12, 4), 5, label="load of the last four bytes")
    equal(mem.load(15, 1), 0, label="load of the last byte")
    _raises(ValueError, mem.load, 0, 3)           # 3 is not a legal size
    equal(bytes(mem.data[12:16]), b"\x05\x00\x00\x00", label="a failed store changes nothing")
    before = bytes(mem.data)
    _raises(MemoryFault, mem.store, 14, 0xFFFFFFFF, 4)
    equal(bytes(mem.data), before, label="memory after a faulting store")


@check("strict_align raises MemoryFault for misaligned accesses; is_aligned agrees")
def test_alignment(sub):
    Memory, MemoryFault, is_aligned = has(sub, "Memory"), has(sub, "MemoryFault"), has(sub, "is_aligned")
    equal(is_aligned(8, 4), True, label="is_aligned(8, 4)")
    equal(is_aligned(6, 4), False, label="is_aligned(6, 4)")
    equal(is_aligned(6, 2), True, label="is_aligned(6, 2)")
    equal(is_aligned(5, 1), True, label="is_aligned(5, 1)")
    equal(is_aligned(24, 8), True, label="is_aligned(24, 8)")
    equal(is_aligned(20, 8), False, label="is_aligned(20, 8)")
    strict = Memory(32, strict_align=True)
    strict.store(4, 7, 4)
    equal(strict.load(4, 4), 7, label="aligned access works")
    _raises(MemoryFault, strict.load, 2, 4)
    _raises(MemoryFault, strict.store, 3, 1, 2)
    _raises(MemoryFault, strict.load, 4, 8)       # 4 is not a multiple of 8
    strict.store(5, 9, 1)                         # a single byte is always aligned
    # A lenient memory (the default) lets the same accesses through.
    lenient = Memory(32)
    lenient.store(2, 0xAABBCCDD, 4)
    equal(lenient.load(2, 4), 0xAABBCCDD, label="misaligned access on a lenient memory")


@check("Stack grows down: push, pop, call, and ret are last in, first out")
def test_stack(sub):
    Memory, Stack, StackError = has(sub, "Memory"), has(sub, "Stack"), has(sub, "StackError")
    mem = Memory(64)
    st = Stack(mem, 64)
    equal(st.sp, 64, label="empty stack: sp == top")
    st.push(11)
    equal(st.sp, 56, label="sp after one push")
    equal(mem.load(56, 8), 11, label="pushed value lives at the new sp")
    st.push(22)
    st.push(33)
    equal(st.sp, 40, label="sp after three pushes")
    equal(mem.load(40, 8), 33, label="top of stack")
    equal(st.pop(), 33, label="first pop")
    equal(st.sp, 48, label="sp after a pop")
    equal(st.pop(), 22, label="second pop")
    equal(st.pop(), 11, label="third pop")
    equal(st.sp, 64, label="sp back at the top")
    _raises(StackError, st.pop)
    st.push(-5)
    equal(st.pop(), 0xFFFFFFFFFFFFFFFB, label="-5 stored in 8 bytes comes back unsigned")
    # call and ret are a push and a pop of the return address.
    Memory, Stack = has(sub, "Memory"), has(sub, "Stack")
    mem = Memory(128)
    st = Stack(mem, 128)
    st.call(0x1004)
    st.call(0x2008)
    equal(st.sp, 112, label="two calls use 16 bytes")
    equal(mem.load(112, 8), 0x2008, label="most recent return address is at sp")
    equal(st.ret(), 0x2008, label="first ret")
    equal(st.ret(), 0x1004, label="second ret")
    equal(st.sp, 128, label="sp restored")


@check("factorial_with_stack computes n! and leaves the stack as it found it")
def test_factorial(sub):
    Memory, Stack = has(sub, "Memory"), has(sub, "Stack")
    factorial_with_stack = has(sub, "factorial_with_stack")
    # 4 frames of 16 bytes (return address + k): depths 16, 32, 48, 64.
    mem = Memory(256)
    st = Stack(mem, 256)
    result, depths, returns = factorial_with_stack(st, 4)
    equal(result, 24, label="4!")
    equal(depths, [16, 32, 48, 64], label="stack depth after each call")
    equal(returns, [0x500, 0x500, 0x500, 0x400], label="return addresses, innermost first")
    equal(st.sp, 256, label="sp after the call returns")
    for n, want in [(1, 1), (2, 2), (5, 120), (10, 3628800)]:
        mem = Memory(1024)
        st = Stack(mem, 1024)
        result, depths, returns = factorial_with_stack(st, n)
        equal(result, want, label=f"{n}!")
        equal(depths[-1], 16 * n, label=f"deepest stack for n={n}")
        equal(len(returns), n, label=f"returns for n={n}")
        equal(st.sp, 1024, label=f"sp restored for n={n}")


@check("a too-small stack runs out of memory and raises MemoryFault")
def test_stack_overflow(sub):
    Memory, Stack, MemoryFault = has(sub, "Memory"), has(sub, "Stack"), has(sub, "MemoryFault")
    factorial_with_stack = has(sub, "factorial_with_stack")
    st = Stack(Memory(64), 64)    # room for 8 slots = 4 frames
    result, _, _ = factorial_with_stack(st, 4)
    equal(result, 24, label="4! just fits in 64 bytes")
    st = Stack(Memory(64), 64)
    _raises(MemoryFault, factorial_with_stack, st, 5)


@check("x86_immediate_bytes shows real x86-64 storing an immediate little-endian")
def test_x86(sub):
    x86_immediate_bytes, to_le_bytes = has(sub, "x86_immediate_bytes"), has(sub, "to_le_bytes")
    # mov eax, 0x11223344 assembles to b8 44 33 22 11: opcode, then the immediate reversed.
    equal(x86_immediate_bytes(0x11223344), b"\x44\x33\x22\x11", label="mov eax, 0x11223344")
    equal(x86_immediate_bytes(1), b"\x01\x00\x00\x00", label="mov eax, 1")
    for value in (0, 0x7FFFFFFF, 0xDEADBEEF, 0x01020304):
        equal(x86_immediate_bytes(value), to_le_bytes(value, 4), label=f"mov eax, {value:#x}")
