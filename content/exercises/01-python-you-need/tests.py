"""Checks for the Python warm-up exercise."""

import cputools
from cpucheck import check, equal, fail, has


@check("double returns an int times two")
def test_double(sub):
    double = has(sub, "double")
    for n, want in [(21, 42), (0, 0), (-4, -8), (1, 2)]:
        equal(double(n), want, label=f"double({n})")


@check("greet builds the greeting with an f-string")
def test_greet(sub):
    greet = has(sub, "greet")
    equal(greet("Ada"), "Hello, Ada!", label="greet('Ada')")
    equal(greet("CPU"), "Hello, CPU!", label="greet('CPU')")


@check("sum_even adds up only the even numbers")
def test_sum_even(sub):
    sum_even = has(sub, "sum_even")
    equal(sum_even([1, 2, 3, 4]), 6, label="sum_even([1, 2, 3, 4])")  # 2 + 4
    equal(sum_even([]), 0, label="sum_even([])")
    equal(sum_even([7, 9]), 0, label="sum_even([7, 9])")
    equal(sum_even([-2, -3, 10]), 8, label="sum_even([-2, -3, 10])")  # -2 + 10


@check("word_counts counts words and ignores case")
def test_word_counts(sub):
    word_counts = has(sub, "word_counts")
    equal(word_counts("the cat The dog"), {"the": 2, "cat": 1, "dog": 1}, label="two 'the'")
    equal(word_counts(""), {}, label="empty text")
    equal(word_counts("a a a"), {"a": 3}, label="three 'a'")


@check("hex_to_int reads hex strings, with or without 0x")
def test_hex_to_int(sub):
    hex_to_int = has(sub, "hex_to_int")
    equal(hex_to_int("ff"), 255, label="hex_to_int('ff')")
    equal(hex_to_int("0x10"), 16, label="hex_to_int('0x10')")
    equal(hex_to_int("DEADBEEF"), 3735928559, label="hex_to_int('DEADBEEF')")


@check("int_to_bin pads binary with zeros on the left")
def test_int_to_bin(sub):
    int_to_bin = has(sub, "int_to_bin")
    equal(int_to_bin(5, 8), "0b00000101", label="int_to_bin(5, 8)")
    equal(int_to_bin(0, 4), "0b0000", label="int_to_bin(0, 4)")
    equal(int_to_bin(255, 8), "0b11111111", label="int_to_bin(255, 8)")
    equal(int_to_bin(13, 4), "0b1101", label="int_to_bin(13, 4)")  # 8 + 4 + 1


@check("text_to_bytes and bytes_to_hex work with bytes")
def test_bytes(sub):
    text_to_bytes = has(sub, "text_to_bytes")
    bytes_to_hex = has(sub, "bytes_to_hex")
    equal(text_to_bytes("Hi"), [72, 105], label="text_to_bytes('Hi')")  # ASCII H=72, i=105
    equal(text_to_bytes(""), [], label="text_to_bytes('')")
    equal(bytes_to_hex(bytes([0xDE, 0xAD, 0xBE, 0xEF])), "de ad be ef", label="deadbeef")
    equal(bytes_to_hex(b"Hi"), "48 69", label="bytes_to_hex(b'Hi')")
    equal(bytes_to_hex(bytes([0, 7])), "00 07", label="leading zeros kept")
    equal(bytes_to_hex(b""), "", label="empty bytes")


@check("return_constant_asm returns text that the real assembler accepts")
def test_asm_text(sub):
    make = has(sub, "return_constant_asm")
    text = make("answer", 42)
    if not isinstance(text, str):
        fail(f"return_constant_asm should return a str, got {type(text).__name__}")
    if ".globl answer" not in text:
        fail("the text needs a `.globl answer` line so Python can find the function")
    try:
        lib = cputools.assemble(text)
    except cputools.ToolError as exc:
        fail(f"the assembler rejected your text:\n{exc}")
    equal(lib.answer(), 42, label="answer()")


@check("return_constant_asm works for other names and values")
def test_asm_other(sub):
    make = has(sub, "return_constant_asm")
    lib = cputools.assemble(make("seven", 7) + make("minus_one", -1))
    equal(lib.seven(), 7, label="seven()")
    equal(lib.minus_one(), -1, label="minus_one()")


@check("Counter starts at start, adds, and resets")
def test_counter(sub):
    Counter = has(sub, "Counter")
    c = Counter()
    equal(c.count, 0, label="new Counter().count")
    c.add()
    c.add(5)
    equal(c.count, 6, label="after add() and add(5)")
    c.reset()
    equal(c.count, 0, label="after reset()")
    d = Counter(10)
    d.add(2)
    equal(d.count, 12, label="Counter(10) then add(2)")
    d.reset()
    equal(d.count, 10, label="Counter(10) after reset()")
    equal(c.count, 0, label="the first counter is separate from the second")
