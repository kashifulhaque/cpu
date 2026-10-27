"""Checks for the caches exercise."""

import array
import ctypes
import random

import cputools
from cpucheck import almost, check, equal, fail, has, timed


def _raises(exc, fn, *args):
    try:
        got = fn(*args)
    except exc:
        return
    fail(f"expected {exc.__name__}, but {fn.__name__}{args!r} returned {got!r}")


@check("amat: hit time plus miss rate times miss penalty")
def test_amat(sub):
    amat = has(sub, "amat")
    almost(amat(1, 0.05, 100), 6.0, 1e-9, label="amat(1, 0.05, 100)")   # 1 + 0.05 * 100
    almost(amat(4, 0.0, 200), 4.0, 1e-9, label="no misses")
    almost(amat(4, 1.0, 200), 204.0, 1e-9, label="all misses")


@check("split_address cuts an address into tag, index, and offset")
def test_split(sub):
    split_address = has(sub, "split_address")
    # 0x1234 = 4660. Block size 16: block 291, offset 4. 4 sets: index 291 % 4 = 3, tag 291 // 4 = 72.
    equal(split_address(0x1234, 16, 4), (72, 3, 4), label="split_address(0x1234, 16, 4)")
    equal(split_address(0, 16, 4), (0, 0, 0), label="address 0")
    # 64-byte blocks, 64 sets (a 4 KiB direct-mapped cache): 0x12345 -> block 0x48D, offset 5.
    # 0x48D = 1165: index 1165 % 64 = 13, tag 1165 // 64 = 18.
    equal(split_address(0x12345, 64, 64), (18, 13, 5), label="split_address(0x12345, 64, 64)")
    # One set (fully associative): the index is always 0 and the tag is the whole block number.
    equal(split_address(0x1234, 16, 1), (291, 0, 4), label="one set")
    for addr in (0, 15, 16, 4095, 123456):
        tag, index, offset = split_address(addr, 32, 8)
        equal((tag * 8 + index) * 32 + offset, addr, label=f"fields rebuild {addr}")


@check("Cache: geometry, hits within a block, misses across blocks")
def test_cache_basic(sub):
    Cache = has(sub, "Cache")
    cache = Cache(size=64, block_size=16, ways=1)
    equal(cache.num_sets, 4, label="num_sets of a 64 B, 16 B-block, direct-mapped cache")
    equal(Cache(size=128, block_size=16, ways=2).num_sets, 4, label="num_sets with 2 ways")
    equal(Cache(size=64, block_size=16, ways=4).num_sets, 1, label="num_sets, fully associative")
    # 0 misses and loads block 0; 4, 8, 12 are in the same 16-byte block and hit.
    got = [cache.access(a) for a in (0, 4, 8, 12, 16, 0)]
    equal(got, [False, True, True, True, False, True], label="hit/miss sequence")
    equal((cache.hits, cache.misses), (4, 2), label="(hits, misses)")
    almost(cache.hit_rate, 4 / 6, 1e-9, label="hit_rate")
    almost(Cache(64, 16, 1).hit_rate, 0.0, 1e-9, label="hit_rate before any access")


@check("Cache: a direct-mapped cache thrashes on conflicting addresses; two ways fix it")
def test_conflict(sub):
    Cache = has(sub, "Cache")
    # Addresses 0 and 64 both have index 0 in a 64 B direct-mapped cache (4 sets of 16 B).
    direct = Cache(size=64, block_size=16, ways=1)
    equal([direct.access(a) for a in (0, 64, 0, 64)], [False] * 4, label="direct-mapped ping-pong")
    # Same addresses in a 128 B 2-way cache: 4 sets, still index 0, but two ways hold both blocks.
    two_way = Cache(size=128, block_size=16, ways=2)
    equal([two_way.access(a) for a in (0, 64, 0, 64)], [False, False, True, True], label="2-way")
    # A third block in the same set pushes one out.
    equal(two_way.access(128), False, label="third block in a 2-way set")


@check("Cache: LRU evicts the least recently used block")
def test_lru(sub):
    Cache = has(sub, "Cache")
    cache = Cache(size=32, block_size=16, ways=2)    # one set of two blocks
    A, B, C = 0, 16, 32
    got = [cache.access(x) for x in (A, B, A, C, B, A)]
    # A miss, B miss, A hit (A is now newest), C miss evicts B (oldest),
    # B miss evicts A (oldest: order was A, C), then A misses again, evicting C.
    equal(got, [False, False, True, False, False, False], label="LRU sequence")
    equal((cache.hits, cache.misses), (1, 5), label="(hits, misses)")
    # Without the hit on A, plain FIFO would evict A at the C access. Check that LRU keeps it:
    cache = Cache(size=32, block_size=16, ways=2)
    for x in (A, B, A, C):
        cache.access(x)
    equal(cache.access(A), True, label="A survives because it was used after B")
    equal(cache.access(B), False, label="B was evicted")


