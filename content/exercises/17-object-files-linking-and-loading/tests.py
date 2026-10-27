"""Checks for the ELF parsing and toy linker exercise."""

import ctypes
import json
import mmap
import os
import select
import signal
import struct
import time

import cputools
from cpucheck import check, equal, fail, has


def in_child(work, timeout=10):
    """Run work() in a forked child and return its JSON-able result, so that a
    crash in linked code fails one check instead of ending the run."""
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        code = 1
        try:
            os.close(r)
            try:
                payload = {"ok": work()}
            except BaseException as exc:  # noqa: BLE001
                payload = {"error": f"{type(exc).__name__}: {exc}"}
            os.write(w, json.dumps(payload).encode())
            code = 0
        finally:
            os._exit(code)
    os.close(w)
    chunks, deadline = [], time.monotonic() + timeout
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([r], [], [], left)[0]:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                fail(f"the linked code ran for more than {timeout} seconds")
            data = os.read(r, 65536)
            if not data:
                break
            chunks.append(data)
    finally:
        os.close(r)
    _, status = os.waitpid(pid, 0)
    if os.WIFSIGNALED(status):
        fail(f"the linked code crashed with signal {os.WTERMSIG(status)}: a call or jump landed on the wrong address")
    if not chunks:
        fail("the child process ended without reporting")
    payload = json.loads(b"".join(chunks))
    if "error" in payload:
        fail(payload["error"])
    return payload["ok"]


