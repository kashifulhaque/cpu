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
    raise NotImplementedError


def read_cstring(data: bytes, offset: int) -> str:
    """The text starting at `offset` and ending at the next zero byte.

    >>> read_cstring(b"\\0.text\\0.data\\0", 1)
    '.text'
    """
    raise NotImplementedError


def parse_sections(data: bytes) -> list:
    """All section headers of the file as `Section` objects, in file order.

    Names come from the section-name string table, the section at index
    `shstrndx`. The list's first item is the empty NULL section.
    """
    raise NotImplementedError


def section_bytes(data: bytes, section: Section) -> bytes:
    """The contents of `section`: `data[offset : offset + size]`."""
    raise NotImplementedError


def parse_symbols(data: bytes) -> list:
    """The entries of `.symtab` as `Symbol` objects, without the null entry at index 0.

    Names come from the string table that the symbol table's `link` points to.
    """
    raise NotImplementedError


def relocations(data: bytes) -> list:
    """The entries of the `.rela.text` section as `Reloc` objects.

    Return an empty list if the object has no `.rela.text`.
    """
    raise NotImplementedError


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
    raise NotImplementedError


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
