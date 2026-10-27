"""LLVM IR by hand.

Each *_ir function returns the text of an LLVM IR module. The checks verify the
text with LLVM's verifier, compile it, and call it from Python through ctypes.
LLVM IR is typed: `i32` is a 32-bit integer, `i64` a 64-bit one, `i1` a single
bit. Both operands of an instruction must have the same type.
"""

import re

import cputools


def add3_ir() -> str:
    """IR for `i32 @add3(i32 %a, i32 %b, i32 %c)`, returning a + b + c.

        define i32 @add3(i32 %a, i32 %b, i32 %c) {
        entry:
          ...
          ret i32 %sum
        }
    """
    return """\
define i32 @add3(i32 %a, i32 %b, i32 %c) {
entry:
  %ab = add i32 %a, %b
  %sum = add i32 %ab, %c
  ret i32 %sum
}
"""


def mul_wide_ir() -> str:
    """IR for `i64 @mul_wide(i32 %a, i32 %b)`, returning the full 64-bit product.

    Widen both arguments with `sext` before multiplying, so no bits are lost:
    mul_wide(65536, 65536) is 4294967296.
    """
    return """\
define i64 @mul_wide(i32 %a, i32 %b) {
entry:
  %wa = sext i32 %a to i64
  %wb = sext i32 %b to i64
  %p = mul i64 %wa, %wb
  ret i64 %p
}
"""


def is_negative_ir() -> str:
    """IR for `i32 @is_negative(i32 %x)`: 1 if x < 0 (signed), else 0.

    Use `icmp slt` for the comparison and `zext` to turn the i1 into an i32.
    """
    return """\
define i32 @is_negative(i32 %x) {
entry:
  %neg = icmp slt i32 %x, 0
  %r = zext i1 %neg to i32
  ret i32 %r
}
"""


def low_byte_ir() -> str:
    """IR for `i32 @low_byte(i32 %x)`: the lowest 8 bits of x, read as a signed byte.

    low_byte(0x1FF) is -1, and low_byte(0x17F) is 127. Use `trunc` and `sext`.
    """
    return """\
define i32 @low_byte(i32 %x) {
entry:
  %b = trunc i32 %x to i8
  %r = sext i8 %b to i32
  ret i32 %r
}
"""


def avg_ir() -> str:
    """IR for `i32 @avg(i32 %a, i32 %b)`: (a + b) / 2, truncating toward zero,
    without overflowing when a + b does not fit in 32 bits.

    avg(2147483647, 2147483647) is 2147483647. Compute in i64 and `trunc` back.
    """
    return """\
define i32 @avg(i32 %a, i32 %b) {
entry:
  %wa = sext i32 %a to i64
  %wb = sext i32 %b to i64
  %sum = add i64 %wa, %wb
  %half = sdiv i64 %sum, 2
  %r = trunc i64 %half to i32
  ret i32 %r
}
"""


def main_ir() -> str:
    """A module whose `i32 @main()` returns (7 * 6 - 2) / 2, which is 20, as the
    process exit code. Use `mul`, `sub`, and `sdiv` instructions on constants
    held in operands, for example `mul i32 7, 6`.
    """
    return """\
define i32 @main() {
entry:
  %p = mul i32 7, 6
  %d = sub i32 %p, 2
  %r = sdiv i32 %d, 2
  ret i32 %r
}
"""


def ir_opcodes(ir: str) -> list:
    """The opcode of every instruction inside function bodies, in order.

    Only lines between `define ... {` and `}` count. Labels and comments do not.
    For `%x = add i32 %a, %b` the opcode is `add`; for `ret i32 %x` it is `ret`.

    >>> ir_opcodes("define i32 @f(i32 %a) {\\nentry:\\n  %b = add i32 %a, 1 ; bump\\n  ret i32 %b\\n}\\n")
    ['add', 'ret']
    """
    ops = []
    inside = False
    for raw in ir.splitlines():
        line = raw.split(";", 1)[0].strip()  # drop the comment
        if line.startswith("define"):
            inside = True
        elif line == "}":
            inside = False
        elif inside and line and not line.endswith(":"):  # not blank, not a label
            m = re.match(r"%[^\s=]+\s*=\s*(\w+)", line)
            ops.append(m.group(1) if m else line.split()[0])
    return ops


if __name__ == "__main__":
    ir = add3_ir()
    cputools.verify_ir(ir)
    lib = cputools.ir_to_lib(ir)
    print("opcodes:", ir_opcodes(ir))
    print("add3(1, 2, 3) =", lib.add3(1, 2, 3), "(want 6)")
    result = cputools.run_ir(main_ir())
    print("main exits with", result.returncode, "(want 20)")