@check("Cache rejects impossible shapes with ValueError")
def test_bad_shape(sub):
    Cache = has(sub, "Cache")
    _raises(ValueError, Cache, 100, 16, 1)    # size is not a power of two
    _raises(ValueError, Cache, 64, 24, 1)     # block size is not a power of two
    _raises(ValueError, Cache, 64, 16, 3)     # ways is not a power of two
    _raises(ValueError, Cache, 16, 16, 2)     # not even one full set
    _raises(ValueError, Cache, 64, 0, 1)


@check("matrix_addresses lists addresses in row-major and column-major order")
def test_matrix_addresses(sub):
    matrix_addresses = has(sub, "matrix_addresses")
    equal(matrix_addresses(2, 2, "row"), [0, 4, 8, 12], label="2x2 row")
    equal(matrix_addresses(2, 2, "col"), [0, 8, 4, 12], label="2x2 col")
    # 2 rows, 3 cols, 4-byte elements: (r, c) at (r * 3 + c) * 4.
    equal(matrix_addresses(2, 3, "row"), [0, 4, 8, 12, 16, 20], label="2x3 row")
    equal(matrix_addresses(2, 3, "col"), [0, 12, 4, 16, 8, 20], label="2x3 col")
    equal(matrix_addresses(1, 2, "row", elem_size=8, base=1000), [1000, 1008], label="elem_size and base")
    _raises(ValueError, matrix_addresses, 2, 2, "diagonal")


@check("a row-major walk uses each block fully; a column-major walk can miss every time")
def test_walks(sub):
    Cache, matrix_addresses, run_trace = has(sub, "Cache"), has(sub, "matrix_addresses"), has(sub, "run_trace")
    # 16 x 16 ints = 1024 bytes, 64 bytes per row. Cache: 256 B, 16 B blocks (4 ints each).
    # Row walk: 1 miss then 3 hits per block: 256 / 4 = 64 misses, 192 hits.
    for ways in (1, 4):
        cache = Cache(size=256, block_size=16, ways=ways)
        equal(run_trace(cache, matrix_addresses(16, 16, "row")), (192, 64), label=f"row walk, {ways}-way")
    # Column walk: consecutive accesses are 64 bytes apart, so one column touches 16 different
    # blocks and the 16-block cache cannot keep a column long enough to reuse it: all 256 miss.
    for ways in (1, 2, 4):
        cache = Cache(size=256, block_size=16, ways=ways)
        equal(run_trace(cache, matrix_addresses(16, 16, "col")), (0, 256), label=f"column walk, {ways}-way")
    # A fully associative 256 B cache (16 ways, one set) holds all 16 blocks of a column.
    cache = Cache(size=256, block_size=16, ways=16)
    equal(run_trace(cache, matrix_addresses(16, 16, "col")), (192, 64), label="column walk, fully associative")
    # With a 1 KiB cache the whole matrix fits, so the column walk finds the other three ints of each block.
    cache = Cache(size=1024, block_size=16, ways=4)
    equal(run_trace(cache, matrix_addresses(16, 16, "col")), (192, 64), label="column walk, cache holds the matrix")
    # run_trace reports this trace only, not the totals.
    cache = Cache(size=256, block_size=16, ways=1)
    run_trace(cache, [0, 4])
    equal(run_trace(cache, [8, 16]), (1, 1), label="second run_trace counts only its own accesses")


@check("the C stride loop returns the right sums (timings are reported, not judged)")
def test_c_stride(sub):
    stride_c_source = has(sub, "stride_c_source")
    lib = cputools.compile_c(stride_c_source(), opt="-O1")
    lib.walk.restype = ctypes.c_long
    lib.walk.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_long, ctypes.c_long]

    def reference(values, stride, iters):
        mask, idx, total = len(values) - 1, 0, 0
        for _ in range(iters):
            total += values[idx]
            idx = (idx + stride) & mask
        return total

    rng = random.Random(0)
    small = array.array("i", [rng.randrange(-1000, 1000) for _ in range(1024)])
    ptr = small.buffer_info()[0]
    for stride, iters in [(1, 1024), (1, 5000), (16, 1000), (7, 3000), (1023, 2048), (0, 10)]:
        got = lib.walk(ptr, 1023, stride, iters)
        equal(got, reference(small, stride, iters), label=f"walk(stride={stride}, iters={iters})")
    equal(lib.walk(ptr, 1023, 1, 0), 0, label="zero iterations")

    # A 4 MiB array, far bigger than the L2 cache of most CPUs. The two timings are reported only.
    n = 1 << 20
    big = array.array("i", [i % 251 for i in range(n)])
    bptr = big.buffer_info()[0]
    iters = 1 << 21
    with timed("stride 1 (16 ints per cache line)"):
        a = lib.walk(bptr, n - 1, 1, iters)
    with timed("stride 16 (a new cache line each access)"):
        b = lib.walk(bptr, n - 1, 16, iters)
    equal(a, sum(i % 251 for i in range(iters % n)) + (iters // n) * sum(i % 251 for i in range(n)),
          label="stride-1 sum over 2 passes of the array")
    # Stride 16 visits indexes 0, 16, 32, ... and wraps after n / 16 = 65536 steps; 2**21 steps is 32 laps.
    equal(b, 32 * sum(i % 251 for i in range(0, n, 16)), label="stride-16 sum over 32 laps")
