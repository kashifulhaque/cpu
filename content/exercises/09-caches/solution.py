"""Caches and the memory hierarchy.

Reference solution.
"""

import cputools


def amat(hit_time, miss_rate, miss_penalty):
    """Average memory access time: every access pays the hit time; misses pay extra."""
    return hit_time + miss_rate * miss_penalty


def _is_power_of_two(n):
    return n > 0 and n & (n - 1) == 0


def split_address(addr, block_size, num_sets):
    """Split an address into (tag, index, offset)."""
    offset = addr % block_size            # byte within the block
    block = addr // block_size            # which block of memory
    return block // num_sets, block % num_sets, offset


class Cache:
    """A set-associative cache with LRU replacement. It tracks tags, not data."""

    def __init__(self, size, block_size, ways):
        if not (_is_power_of_two(size) and _is_power_of_two(block_size) and _is_power_of_two(ways)):
            raise ValueError("size, block_size, and ways must be powers of two")
        if size < block_size * ways:
            raise ValueError("size must hold at least one set of `ways` blocks")
        self.size, self.block_size, self.ways = size, block_size, ways
        self.num_sets = size // (block_size * ways)
        # sets[i] lists the tags in set i, least recently used first.
        self.sets = [[] for _ in range(self.num_sets)]
        self.hits = 0
        self.misses = 0

    def access(self, addr):
        """Look up addr. Return True on a hit, False on a miss (and load the block)."""
        tag, index, _ = split_address(addr, self.block_size, self.num_sets)
        tags = self.sets[index]
        if tag in tags:
            tags.remove(tag)
            tags.append(tag)              # now the most recently used
            self.hits += 1
            return True
        if len(tags) == self.ways:
            tags.pop(0)                   # evict the least recently used
        tags.append(tag)
        self.misses += 1
        return False

    @property
    def hit_rate(self):
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


def matrix_addresses(rows, cols, order="row", elem_size=4, base=0):
    """Addresses touched when walking a row-major rows x cols array.

    order="row" visits (0,0), (0,1), ...; order="col" visits (0,0), (1,0), ...
    """
    if order == "row":
        pairs = [(r, c) for r in range(rows) for c in range(cols)]
    elif order == "col":
        pairs = [(r, c) for c in range(cols) for r in range(rows)]
    else:
        raise ValueError("order must be 'row' or 'col'")
    return [base + (r * cols + c) * elem_size for r, c in pairs]


def run_trace(cache, addresses):
    """Feed every address to the cache and return (hits, misses) for this trace."""
    start_hits, start_misses = cache.hits, cache.misses
    for addr in addresses:
        cache.access(addr)
    return cache.hits - start_hits, cache.misses - start_misses


def stride_c_source():
    """C source for: long walk(const int *a, long mask, long stride, long iters)."""
    return """
long walk(const int *a, long mask, long stride, long iters) {
    long sum = 0, idx = 0;
    for (long k = 0; k < iters; k++) {
        sum += a[idx];
        idx = (idx + stride) & mask;
    }
    return sum;
}
"""


if __name__ == "__main__":
    for order in ("row", "col"):
        cache = Cache(size=256, block_size=16, ways=1)
        hits, misses = run_trace(cache, matrix_addresses(16, 16, order))
        print(f"16x16 ints, {order}-major walk, 256 B direct-mapped cache: {hits} hits, {misses} misses")
    lib = cputools.compile_c(stride_c_source(), opt="-O1")
    print("C walk compiled:", lib.walk is not None)
