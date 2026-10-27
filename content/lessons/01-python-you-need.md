---
title: The Python you need for this course
slug: 01-python-you-need
part: "Part 0 — Getting started"
summary: Learn the small slice of Python this course uses, from f-strings and dicts to hex, bytes, and a tiny class.
minutes: 40
gpu: false
objectives:
  - Write short functions over ints, strings, lists, and dicts.
  - Build text with f-strings and triple-quoted strings, the way later lessons build assembly.
  - Convert between ints and hex or binary text, and read a `bytes` value.
  - Define a small class with an `__init__` method and methods that change its state.
exercise: 01-python-you-need
---

# The Python you need for this course

This course explains what a computer does when it runs your program. You will not read about it. You will build small models of a CPU in Python, and later you will hand real assembly and real C to a real compiler and watch what comes back.

That means Python is your workbench. You need only a small slice of it, and this lesson teaches that slice. It is gentle on purpose. Every idea comes with a tiny example, and the exercise has ten short functions, most of them one to four lines long.

If you already write Python, skim the headings, then do the exercise for the parts that are less familiar. Text that holds assembly, `int(s, 16)`, `bytes`, and a small class matter most.

## What you already know

- A browser, which is all you need. The course runs your code for you, so there is nothing to install.
- Curiosity about what happens under a program. That is the real prerequisite.

You do not need to know any programming language. If a word looks strange, this lesson defines it the first time it appears.

## Run a line of Python

*Python* is a programming language. You write instructions in a text file, and a program called the *interpreter* reads them and does what they say, one at a time.

Each exercise in this course is one Python file. When you press **Run**, the interpreter executes the part of the file below `if __name__ == "__main__":`. The checks are a second file that tries your functions and reports which ones work.

Here is the smallest useful program. It uses `print`, which shows a value on the screen.

```python
print("hello")
print(2 + 3)
```

The first line shows `hello`. The second shows `5`. A line that starts with `#` is a *comment*: Python ignores it, and it is there for people.

## Numbers, names, and functions

A *value* is a piece of data, such as `42` or `"hello"`. A *variable* is a name that points at a value. You create one with `=`.

```python
n = 21
total = n * 2     # total is 42
```

The usual arithmetic works: `+`, `-`, `*`. Two forms of division matter here. The operator `//` divides and drops the fraction, and `%` gives the remainder.

| Expression | Result | Meaning |
|---|---|---|
| `17 // 5` | `3` | how many whole fives fit in 17 |
| `17 % 5` | `2` | what is left over |
| `2 ** 10` | `1024` | 2 to the power 10 |
| `-7 % 4` | `1` | the remainder is never negative for a positive divisor |

The last row matters later. In lesson 03 you use `%` to wrap a number into a fixed range.

A *function* is a named recipe. It takes inputs, called *parameters*, and hands back a result with `return`. You define one with `def`. The lines inside are indented by four spaces. That indentation is how Python knows where the function ends.

```python
def double(n):
    return n * 2

print(double(21))   # 42
```

Every exercise asks you to fill in functions like this one. A function that is not filled in yet raises `NotImplementedError`, which is how you know what is left to do.

> [!KEY]
> A function takes values in, returns a value out, and has no other effect. Most of this course is writing small functions and checking them against examples worked by hand.

## Text: strings and f-strings

A *string* is a value that holds text. Write it between quotes: `"Ada"` or `'Ada'`. You can join strings with `+`, take a piece with a slice, and ask for its length.

```python
word = "processor"
print(word[0])      # p       the first character; counting starts at 0
print(word[0:4])    # proc    characters 0 up to, but not including, 4
print(len(word))    # 9
print(word.upper()) # PROCESSOR
```

Building text out of pieces with `+` gets awkward. An *f-string* is easier. Put the letter `f` before the opening quote, and write a value inside curly braces. Python puts the value into the text.

```python
name = "Ada"
print(f"Hello, {name}!")          # Hello, Ada!
print(f"{3} + {4} = {3 + 4}")      # 3 + 4 = 7
```

Anything can go between the braces, including arithmetic. After a colon you can say how to format the value. You will use this a lot, so here is the table:

| Format | Example | Result |
|---|---|---|
| `{n:x}` | `f"{255:x}"` | `ff` (lowercase hex) |
| `{n:02x}` | `f"{10:02x}"` | `0a` (hex, padded with zeros to two digits) |
| `{n:b}` | `f"{5:b}"` | `101` (binary) |
| `{n:08b}` | `f"{5:08b}"` | `00000101` (binary, eight digits) |

### Triple-quoted strings

A *triple-quoted string* starts and ends with three quotes, and it can span many lines. Line breaks and indentation stay as you wrote them. This is the tool for text that has a shape, and from Part 2 on, your exercises return assembly, C, and LLVM IR as exactly this kind of text.

Put an `f` in front and the braces still work. Here is a function that returns a line of assembly text for a given number:

