"""Thin wrappers around the real toolchain: clang, llc, opt, lli, llvm-objdump.

Exercises and checks import this module as `cputools`. It sits beside the
harness, so it is on the import path at run time. Every function takes source
text (C, x86-64 assembly, or LLVM IR) as a string, writes it to a scratch
directory, runs one tool, and returns text or a loaded library.

A tool that fails raises `ToolError`, whose message is the tool's own error
output, trimmed. That is the message the reader needs: the line and column
clang or opt complained about.

    lib = compile_c("int add(int a, int b) { return a + b; }")
    lib.add(2, 3)                          # 5

    lib = assemble('''
        .globl add
    add:
        lea eax, [rdi + rsi]
        ret
    ''')
    lib.add(2, 3)                          # 5

    run_ir('define i32 @main() { ret i32 7 }').returncode   # 7
"""

from __future__ import annotations

import ctypes
import itertools
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Each call writes into its own numbered directory under one scratch root, so a
# library loaded earlier keeps its file while later calls make new ones.
_ROOT = Path(tempfile.mkdtemp(prefix="cputools-"))
_COUNTER = itertools.count()
_TIMEOUT = 20


class ToolError(RuntimeError):
    """A compiler, assembler, or LLVM tool rejected its input."""


@dataclass
class Result:
    """What a program did: its exit code and everything it printed."""

    returncode: int
    stdout: str
    stderr: str


def tool(name: str) -> str:
    """The path of an LLVM tool, trying the plain name and versioned names."""
    for candidate in (name, *(f"{name}-{v}" for v in range(22, 13, -1))):
        found = shutil.which(candidate)
        if found:
            return found
    raise ToolError(f"{name} is not installed in this runner")


def _workdir() -> Path:
    path = _ROOT / str(next(_COUNTER))
    path.mkdir()
    return path


def _trim(text: str, limit: int = 3000) -> str:
    text = text.strip()
    # Paths to the scratch directory mean nothing to the reader.
    text = text.replace(str(_ROOT) + "/", "")
    return text if len(text) <= limit else text[:limit] + "\n..."


def _call(argv: list[str], *, stdin: str | None = None, what: str) -> subprocess.CompletedProcess:
    try:
        done = subprocess.run(
            argv, input=stdin, capture_output=True, text=True, timeout=_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"{what} took longer than {_TIMEOUT} seconds") from None
    if done.returncode != 0:
        raise ToolError(f"{what} failed:\n{_trim(done.stderr or done.stdout)}")
    return done


def _load(path: Path) -> ctypes.CDLL:
    return ctypes.CDLL(str(path))


# ---------------------------------------------------------------------------
# C
# ---------------------------------------------------------------------------


def compile_c(source: str, *, opt: str = "-O1", flags: tuple[str, ...] = ()) -> ctypes.CDLL:
    """Compile C source into a shared library and load it with ctypes.

    Functions are called through the returned library: `lib.name(args)`. ctypes
    assumes `int` arguments and an `int` result; set `lib.name.restype` and
    `lib.name.argtypes` for anything else.
    """
    work = _workdir()
    (work / "code.c").write_text(source)
    out = work / "libcode.so"
    _call(
        [tool("clang"), opt, "-shared", "-fPIC", "-Wall", *flags, "-o", str(out), str(work / "code.c")],
        what="clang",
    )
    return _load(out)


def c_to_asm(source: str, *, opt: str = "-O1", intel: bool = True, flags: tuple[str, ...] = ()) -> str:
    """The x86-64 assembly clang produces for C source, without debug noise."""
    work = _workdir()
    (work / "code.c").write_text(source)
    argv = [tool("clang"), opt, "-S", "-fno-asynchronous-unwind-tables", "-fno-addrsig", *flags]
    if intel:
        argv.append("-masm=intel")
    _call([*argv, "-o", str(work / "code.s"), str(work / "code.c")], what="clang")
    return (work / "code.s").read_text()


def c_to_ir(source: str, *, opt: str = "-O1", flags: tuple[str, ...] = ()) -> str:
    """The LLVM IR clang produces for C source.

    At `-O0` clang marks every function `optnone`, so `opt` would skip it. The
    `-Xclang -disable-O0-optnone` flag leaves that mark off, so the IR can be
    fed to `run_opt` afterwards.
    """
    work = _workdir()
    (work / "code.c").write_text(source)
    argv = [tool("clang"), opt, "-S", "-emit-llvm", "-fno-discard-value-names", *flags]
    if opt == "-O0":
        argv += ["-Xclang", "-disable-O0-optnone"]
    _call([*argv, "-o", str(work / "code.ll"), str(work / "code.c")], what="clang")
    return (work / "code.ll").read_text()


def build_c(source: str, *, opt: str = "-O1", flags: tuple[str, ...] = ()) -> Path:
    """Compile and link C source into an executable and return its path."""
    work = _workdir()
    (work / "code.c").write_text(source)
    out = work / "program"
    _call([tool("clang"), opt, "-Wall", *flags, "-o", str(out), str(work / "code.c")], what="clang")
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _asm_text(source: str, intel: bool) -> str:
    head = ".intel_syntax noprefix\n" if intel else ""
    # A note section tells the linker this code needs no executable stack.
    return head + ".text\n" + source + '\n.section .note.GNU-stack,"",@progbits\n'


