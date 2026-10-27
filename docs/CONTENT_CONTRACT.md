# Content contract

Every lesson in this course is two things on disk: one Markdown file that the
reader reads, and one exercise directory that the reader's code is checked
against. This document is the exact contract both must satisfy. The loader in
`backend/app/curriculum.py` and the harness in `backend/app/runner/harness.py`
depend on it. The lesson list is in `docs/CURRICULUM.md`.

## Audience

Readers have no background in computer architecture, assembly, C, or
compilers. They may have written a little code in some language, but assume
nothing beyond what Part 0 teaches: Python functions, lists, dicts, classes,
`bytes`, strings, and the idea of a loop. They have never heard of a register,
a carry flag, a cache line, a calling convention, or SSA. They learn by
building. Write for them:

- Start with the intuition in plain words. Before any detail, say what the
  mechanism does and why it exists, in one or two sentences a first-year
  student could repeat to a friend. Use an everyday analogy when one fits: an
  assembly line for a pipeline, a desk drawer beside a filing cabinet for a
  cache, a recipe card for an instruction.
- Define every term the first time it appears, including ones that feel basic,
  such as "bit", "register", "instruction", "address", "compiler", "function
  call", or "basic block". Prefer an ordinary word to jargon when both mean the
  same thing, and when you must use jargon, say it in plain words first.
- Show, then tell. Each concept gets a small concrete example worked by hand
  with real numbers: 13 in binary bit by bit, `-5` as an 8-bit two's
  complement value, an `addi` instruction split into its fields, a four-line
  loop traced through the pipeline cycle by cycle, the exact IR clang emits for
  a three-line C function. Show every intermediate value, so the reader can
  check their code against it.
- Draw pictures in text. Use fenced `text` blocks for ASCII diagrams of
  registers, memory and stack layouts, instruction fields, pipeline timelines,
  cache sets, and control-flow graphs. Every diagram is introduced by a
  sentence.
- Connect to the real machine. After a mechanism is clear, show where it lives
  on a real x86-64 Linux machine: a command to run (`clang -S -O2`,
  `objdump -d`, `llc`, `opt -passes=...`, `lscpu`, `perf stat`), a real
  instruction, or a real number (a 64-byte cache line, 16 general-purpose
  registers, a 4 to 5 cycle L1 hit). Readers should finish feeling they could
  poke at their own machine. Mark anything that needs a tool beyond clang and
  LLVM.
- Keep the conditions honest. When a claim depends on the processor model, the
  compiler version, or the optimization level, say which. The runner uses
  clang and LLVM 19 on x86-64 Linux; assembly in this course is x86-64 Intel
  syntax unless a lesson says otherwise. When real hardware does something the
  simple model does not, say so.
- Connect ideas to code. The reader should finish every section knowing which
  code they will write.

Every claim on the page must be correct. Simpler wording must never change
what a result says.

## Prose style

Follow the Google developer documentation style guide:

- Address the reader as "you". Use active voice and present tense.
- One idea per sentence. Short sentences and short paragraphs.
- Sentence case for every heading. Start task headings with a bare infinitive.
- Serial commas. Em dashes with no surrounding spaces.
- Code, filenames, commands, and identifiers in code font. No `simply`,
  `just`, `easily`, `obviously`, `note that`, `e.g.`, `i.e.`, `etc.`
- Don't write timelessly-rotting words: `currently`, `now`, `new`, `latest`,
  `recently`, `state of the art`.
- Introduce every list, table, and code block with a complete sentence.

## Lesson file

Path: `content/lessons/NN-slug.md`, where `NN` is the two-digit order prefix and
`slug` matches the `slug` field.

The file starts with YAML front matter:

```yaml
---
title: "Flags, comparisons, and control flow"
slug: 12-flags-and-control-flow
part: "Part 2 — x86-64 assembly"
summary: One sentence, under 140 characters, that says what the lesson delivers.
minutes: 55
gpu: false
objectives:
  - Say which flags `cmp` sets and how a conditional jump reads them.
  - Write a loop in x86-64 assembly with a counter, a compare, and a backward jump.
  - "Choose the right condition for the data: `jl` for signed values, `jb` for unsigned."
prereqs:
  - 11-first-assembly
exercise: 12-flags-and-control-flow
---
```

Every value that holds a colon must be wrapped in double quotes, or YAML reads
the item as a mapping rather than a string. `scripts/check_content.py` rejects
one. Every field is required except `prereqs`, which can be omitted. `gpu` is
always `false`. The `part` string must match `docs/CURRICULUM.md` exactly,
including the em dash. `minutes` is an honest reading and working estimate.

