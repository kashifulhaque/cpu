"""Control flow, basic blocks, and SSA in LLVM IR.

Part one: write IR functions that use `br` and `phi`. Part two: parse IR text in
Python into a control-flow graph and check it.

Every IR function the checks call uses i64 or i32 values and labelled blocks.
`Block` is given.
"""

import ctypes
import re
from dataclasses import dataclass, field

import cputools


@dataclass
class Block:
    label: str
    succs: list = field(default_factory=list)  # labels this block can jump to
    preds: list = field(default_factory=list)  # labels of blocks that can jump here


def max_ir() -> str:
    """IR for `i32 @imax(i32 %a, i32 %b)`, the larger of two signed ints.

    Use `icmp sgt`, a conditional `br`, two blocks, and a `phi` in a join block.
    """
    raise NotImplementedError


def abs_ir() -> str:
    """IR for `i32 @iabs(i32 %x)`, the absolute value, using `br` and `phi`.

    iabs(-5) is 5. For the most negative i32 the result wraps and stays negative,
    as in C: compute the negative with `sub i32 0, %x`.
    """
    raise NotImplementedError


def sum_to_ir() -> str:
    """IR for `i64 @sum_to(i64 %n)`: 1 + 2 + ... + n, and 0 when n <= 0.

    A loop block with two phis (the counter i and the running sum s), a body
    block, and an exit block. sum_to(4) is 10.
    """
    raise NotImplementedError


def factorial_ir() -> str:
    """IR for `i64 @fact(i64 %n)`: n!, and 1 when n <= 1. fact(5) is 120."""
    raise NotImplementedError


def gcd_ir() -> str:
    """IR for `i64 @gcd(i64 %a, i64 %b)`: the greatest common divisor of two
    non-negative numbers, by Euclid's algorithm. gcd(12, 18) is 6, gcd(7, 0) is 7,
    and gcd(0, 0) is 0. Use `srem` and a loop with phis for a and b.
    """
    raise NotImplementedError


def build_cfg(ir: str) -> dict:
    """Build the control-flow graph of the one function in `ir`.

    Return a dict from block label to `Block`, in the order the blocks appear.
    Every block in the text has a label. A block's successors are the labels
    named by its terminator (`br`, `switch`; `ret` and `unreachable` have none),
    without duplicates, in order of first appearance. Predecessors are filled
    from the successors, in the order the blocks appear.
    """
    raise NotImplementedError


def phi_problems(ir: str) -> list:
    """Check that every phi names exactly the predecessors of its block.

    Return a list of problem strings, empty when all phis are right. Each
    string names the block label and the phi, such as
    "block loop: phi %i has no incoming value for body".
    """
    raise NotImplementedError


def back_edges(cfg: dict) -> list:
    """The back edges of a CFG as sorted `(from_label, to_label)` pairs.

    A back edge points at a block that is still being explored in a depth-first
    search from the first block, so it closes a loop.
    """
    raise NotImplementedError


if __name__ == "__main__":
    ir = sum_to_ir()
    cputools.verify_ir(ir)
    cfg = build_cfg(ir)
    for block in cfg.values():
        print(f"{block.label:8} succs={block.succs} preds={block.preds}")
    print("back edges:", back_edges(cfg))
    print("phi problems:", phi_problems(ir))
    lib = cputools.ir_to_lib(ir)
    lib.sum_to.restype = ctypes.c_int64
    lib.sum_to.argtypes = [ctypes.c_int64]
    print("sum_to(4) =", lib.sum_to(4), "(want 10)")