def assemble(source: str, *, intel: bool = True) -> ctypes.CDLL:
    """Assemble x86-64 source into a shared library and load it with ctypes.

    Intel syntax (`mov rax, 1`) is the default. Each function you want to call
    from Python needs a `.globl name` line and a `name:` label.
    """
    work = _workdir()
    (work / "code.s").write_text(_asm_text(source, intel))
    out = work / "libcode.so"
    _call([tool("clang"), "-shared", "-fPIC", "-nostdlib", "-o", str(out), str(work / "code.s")], what="assembler")
    return _load(out)


def assemble_object(source: str, *, intel: bool = True) -> bytes:
    """Assemble x86-64 source into an ELF object file and return its bytes."""
    work = _workdir()
    (work / "code.s").write_text(_asm_text(source, intel))
    out = work / "code.o"
    _call([tool("clang"), "-c", "-o", str(out), str(work / "code.s")], what="assembler")
    return out.read_bytes()


def machine_code(source: str, *, intel: bool = True) -> bytes:
    """The raw bytes of the `.text` section the assembler produces."""
    work = _workdir()
    (work / "code.s").write_text(_asm_text(source, intel))
    obj = work / "code.o"
    _call([tool("clang"), "-c", "-o", str(obj), str(work / "code.s")], what="assembler")
    out = work / "text.bin"
    _call([tool("llvm-objcopy"), "-O", "binary", "--only-section=.text", str(obj), str(out)], what="llvm-objcopy")
    return out.read_bytes()


def disassemble(path_or_bytes: Path | str | bytes, *, intel: bool = True) -> str:
    """`llvm-objdump -d` of an object file, executable, or shared library."""
    if isinstance(path_or_bytes, bytes):
        work = _workdir()
        target = work / "blob.o"
        target.write_bytes(path_or_bytes)
    else:
        target = Path(path_or_bytes)
    argv = [tool("llvm-objdump"), "-d", "--no-show-raw-insn"]
    if intel:
        argv.append("-Mintel")
    text = _call([*argv, str(target)], what="llvm-objdump").stdout
    # The scratch path in the header line means nothing to the reader.
    return text.replace(str(_ROOT) + "/", "")


# ---------------------------------------------------------------------------
# LLVM IR
# ---------------------------------------------------------------------------


def verify_ir(ir: str) -> None:
    """Raise `ToolError` with the verifier's message if the IR is not valid."""
    _call([tool("opt"), "-passes=verify", "-disable-output"], stdin=ir, what="the IR verifier")


def run_opt(ir: str, passes: str) -> str:
    """Run `opt -S -passes=<passes>` on IR text and return the result.

    `passes` uses the new pass manager's syntax: "mem2reg", "instcombine,dce",
    "default<O2>".
    """
    return _call([tool("opt"), "-S", f"-passes={passes}"], stdin=ir, what="opt").stdout


def ir_to_asm(ir: str, *, opt: str = "-O2", intel: bool = True) -> str:
    """Lower IR to x86-64 assembly with `llc`."""
    argv = [tool("llc"), opt, "-o", "-"]
    if intel:
        argv.append("--x86-asm-syntax=intel")
    return _call(argv, stdin=ir, what="llc").stdout


def ir_to_lib(ir: str, *, opt: str = "-O1") -> ctypes.CDLL:
    """Compile IR into a shared library and load it with ctypes."""
    work = _workdir()
    (work / "code.ll").write_text(ir)
    out = work / "libcode.so"
    _call(
        [tool("clang"), opt, "-shared", "-fPIC", "-Wno-override-module", "-o", str(out), str(work / "code.ll")],
        what="clang",
    )
    return _load(out)


def run_ir(ir: str, *, args: tuple[str, ...] = (), stdin: str | None = None) -> Result:
    """Run a module's `@main` with `lli` and report what it did.

    A nonzero exit code is a result here, not an error: `ret i32 7` from
    `@main` gives `returncode == 7`. Only IR that does not parse raises.
    """
    verify_ir(ir)
    work = _workdir()
    (work / "code.ll").write_text(ir)
    result = run([tool("lli"), work / "code.ll", *args], stdin=stdin)
    result.stderr = _trim(result.stderr)
    return result


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------


def run(argv: list[str] | Path | str, *, stdin: str | None = None) -> Result:
    """Run an executable and report its exit code and output."""
    if isinstance(argv, (str, Path)):
        argv = [str(argv)]
    try:
        done = subprocess.run(
            [str(a) for a in argv], input=stdin, capture_output=True, text=True, timeout=_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"{argv[0]} took longer than {_TIMEOUT} seconds") from None
    return Result(done.returncode, done.stdout, done.stderr)


def clang_version() -> str:
    """The first line of `clang --version`."""
    return _call([tool("clang"), "--version"], what="clang").stdout.splitlines()[0]


def environment() -> dict[str, str]:
    """The tools this runner has, for the reader's curiosity."""
    found = {}
    for name in ("clang", "llc", "opt", "lli", "llvm-objdump", "llvm-objcopy"):
        try:
            found[name] = tool(name)
        except ToolError:
            found[name] = "missing"
    found["cpu"] = os.uname().machine
    return found
