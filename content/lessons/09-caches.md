---
title: Caches and the memory hierarchy
slug: 09-caches
part: "Part 1 — How a CPU works"
summary: Simulate a set-associative cache with LRU, see why walking a matrix by rows beats columns, and measure strides in real C.
minutes: 60
gpu: false
objectives:
  - Split an address into tag, index, and offset for a given cache shape.
  - Simulate a direct-mapped and a set-associative cache with LRU replacement and count hits and misses.
  - Explain spatial and temporal locality, and why a row-major walk beats a column-major walk.
  - Compute average memory access time and read a real machine's cache sizes.
prereqs:
  - 07-memory-and-the-stack
  - 08-pipelining
exercise: 09-caches
---

# Caches and the memory hierarchy

A modern CPU can finish several instructions per cycle. Main memory, the DRAM chips on the motherboard, takes roughly 60 to 100 nanoseconds to answer a read. At 3 GHz that is 200 to 300 cycles, during which the CPU could have run hundreds of instructions. If every load went to main memory, the processor would spend almost all of its time waiting.

The fix is a **cache**: a small, fast memory placed between the CPU and main memory that holds copies of recently used data. Think of a desk and a filing cabinet. The cabinet holds everything but takes a walk to reach. The desk drawer holds a few folders within arm's reach. If the folder you need is in the drawer, you save the walk.

This lesson builds a cache simulator and shows why the order in which a program touches its data can change its speed several times over, with no change to what it computes.

## What you already know

- Memory is a row of bytes, each with an address (lesson 07).
- A shift and a mask split a number into fields (lesson 02), and `//` and `%` do the same for non-powers of two.
- A load that must wait for memory stalls the pipeline (lesson 08).
- A **cycle** is one tick of the CPU clock.
- An array of `int` values sits in consecutive 4-byte slots, so element `i` is at `base + 4 * i`.

## Locality: why a cache works

A cache works because programs are predictable. Two habits show up almost everywhere:

- **Temporal locality**: data used recently is likely to be used again soon. A loop counter and the variables in a loop body are touched every iteration.
- **Spatial locality**: data near recently used data is likely to be used soon. After reading `a[0]`, a program usually reads `a[1]`.

A cache exploits both. It keeps what you used recently (temporal). And when it fetches data, it fetches a whole neighbourhood, called a **block** or **cache line**, not one byte (spatial). On x86-64 a line is 64 bytes. Reading one `int` pulls in the 16 `int` values around it.

When the CPU asks for an address and the cache has it, that is a **hit**. When the cache does not have it, that is a **miss**: the line is fetched from the next level down, which takes longer, and it replaces something else.

> [!KEY]
> A cache holds copies of recent blocks. Reusing data (temporal locality) and touching neighbouring data (spatial locality) both produce hits.

## The hierarchy

No single memory is large, fast, and cheap. Computers use several, each larger and slower than the one above:

| Level | Typical size | Typical latency |
|---|---|---|
| Registers | a few hundred bytes | 0 cycles of delay |
| L1 cache (one per core) | 32 to 48 KiB | 4 to 5 cycles |
| L2 cache | 256 KiB to 2 MiB | roughly 12 to 15 cycles |
| L3 cache (shared) | several MiB to tens of MiB | roughly 40 cycles |
| Main memory (DRAM) | gigabytes | roughly 200 to 300 cycles |

The numbers vary by processor model. What holds across models is the shape: each step down is several times slower and much larger.

Average memory access time, **AMAT**, combines them. Every access pays the hit time, and a miss adds the miss penalty:

$$
\text{AMAT} = \text{hit time} + \text{miss rate} \times \text{miss penalty}
$$

With a 4-cycle hit time, a 5% miss rate, and a 200-cycle penalty, AMAT is `4 + 0.05 * 200 = 14` cycles. A 5% miss rate more than triples the average cost. Small changes in the miss rate matter a lot.

## Finding a block: tag, index, offset

A cache stores blocks, so it names them by address. It splits each address into three fields.

- The **offset** says which byte inside the block. A 16-byte block needs 4 bits.
- The **index** picks which **set** of the cache to look in.
- The **tag** is the remaining high bits. It identifies which block of memory occupies a slot.