```python
def load_asm(value):
    return f"""
    mov eax, {value}
    ret
"""

print(load_asm(42))
```

The result is the text `mov eax, 42` and `ret` on two lines. You have not met `mov` or `eax` yet, and that is fine. Python does not care what the text means. It builds a string, and later a real assembler reads it.

> [!WARNING]
> Inside an f-string, curly braces mean "put a value here". Assembly does not use braces, but C does. When a later lesson builds C text with an f-string, write each literal brace twice: `{{` and `}}`.

## Lists, loops, and dicts

A *list* holds values in order. Write it between square brackets. You find a value by its position, called its *index*, starting from 0.

```python
sizes = [8, 16, 32, 64]
print(sizes[0])      # 8
print(sizes[-1])     # 64, a negative index counts from the end
sizes.append(128)    # the list grows to five items
print(len(sizes))    # 5
```

A *loop* repeats work. A `for` loop visits each item in turn. An `if` runs a block only when a condition is true.

```python
total = 0
for size in sizes:
    if size > 16:
        total += size    # same as: total = total + size
print(total)             # 32 + 64 + 128 = 224
```

Two helpers show up everywhere. `range(4)` produces 0, 1, 2, 3, and `enumerate` gives you each item with its index.

```python
for i in range(3):
    print(i)                       # 0, then 1, then 2

for i, size in enumerate(sizes):
    print(i, size)                 # 0 8, then 1 16, and so on
```

A *dict*, short for dictionary, maps *keys* to *values*. You look a value up by its key, and a key that is missing needs `get`, which lets you supply a default.

```python
counts = {}
for word in ["cat", "dog", "cat"]:
    counts[word] = counts.get(word, 0) + 1
print(counts)        # {'cat': 2, 'dog': 1}
```

This "count how many times each thing appears" pattern is how you will tally cache hits in Part 1 and instruction kinds later.

## Numbers in other bases: hex and binary

Computers store numbers as rows of 0s and 1s. You meet the details in lesson 02. In this lesson you need only Python's tools for writing the same number in several ways, because a CPU manual shows binary and hexadecimal everywhere.

*Hexadecimal*, or hex, writes numbers in base 16, using the digits `0` to `9` and `a` to `f`. A prefix says which base a number is written in: `0x` for hex and `0b` for binary.

```python
print(0xFF)          # 255
print(0b101)         # 5
print(hex(255))      # '0xff'      an int becomes hex text
print(bin(5))        # '0b101'     an int becomes binary text
print(int("ff", 16)) # 255         hex text becomes an int
print(int("101", 2)) # 5           binary text becomes an int
```

Notice the direction. `hex` and `bin` go from a number to text. `int(text, base)` goes from text back to a number. `int("0x10", 16)` works too, because Python accepts the `0x` prefix when the base is 16.

To drop the prefix, slice it off: `bin(5)[2:]` is `'101'`. To pad with zeros on the left, use the string method `zfill`: `"101".zfill(8)` is `'00000101'`.

## Bytes

A *byte* is a number from 0 to 255. It is the unit that memory is made of. You will meet it properly in lesson 02, and here you only need the Python type.

A `bytes` value is a row of bytes that cannot be changed. Write one with a `b` before the quotes, or build it from a list of numbers.

```python
data = b"Hi"                  # two bytes
print(data[0], data[1])       # 72 105, the numbers behind 'H' and 'i'
print(list(data))             # [72, 105]
print(bytes([222, 173]))      # b'\xde\xad'
print(data.hex(" "))          # 48 69   each byte as two hex digits
```

Looping over `bytes` gives you ints. Text and bytes convert with `encode` and `decode`: `"Hi".encode("ascii")` gives `b"Hi"`, and `b"Hi".decode("ascii")` gives `"Hi"`.

> [!TIP]
> When Python shows `b'\xde\xad'`, the `\x` means "the next two hex digits are a byte". It is the same as the two bytes 222 and 173.

## A tiny class

A *class* is a blueprint for an object that holds some data and the functions that work on it. An *object*, or *instance*, is one thing built from the blueprint. The functions inside a class are *methods*. The first parameter of every method is `self`, which stands for the object the method was called on.

The special method `__init__` runs when you create an object. It sets up the object's *attributes*, the named values it holds.

```python
class Register:
    def __init__(self, name):
        self.name = name
        self.value = 0

    def write(self, value):
        self.value = value

eax = Register("eax")
eax.write(7)
print(eax.name, eax.value)     # eax 7
```

Two objects from the same class have separate attributes. If you make a second `Register`, writing to one leaves the other alone. From lesson 05 on, a CPU is a class like this: its attributes are registers and memory, and its methods run instructions.

## Try it on your own machine

You can run all of this on any Linux or macOS terminal that has Python 3.

