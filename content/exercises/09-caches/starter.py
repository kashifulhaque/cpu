"""Caches and the memory hierarchy.

Fill in every function and method that raises NotImplementedError.
"""

import cputools


def amat(hit_time, miss_rate, miss_penalty):
    """Average memory access time: hit_time + miss_rate * miss_penalty.

    amat(1, 0.05, 100) == 6.0
    """
    raise NotImplementedError


def split_address(addr, block_size, num_sets):
    """Split an address into (tag, index, offset).

    The offset picks a byte inside the block, the index picks the set, the tag
    is what is left. With block_size=16 and num_sets=4,
    split_address(0x1234, 16, 4) == (72, 3, 4)   # 0x1234 = block 291, offset 4
    """
    raise NotImplementedError


class Cache:
    """A set-associative cache with LRU replacement. It tracks tags, not data.

    Cache(size=64, block_size=16, ways=1) is direct-mapped with 4 sets.
    Public attributes: num_sets, hits, misses.
    Raise ValueError unless size, block_size, and ways are powers of two and the
    cache holds at least one full set (size >= block_size * ways).
    """

    def __init__(self, size, block_size, ways):
        raise NotImplementedError

    def access(self, addr):
        """Look up `addr`. Return True on a hit. On a miss, load its block
        (evicting the set's least recently used block if the set is full),
        count the miss, and return False. A hit makes the block most recently used.
        """
        raise NotImplementedError

    @property
    def hit_rate(self):
        """hits / (hits + misses), or 0.0 before any access."""
        raise NotImplementedError


def matrix_addresses(rows, cols, order="row", elem_size=4, base=0):
    """Addresses touched when walking a rows x cols array stored row by row.

    Element (r, c) lives at base + (r * cols + c) * elem_size.
    order="row" visits (0,0), (0,1), ..., order="col" visits (0,0), (1,0), ...
    matrix_addresses(2, 2, "row") == [0, 4, 8, 12]
    matrix_addresses(2, 2, "col") == [0, 8, 4, 12]
    Raise ValueError for any other order.
    """
    raise NotImplementedError


def run_trace(cache, addresses):
    """Feed every address to `cache` and return (hits, misses) for this trace only."""
    raise NotImplementedError


def stride_c_source():
    """Return C source that defines

        long walk(const int *a, long mask, long stride, long iters)

    It starts with idx = 0 and sum = 0. Each of `iters` iterations adds a[idx] to
    sum and then sets idx = (idx + stride) & mask. It returns sum.
    """
    raise NotImplementedError


if __name__ == "__main__":
    for order in ("row", "col"):
        cache = Cache(size=256, block_size=16, ways=1)
        hits, misses = run_trace(cache, matrix_addresses(16, 16, order))
        print(f"16x16 ints, {order}-major walk, 256 B direct-mapped cache: {hits} hits, {misses} misses")
    lib = cputools.compile_c(stride_c_source(), opt="-O1")
    print("C walk compiled:", lib.walk is not None)