The index limits where a block can live. Without it, the cache would have to search every slot. Take a tiny cache with 16-byte blocks and 4 sets. The address `0x1234` is:

```text
0x1234 = 0001 0010 0011 0100
                         ^^^^   offset = 0100 = 4     (4 bits: 16-byte blocks)
                       ^^       index  = 11   = 3     (2 bits: 4 sets)
         ^^^^^^^^^^^^           tag    = 1001000 = 72 (the rest)
```

With `//` and `%` the same split is:

```python
block  = addr // block_size        # 4660 // 16 = 291
offset = addr %  block_size        # 4
index  = block % num_sets          # 291 % 4  = 3
tag    = block // num_sets         # 291 // 4 = 72
```

The cache stores the tag alongside the data. A lookup reads the set the index selects and compares the stored tags with the address's tag. A match is a hit.

## Associativity

How many slots does a set have? The number of **ways**.

- **Direct-mapped**: 1 way. Each block has exactly one possible slot. Fast and simple.
- **N-way set associative**: N ways per set. A block can sit in any of N slots of its set.
- **Fully associative**: one set holding every block. A block can go anywhere. Flexible and expensive.

A cache of `size` bytes with `block_size` and `ways` has:

```text
num_sets = size // (block_size * ways)
```

A 64-byte cache with 16-byte blocks has 4 slots. Direct-mapped, that is 4 sets of 1. Two-way, it is 2 sets of 2 (and a 128-byte two-way cache has 4 sets). Four-way, it is one set of 4: fully associative.

More ways means fewer **conflicts**. Look at addresses 0 and 64 in a 64-byte direct-mapped cache with 16-byte blocks. Both have index 0, and tags 0 and 1. They want the same slot:

```text
access 0    miss   set 0 holds tag 0
access 64   miss   set 0 holds tag 1   (evicted tag 0)
access 0    miss   set 0 holds tag 0   (evicted tag 1)
access 64   miss   ...
```

Every access misses, though the cache has three empty slots in other sets. This is **thrashing**. Give the cache two ways (a 128-byte cache, still 4 sets) and both blocks sit in set 0: the trace is miss, miss, hit, hit.

## Replacement: LRU

When a set is full and a new block arrives, the cache must **evict** one. A popular policy is **LRU**, least recently used: evict the block untouched the longest. It bets on temporal locality.

An implementation keeps the tags of each set in order from least to most recently used. A hit moves the tag to the end. A miss removes the first tag when the set is full, then adds the new tag at the end.

Trace a set with 2 ways. The blocks `A`, `B`, `C` all map to this set:

```text
access   result   set (least recent -> most recent)
A        miss     [A]
B        miss     [A, B]
A        hit      [B, A]        A moves to the end
C        miss     [A, C]        set full: B, the least recent, is evicted
B        miss     [C, B]        A is evicted
A        miss     [B, A]        C is evicted
```

One hit in six accesses. A first-in, first-out policy would have evicted `A` at the access of `C`, though `A` had just been used.

> [!KEY]
> Direct-mapped caches suffer from conflicts, and associativity fixes them by giving each block several possible slots. LRU decides which slot to free.

### Three kinds of miss

- A **compulsory** miss is the first access to a block. No cache avoids it.
- A **capacity** miss happens because the data in use is bigger than the cache.
- A **conflict** miss happens because too many blocks map to one set, though other sets have room.

## Walking a matrix

Here is where order matters. A 2D array in C is stored **row-major**: row 0, then row 1, and so on. Element `(r, c)` of a matrix with `cols` columns and 4-byte elements is at address `base + (r * cols + c) * 4`.

Two loops visit the same 16 x 16 matrix of `int` (1024 bytes, 64 bytes per row):

```c
for (r = 0; r < 16; r++) for (c = 0; c < 16; c++) sum += m[r][c];   /* row-major  */
for (c = 0; c < 16; c++) for (r = 0; r < 16; r++) sum += m[r][c];   /* column-major */
```

Use a 256-byte direct-mapped cache with 16-byte blocks: 16 sets, and 4 `int` values per block.

