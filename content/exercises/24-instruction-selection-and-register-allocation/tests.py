"""Checks for the register allocation and x86-64 exercise."""

import ctypes
import json
import os
import random
import re
import select

import cputools
from cpucheck import check, equal, fail, has

STRAIGHT = ("f", "a b", "t1 = add a b\nt2 = mul t1 a\nt3 = sub t2 b\nret t3")
SUM_TO = (
    "sum_to", "n",
    "s = const 0\ntop:\ns = add s n\none = const 1\nn = sub n one\njnz n top\nret s",
)
FACT = (
    "fact", "n",
    "r = const 1\ntop:\nr = mul r n\none = const 1\nn = sub n one\njnz n top\nret r",
)


def _child(fn, seconds=10):
    """Run fn() in a forked child and return its JSON-able result.

    Generated assembly can crash (a bad stack, a wild jump) or loop forever, so
    it runs in a child: the parent reads the answer through a pipe and kills a
    child that takes too long.
    """
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        code = 1
        try:
            os.close(r)
            os.write(w, json.dumps(fn()).encode())
            code = 0
        except BaseException:
            pass
        finally:
            os._exit(code)
    os.close(w)
    data = b""
    ready, _, _ = select.select([r], [], [], seconds)
    if ready:
        while True:
            chunk = os.read(r, 65536)
            if not chunk:
                break
            data += chunk
    else:
        os.kill(pid, 9)
    os.close(r)
    os.waitpid(pid, 0)
    if not data:
        fail("your generated code crashed or never returned (a broken stack, a wrong jump, or a missing ret)")
    return json.loads(data)


def _wrap(n):
    n &= (1 << 64) - 1
    return n - (1 << 64) if n >> 63 else n


def _interpret(prog, args):
    """Reference semantics, with 64-bit wrap-around."""
    env = dict(zip(prog.params, args))
    labels = {i.args[0]: k for k, i in enumerate(prog.code) if i.op == "label"}
    pc = 0
    for _ in range(100000):
        i = prog.code[pc]
        pc += 1
        if i.op == "const":
            env[i.dest] = i.args[0]
        elif i.op == "copy":
            env[i.dest] = env[i.args[0]]
        elif i.op in ("add", "sub", "mul"):
            a, b = env[i.args[0]], env[i.args[1]]
            env[i.dest] = _wrap({"add": a + b, "sub": a - b, "mul": a * b}[i.op])
        elif i.op == "jmp":
            pc = labels[i.args[0]]
        elif i.op == "jnz":
            if env[i.args[0]] != 0:
                pc = labels[i.args[1]]
        elif i.op == "ret":
            return env[i.args[0]]
    raise AssertionError("reference interpreter ran too long")


def _run_asm(sub, prog, k, inputs):
    """Allocate, emit, assemble in the parent, and run on every input in a child."""
    alloc = has(sub, "allocate")(prog, k)
    asm = has(sub, "emit_x86")(prog, alloc)
    lib = cputools.assemble(asm)
    fn = getattr(lib, prog.name)
    fn.restype = ctypes.c_int64
    fn.argtypes = [ctypes.c_int64] * len(prog.params)
    return _child(lambda: [fn(*args) for args in inputs]), asm


def _sets(rows):
    return [set(r) for r in rows]


@check("liveness of straight-line code: each name is live from its definition to its last use")
def test_live_straight(sub):
    live_in, live_out = has(sub, "liveness")(sub.parse_program(*STRAIGHT))
    # i0: t1 = add a b   i1: t2 = mul t1 a   i2: t3 = sub t2 b   i3: ret t3
    equal(_sets(live_in), [{"a", "b"}, {"a", "b", "t1"}, {"b", "t2"}, {"t3"}], label="live_in")
    equal(_sets(live_out), [{"a", "b", "t1"}, {"b", "t2"}, {"t3"}, set()], label="live_out")


@check("liveness of a loop: the back edge keeps the loop's variables alive around the whole loop")
def test_live_loop(sub):
    live_in, live_out = has(sub, "liveness")(sub.parse_program(*SUM_TO))
    # 0: s = const 0   1: top:   2: s = add s n   3: one = const 1   4: n = sub n one   5: jnz n top   6: ret s
    equal(
        _sets(live_in),
        [{"n"}, {"n", "s"}, {"n", "s"}, {"n", "s"}, {"n", "s", "one"}, {"n", "s"}, {"s"}],
        label="live_in",
    )
    equal(
        _sets(live_out),
        [{"n", "s"}, {"n", "s"}, {"n", "s"}, {"n", "s", "one"}, {"n", "s"}, {"n", "s"}, set()],
        label="live_out",
    )


