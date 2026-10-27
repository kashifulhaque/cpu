"""Branch prediction and out-of-order execution.

Reference solution.

A trace is a list of (pc, taken) pairs: which branch ran, and whether it jumped.
"""


class StaticPredictor:
    """Always predicts the same direction and never learns."""

    def __init__(self, taken=True):
        self.taken = taken

    def predict(self, pc):
        return self.taken

    def update(self, pc, taken):
        pass


class OneBitPredictor:
    """Remembers the last outcome of each branch (indexed by pc % table_size)."""

    def __init__(self, table_size=64):
        self.table_size = table_size
        self.table = [False] * table_size      # start by predicting not taken

    def predict(self, pc):
        return self.table[pc % self.table_size]

    def update(self, pc, taken):
        self.table[pc % self.table_size] = taken


class TwoBitPredictor:
    """A saturating counter per branch: 0 strongly not taken ... 3 strongly taken."""

    def __init__(self, table_size=64):
        self.table_size = table_size
        self.counters = [1] * table_size       # start weakly not taken

    def predict(self, pc):
        return self.counters[pc % self.table_size] >= 2

    def update(self, pc, taken):
        i = pc % self.table_size
        if taken:
            self.counters[i] = min(3, self.counters[i] + 1)
        else:
            self.counters[i] = max(0, self.counters[i] - 1)


class GsharePredictor:
    """2-bit counters indexed by (pc XOR global history). Table size is 2**index_bits."""

    def __init__(self, index_bits=8):
        self.mask = (1 << index_bits) - 1
        self.counters = [1] * (1 << index_bits)
        self.history = 0                       # the last index_bits outcomes, newest in bit 0

    def _index(self, pc):
        return (pc ^ self.history) & self.mask

    def predict(self, pc):
        return self.counters[self._index(pc)] >= 2

    def update(self, pc, taken):
        i = self._index(pc)                    # same index predict used: history not shifted yet
        if taken:
            self.counters[i] = min(3, self.counters[i] + 1)
        else:
            self.counters[i] = max(0, self.counters[i] - 1)
        self.history = ((self.history << 1) | int(taken)) & self.mask


def run_predictor(predictor, trace):
    """Number of correct predictions over the trace. Predict first, then update."""
    correct = 0
    for pc, taken in trace:
        if predictor.predict(pc) == taken:
            correct += 1
        predictor.update(pc, taken)
    return correct


def ooo_time(ops):
    """Finish time with unlimited out-of-order hardware: the critical path.

    ops is a list of (latency, deps); deps are indexes of earlier ops.
    """
    finish = []
    for latency, deps in ops:
        start = max((finish[d] for d in deps), default=0)
        finish.append(start + latency)
    return max(finish, default=0)


def in_order_time(ops):
    """Finish time when ops must start in program order, one start per cycle."""
    finish = []
    previous_start = -1
    for latency, deps in ops:
        start = max([previous_start + 1] + [finish[d] for d in deps])
        finish.append(start + latency)
        previous_start = start
    return max(finish, default=0)


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