The row walk goes 0, 4, 8, 12, 16, ... Each block holds four consecutive elements. The first is a miss, and the other three are hits. Over 256 accesses that is 64 misses and 192 hits, a **75% hit rate**.

The column walk goes 0, 64, 128, ... each access 64 bytes from the previous one, always a different block. A column touches 16 blocks. The cache has 16 sets, but those blocks fall into only four of them (indices 0, 4, 8, and 12, plus a column offset), four blocks per set. A direct-mapped set holds one. Each block is evicted before the next column returns to it, so the result is **0 hits and 256 misses**.

Two or four ways do not rescue the walk, because the 64-byte stride still crowds one column's 16 blocks into one to four sets, and those sets hold only two to four blocks each. These are **conflict** misses. A fully associative 256-byte cache (16 ways, one set) holds all 16 blocks of a column, so the other three `int` values in each block are still there when the next column arrives: 192 hits. A 1 KiB cache has room for the whole matrix and gets the same result.

| Walk | 256 B, 1 to 8 ways | 256 B, 16 ways (fully associative) | 1 KiB, 4 ways |
|---|---|---|---|
| Row-major | 192 hits, 64 misses | 192 hits, 64 misses | 192 hits, 64 misses |
| Column-major | 0 hits, 256 misses | 192 hits, 64 misses | 192 hits, 64 misses |

Real matrices are bigger than any cache, so the column walk loses on real hardware too.

## Connect to the real machine

On Linux, ask your machine for its caches:

- `lscpu` prints the L1, L2, and L3 sizes.
- `getconf LEVEL1_DCACHE_LINESIZE` prints the line size, 64 on x86-64.
- `/sys/devices/system/cpu/cpu0/cache/index0/` holds the level, size, line size, and number of ways of each cache.

A real L1 data cache is commonly 32 KiB, 8-way, with 64-byte lines: `32768 / (64 * 8) = 64` sets. The index is 6 bits and the offset 6 bits, so the tag and index come from the same address split you wrote.

The exercise's C part measures stride. It adds up an array in steps of `stride` ints, wrapping at the end:

```c
long walk(const int *a, long mask, long stride, long iters) {
    long sum = 0, idx = 0;
    for (long k = 0; k < iters; k++) {
        sum += a[idx];
        idx = (idx + stride) & mask;
    }
    return sum;
}
```

With stride 1 the loop uses all 16 `int` values of each line before moving on. With stride 16, each access lands in a new 64-byte line, so every access is a new block. On the course runner, a 4 MiB array and about 2 million iterations took a few milliseconds at stride 1 and about two to three times that at stride 16. The ratio is smaller than a pure miss count predicts, because hardware **prefetchers** notice a constant stride and fetch lines before the loop asks for them.

> [!WARNING]
> Timing depends on the processor, other programs, and the machine's power state. The checks in this exercise verify that the C loop computes the right sum, and they report the timings. They never pass or fail on speed.

## Try it on your own machine

1. Read your cache sizes (Linux):

   ```bash
   lscpu | grep -i cache
   getconf LEVEL1_DCACHE_LINESIZE
   ```

   Expect a 64-byte line and an L1 data cache of 32 or 48 KiB per core.

2. See how the cache is organised (Linux):

   ```bash
   cat /sys/devices/system/cpu/cpu0/cache/index0/{level,type,size,ways_of_associativity,coherency_line_size}
   ```

   Compute `size / (line size * ways)` and compare to `number_of_sets`.

3. Time a stride loop of your own: add a `main` to `walk` that allocates `1 << 24` ints, fills them, and calls `walk` with strides 1, 2, 4, 8, 16, 32 and equal iteration counts. Build with `clang -O2` and time each call with `clock_gettime`. Expect the time per access to climb until the stride reaches 16 ints (64 bytes), then level off.

4. Count cache misses for a program (Linux, needs the `perf` package):

   ```bash
   perf stat -e cache-references,cache-misses ./a.out
   ```

   Some virtual machines hide these counters. If you see `<not supported>`, skip this step.

> [!RECAP]
> - A cache holds recent blocks. An address splits into offset (byte in block), index (which set), and tag (which block).
> - More ways per set cut conflict misses, and LRU evicts the block unused the longest.
> - AMAT is hit time plus miss rate times miss penalty, so small miss rates matter.
> - Row-major walks use every byte of a fetched block, and column-major walks can use one.

