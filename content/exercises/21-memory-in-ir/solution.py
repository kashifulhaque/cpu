"""Memory in LLVM IR: alloca, load, store, getelementptr, and mem2reg."""

import re

import cputools

_LABEL = re.compile(r"^[\w.$-]+:")
_ASSIGN = re.compile(r"^%[\w.$-]+\s*=\s*(.*)$")


def count_opcodes(ir: str) -> dict[str, int]:
    """Count the instructions in every function body of `ir`, by opcode.

    Only lines between a `define ... {` line and its closing `}` count. Skip
    blank lines, comments (`;`), and block labels such as `loop:`.

    The opcode is the first word after `%name = `, or the first word when there
    is no assignment. A `tail` / `musttail` / `notail` prefix on a call is not
    the opcode: `call` is.

    >>> count_opcodes("define i32 @f(i32 %x) {\\nentry:\\n  %y = add i32 %x, 1\\n  ret i32 %y\\n}")
    {'add': 1, 'ret': 1}
    """
    counts: dict[str, int] = {}
    inside = False
    for raw in ir.splitlines():
        line = raw.split(";", 1)[0].strip()  # drop comments
        if not line:
            continue
        if line.startswith("define"):
            inside = True
            continue
        if not inside:
            continue
        if line == "}":
            inside = False
            continue
        if _LABEL.match(line):
            continue
        m = _ASSIGN.match(line)
        if m:
            line = m.group(1)
        words = line.split()
        if words[0] in ("tail", "musttail", "notail"):
            words = words[1:]
        counts[words[0]] = counts.get(words[0], 0) + 1
    return counts


_KEYS = ("alloca", "load", "store", "phi")


def _only_memory(counts: dict[str, int]) -> dict[str, int]:
    return {k: counts.get(k, 0) for k in _KEYS}


def mem2reg_report(c_source: str) -> dict[str, dict[str, int]]:
    """Compile C at -O0, run mem2reg, and count memory instructions before and after.

    Returns {"before": counts, "after": counts}. Each `counts` has exactly the
    keys "alloca", "load", "store", and "phi", with 0 for an absent opcode.
    """
    before = cputools.c_to_ir(c_source, opt="-O0")
    after = cputools.run_opt(before, "mem2reg")
    return {
        "before": _only_memory(count_opcodes(before)),
        "after": _only_memory(count_opcodes(after)),
    }


def swap_ir() -> str:
    """IR for `void swap(int *a, int *b)`: exchange the two ints the pointers refer to."""
    return """
define void @swap(ptr %a, ptr %b) {
entry:
  %x = load i32, ptr %a
  %y = load i32, ptr %b
  store i32 %y, ptr %a
  store i32 %x, ptr %b
  ret void
}
"""


def sum_array_ir() -> str:
    """IR for `int sum_array(const int *a, int n)`: the sum of a[0] .. a[n-1]."""
    # A phi-based loop: the counter and the total are SSA values, and the only
    # memory access is the load of each element.
    return """
define i32 @sum_array(ptr %a, i32 %n) {
entry:
  br label %cond

cond:
  %i = phi i32 [ 0, %entry ], [ %i.next, %body ]
  %s = phi i32 [ 0, %entry ], [ %s.next, %body ]
  %more = icmp slt i32 %i, %n
  br i1 %more, label %body, label %done

body:
  %idx = sext i32 %i to i64
  %p = getelementptr inbounds i32, ptr %a, i64 %idx
  %v = load i32, ptr %p
  %s.next = add i32 %s, %v
  %i.next = add i32 %i, 1
  br label %cond

done:
  ret i32 %s
}
"""


def get_b_ir() -> str:
    """IR with `%Point = type { i32, i64 }`, `@get_b`, and `@set_a`."""
    return """
%Point = type { i32, i64 }

define i64 @get_b(ptr %p) {
entry:
  %fb = getelementptr inbounds %Point, ptr %p, i32 0, i32 1
  %b = load i64, ptr %fb
  ret i64 %b
}

define void @set_a(ptr %p, i32 %v) {
entry:
  %fa = getelementptr inbounds %Point, ptr %p, i32 0, i32 0
  store i32 %v, ptr %fa
  ret void
}
"""


def local_sum_ir() -> str:
    """IR for `int local_sum(int n)`, with the variables kept in allocas."""
    return """
define i32 @local_sum(i32 %n) {
entry:
  %s = alloca i32
  %i = alloca i32
  store i32 0, ptr %s
  store i32 1, ptr %i
  br label %cond

cond:
  %i.cur = load i32, ptr %i
  %more = icmp sle i32 %i.cur, %n
  br i1 %more, label %body, label %done

body:
  %s.cur = load i32, ptr %s
  %i.val = load i32, ptr %i
  %s.new = add i32 %s.cur, %i.val
  store i32 %s.new, ptr %s
  %i.new = add i32 %i.val, 1
  store i32 %i.new, ptr %i
  br label %cond

done:
  %result = load i32, ptr %s
  ret i32 %result
}
"""


if __name__ == "__main__":
    src = "int f(int x) { int y = x + 1; return y * 2; }"
    report = mem2reg_report(src)
    print("before mem2reg:", report["before"])
    print("after  mem2reg:", report["after"])
    after = cputools.run_opt(local_sum_ir(), "mem2reg")
    body = after[after.index("define"):]
    print(body[: body.index("\n}") + 2])
