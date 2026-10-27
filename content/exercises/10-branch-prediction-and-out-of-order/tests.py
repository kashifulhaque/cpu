"""Checks for the branch prediction and out-of-order exercise."""

import random

from cpucheck import almost, check, equal, has


def _loop_trace(trip, repeats, pc=0x40):
    """A loop branch: taken (trip - 1) times, then not taken, repeated."""
    return ([(pc, True)] * (trip - 1) + [(pc, False)]) * repeats


def _random_trace(n, p_taken, pc=0x40):
    rng = random.Random(0)
    return [(pc, rng.random() < p_taken) for _ in range(n)]


@check("StaticPredictor and run_predictor count correct predictions")
def test_static(sub):
    Static, run_predictor = has(sub, "StaticPredictor"), has(sub, "run_predictor")
    trace = [(0, True), (0, False), (4, True)]
    equal(run_predictor(Static(True), trace), 2, label="always taken")
    equal(run_predictor(Static(False), trace), 1, label="always not taken")
    equal(run_predictor(Static(True), []), 0, label="empty trace")
    # A loop taken 9 times in 10: always-taken gets 90 of 100 right.
    equal(run_predictor(Static(True), _loop_trace(10, 10)), 90, label="loop trace")


@check("OneBitPredictor remembers the last outcome, starting from not taken")
def test_one_bit(sub):
    OneBit, run_predictor = has(sub, "OneBitPredictor"), has(sub, "run_predictor")
    p = OneBit(table_size=8)
    equal(p.predict(3), False, label="first prediction")
    p.update(3, True)
    equal(p.predict(3), True, label="after a taken")
    equal(p.predict(4), False, label="a different branch is unaffected")
    p.update(3, False)
    equal(p.predict(3), False, label="after a not taken")
    # Loop of 10 trips, 10 times. Each trip mispredicts the exit, and then the first iteration
    # of the next trip: 2 wrong per trip = 20 wrong, so 80 right.
    equal(run_predictor(OneBit(), _loop_trace(10, 10)), 80, label="loop, 10 trips x 10")
    equal(run_predictor(OneBit(), _loop_trace(10, 100)), 800, label="loop, 10 trips x 100")
    # T N T N ...: the last outcome is always wrong next time, so every prediction misses.
    alternating = [(0x40, i % 2 == 0) for i in range(100)]
    equal(run_predictor(OneBit(), alternating), 0, label="alternating")


@check("TwoBitPredictor needs two surprises to change its mind")
def test_two_bit(sub):
    TwoBit, run_predictor = has(sub, "TwoBitPredictor"), has(sub, "run_predictor")
    p = TwoBit(table_size=8)
    equal(p.predict(1), False, label="counter starts at 1: weakly not taken")
    p.update(1, True)                       # counter 1 -> 2
    equal(p.predict(1), True, label="one taken moves it to weakly taken")
    p.update(1, True)                       # 2 -> 3
    p.update(1, True)                       # stays at 3 (saturated)
    p.update(1, False)                      # 3 -> 2
    equal(p.predict(1), True, label="one not taken from strongly taken still predicts taken")
    p.update(1, False)                      # 2 -> 1
    equal(p.predict(1), False, label="a second not taken flips the prediction")
    for _ in range(5):
        p.update(1, False)                  # saturates at 0
    p.update(1, True)                       # 0 -> 1
    equal(p.predict(1), False, label="saturated low: one taken is not enough")
    # Loop, 10 trips x 10. Wrong: the first taken (counter starts at 1) and each exit = 11 wrong, 89 right.
    equal(run_predictor(TwoBit(), _loop_trace(10, 10)), 89, label="loop, 10 trips x 10")
    equal(run_predictor(TwoBit(), _loop_trace(10, 100)), 899, label="loop, 10 trips x 100")
    alternating = [(0x40, i % 2 == 0) for i in range(100)]
    # T N T N: counter 1 predicts N but the first outcome is T (wrong, counter 2); it predicts T but the outcome is N (wrong, counter 1); and so on.
    equal(run_predictor(TwoBit(), alternating), 0, label="alternating")


@check("a 2-bit counter beats a 1-bit one on a branch that is mostly taken")
def test_biased(sub):
    Static, OneBit, TwoBit = has(sub, "StaticPredictor"), has(sub, "OneBitPredictor"), has(sub, "TwoBitPredictor")
    run_predictor = has(sub, "run_predictor")
    # Seeded: 1000 outcomes, each taken with probability 0.9. 896 of them are taken.
    trace = _random_trace(1000, 0.9)
    equal(run_predictor(Static(True), trace), 896, label="always taken")
    equal(run_predictor(OneBit(), trace), 823, label="1-bit")
    equal(run_predictor(TwoBit(), trace), 882, label="2-bit")


