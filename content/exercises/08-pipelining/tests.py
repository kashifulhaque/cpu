"""Checks for the pipelining exercise."""

from cpucheck import almost, check, equal, has


def _prog(sub, *lines):
    parse = has(sub, "parse")
    return [parse(line) for line in lines]


@check("ideal_cycles: n independent instructions take n + 4 cycles")
def test_ideal(sub):
    ideal_cycles = has(sub, "ideal_cycles")
    # The first instruction needs 5 cycles; each following one finishes 1 cycle later.
    for n, want in [(0, 0), (1, 5), (2, 6), (4, 8), (100, 104)]:
        equal(ideal_cycles(n), want, label=f"ideal_cycles({n})")


@check("find_raw reports read-after-write pairs within two instructions")
def test_find_raw(sub):
    find_raw = has(sub, "find_raw")
    p = _prog(sub, "add x1, x2, x3", "add x4, x1, x5")
    equal(find_raw(p), [(0, 1)], label="distance 1")
    p = _prog(sub, "add x1, x2, x3", "add x6, x7, x8", "add x4, x1, x5")
    equal(find_raw(p), [(0, 2)], label="distance 2")
    p = _prog(sub, "add x1, x2, x3", "add x6, x7, x8", "add x9, x10, x11", "add x4, x1, x5")
    equal(find_raw(p), [], label="distance 3 is safe: WB writes before ID reads")
    p = _prog(sub, "add x1, x2, x3", "add x4, x1, x1", "add x5, x4, x1")
    # i=1 reads x1 from 0; i=2 reads x4 from 1 (distance 1) and x1 from 0 (distance 2).
    equal(find_raw(p), [(0, 1), (0, 2), (1, 2)], label="chain of three")
    p = _prog(sub, "add x1, x2, x3", "add x1, x4, x5", "add x6, x1, x7")
    equal(find_raw(p), [(1, 2)], label="only the nearest writer counts")
    p = _prog(sub, "addi x0, x1, 5", "add x2, x0, x3", "sw x2, 0(x0)")
    # x0 is never a dependency; sw reads x2 from instruction 1.
    equal(find_raw(p), [(1, 2)], label="x0 is not a dependency")
    p = _prog(sub, "lw x5, 0(x1)", "sw x5, 4(x1)")
    equal(find_raw(p), [(0, 1)], label="a load feeding a store")


@check("stalls_no_forwarding: a distance-1 dependency costs 2 cycles, distance-2 costs 1")
def test_stalls_nofwd(sub):
    stalls = has(sub, "stalls_no_forwarding")
    # id[0] = 2, WB of 0 is cycle 5, so an immediate reader waits in ID until cycle 5: 2 stalls.
    equal(stalls(_prog(sub, "add x1, x2, x3", "add x4, x1, x5")), [0, 2], label="distance 1")
    # The reader is the third instruction: it would be in ID at cycle 4, waits to 5: 1 stall.
    equal(stalls(_prog(sub, "add x1, x2, x3", "add x6, x7, x8", "add x4, x1, x5")), [0, 0, 1], label="distance 2")
    equal(stalls(_prog(sub, "addi x1, x0, 1", "addi x2, x0, 2", "addi x3, x0, 3")), [0, 0, 0], label="independent")
    # id: 2, 5 (waits for WB at 5), 8 (waits for x4's WB at 5 + 3 = 8).
    equal(stalls(_prog(sub, "add x1, x2, x3", "add x4, x1, x1", "add x5, x4, x1")), [0, 2, 2], label="chain of three")
    equal(stalls([]), [], label="empty program")


@check("stalls_no_forwarding handles loads, stores, and stalls that pile up")
def test_stalls_nofwd_mixed(sub):
    stalls = has(sub, "stalls_no_forwarding")
    # id: lw0=2, lw1=3, add waits for lw1's WB at 3+3 = 6 -> stall 2, sw waits for add's WB at 6+3 = 9 -> stall 2.
    p = _prog(sub, "lw x1, 0(x2)", "lw x3, 4(x2)", "add x4, x1, x3", "sw x4, 8(x2)")
    equal(stalls(p), [0, 0, 2, 2], label="two loads, an add, a store")
    # A later instruction after a stall is delayed too, even with no dependency:
    # id: 2, 5, 6 (the independent add follows the stalled one), so its stall count is 0.
    p = _prog(sub, "add x1, x2, x3", "add x4, x1, x5", "add x6, x7, x8")
    equal(stalls(p), [0, 2, 0], label="an independent instruction behind a stall")