The body is Markdown with these conventions:

- One `#` heading, matching `title`, as the first line after the front matter.
- `##` for sections, `###` for subsections. Never skip a level.
- Math is rare in this course. When you need it, use KaTeX: `$inline$` and
  `$$display$$`, with each `$$` on its own line above and below the equation.
  A one-line `$$...$$` is rejected by `scripts/check_content.py`. Never put a
  literal dollar sign in prose; write "dollars" instead.
- Fenced code blocks tagged with a language (`python`, `text`, `bash`, `c`,
  `asm` for x86-64 assembly, `llvm` for LLVM IR). Blocks show the shape of an
  implementation, not a full solution to the exercise. Real assembly and IR are
  the point of Parts 2 to 5: show them, explain them line by line, and let the
  reader write them.
- Tables for genuinely two-dimensional data.
- Callouts, written as a blockquote whose first line is a type marker:

  ```markdown
  > [!KEY]
  > A register is a tiny, named storage slot inside the CPU, and every instruction reads or writes registers.
  ```

  | Marker | Label | Use it for |
  |---|---|---|
  | `[!KEY]` | Key idea | The one sentence to remember from a section. Two to four per lesson. |
  | `[!TIP]` | Tip | A practical shortcut or habit. At most two per lesson. |
  | `[!WARNING]` | Watch out | A trap the reader is about to fall into. At most two per lesson. |
  | `[!RECAP]` | Before you build | Three to five bullets, placed right before `## Build it step by step`. One per lesson. |

  `scripts/check_content.py` rejects any other marker, and a second recap.

Every lesson body includes, in this order:

1. An opening that says, in plain words, what problem the lesson solves and why
   it matters. Two or three short paragraphs. No heading.
2. `## What you already know` — a short list of the ideas the lesson builds on,
   each in one plain sentence. Keep it to five bullets. Lesson 01 says what
   the reader needs instead: a browser and curiosity.
3. The substance, in as many `##` sections as the material needs. Each section
   leads with intuition, then the mechanism, then a worked example with real
   numbers or a diagram.
4. `## Try it on your own machine` — two to five commands or tiny Python
   snippets the reader can run on a Linux or macOS terminal to see the idea on
   a real system, each with a sentence saying what to look for. Mark anything
   Linux-only.
5. `## Build it step by step` — a numbered walkthrough of the exercise, one
   step per function in the order the checks test them. Each step says what the
   function takes and returns, the Python it needs, and the mistake people most
   often make. It gives the shape of the code, never the full answer.
6. `## Where this breaks` — the ways the mechanism fails or costs too much in
   practice, and what real systems do about each one.
