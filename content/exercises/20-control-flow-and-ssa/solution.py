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
    return """\
define i32 @imax(i32 %a, i32 %b) {
entry:
  %gt = icmp sgt i32 %a, %b
  br i1 %gt, label %then, label %else
then:
  br label %done
else:
  br label %done
done:
  %r = phi i32 [ %a, %then ], [ %b, %else ]
  ret i32 %r
}
"""


def abs_ir() -> str:
    """IR for `i32 @iabs(i32 %x)`, the absolute value, using `br` and `phi`.

    iabs(-5) is 5. For the most negative i32 the result wraps and stays negative,
    as in C: compute the negative with `sub i32 0, %x`.
    """
    return """\
define i32 @iabs(i32 %x) {
entry:
  %neg = icmp slt i32 %x, 0
  br i1 %neg, label %flip, label %keep
flip:
  %minus = sub i32 0, %x
  br label %done
keep:
  br label %done
done:
  %r = phi i32 [ %minus, %flip ], [ %x, %keep ]
  ret i32 %r
}
"""


def sum_to_ir() -> str:
    """IR for `i64 @sum_to(i64 %n)`: 1 + 2 + ... + n, and 0 when n <= 0.

    A loop block with two phis (the counter i and the running sum s), a body
    block, and an exit block. sum_to(4) is 10.
    """
    return """\
define i64 @sum_to(i64 %n) {
entry:
  br label %loop
loop:
  %i = phi i64 [ 1, %entry ], [ %i.next, %body ]
  %s = phi i64 [ 0, %entry ], [ %s.next, %body ]
  %done = icmp sgt i64 %i, %n
  br i1 %done, label %exit, label %body
body:
  %s.next = add i64 %s, %i
  %i.next = add i64 %i, 1
  br label %loop
exit:
  ret i64 %s
}
"""


def factorial_ir() -> str:
    """IR for `i64 @fact(i64 %n)`: n!, and 1 when n <= 1. fact(5) is 120."""
    return """\
define i64 @fact(i64 %n) {
entry:
  br label %loop
loop:
  %i = phi i64 [ 2, %entry ], [ %i.next, %body ]
  %acc = phi i64 [ 1, %entry ], [ %acc.next, %body ]
  %done = icmp sgt i64 %i, %n
  br i1 %done, label %exit, label %body
body:
  %acc.next = mul i64 %acc, %i
  %i.next = add i64 %i, 1
  br label %loop
exit:
  ret i64 %acc
}
"""


def gcd_ir() -> str:
    """IR for `i64 @gcd(i64 %a, i64 %b)`: the greatest common divisor of two
    non-negative numbers, by Euclid's algorithm. gcd(12, 18) is 6, gcd(7, 0) is 7,
    and gcd(0, 0) is 0. Use `srem` and a loop with phis for a and b.
    """
    return """\
define i64 @gcd(i64 %a, i64 %b) {
entry:
  br label %loop
loop:
  %x = phi i64 [ %a, %entry ], [ %y, %body ]
  %y = phi i64 [ %b, %entry ], [ %r, %body ]
  %zero = icmp eq i64 %y, 0
  br i1 %zero, label %exit, label %body
body:
  %r = srem i64 %x, %y
  br label %loop
exit:
  ret i64 %x
}
"""


def build_cfg(ir: str) -> dict:
    """Build the control-flow graph of the one function in `ir`.

    Return a dict from block label to `Block`, in the order the blocks appear.
    Every block in the text has a label. A block's successors are the labels
    named by its terminator (`br`, `switch`; `ret` and `unreachable` have none),
    without duplicates, in order of first appearance. Predecessors are filled
    from the successors, in the order the blocks appear.
    """
    cfg = {}
    current = None
    inside = False
    for raw in ir.splitlines():
        line = raw.split(";", 1)[0].strip()
        if line.startswith("define"):
            inside = True
        elif line == "}":
            inside = False
        elif not inside or not line:
            continue
        elif line.endswith(":"):  # a label starts a new block
            current = Block(line[:-1])
            cfg[current.label] = current
        elif line.split()[0] in ("br", "switch"):  # the terminator names the successors
            for target in re.findall(r"label %([\w.$-]+)", line):
                if target not in current.succs:
                    current.succs.append(target)
    for block in cfg.values():
        for target in block.succs:
            if block.label not in cfg[target].preds:
                cfg[target].preds.append(block.label)
    return cfg


def phi_problems(ir: str) -> list:
    """Check that every phi names exactly the predecessors of its block.

    Return a list of problem strings, empty when all phis are right. Each
    string names the block label and the phi, such as
    "block loop: phi %i has no incoming value for body".
    """
    cfg = build_cfg(ir)
    problems = []
    inside, current = False, None
    for raw in ir.splitlines():
        line = raw.split(";", 1)[0].strip()
        if line.startswith("define"):
            inside = True
        elif line == "}":
            inside = False
        elif inside and line.endswith(":"):
            current = line[:-1]
        elif inside:
            m = re.match(r"%([\w.$-]+)\s*=\s*phi\s+\S+\s+(.*)", line)
            if not m:
                continue
            name, rest = m.groups()
            incoming = set(re.findall(r"\[\s*[^,\]]+,\s*%([\w.$-]+)\s*\]", rest))
            preds = set(cfg[current].preds)
            for label in sorted(preds - incoming):
                problems.append(f"block {current}: phi %{name} has no incoming value for {label}")
            for label in sorted(incoming - preds):
                problems.append(f"block {current}: phi %{name} names {label}, which is not a predecessor")
    return problems


def back_edges(cfg: dict) -> list:
    """The back edges of a CFG as sorted `(from_label, to_label)` pairs.

    A back edge points at a block that is still being explored in a depth-first
    search from the first block, so it closes a loop.
    """
    found = set()
    visiting, done = set(), set()

    def visit(label):
        visiting.add(label)
        for target in cfg[label].succs:
            if target in visiting:
                found.add((label, target))  # still on the stack: this edge closes a loop
            elif target not in done:
                visit(target)
        visiting.discard(label)
        done.add(label)

    if cfg:
        visit(next(iter(cfg)))
    return sorted(found)


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