1. Open an interactive session with `python3`. Type `255` and press Enter, then `hex(255)`, then `f"{255:08b}"`. The prompt shows each result as soon as you press Enter, so you can try ideas fast. Press Ctrl-D to leave.
2. Ask Python what a name holds: `python3 -c "print(int('deadbeef', 16))"`. Look for the number 3735928559.
3. See the bytes of a string: `python3 -c "print(list('CPU'.encode()))"`. Look for `[67, 80, 85]`, the ASCII codes of the letters.
4. Check which assembler text your machine would accept. This needs `clang`, which is not part of Python. Run `printf '.intel_syntax noprefix\n.globl f\nf:\n mov eax, 42\n ret\n' > f.s && clang -c f.s`. If you see no error, the file `f.o` holds machine code for a function that returns 42.

## Build it step by step

Open the exercise. The starter lists every function with an example in its docstring. Fill them in from the top. The checks run in the same order, so you see progress right away.

1. `double(n)` takes an int and returns it times two. Use `*`. If this one passes, your setup works.
2. `greet(name)` returns `"Hello, Ada!"` for `"Ada"`. Use an f-string. The most common mistake is to leave out the final `!` or the space after the comma.
3. `sum_even(numbers)` takes a list and returns the sum of the even numbers. Keep a `total`, loop over the list, and add a number only when `n % 2 == 0`. Start `total` at 0, so an empty list gives 0.
4. `word_counts(text)` returns a dict from word to count, ignoring case. Call `text.lower().split()` to get the words, then use the `counts.get(word, 0) + 1` pattern. Writing `counts[word] += 1` for a word you have not seen raises `KeyError`.
5. `hex_to_int(text)` reads hex text with `int(text, 16)`. It must accept `"ff"` and `"0x10"`.
6. `int_to_bin(n, width)` returns binary text with a `0b` prefix, padded with zeros. For `(5, 8)` the answer is `"0b00000101"`. People often pad the whole string, prefix included. Pad only the digits.
7. `text_to_bytes(text)` returns the ASCII codes of a string as a list of ints. Encode first, then convert to a list.
8. `bytes_to_hex(data)` writes each byte as two lowercase hex digits, separated by single spaces, with no space at the end. Use `f"{byte:02x}"` and `" ".join(...)`. An empty `bytes` gives the empty string.
9. `return_constant_asm(name, value)` returns x86-64 assembly text. It is the first time your Python builds code. Use a triple-quoted f-string with a `.globl` line, a label, `mov eax, <value>`, and `ret`. The check hands your text to a real assembler, loads the result, and calls it. A common mistake is a label without its colon.
10. `Counter` is a class with a `count` attribute. `Counter(start=0)` sets it, `add(amount=1)` increases it, and `reset()` sets it back to `start`. Remember to save `start` in `__init__`, or `reset` has nothing to go back to.

## Where this breaks

Python is a good workbench but a poor model of a machine. Three differences matter, and later lessons return to each.

- **Python ints never overflow.** A real CPU keeps numbers in a fixed number of bits, such as 8, 32, or 64. Add enough and the value wraps around. In Python, `2 ** 100` is a perfectly good int. Lesson 03 makes your Python behave like fixed-width hardware.
- **Python is slow compared with the machine.** The interpreter does a lot of work for each line. That is fine for models. It is the reason that from Part 3 on, performance claims come from real compiled C, timed through the toolchain.
- **Names and types hide the memory.** A Python variable points at an object somewhere, and you never see an address. In C and assembly you see and handle addresses directly, starting in lesson 07.

There is one more habit to keep. A bug in indentation or a missing colon is an error before your code even runs. Read the line number the error shows, then look at the line above it too.

## Further reading

- [The Python tutorial](https://docs.python.org/3/tutorial/) is the official, free, step-by-step guide. Sections 3 to 5 cover everything used here.
- [Formatted string literals](https://docs.python.org/3/reference/lexical_analysis.html#f-strings) is the reference for f-strings and the format codes such as `02x`.
- [Built-in types: bytes and ints](https://docs.python.org/3/library/stdtypes.html) lists every operation on ints, strings, lists, dicts, and `bytes`.
- [Classes in the Python tutorial](https://docs.python.org/3/tutorial/classes.html) goes deeper on `__init__`, `self`, and methods.
- [Compiler Explorer](https://godbolt.org) lets you type C and see the assembly it becomes. You use it from lesson 11 onward, and a quick look shows where the course is headed.

## The exercise

You write ten small pieces in one file: `double`, `greet`, `sum_even`, `word_counts`, `hex_to_int`, `int_to_bin`, `text_to_bytes`, `bytes_to_hex`, `return_constant_asm`, and the class `Counter`. Each piece is short, and each docstring in the starter has an example to compare with.

The checks call each function on hand-computed inputs, including empty inputs and zero. The check for `return_constant_asm` goes further: it assembles the text you return with the real x86-64 assembler, loads the result, and calls your function from Python. When it passes, the string you built is a working machine-code function.