7. `## Further reading` — three to six references, each a Markdown link, with
   one sentence on what it adds. Prefer free sources: the relevant chapter of
   the LLVM documentation (https://llvm.org/docs/LangRef.html and the other
   pages on llvm.org/docs), Compiler Explorer (https://godbolt.org), Felix
   Cloutier's x86 reference (https://www.felixcloutier.com/x86/), the
   System V AMD64 ABI, Agner Fog's optimization manuals
   (https://www.agner.org/optimize/), *Computer Systems: A Programmer's
   Perspective* material, *Crafting Interpreters* (https://craftinginterpreters.com),
   the RISC-V specifications, and classic papers. Only link URLs you are confident exist.
8. `## The exercise` — one or two paragraphs that say what the reader builds
   and what the checks verify. Name the functions by their exact identifiers.

Aim for 1800 to 3000 words of body. Short sentences and short paragraphs
matter more than the word count.

## Exercise directory

Path: `content/exercises/<id>/`, where `<id>` matches the lesson's `exercise`
field (and equals the slug). It holds exactly four files.

### `meta.json`

```json
{
  "id": "12-flags-and-control-flow",
  "title": "Branch and loop in x86-64 assembly",
  "brief": "Write max, abs, and a summing loop in assembly, and see signed and unsigned comparisons disagree.",
  "needs_gpu": false,
  "timeout": 30,
  "packages": [],
  "hints": [
    "The first integer argument arrives in rdi (edi for 32 bits), the second in rsi, and the result goes in rax.",
    "`cmp a, b` computes a - b, throws the answer away, and keeps the flags. The jump after it reads those flags."
  ]
}
```

`needs_gpu` is always `false`. `packages` is documentation only; the runtime is
Python 3.12 with the standard library, plus clang 19 and the LLVM 19 tools,
reached through the `cputools` module (below). Exercises use the standard
library and `cputools` only. `timeout` is in seconds: 30 for most exercises, up to 60 for one
that compiles many programs or starts real processes. Give three to six hints, ordered from
gentlest to most specific.

### `starter.py`

What the reader sees when the lesson opens. It must:

- Import only from the Python standard library and `cputools`.
- Define every function and class the checks call, with the exact signature, a
  docstring that states the contract with a tiny example, and a body that
  raises `NotImplementedError`. Where the reader writes assembly, C, or IR,
  the starter defines a function that returns that text, such as
  `def max_asm() -> str:`, whose body raises `NotImplementedError` and whose
  docstring gives the exact symbol name, signature, and a tiny example. A
  function, not a module-level string, keeps the "not filled in yet" signal
  the same everywhere. Helper classes the reader is not asked to
  write (an exception type, a dataclass for a job, a provided `Disk`) are given
  in full, and repeated identically in `solution.py`.
- Carry a `if __name__ == "__main__":` block that builds a small example and
  prints something informative. The **Run** button executes this block, so it
  must work once the reader fills in the functions, and it must fail with a
  clear `NotImplementedError` before that.
- Never contain the answer, in a comment or anywhere else.

The **Run** button has the same time limit as the checks, so keep the
`__main__` block to a second or two of work.

### `solution.py`

A correct, idiomatic, well-commented reference implementation with the same
public surface as `starter.py`. It must pass every check in `tests.py`. Keep it
clean enough to read as the worked answer, because the reader can reveal it.

### `tests.py`

The checks. Import the helpers and register each check with `@check`:

```python
"""Checks for the flags and control flow exercise."""

import ctypes

import cputools
from cpucheck import check, equal, fail, has


def _lib(text_fn):
    # Calling the reader's function first means a starter shows "not implemented yet".
    return cputools.assemble(text_fn())


@check("max_asm returns the larger of two signed 32-bit ints")
def test_max(sub):
    lib = _lib(has(sub, "max_asm"))
    for a, b in [(3, 7), (7, 3), (-5, 2), (-1, -9), (0, 0)]:
        equal(lib.max2(a, b), max(a, b), label=f"max2({a}, {b})")


@check("sum_to_asm loops: sum_to(n) is 1 + 2 + ... + n, and 0 for n <= 0")
def test_sum(sub):
    lib = _lib(has(sub, "sum_to_asm"))
    lib.sum_to.restype = ctypes.c_int64
    for n, want in [(0, 0), (1, 1), (4, 10), (100, 5050), (-3, 0)]:  # n(n+1)/2
        equal(lib.sum_to(n), want, label=f"sum_to({n})")
```

The `cpucheck` module is on the import path at run time. Its API:

| Name | Signature | Behaviour |
|---|---|---|
| `check` | `@check("description")` | Registers a check. The description is what the reader sees. |
| `equal` | `equal(got, want, label=None)` | Exact equality with a readable message. Use it for ints, strings, lists, tuples, dicts. |
| `almost` | `almost(got, want, tol, label=None)` | Scalar float comparison within `tol`. |
| `close` | `close(got, want, rtol=1e-5, atol=1e-8, label=None)` | Elementwise float comparison for lists of floats. |
| `fail` | `fail("message")` | Fails the check with that message. |
| `has` | `has(sub, "name")` | Returns the reader's function or class, or fails naming what is missing. |
| `timed` | `with timed("label"):` | Records elapsed seconds, reported to the reader. |

Rules for checks:

- Each check receives `sub`, the reader's module, as its only argument.
- Seed every random number generator: `random.Random(0)`. A check that passes
  intermittently is a bug. Real threads and processes must be checked on
  outcomes that hold under every interleaving, never on timing.
- Write six to ten checks per exercise, ordered from the smallest piece to the
  whole. The first check must pass as soon as the reader gets one function
  right, so the pane shows progress early.
- Check behaviour, not implementation. Compare against hand-computed answers
  (put the arithmetic in a comment) and against independent properties.
- Never import `solution` from `tests.py`.
- The whole suite runs the reference solution in under 5 seconds.
- Failure messages must say what was expected and what arrived. The reader
  cannot see your code.
- Every check works in a fresh temporary working directory. Create files only
  under `tempfile.mkdtemp()` or the current directory, and clean up.

### The toolchain: `cputools`

`backend/app/runner/cputools.py` is on the import path at run time, for the
reader's code and for `tests.py`. It writes text to a scratch directory, runs one
real tool, and returns text or a loaded `ctypes` library. A tool that rejects
its input raises `cputools.ToolError`, whose message is the tool's own error
output (the line and column clang or opt complained about).

| Function | Returns | What it runs |
|---|---|---|
| `compile_c(src, opt="-O1", flags=())` | `ctypes.CDLL` | `clang -shared -fPIC` |
| `c_to_asm(src, opt="-O1", intel=True, flags=())` | assembly text | `clang -S -masm=intel` |
| `c_to_ir(src, opt="-O1", flags=())` | LLVM IR text | `clang -S -emit-llvm` (at `-O0`, without `optnone`) |
| `build_c(src, opt="-O1", flags=())` | path to an executable | `clang` |
| `assemble(src, intel=True)` | `ctypes.CDLL` | the assembler, as a shared library. Each callable function needs `.globl name` and `name:` |
| `assemble_object(src, intel=True)` | ELF object bytes | `clang -c` |
| `machine_code(src, intel=True)` | bytes of `.text` | `clang -c` then `llvm-objcopy` |
| `disassemble(path_or_bytes, intel=True)` | text | `llvm-objdump -d` |
| `verify_ir(ir)` | `None`, or raises | `opt -passes=verify` |
| `run_opt(ir, passes)` | IR text | `opt -S -passes=<passes>` |
| `ir_to_asm(ir, opt="-O2", intel=True)` | assembly text | `llc` |
| `ir_to_lib(ir, opt="-O1")` | `ctypes.CDLL` | `clang` on IR, as a shared library |
| `run_ir(ir, args=(), stdin=None)` | `Result(returncode, stdout, stderr)` | verifies, then `lli` on the module's `@main` |
| `run(argv, stdin=None)` | `Result` | any executable |
| `environment()`, `clang_version()` | info | |

`assemble` prepends `.intel_syntax noprefix` and `.text`, so reader assembly
is bare Intel syntax. ctypes treats arguments and results as C `int` unless
told otherwise; for 64-bit values, pointers, and arrays, set `argtypes` and
`restype` in the check (or in a helper the starter provides in full), and say
so in the lesson. Libraries load into the harness process, so:

- A crash in reader assembly (a segfault from a bad address or a broken
  stack) kills the whole check run. Wherever a mistake can crash, run that
  check in a child: `cputools.build_c` a small C driver and `cputools.run` it,
  or `os.fork` a child that calls the function, reports through a pipe, and
  ends with `os._exit`. A starter's `NotImplementedError` must still show as
  "not implemented yet", so call the reader's text-returning function in the
  parent and only run the compiled code in the child. A shared helper for
  this, `cputools_safe_call` style, may be written inside `tests.py`.
- Check behaviour on many inputs, including edge cases (zero, negative,
  `INT_MIN`, empty arrays, large values), against a Python reference.
- Where a lesson asks the reader to use a particular construct (a `phi`, a
  `cmov`, an SSE instruction, no `alloca` after `mem2reg`), a check may inspect
  the text the reader wrote, but say so in the check's description.
- Never make pass or fail depend on timing. Measure with `timed` and report;
  compare speeds only where the gap is ten times or more and the check would
  still pass on a slow, shared, two-core machine.
- Exact compiler output differs between versions. Checks over clang or opt
  output test robust properties (a loop is gone, a `call` remains, an
  instruction family appears), not exact text.

### Rules for real processes

When a check forks, the harness talks to the app through file descriptor 1 as
JSON lines. A forked child must end with `os._exit(code)` inside a
`try`/`finally`, write results to a pipe the parent reads, and be reaped with
`os.waitpid`. Guard every child with a timeout.

## Verifying your work

From the repository root, build the toolchain image once, then run the harness
inside it on the solution and on the starter:

```bash
docker build -t cpu-toolchain:local -f scripts/Dockerfile.toolchain scripts
scripts/harness.sh check content/exercises/<id> content/exercises/<id>/solution.py
scripts/harness.sh check content/exercises/<id> content/exercises/<id>/starter.py
scripts/harness.sh run   content/exercises/<id> content/exercises/<id>/solution.py
python3 scripts/check_content.py <id>
```

`scripts/harness.sh` prints the harness's JSON events. `check_content.py` uses
the same image when this machine has no clang. The solution must pass every
check; the starter must fail every check with `NotImplementedError`, not with an
import error; the run block of the solution must print its example. Run the
solution's checks three times to catch flaky checks. The machine has two cores
and little memory, so run one harness at a time.