@check("predictors keep separate state for branches at different addresses, and alias when the table is small")
def test_aliasing(sub):
    OneBit, TwoBit = has(sub, "OneBitPredictor"), has(sub, "TwoBitPredictor")
    run_predictor = has(sub, "run_predictor")
    # Branch 0 is always taken and branch 4 never is, interleaved, 10 times (20 outcomes).
    trace = []
    for _ in range(10):
        trace += [(0, True), (4, False)]
    # table_size 8: separate entries. Branch 0 is wrong once (the start), branch 4 never: 19 right.
    equal(run_predictor(OneBit(8), trace), 19, label="1-bit, table of 8")
    equal(run_predictor(TwoBit(8), trace), 19, label="2-bit, table of 8")
    # table_size 4: pcs 0 and 4 share entry 0 and fight over it. Every prediction is wrong.
    equal(run_predictor(OneBit(4), trace), 0, label="1-bit, table of 4 (aliasing)")
    equal(run_predictor(TwoBit(4), trace), 0, label="2-bit, table of 4 (aliasing)")


@check("GsharePredictor learns patterns that depend on recent history")
def test_gshare(sub):
    Gshare, run_predictor = has(sub, "GsharePredictor"), has(sub, "run_predictor")
    # Alternating T N, 100 outcomes. A 2-bit history sees "the last was T" or "the last was N"
    # and learns the next outcome. Only the first couple of predictions are wrong.
    alternating = [(0x40, i % 2 == 0) for i in range(100)]
    equal(run_predictor(Gshare(index_bits=2), alternating), 98, label="alternating, 2 history bits")
    # Loop: taken 3 times, then not taken (trip count 4), 100 times. With 4 history bits the
    # pattern T T T N is fully visible, so only the warm-up is wrong.
    equal(run_predictor(Gshare(index_bits=4), _loop_trace(4, 100)), 394, label="trip 4, 4 history bits")
    # The same loop defeats 1-bit (200) and 2-bit (299) predictors.
    equal(run_predictor(has(sub, "OneBitPredictor")(), _loop_trace(4, 100)), 200, label="trip 4, 1-bit")
    equal(run_predictor(has(sub, "TwoBitPredictor")(), _loop_trace(4, 100)), 299, label="trip 4, 2-bit")
    # A trip count of 10 needs a history of at least 9 outcomes. 10 bits learns it, 4 bits cannot.
    equal(run_predictor(Gshare(index_bits=10), _loop_trace(10, 100)), 982, label="trip 10, 10 history bits")
    equal(run_predictor(Gshare(index_bits=4), _loop_trace(10, 100)), 892, label="trip 10, 4 history bits")


@check("on random outcomes no predictor is much better than a coin flip")
def test_random(sub):
    Static, OneBit, TwoBit, Gshare = (has(sub, n) for n in
                                      ("StaticPredictor", "OneBitPredictor", "TwoBitPredictor", "GsharePredictor"))
    run_predictor = has(sub, "run_predictor")
    trace = _random_trace(1000, 0.5)
    # Seeded: 508 of the 1000 outcomes are taken.
    equal(run_predictor(Static(True), trace), 508, label="always taken")
    equal(run_predictor(OneBit(), trace), 477, label="1-bit")
    equal(run_predictor(TwoBit(), trace), 503, label="2-bit")
    equal(run_predictor(Gshare(8), trace), 503, label="gshare")
    for make in (OneBit, TwoBit, Gshare):
        got = run_predictor(make(), trace)
        almost(got / 1000, 0.5, 0.06, label=f"{make.__name__} accuracy on random outcomes")


@check("ooo_time is the critical path; in_order_time lets stalls block later ops")
def test_ooo(sub):
    ooo_time, in_order_time = has(sub, "ooo_time"), has(sub, "in_order_time")
    # Two loads (4 cycles), each followed by an add that uses it, then an add of both.
    ops = [(4, ()), (1, (0,)), (4, ()), (1, (2,)), (1, (1, 3))]
    # Out of order: both loads start at 0 and finish at 4; the adds finish at 5; the last add at 6.
    equal(ooo_time(ops), 6, label="out of order")
    # In order: load0 0-4; add 4-5; load1 starts 5 (after add's start 4 + 1) and ends 9;
    # add 9-10; final add starts at max(10, 5) = 10, ends 11.
    equal(in_order_time(ops), 11, label="in order")
    equal(ooo_time([]), 0, label="empty list, out of order")
    equal(in_order_time([]), 0, label="empty list, in order")
    # A dependent chain gives the two models the same answer: 1 + 1 + 1 = 3 either way.
    chain = [(1, ()), (1, (0,)), (1, (1,))]
    equal(ooo_time(chain), 3, label="chain, out of order")
    equal(in_order_time(chain), 3, label="chain, in order")
    # Independent ops: out of order they all start at 0, in order they start 0, 1, 2, 3.
    independent = [(3, ())] * 4
    equal(ooo_time(independent), 3, label="independent, out of order")
    equal(in_order_time(independent), 6, label="independent, in order (last starts at 3, ends at 6)")
    # Dependency on a slow op: the independent op behind it is stuck in order.
    slow = [(10, ()), (1, (0,)), (1, ())]
    equal(ooo_time(slow), 11, label="slow op, out of order")
    equal(in_order_time(slow), 12, label="slow op, in order: the last op starts at 11, ends at 12")