def call_linked(linked, name, args, restype=ctypes.c_int32):
    """Copy linked.text into executable memory and call `name` there, in a child."""

    def work():
        buf = mmap.mmap(-1, 4096 * ((len(linked.text) // 4096) + 1), prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
        buf.write(linked.text)
        base = ctypes.addressof(ctypes.c_char.from_buffer(buf))
        fn = ctypes.CFUNCTYPE(restype, *([ctypes.c_int32] * len(args)))(base + linked.symbols[name])
        return fn(*args)

    return in_child(work)


MAIN_SRC = """
    .globl twice_plus_one
twice_plus_one:
    call double_it
    add eax, 1
    ret
"""
LIB_SRC = """
    .globl double_it
double_it:
    lea eax, [rdi + rdi]
    ret
"""
THREE_SRC = """
    .globl a
a:
    call b
    ret
    .globl b
b:
    call c
    ret
"""
C_SRC = """
    .globl c
c:
    mov eax, 7
    ret
"""


@check("parse_header reads the type, machine, and section-header table of a real object file")
def test_header(sub):
    parse_header = has(sub, "parse_header")
    obj = cputools.assemble_object(MAIN_SRC)
    h = parse_header(obj)
    equal(h["type"], 1, label="e_type (1 = relocatable file)")
    equal(h["machine"], 62, label="e_machine (62 = x86-64)")
    equal(h["shentsize"], 64, label="e_shentsize")
    # The same numbers, read the long way from fixed offsets of the 64-byte header.
    equal(h["shoff"], struct.unpack_from("<Q", obj, 40)[0], label="e_shoff (offset 40)")
    equal(h["shnum"], struct.unpack_from("<H", obj, 60)[0], label="e_shnum (offset 60)")
    equal(h["shstrndx"], struct.unpack_from("<H", obj, 62)[0], label="e_shstrndx (offset 62)")


@check("parse_header rejects data that is not a little-endian ELF64 file")
def test_header_errors(sub):
    parse_header = has(sub, "parse_header")
    obj = bytearray(cputools.assemble_object(MAIN_SRC))
    for label, bad in [
        ("text", b"hello world, this is not an object file at all" * 3),
        ("an empty file", b""),
        ("a 32-bit class byte", bytes(obj[:4]) + b"\x01" + bytes(obj[5:])),
        ("a big-endian data byte", bytes(obj[:5]) + b"\x02" + bytes(obj[6:])),
    ]:
        try:
            parse_header(bad)
        except ValueError:
            continue
        except NotImplementedError:
            raise
        except Exception as exc:  # noqa: BLE001
            fail(f"{label}: expected ValueError, got {type(exc).__name__}: {exc}")
        fail(f"{label}: expected ValueError, but parse_header returned normally")


@check("read_cstring reads up to the zero byte")
def test_cstring(sub):
    read = has(sub, "read_cstring")
    blob = b"\0.text\0.symtab\0\0x"
    equal(read(blob, 1), ".text", label="offset 1")
    equal(read(blob, 7), ".symtab", label="offset 7")
    equal(read(blob, 0), "", label="offset 0 is an empty name")
    equal(read(blob, 3), "ext", label="a name can start in the middle")


@check("parse_sections lists the sections by name, with .text flagged alloc and exec")
def test_sections(sub):
    parse_sections, section_bytes = has(sub, "parse_sections"), has(sub, "section_bytes")
    obj = cputools.assemble_object(MAIN_SRC)
    secs = parse_sections(obj)
    names = [s.name for s in secs]
    equal(names[0], "", label="section 0 is the empty NULL section")
    for want in (".text", ".symtab", ".strtab", ".rela.text"):
        if want not in names:
            fail(f"expected a section named {want}, got {names}")
    text = secs[names.index(".text")]
    equal(text.type, 1, label=".text type (SHT_PROGBITS)")
    equal(text.flags & 0b110, 0b110, label=".text flags include SHF_ALLOC (2) and SHF_EXECINSTR (4)")
    # call rel32 (5 bytes: e8 + 4) then add eax,1 (3 bytes) then ret (1 byte) = 9 bytes
    code = section_bytes(obj, text)
    equal(len(code), text.size, label="length of section_bytes")
    equal(code, cputools.machine_code(MAIN_SRC), label=".text bytes match what machine_code reports")
    equal(code[0], 0xE8, label="the first byte is the call opcode")


@check("parse_symbols lists global definitions and undefined references")
def test_symbols(sub):
    parse_symbols = has(sub, "parse_symbols")
    syms = {s.name: s for s in parse_symbols(cputools.assemble_object(MAIN_SRC))}
    if set(syms) != {"twice_plus_one", "double_it"}:
        fail(f"expected symbols twice_plus_one and double_it, got {sorted(syms)}")
    d, u = syms["twice_plus_one"], syms["double_it"]
    equal((d.bind, d.shndx != 0, d.value), (1, True, 0), label="twice_plus_one: global, defined, at offset 0")
    equal((u.bind, u.shndx), (1, 0), label="double_it: global and undefined (shndx 0)")
    two = {s.name: s for s in parse_symbols(cputools.assemble_object(THREE_SRC))}
    # a is a 5-byte call and a 1-byte ret, so b starts at offset 6.
    equal(two["b"].value, 6, label="offset of b inside .text")


@check("relocations names the symbol, type, offset, and addend of each call to patch")
def test_relocs(sub):
    relocations = has(sub, "relocations")
    rel = relocations(cputools.assemble_object(MAIN_SRC))
    equal(len(rel), 1, label="number of relocations")
    r = rel[0]
    equal(r.symbol, "double_it", label="symbol")
    equal(r.offset, 1, label="offset (after the e8 opcode byte)")
    equal(r.type, 4, label="type (R_X86_64_PLT32)")
    equal(r.addend, -4, label="addend")
    equal(relocations(cputools.assemble_object(LIB_SRC)), [], label="an object with no calls has no relocations")
    two = relocations(cputools.assemble_object(THREE_SRC))
    equal([(x.symbol, x.offset) for x in two], [("b", 1), ("c", 7)], label="two calls in one object")


@check("link patches a call between two objects, and the result runs")
def test_link(sub):
    link = has(sub, "link")
    linked = link([cputools.assemble_object(MAIN_SRC), cputools.assemble_object(LIB_SRC)])
    equal(sorted(linked.symbols), ["double_it", "twice_plus_one"], label="global symbols")
    equal(linked.symbols["twice_plus_one"], 0, label="the first object starts at offset 0")
    equal(linked.symbols["double_it"] % 16, 0, label="the second object is 16-byte aligned")
    # main's .text is 9 bytes long, so double_it lands at offset 16. The call's rel32 field is at
    # offset 1, so P = 1 and the value is S + A - P = 16 + (-4) - 1 = 11.
    equal(struct.unpack_from("<i", linked.text, 1)[0], 11, label="the patched rel32 of the call")
    for x in (0, 5, -3, 1000):
        equal(call_linked(linked, "twice_plus_one", (x,)), 2 * x + 1, label=f"twice_plus_one({x})")


@check("link handles three objects in any order, including calls that go backward")
def test_link_three(sub):
    link = has(sub, "link")
    a, c = cputools.assemble_object(THREE_SRC), cputools.assemble_object(C_SRC)
    equal(call_linked(link([a, c]), "a", ()), 7, label="a -> b -> c, c placed after")
    equal(call_linked(link([c, a]), "a", ()), 7, label="a -> b -> c, c placed first (a negative displacement)")
    twice = cputools.assemble_object(MAIN_SRC)
    lib = cputools.assemble_object(LIB_SRC)
    equal(call_linked(link([lib, twice]), "twice_plus_one", (20,)), 41, label="library first")


@check("link raises UndefinedSymbol and DuplicateSymbol")
def test_link_errors(sub):
    link, Undef, Dup = has(sub, "link"), has(sub, "UndefinedSymbol"), has(sub, "DuplicateSymbol")
    main = cputools.assemble_object(MAIN_SRC)
    try:
        link([main])
    except Undef as exc:
        if "double_it" not in str(exc):
            fail(f"the error should name the missing symbol, got {str(exc)!r}")
    except NotImplementedError:
        raise
    except Exception as exc:  # noqa: BLE001
        fail(f"expected UndefinedSymbol, got {type(exc).__name__}: {exc}")
    else:
        fail("linking main without double_it should raise UndefinedSymbol")
    lib = cputools.assemble_object(LIB_SRC)
    try:
        link([lib, lib])
    except Dup as exc:
        if "double_it" not in str(exc):
            fail(f"the error should name the duplicate symbol, got {str(exc)!r}")
    except NotImplementedError:
        raise
    except Exception as exc:  # noqa: BLE001
        fail(f"expected DuplicateSymbol, got {type(exc).__name__}: {exc}")
    else:
        fail("linking the same definition twice should raise DuplicateSymbol")