@check("stalls_forwarding: only a load followed by its user stalls, for one cycle")
def test_stalls_fwd(sub):
    stalls = has(sub, "stalls_forwarding")
    equal(stalls(_prog(sub, "add x1, x2, x3", "add x4, x1, x5")), [0, 0], label="ALU to ALU is forwarded")
    equal(stalls(_prog(sub, "lw x1, 0(x2)", "add x3, x1, x4")), [0, 1], label="load-use")
    equal(stalls(_prog(sub, "lw x1, 0(x2)", "add x6, x7, x8", "add x3, x1, x4")), [0, 0, 0], label="load two ahead")
    equal(stalls(_prog(sub, "lw x1, 0(x2)", "add x3, x4, x5")), [0, 0], label="load with no user")
    equal(stalls(_prog(sub, "lw x1, 0(x2)", "lw x3, 4(x2)", "add x4, x1, x3", "sw x4, 8(x2)")),
          [0, 0, 1, 0], label="loads feeding an add feeding a store")
    equal(stalls(_prog(sub, "lw x1, 0(x2)", "lw x3, 0(x1)")), [0, 1], label="pointer chase")
    equal(stalls([]), [], label="empty program")


@check("total_cycles counts stalls without and with forwarding")
def test_total(sub):
    total_cycles = has(sub, "total_cycles")
    equal(total_cycles([]), 0, label="empty program")
    p = _prog(sub, "addi x1, x0, 1", "addi x2, x0, 2", "addi x3, x0, 3")
    equal(total_cycles(p), 7, label="three independent instructions, no forwarding")
    equal(total_cycles(p, forwarding=True), 7, label="three independent instructions, forwarding")
    p = _prog(sub, "add x1, x2, x3", "add x4, x1, x5")
    # 2 instructions: 6 ideal cycles + 2 stalls = 8; forwarding removes them.
    equal(total_cycles(p), 8, label="dependent adds, no forwarding")
    equal(total_cycles(p, forwarding=True), 6, label="dependent adds, forwarding")
    p = _prog(sub, "lw x1, 0(x2)", "add x3, x1, x4")
    equal(total_cycles(p), 8, label="load-use, no forwarding (6 + 2)")
    equal(total_cycles(p, forwarding=True), 7, label="load-use, forwarding (6 + 1)")
    p = _prog(sub, "lw x1, 0(x2)", "lw x3, 4(x2)", "add x4, x1, x3", "sw x4, 8(x2)")
    equal(total_cycles(p), 12, label="array example, no forwarding (8 + 4)")
    equal(total_cycles(p, forwarding=True), 9, label="array example, forwarding (8 + 1)")
    p = _prog(sub, "add x1, x2, x3", "add x4, x1, x1", "add x5, x4, x1")
    equal(total_cycles(p), 11, label="chain of three, no forwarding (7 + 4)")
    equal(total_cycles(p, forwarding=True), 7, label="chain of three, forwarding")


@check("cpi is cycles per instruction")
def test_cpi(sub):
    cpi = has(sub, "cpi")
    p = _prog(sub, "lw x1, 0(x2)", "lw x3, 4(x2)", "add x4, x1, x3", "sw x4, 8(x2)")
    almost(cpi(p), 3.0, 1e-9, label="12 cycles / 4 instructions")
    almost(cpi(p, forwarding=True), 2.25, 1e-9, label="9 cycles / 4 instructions")
    # 100 independent instructions: 104 cycles, CPI 1.04, approaching 1.
    p = [has(sub, "parse")(f"addi x{1 + i % 30}, x0, {i}") for i in range(100)]
    almost(cpi(p, forwarding=True), 1.04, 1e-9, label="100 independent instructions")


@check("a loop body unrolled ten times: stalls add up across the whole program")
def test_unrolled(sub):
    total_cycles, cpi = has(sub, "total_cycles"), has(sub, "cpi")
    body = ["lw x1, 0(x2)", "add x3, x1, x4", "sw x3, 0(x2)", "addi x2, x2, 4"]
    p = _prog(sub, *(body * 10))
    # Forwarding: each lw is followed by its user (1 stall); nothing else stalls.
    # 40 instructions: 44 ideal cycles + 10 bubbles = 54.
    equal(total_cycles(p, forwarding=True), 54, label="forwarding, 10 copies")
    almost(cpi(p, forwarding=True), 54 / 40, 1e-9, label="CPI with forwarding")
    # No forwarding (hand count per copy): lw 0 stalls (after addi), add waits for lw, sw waits for add.
    # Copy 1 ids: lw=2, add=5, sw=8, addi=9. Copy 2: lw needs x2 from addi (WB 9+3=12) -> id 12, add 15, sw 18, addi 19.
    # Each copy after the first adds 10 cycles to the last id, so id of the last addi is 9 + 10 * 9 = 99;
    # total = 99 + 3 = 102.
    equal(total_cycles(p), 102, label="no forwarding, 10 copies")