@check("interference_graph: edges between names live at the same time, symmetric, with every name present")
def test_graph(sub):
    graph = has(sub, "interference_graph")
    g = graph(sub.parse_program(*STRAIGHT))
    equal(
        {k: sorted(v) for k, v in g.items()},
        {"a": ["b", "t1"], "b": ["a", "t1", "t2"], "t1": ["a", "b"], "t2": ["b"], "t3": []},
        label="straight-line graph",
    )
    g = graph(sub.parse_program(*SUM_TO))
    equal(
        {k: sorted(v) for k, v in g.items()},
        {"n": ["one", "s"], "s": ["n", "one"], "one": ["n", "s"]},
        label="loop graph (a triangle)",
    )
    g = graph(sub.parse_program("h", "a b", "x = const 1\nret x"))
    equal(sorted(g["a"]), ["b"], label="two parameters interfere even when unused")


def _valid(graph, colors, spilled, k, label):
    for v in graph:
        if (v in colors) == (v in spilled):
            fail(f"{label}: {v!r} must be either colored or spilled, not both or neither")
    for v, c in colors.items():
        if not 0 <= c < k:
            fail(f"{label}: {v!r} has color {c}, outside 0..{k - 1}")
        for w in graph[v]:
            if w in colors and colors[w] == c:
                fail(f"{label}: neighbours {v!r} and {w!r} share color {c}")


def _graph(edges, extra=()):
    g = {v: set() for v in extra}
    for a, b in edges:
        g.setdefault(a, set()).add(b)
        g.setdefault(b, set()).add(a)
    return g


