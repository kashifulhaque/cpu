"""The Python you need: ints, strings, lists, dicts, hex, bytes, and a tiny class."""


def double(n):
    """Return n times two.

    double(21) -> 42
    """
    raise NotImplementedError


def greet(name):
    """Return the greeting "Hello, <name>!" using an f-string.

    greet("Ada") -> "Hello, Ada!"
    """
    raise NotImplementedError


def sum_even(numbers):
    """Return the sum of the even numbers in a list. An empty list gives 0.

    sum_even([1, 2, 3, 4]) -> 6
    """
    raise NotImplementedError


def word_counts(text):
    """Count words, ignoring case. Return a dict from word to count.

    word_counts("the cat The dog") -> {"the": 2, "cat": 1, "dog": 1}
    """
    raise NotImplementedError


def hex_to_int(text):
    """Read a hex string, with or without a leading 0x, as an int.

    hex_to_int("ff") -> 255; hex_to_int("0x10") -> 16
    """
    raise NotImplementedError


def int_to_bin(n, width):
    """Write a non-negative int in binary with a 0b prefix, padded with zeros
    on the left to `width` binary digits.

    int_to_bin(5, 8) -> "0b00000101"
    """
    raise NotImplementedError


def text_to_bytes(text):
    """Return the ASCII bytes of a string as a list of ints.

    text_to_bytes("Hi") -> [72, 105]
    """
    raise NotImplementedError


def bytes_to_hex(data):
    """Write a bytes value as two lowercase hex digits per byte, separated by spaces.

    bytes_to_hex(bytes([222, 173, 190, 239])) -> "de ad be ef"
    bytes_to_hex(b"") -> ""
    """
    raise NotImplementedError


def return_constant_asm(name, value):
    """Return x86-64 assembly text for a function `name` that returns `value`.

    The text must declare the symbol with `.globl`, define the label, move the
    value into eax, and return. For return_constant_asm("answer", 42):

        .globl answer
    answer:
        mov eax, 42
        ret
    """
    raise NotImplementedError


class Counter:
    """A counter that starts at `start` and counts up.

    c = Counter(); c.add(); c.add(5); c.count -> 6
    c.reset() sets count back to the starting value.
    """

    def __init__(self, start=0):
        raise NotImplementedError

    def add(self, amount=1):
        """Increase `count` by `amount` (default 1)."""
        raise NotImplementedError

    def reset(self):
        """Set `count` back to the value passed as `start`."""
        raise NotImplementedError


if __name__ == "__main__":
    print(greet("Ada"), "double(21) =", double(21))
    print("sum_even([1, 2, 3, 4]) =", sum_even([1, 2, 3, 4]))
    print("word_counts =", word_counts("the cat The dog"))
    print("0xff is", hex_to_int("0xff"), "and 5 in binary is", int_to_bin(5, 8))
    print("bytes of 'Hi':", text_to_bytes("Hi"), "->", bytes_to_hex(b"Hi"))
    print(return_constant_asm("answer", 42))
    c = Counter()
    c.add()
    c.add(5)
    print("counter:", c.count)
