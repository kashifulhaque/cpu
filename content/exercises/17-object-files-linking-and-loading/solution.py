"""Parse ELF64 object files with struct, then link two of them.

The classes below are given. You write the parsing functions and the linker.
All offsets and sizes are for little-endian ELF64 files, the format of
`cputools.assemble_object` output on x86-64 Linux.
"""

import struct
from dataclasses import dataclass

import cputools

SHT_PROGBITS, SHT_SYMTAB, SHT_STRTAB, SHT_RELA = 1, 2, 3, 4
STB_LOCAL, STB_GLOBAL = 0, 1
R_X86_64_PC32, R_X86_64_PLT32 = 2, 4


class UndefinedSymbol(Exception):
    """A relocation names a symbol that no object defines."""


class DuplicateSymbol(Exception):
    """Two objects define the same global symbol."""


@dataclass
class Section:
    name: str
    type: int
    flags: int
    addr: int
    offset: int  # where the section's bytes start in the file
    size: int
    link: int
    info: int
    entsize: int


@dataclass
class Symbol:
    name: str
    bind: int  # STB_LOCAL or STB_GLOBAL
    type: int
    shndx: int  # index of the section that defines it; 0 means undefined
    value: int  # offset inside that section
    size: int


@dataclass
class Reloc:
    offset: int  # where in the patched section the 4 bytes live
    symbol: str
    type: int
    addend: int


@dataclass
class Linked:
    text: bytes  # all the .text sections, joined, with calls patched
    symbols: dict  # global name -> offset of that function inside `text`


def parse_header(data: bytes) -> dict:
    """Read the 64-byte ELF header.

    Raise ValueError if `data` is not a little-endian ELF64 file. Return a dict
    with the keys "type", "machine", "shoff", "shentsize", "shnum", "shstrndx".

    For an x86-64 object file, "type" is 1 (relocatable) and "machine" is 62.
    """
    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file: the first four bytes are not 7f 45 4c 46")
    if data[4] != 2:
        raise ValueError("not a 64-bit ELF file (EI_CLASS is not 2)")
    if data[5] != 1:
        raise ValueError("not a little-endian ELF file (EI_DATA is not 1)")
    (_ident, e_type, machine, _version, _entry, _phoff, shoff, _flags,
     _ehsize, _phentsize, _phnum, shentsize, shnum, shstrndx) = struct.unpack_from("<16sHHIQQQIHHHHHH", data, 0)
    return {"type": e_type, "machine": machine, "shoff": shoff,
            "shentsize": shentsize, "shnum": shnum, "shstrndx": shstrndx}


def read_cstring(data: bytes, offset: int) -> str:
    """The text starting at `offset` and ending at the next zero byte.

    >>> read_cstring(b"\\0.text\\0.data\\0", 1)
    '.text'
    """
    end = data.index(b"\0", offset)  # the string stops at the first zero byte
    return data[offset:end].decode()


def parse_sections(data: bytes) -> list:
    """All section headers of the file as `Section` objects, in file order.

    Names come from the section-name string table, the section at index
    `shstrndx`. The list's first item is the empty NULL section.
    """
    h = parse_header(data)
    raw = []
    for i in range(h["shnum"]):
        at = h["shoff"] + i * h["shentsize"]
        raw.append(struct.unpack_from("<IIQQQQIIQQ", data, at))
    names_at = raw[h["shstrndx"]][4]  # file offset of the section-name string table
    sections = []
    for name, typ, flags, addr, offset, size, link, info, _align, entsize in raw:
        sections.append(Section(read_cstring(data, names_at + name), typ, flags, addr, offset, size, link, info, entsize))
    return sections


def section_bytes(data: bytes, section: Section) -> bytes:
    """The contents of `section`: `data[offset : offset + size]`."""
    return data[section.offset : section.offset + section.size]


def parse_symbols(data: bytes) -> list:
    """The entries of `.symtab` as `Symbol` objects, without the null entry at index 0.

    Names come from the string table that the symbol table's `link` points to.
    """
    sections = parse_sections(data)
    symtab = next((s for s in sections if s.type == SHT_SYMTAB), None)
    if symtab is None:
        return []
    strtab = sections[symtab.link]
    symbols = []
    for i in range(1, symtab.size // 24):  # entry 0 is the null symbol
        name, info, _other, shndx, value, size = struct.unpack_from("<IBBHQQ", data, symtab.offset + i * 24)
        symbols.append(Symbol(read_cstring(data, strtab.offset + name), info >> 4, info & 0xF, shndx, value, size))
    return symbols


def relocations(data: bytes) -> list:
    """The entries of the `.rela.text` section as `Reloc` objects.

    Return an empty list if the object has no `.rela.text`.
    """
    sections = parse_sections(data)
    rela = next((s for s in sections if s.name == ".rela.text"), None)
    if rela is None:
        return []
    # Symbol indices count the null entry, so put it back at the front.
    symbols = [None] + parse_symbols(data)
    out = []
    for i in range(rela.size // 24):
        offset, info, addend = struct.unpack_from("<QQq", data, rela.offset + i * 24)
        out.append(Reloc(offset, symbols[info >> 32].name, info & 0xFFFFFFFF, addend))
    return out


def link(objects: list) -> Linked:
    """Link relocatable objects (each a `bytes` ELF file) into one code blob.

    1. Place each object's `.text` one after another, each starting at an offset
       that is a multiple of 16 (pad with zero bytes).
    2. Give every global symbol that is defined in a `.text` the address
       `base + value`. Raise DuplicateSymbol for a name defined twice.
    3. For every relocation, write S + A - P as a signed 32-bit little-endian
       number at the patched bytes. S is the symbol's address, A the addend, and
       P the address of the patched bytes. Raise UndefinedSymbol for a symbol
       with no definition.
    """
    text = bytearray()
    bases = []  # where each object's .text starts inside the blob
    for obj in objects:
        while len(text) % 16:
            text.append(0)
        bases.append(len(text))
        sections = parse_sections(obj)
        text += section_bytes(obj, next(s for s in sections if s.name == ".text"))

    # Pass 1: find every global definition.
    table = {}
    for obj, base in zip(objects, bases):
        text_index = next(i for i, s in enumerate(parse_sections(obj)) if s.name == ".text")
        for sym in parse_symbols(obj):
            if sym.bind == STB_GLOBAL and sym.shndx == text_index:
                if sym.name in table:
                    raise DuplicateSymbol(sym.name)
                table[sym.name] = base + sym.value

    # Pass 2: patch every relocation.
    for obj, base in zip(objects, bases):
        for rel in relocations(obj):
            if rel.symbol not in table:
                raise UndefinedSymbol(rel.symbol)
            place = base + rel.offset  # P
            value = table[rel.symbol] + rel.addend - place  # S + A - P
            struct.pack_into("<i", text, place, value)
    return Linked(bytes(text), table)


if __name__ == "__main__":
    obj = cputools.assemble_object(
        """
        .globl start
start:
        call helper
        ret
        """
    )
    print("object file:", len(obj), "bytes")
    print("header:", parse_header(obj))
    print("sections:", [s.name for s in parse_sections(obj)])
    print("symbols:", [(s.name, s.bind, s.shndx) for s in parse_symbols(obj)])
    print("relocations:", relocations(obj))
