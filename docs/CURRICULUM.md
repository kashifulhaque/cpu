# Curriculum

Low-level computing from zero. Twenty-five lessons in six parts take a reader
who has never studied how a computer works to the point where they can read and
write x86-64 assembly, explain what a CPU does with each instruction and why
some code is fast and some is slow, follow C source down to machine code, and
write, optimize, and generate LLVM IR.

Every exercise is a Python file. Parts 0 and 1 build models in Python: number
encodings, gates and adders, a toy CPU, an instruction encoder, a pipeline, a
cache, a branch predictor. From Part 2 on, the Python file holds real
x86-64 assembly, C, or LLVM IR as strings, and the checks hand that text to the
real toolchain (clang 19, `llc`, `opt`, `lli`) through the `cputools` module,
then call the result from Python with `ctypes` or run it. Python is the glue;
the reader writes the low-level code. Part 0 teaches the Python the course needs.

The column "Exercise" sketches what the reader builds. Exact function names are
chosen by the lesson author and must match between the lesson's
`## Build it step by step`, the starter, and the checks.

## Part 0 — Getting started

| # | Slug | Title | Exercise |
|---|---|---|---|
| 01 | `01-python-you-need` | The Python you need for this course | Small functions over ints, strings, lists, dicts, and `bytes`; triple-quoted strings and f-strings (because later exercises hold assembly in strings); `int(s, 16)`, `hex`, `bin`; a tiny class. Gentle, many early passes. |
| 02 | `02-bits-and-binary` | Bits, binary, and hexadecimal | Convert between decimal, binary, and hex by hand-written loops (not `bin`/`int`); bit masks, shifts, `get_bits(x, lo, hi)`, `set_bit`, `popcount`; little-endian vs big-endian byte packing into `bytes`. |
| 03 | `03-integers-and-overflow` | Integers, two's complement, and overflow | Wrap a Python int to an N-bit unsigned and signed value; two's complement negate; detect signed and unsigned overflow of an add; sign and zero extension; compare with what real C returns via `cputools.compile_c`. |
| 04 | `04-logic-gates-and-adders` | Logic gates and adders | Build NOT/AND/OR/XOR from NAND; a half adder, full adder, and N-bit ripple-carry adder over lists of bits; a tiny ALU with add, sub (via two's complement), and, or, and the zero/negative/carry/overflow flags. |

## Part 1 — How a CPU works

| # | Slug | Title | Exercise |
|---|---|---|---|
| 05 | `05-a-toy-cpu` | A toy CPU: fetch, decode, execute | An emulator for a small register machine: registers, memory as a list, program counter, flags; `LOAD`, `STORE`, `ADD`, `SUB`, `JMP`, `JZ`, `HALT`; run programs that sum a list and compute a factorial. |
| 06 | `06-instruction-encoding` | Instruction encoding: from text to bits | An assembler and disassembler for a subset of RISC-V RV32I (`add`, `addi`, `sub`, `lw`, `sw`, `beq`, `jal`): R/I/S/B/J formats, immediates split across fields, sign extension; round-trip checks against known encodings. |
| 07 | `07-memory-and-the-stack` | Memory, the stack, and endianness | A byte-addressed memory with `load`/`store` of 1/2/4/8-byte little-endian values; alignment checks; a stack pointer that grows down with `push`/`pop`; `call`/`ret` saving a return address; trace a recursive call. |
| 08 | `08-pipelining` | Pipelining and hazards | A five-stage pipeline timing model (IF, ID, EX, MEM, WB): count cycles for an instruction list, detect RAW data hazards, insert stalls, then add forwarding and the load-use bubble; compute CPI. |
| 09 | `09-caches` | Caches and the memory hierarchy | A set-associative cache simulator: split address into tag/index/offset, LRU replacement, hit/miss counts; compare row-major vs column-major matrix walks; then time a real C loop with strides through `cputools.compile_c`. |
| 10 | `10-branch-prediction-and-out-of-order` | Branch prediction and out-of-order execution | Static, 1-bit, and 2-bit saturating-counter predictors and a gshare predictor over branch traces; accuracy on loop and random patterns; a short reading on out-of-order execution and speculation with a dependency-chain latency model. |

## Part 2 — x86-64 assembly

| # | Slug | Title | Exercise |
|---|---|---|---|
| 11 | `11-first-assembly` | Your first x86-64 assembly | Write Intel-syntax functions as strings, assembled by `cputools.assemble` and called with `ctypes`: return a constant, add two arguments, `lea` for `a*4+b`, 64-bit vs 32-bit registers, `imul`, shifts. |
| 12 | `12-flags-and-control-flow` | Flags, comparisons, and control flow | Assembly with `cmp`, `test`, conditional jumps and `cmovcc`/`setcc`: `max`, `abs`, `clamp`, a loop that sums 1..n, a loop that counts set bits; signed vs unsigned conditions (`jl` vs `jb`). |
| 13 | `13-memory-and-arrays-in-assembly` | Memory, pointers, and arrays in assembly | Addressing modes `[base + index*scale + disp]`: sum an `int64` array, find the max, reverse in place, `strlen` on a C string, copy bytes; arrays passed from Python through `ctypes`. |
| 14 | `14-functions-and-the-calling-convention` | Functions, the stack, and the System V calling convention | Prologue/epilogue, callee-saved registers, stack alignment; a recursive `fib` and `factorial` in assembly; a function that calls a C function passed as a pointer (a callback); reading a stack frame. |

## Part 3 — From C to machine code

| # | Slug | Title | Exercise |
|---|---|---|---|
| 15 | `15-c-for-the-curious` | C for the curious: types, pointers, and memory | Write small C functions as strings compiled with `cputools.compile_c`: pointer arithmetic, structs and their layout (`sizeof`, `offsetof`, padding computed in Python and checked against C), arrays vs pointers, undefined behaviour examples explained. |
| 16 | `16-how-a-compiler-sees-c` | How a compiler turns C into assembly | Read `cputools.c_to_asm` output at `-O0` and `-O2`; write predicates over the assembly text (does `-O2` keep the loop? use `lea` for multiply-by-5?); hand-write assembly that matches a given C function and passes the same tests. |
| 17 | `17-object-files-linking-and-loading` | Object files, linking, and loading | Parse an ELF64 header and section headers from `cputools.assemble_object` bytes with `struct`; list symbols from `.symtab`; resolve relocations in a toy linker that patches call targets between two "object files". |

## Part 4 — Compilers and LLVM IR

| # | Slug | Title | Exercise |
|---|---|---|---|
| 18 | `18-what-a-compiler-is` | What a compiler is: lexing and parsing | A lexer and recursive-descent parser for a tiny expression language (integers, `+ - * /`, parentheses, `let`), producing an AST; an interpreter over the AST; precedence and associativity. |
| 19 | `19-llvm-ir-basics` | LLVM IR: the language in the middle | Hand-write IR modules as strings: functions with `add`/`mul`/`sdiv`, integer types `i1`..`i64`, `icmp`, `zext`/`sext`/`trunc`; verify with `cputools.verify_ir`, run with `cputools.run_ir`, call through `cputools.ir_to_lib`. |
| 20 | `20-control-flow-and-ssa` | Control flow, basic blocks, and SSA | IR with `br`, labels, and `phi`: `max`, `abs`, a loop computing sum 1..n, factorial, `gcd`; build a control-flow graph from IR text in Python (blocks, successors, predecessors) and check that every phi matches its predecessors. |
| 21 | `21-memory-in-ir` | Memory in IR: alloca, load, store, and mem2reg | IR with `alloca`/`load`/`store` and `getelementptr` over arrays and structs; take clang's `-O0` IR, run `mem2reg` through `cputools.run_opt`, and count what disappeared; write a function that sums an array passed from Python. |
| 22 | `22-optimization-passes` | Optimization passes | Implement constant folding, algebraic simplification (`x*1`, `x+0`, `x*2 → x<<1`), and dead-code elimination over a small three-address IR in Python; then compare with LLVM's `instcombine`, `dce`, `gvn`, and `default<O2>` output on the same functions. |
| 23 | `23-generating-llvm-ir` | Generating LLVM IR from your own language | Extend the lesson-18 parser with comparisons, `if`, and `while`; a code generator that emits LLVM IR text (allocas for variables, basic blocks for control flow); compile programs with `cputools.run_ir` and check results. |

## Part 5 — The back end and performance

| # | Slug | Title | Exercise |
|---|---|---|---|
| 24 | `24-instruction-selection-and-register-allocation` | Instruction selection and register allocation | Liveness analysis over a straight-line and a looping three-address program; build an interference graph; graph-colouring allocation with K registers and spilling; emit x86-64 for a tiny IR and run it with `cputools.assemble`. |
| 25 | `25-performance-and-simd` | Performance, vectorization, and SIMD | Measure real C loops compiled at `-O0`, `-O2`, and `-O3 -march=native` through `cputools`; detect vectorized instructions (`vpaddd`, `xmm`/`ymm`) in `c_to_asm` output; write an SSE2 assembly loop that adds four `int32` at a time and beats the scalar version on a large array. |
