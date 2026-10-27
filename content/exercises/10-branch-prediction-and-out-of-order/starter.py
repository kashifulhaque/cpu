"""Branch prediction and out-of-order execution.

A trace is a list of (pc, taken) pairs: which branch ran, and whether it jumped.
Every predictor has predict(pc) -> bool and update(pc, taken).
Fill in everything that raises NotImplementedError.
"""


class StaticPredictor:
    """Always predicts the same direction and never learns. Given in full."""

    def __init__(self, taken=True):
        self.taken = taken

    def predict(self, pc):
        return self.taken

    def update(self, pc, taken):
        pass


class OneBitPredictor:
    """Remembers the last outcome of each branch, in a table indexed by pc % table_size.

    Every entry starts as False (predict not taken).
    After update(pc, True), predict(pc) is True; after update(pc, False), it is False.
    """

    def __init__(self, table_size=64):
        raise NotImplementedError

    def predict(self, pc):
        raise NotImplementedError

    def update(self, pc, taken):
        raise NotImplementedError


class TwoBitPredictor:
    """A saturating counter per branch, indexed by pc % table_size.

    Counters run 0 (strongly not taken) to 3 (strongly taken) and start at 1.
    predict is True when the counter is 2 or 3. update adds 1 when taken and
    subtracts 1 when not, never leaving the range 0..3.
    """

    def __init__(self, table_size=64):
        raise NotImplementedError

    def predict(self, pc):
        raise NotImplementedError

    def update(self, pc, taken):
        raise NotImplementedError


class GsharePredictor:
    """2-bit counters (start at 1) in a table of 2**index_bits entries.

    The index is (pc ^ history) & (2**index_bits - 1), where `history` holds the
    last `index_bits` outcomes of all branches, newest in bit 0, starting at 0.
    update uses the same index predict did, adjusts that counter like
    TwoBitPredictor, and only then shifts the outcome into history:
    history = ((history << 1) | taken) & mask.
    """

    def __init__(self, index_bits=8):
        raise NotImplementedError

    def predict(self, pc):
        raise NotImplementedError

    def update(self, pc, taken):
        raise NotImplementedError


def run_predictor(predictor, trace):
    """Number of correct predictions over the trace.

    For each (pc, taken): ask predict(pc) and compare with `taken`, then call
    update(pc, taken). run_predictor(StaticPredictor(True), [(0, True), (0, False)]) == 1
    """
    raise NotImplementedError


def ooo_time(ops):
    """Finish time with unlimited out-of-order hardware (the critical path).

    `ops` is a list of (latency, deps); deps is a tuple of indexes of earlier ops.
    An op starts as soon as all its deps have finished (time 0 with no deps) and
    finishes `latency` cycles later. Return the latest finish; 0 for an empty list.
    ooo_time([(4, ()), (1, (0,)), (4, ()), (1, (2,)), (1, (1, 3))]) == 6
    """
    raise NotImplementedError


def in_order_time(ops):
    """Finish time when ops must start in program order, at most one start per cycle.

    Like ooo_time, but an op may not start before the previous op started plus 1.
    The first op can start at time 0.
    in_order_time([(4, ()), (1, (0,)), (4, ()), (1, (2,)), (1, (1, 3))]) == 11
    """
    raise NotImplementedError


if __name__ == "__main__":
    # A loop branch: taken 9 times, then not taken once, ten times over.
    trace = ([(0x40, True)] * 9 + [(0x40, False)]) * 10
    for name, predictor in [
        ("always taken", StaticPredictor(True)),
        ("1-bit", OneBitPredictor()),
        ("2-bit", TwoBitPredictor()),
        ("gshare", GsharePredictor(index_bits=4)),
    ]:
        print(f"{name:13s} {run_predictor(predictor, trace)} / {len(trace)} correct")
    # Two loads (4 cycles each), each followed by an add, then a final add.
    ops = [(4, ()), (1, (0,)), (4, ()), (1, (2,)), (1, (1, 3))]
    print("in-order:", in_order_time(ops), "cycles;  out-of-order:", ooo_time(ops), "cycles")
