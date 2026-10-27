"""Memory in LLVM IR: alloca, load, store, getelementptr, and mem2reg."""

import cputools


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
    raise NotImplementedError


def mem2reg_report(c_source: str) -> dict[str, dict[str, int]]:
    """Compile C at -O0, run mem2reg, and count memory instructions before and after.

    Returns {"before": counts, "after": counts}. Each `counts` has exactly the
    keys "alloca", "load", "store", and "phi", with 0 for an absent opcode.

    For `int f(int x) { int y = x + 1; return y * 2; }`, "before" has
    alloca 2, load 2, store 2, and "after" has all four at 0.
    """
    raise NotImplementedError


def swap_ir() -> str:
    """IR for `void swap(int *a, int *b)`: exchange the two ints the pointers refer to.

    Define `@swap(ptr %a, ptr %b)` returning void. Called with pointers to 3
    and 9, the two ints end up as 9 and 3.
    """
    raise NotImplementedError


def sum_array_ir() -> str:
    """IR for `int sum_array(const int *a, int n)`: the sum of a[0] .. a[n-1].

    Define `@sum_array(ptr %a, i32 %n)` returning i32. It returns 0 when
    n <= 0. Use `getelementptr` to reach each element. Called with the array
    [1, 2, 3, 4] and n = 4, it returns 10.
    """
    raise NotImplementedError


def get_b_ir() -> str:
    """IR with `%Point = type { i32, i64 }` and two functions over it.

    `i64 @get_b(ptr %p)` returns field 1 (the i64) of the Point at `%p`.
    `void @set_a(ptr %p, i32 %v)` stores `%v` into field 0 (the i32).
    Use `getelementptr` with the struct type. For a Point {a=5, b=70}, get_b
    returns 70.
    """
    raise NotImplementedError


def local_sum_ir() -> str:
    """IR for `int local_sum(int n)`: 1 + 2 + ... + n, using allocas for variables.

    Define `@local_sum(i32 %n)` returning i32. Keep the running total and the
    counter in `alloca` slots in the entry block, written the way clang -O0
    writes them: `store` and `load`, and no `phi` anywhere. It returns 0 for
    n <= 0, and 55 for n = 10.
    """
    raise NotImplementedError


if __name__ == "__main__":
    src = "int f(int x) { int y = x + 1; return y * 2; }"
    report = mem2reg_report(src)
    print("before mem2reg:", report["before"])
    print("after  mem2reg:", report["after"])
    after = cputools.run_opt(local_sum_ir(), "mem2reg")
    body = after[after.index("define"):]
    print(body[: body.index("\n}") + 2])