## Build it step by step

Open `starter.py`. You write seven pieces, in this order.

1. `amat(hit_time, miss_rate, miss_penalty)` returns `hit_time + miss_rate * miss_penalty`.

2. `split_address(addr, block_size, num_sets)` returns `(tag, index, offset)`. Use `//` and `%`. The common mistake is to divide by `num_sets` before dividing by `block_size`. Find the block number first.

3. `Cache(size, block_size, ways)` stores `num_sets` and one list of tags per set. Raise `ValueError` unless all three arguments are powers of two and the cache holds at least one full set. `n & (n - 1) == 0` tests for a power of two.

4. `Cache.access(addr)` returns `True` on a hit and `False` on a miss, and updates `hits` and `misses`. Move a hit tag to the end of its set's list. On a miss, remove the first tag when the set is full, then append the new one. The common mistake is to forget to refresh the order on a hit, which makes the policy FIFO instead of LRU.

5. `Cache.hit_rate` is a property: hits over total accesses, `0.0` when there are none.

6. `matrix_addresses(rows, cols, order, elem_size, base)` returns the address list for a `"row"` or `"col"` walk of a row-major array. Both orders use the same address formula and differ only in the loop nesting. Raise `ValueError` for any other order.

7. `run_trace(cache, addresses)` feeds the addresses to the cache and returns `(hits, misses)` for this trace only. Subtract the counts from before the call.

Last, `stride_c_source()` returns the C text of `walk`, with the signature shown above. Python compiles it with `cputools.compile_c`. ctypes needs `restype` and `argtypes` set for `long` results and pointer arguments, and the checks do this for you.

## Where this breaks

- **The simulator tracks tags, not data.** It ignores writes. Real caches must handle a store: **write-back** caches mark a line dirty and write it later, and **write-allocate** caches load a line on a store miss.
- **Real replacement is approximate.** True LRU is costly for 8 or 16 ways, so hardware uses pseudo-LRU.
- **Prefetchers change the picture.** A real CPU watches the address stream and fetches ahead. Sequential and constant-stride walks hide much of the latency. Random access (a linked list, a hash table) defeats it.
- **Several levels and several cores.** Real machines chain L1, L2, and L3, and keep the private caches of different cores **coherent**. Two cores writing different variables on the same line fight over it, called **false sharing**.
- **Virtual memory interferes.** Addresses are translated first, using a small cache called the TLB. A strided walk across many pages can miss in the TLB as well as in the data cache.
- **Power-of-two strides are a trap.** A matrix whose row length is a power of two maps a column to few sets, so real hardware gets conflict misses, as in the exercise's column walk.

## Further reading

- [Ulrich Drepper, "What Every Programmer Should Know About Memory"](https://people.freebsd.org/~lstewart/articles/cpumemory.pdf) is the long, detailed reference on caches, DRAM, and the performance of real code.
- [Igor Ostrovsky, "Gallery of Processor Cache Effects"](http://igoro.com/archive/gallery-of-processor-cache-effects/) shows seven small C# experiments, including strides and cache line size.
- [CPU cache](https://en.wikipedia.org/wiki/CPU_cache) on Wikipedia covers associativity, replacement, write policies, and the real hierarchy.
- [Computer Systems: A Programmer's Perspective](https://csapp.cs.cmu.edu/), chapter 6, builds the "memory mountain" from stride and working-set measurements.

## The exercise

You build a cache simulator and use it to explain a performance gap. `split_address` cuts an address into tag, index, and offset. `Cache` is a set-associative cache with LRU replacement that counts hits and misses, and `amat` turns a miss rate into an average access time. `matrix_addresses` and `run_trace` run row-major and column-major walks through your cache. `stride_c_source` returns a C loop that Python compiles and runs.

The checks use the hand-worked numbers in this lesson: the `0x1234` split, the 0/64 conflict that a second way fixes, the six-access LRU trace, and the 16 x 16 walks (192 hits and 64 misses by row, none by column in a 256-byte cache). They check that the C loop returns the right sums for several strides, and they report its timing without judging it.