@check("color_graph gives neighbours different colors and spills only when it must")
def test_color(sub):
    color = has(sub, "color_graph")
    tri = _graph([("a", "b"), ("b", "c"), ("a", "c")])
    for name, g, k, expected_spills in [
        ("triangle, k=3", tri, 3, 0),
        ("path, k=2", _graph([("a", "b"), ("b", "c"), ("c", "d")]), 2, 0),
        ("five cycle, k=3", _graph([("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "a")]), 3, 0),
        ("no edges, k=1", _graph([], extra="abcd"), 1, 0),
        ("K4, k=3", _graph([(x, y) for x in "abcd" for y in "abcd" if x < y]), 3, 1),
        ("K5, k=2", _graph([(x, y) for x in "abcde" for y in "abcde" if x < y]), 2, 3),
    ]:
        colors, spilled = color(g, k)
        _valid(g, colors, set(spilled), k, name)
        equal(len(spilled), expected_spills, label=f"{name}: number of spilled nodes")
        equal(list(spilled), sorted(spilled), label=f"{name}: spilled is sorted")
    colors, spilled = color(_graph([("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "a")]), 2)
    if not spilled:
        fail("a five-cycle cannot be colored with 2 colors, so something must be spilled")
    rng = random.Random(0)
    for trial in range(30):
        names = [f"v{i}" for i in range(rng.randint(1, 12))]
        edges = [(a, b) for a in names for b in names if a < b and rng.random() < 0.35]
        g = _graph(edges, extra=names)
        for k in (1, 2, 3, 5):
            colors, spilled = color(g, k)
            _valid(g, colors, set(spilled), k, f"random graph {trial}, k={k}")


@check("allocate puts interfering variables in different registers and gives each spilled variable its own slot")
def test_allocate(sub):
    allocate = has(sub, "allocate")
    prog = sub.parse_program(*STRAIGHT)
    a = allocate(prog, 5)
    equal(a.slot, {}, label="with 5 registers nothing spills")
    for v in "a b t1 t2 t3".split():
        if v not in a.reg:
            fail(f"{v!r} has no register")
    equal(len(set(a.reg.values()) - set(sub.REGS[:5])), 0, label="registers come from REGS")
    graph = sub.interference_graph(prog)
    for v, nbs in graph.items():
        for w in nbs:
            if v in a.reg and w in a.reg and a.reg[v] == a.reg[w]:
                fail(f"{v!r} and {w!r} interfere but share {a.reg[v]}")
    b = allocate(prog, 2)
    if not b.slot:
        fail("with 2 registers the triangle a, b, t1 cannot fit: at least one variable must spill")
    equal(sorted(b.slot.values()), list(range(len(b.slot))), label="slot numbers are 0, 1, 2, ...")
    equal(set(b.reg) | set(b.slot), set(graph), label="every variable is placed")
    equal(set(b.reg) & set(b.slot), set(), label="no variable is both in a register and a slot")
    if not set(b.reg.values()) <= set(sub.REGS[:2]):
        fail(f"with k=2 only {sub.REGS[:2]} may be used, got {sorted(set(b.reg.values()))}")


@check("emit_x86: straight-line code returns (a + b) * a - b with enough registers")
def test_emit_straight(sub):
    prog = sub.parse_program(*STRAIGHT)
    inputs = [(3, 4), (0, 0), (-5, 2), (10**9, 7), (-(2**40), 3)]
    got, _ = _run_asm(sub, prog, 5, inputs)
    # (3+4)*3 - 4 = 17; (a+b)*a - b in general
    equal(got, [_interpret(prog, list(x)) for x in inputs])
    equal(got[0], 17, label="f(3, 4)")


@check("emit_x86 with spills: the same function is correct with 2 registers and with 1")
def test_emit_spill(sub):
    prog = sub.parse_program(*STRAIGHT)
    inputs = [(3, 4), (0, 0), (-5, 2), (10**9, 7), (-(2**40), 3)]
    want = [_interpret(prog, list(x)) for x in inputs]
    for k in (2, 1):
        got, asm = _run_asm(sub, prog, k, inputs)
        equal(got, want, label=f"k={k}")
        if "rsp" not in asm:
            fail(f"k={k} forces a spill, but your assembly never touches rsp")


@check("emit_x86 on loops: sum_to(n) and fact(n) are right for n = 1..20, with 3, 2, and 1 registers")
def test_emit_loops(sub):
    inputs = [(n,) for n in range(1, 21)]
    for src in (SUM_TO, FACT):
        prog = sub.parse_program(*src)
        want = [_interpret(prog, list(x)) for x in inputs]
        for k in (3, 2, 1):
            got, _ = _run_asm(sub, prog, k, inputs)
            equal(got, want, label=f"{prog.name} with k={k}")
    # n(n+1)/2 for sum_to, and 20! for fact
    prog = sub.parse_program(*SUM_TO)
    got, _ = _run_asm(sub, prog, 3, [(10,), (100,)])
    equal(got, [55, 5050], label="sum_to(10), sum_to(100)")
    prog = sub.parse_program(*FACT)
    got, _ = _run_asm(sub, prog, 3, [(20,)])
    equal(got, [2432902008176640000], label="fact(20)")


def _random_program(sub, rng, n):
    names = ["a", "b"]
    lines = []
    for k in range(n):
        d = f"v{k}"
        kind = rng.choice(["const", "copy", "add", "sub", "mul", "add", "mul"])
        if kind == "const":
            lines.append(f"{d} = const {rng.randint(-50, 50)}")
        elif kind == "copy":
            lines.append(f"{d} = copy {rng.choice(names)}")
        else:
            lines.append(f"{d} = {kind} {rng.choice(names)} {rng.choice(names)}")
        names.append(d)
    lines.append(f"ret {rng.choice(names[-3:])}")
    return sub.parse_program("g", "a b", "\n".join(lines))


@check("random straight-line programs run correctly with 5, 2, and 1 registers")
def test_random(sub):
    rng = random.Random(0)
    inputs = [(0, 0), (1, 2), (-7, 13), (2**31, -(2**33))]
    for t in range(6):
        prog = _random_program(sub, rng, rng.randint(3, 14))
        want = [_interpret(prog, list(x)) for x in inputs]
        for k in (5, 2, 1):
            got, _ = _run_asm(sub, prog, k, inputs)
            equal(got, want, label=f"random program {t}, k={k}")


@check("with enough registers the code never touches the stack, and it uses only the first k of REGS (checked in your assembly text)")
def test_text(sub):
    prog = sub.parse_program(*SUM_TO)
    asm = sub.emit_x86(prog, sub.allocate(prog, 3))
    if "rsp" in asm:
        fail("sum_to fits in 3 registers, but your assembly uses rsp")
    allowed = set(sub.REGS[:3]) | {"rax", "rdi", "rsi"}
    seen = set(re.findall(r"\b(r(?:cx|8|9|1[0-5]|dx|bx|si|di|ax))\b", asm))
    extra = seen - allowed
    if extra:
        fail(f"with k=3 your code mentions registers outside {sorted(allowed)}: {sorted(extra)}")
