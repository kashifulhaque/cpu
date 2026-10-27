---
title: "Object files, linking, and loading"
slug: 17-object-files-linking-and-loading
part: "Part 3 — From C to machine code"
summary: Parse an ELF64 object file with struct, read its symbols and relocations, and write a toy linker that patches calls between objects.
minutes: 70
gpu: false
objectives:
  - Say what an object file holds and why a compiler does not produce a runnable program directly.
  - Read the ELF64 header, section headers, symbol table, and relocation entries from raw bytes.
  - Explain what a relocation is and compute the value a linker writes for a call.
  - Write a linker that places code from two objects and resolves a call between them.
prereqs:
  - 16-how-a-compiler-sees-c
exercise: 17-object-files-linking-and-loading
---

# Object files, linking, and loading

When you call `cputools.assemble`, a lot happens out of sight. The assembler turns your text into bytes. A linker packages those bytes into a shared library. The loader maps the library into your Python process, and `ctypes` finds the function by name. Every compiled program on your machine goes through the same steps.

This lesson opens the box. A compiler works on one source file at a time, so when it compiles `main.c` it has no idea where the function `helper` from `helper.c` will end up in memory. It cannot write the address of `helper` into the call instruction, because the address does not exist yet. It writes a placeholder and a reminder that says "fill this in later". The file that holds the code, the placeholder, and the reminder is an **object file**. The program that fills in the placeholders is the **linker**.

You will read a real object file byte by byte, with Python's `struct` module, and then write a small linker of your own.

## What you already know

- Machine code is bytes, and `cputools.machine_code` returns the bytes of the code you assemble.
- A `call` instruction jumps to another function and `ret` comes back.
- A label names an address, and a function is a labeled stretch of code.
- `struct.unpack_from("<I", data, offset)` reads a little-endian 32-bit integer from `bytes`.
- A string in a binary file is often stored as bytes that end with a zero byte.

## From source to a running program

The picture below shows every step between C and a running process. This lesson covers the three on the right.

```text
  main.c ──compile──> main.s ──assemble──> main.o ──┐
                                                    ├──link──> program ──load──> process
  helper.c ─compile─> helper.s ─assemble─> helper.o ┘
  (clang -S)             (clang -c)                  (ld)        (the kernel)
```

The `.o` files are object files. Each one is complete in itself, but has holes. The linker joins them into one executable (or a shared library) and fills the holes. The loader, part of the operating system and the dynamic loader `ld.so`, maps the result into memory and starts it.

Compiling one file at a time is the point. When you change `helper.c`, you rebuild only `helper.o` and run the linker again.

## The hole in a call

Assemble a function that calls another function that lives somewhere else.

```asm
    .globl start
start:
    call helper
    ret
```

`cputools.machine_code` returns these bytes:

```text
e8 00 00 00 00 c3
```

`e8` is the opcode for `call` with a 32-bit relative displacement. The next four bytes are the displacement, and they are all zero: the assembler does not know where `helper` is. `c3` is `ret`. The four zero bytes are the hole. At run time the CPU computes the call target as the address of the next instruction plus that signed 32-bit number, so the linker must write `helper`'s distance from the end of the call into those bytes.

The object file records where the hole is and what goes there. That record is a **relocation**.

## The ELF file format

On Linux, object files, executables, and shared libraries share one format: **ELF**, short for Executable and Linkable Format. An ELF file is a sequence of bytes with a fixed header at the start that says where everything else is. The picture below shows the layout of the object file for the `call helper` function above. Offsets are in bytes.

```text
  offset   contents
  ------   ----------------------------------------------
       0   ELF header (64 bytes)
      64   .text           the machine code (6 bytes)
      72   .symtab         3 symbols x 24 bytes
     144   .rela.text      1 relocation x 24 bytes
     168   .strtab         names: "start", "helper", and the section names
     232   section header table: 6 entries x 64 bytes
```

The offsets of the middle parts vary from file to file. The header tells you where the section table is, and the table tells you where each section is. Only the header's position is fixed.

### The ELF header

The header is 64 bytes. These are the real bytes from `cputools.assemble_object` for the function above, in hex.

```text
7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00   e_ident (16 bytes)
01 00 3e 00 01 00 00 00 00 00 00 00 00 00 00 00   type, machine, version, entry
00 00 00 00 00 00 00 00 e8 00 00 00 00 00 00 00   phoff, shoff
00 00 00 00 40 00 00 00 00 00 40 00 06 00 01 00   flags, sizes, counts
```

The table below names every field with its offset. `struct` format letters are `H` for 2 bytes, `I` for 4, and `Q` for 8.

| Offset | Size | Field | Value here | Meaning |
|---|---|---|---|---|
| 0 | 4 | magic | `7f 45 4c 46` | `0x7f` and the letters `ELF` |
| 4 | 1 | class | 2 | 2 means 64-bit |
| 5 | 1 | data | 1 | 1 means little-endian |
| 6 | 1 | version | 1 | always 1 |
| 16 | 2 | `e_type` | 1 | 1 is a relocatable object, 2 an executable, 3 a shared library |
| 18 | 2 | `e_machine` | 62 (`0x3e`) | 62 is x86-64 |
| 24 | 8 | `e_entry` | 0 | entry point; zero in an object |
| 32 | 8 | `e_phoff` | 0 | program headers; an object has none |
| 40 | 8 | `e_shoff` | 232 (`0xe8`) | where the section header table starts |
| 52 | 2 | `e_ehsize` | 64 | size of this header |
| 58 | 2 | `e_shentsize` | 64 | size of one section header |
| 60 | 2 | `e_shnum` | 6 | number of section headers |
| 62 | 2 | `e_shstrndx` | 1 | which section holds the section names |

One call reads the whole header: `struct.unpack_from("<16sHHIQQQIHHHHHH", data, 0)`. The `<` means little-endian with no padding, and the 16 bytes of `e_ident` come back as one `bytes` value.

> [!KEY]
> An ELF file describes itself. The header says where the section header table is, the section headers say where each section's bytes are, and nothing else in the file has a fixed place.

### Sections

A **section** is a named block of bytes with one purpose. The section header table has one 64-byte entry per section. Each entry has these fields, in order.

| Field | `struct` letter | Meaning |
|---|---|---|
| `sh_name` | `I` | offset of the section's name in the name string table |
| `sh_type` | `I` | 1 `PROGBITS` (code or data), 2 `SYMTAB`, 3 `STRTAB`, 4 `RELA` |
| `sh_flags` | `Q` | bit 1 `ALLOC` (occupies memory), bit 2 `WRITE`, bit 4 `EXECINSTR` |
| `sh_addr` | `Q` | address when loaded; zero in an object |
| `sh_offset` | `Q` | where the section's bytes start in the file |
| `sh_size` | `Q` | length in bytes |
| `sh_link` | `I` | index of a related section (a symbol table's string table) |
| `sh_info` | `I` | extra index (a relocation section's target) |
| `sh_addralign` | `Q` | alignment |
| `sh_entsize` | `Q` | size of one entry for table sections |

The format string is `"<IIQQQQIIQQ"`, 64 bytes in all. Here are the six sections of the object above, as `llvm-readelf -S` prints them.

```text
  [Nr] Name              Type            Off    Size   ES Flg Lk Inf
  [ 0]                   NULL            000000 000000 00      0   0
  [ 1] .strtab           STRTAB          0000a8 000039 00      0   0
  [ 2] .text             PROGBITS        000040 000006 00  AX  0   0
  [ 3] .rela.text        RELA            000090 000018 18   I  5   2
  [ 4] .note.GNU-stack   PROGBITS        000046 000000 00      0   0
  [ 5] .symtab           SYMTAB          000048 000048 18      1   1
```

Section 0 is always empty. `.text` holds 6 bytes at file offset 64 (`0x40`), right after the header, with flags `AX` (alloc and execute). The `.rela.text` section's `Lk` is 5 (its symbol table) and `Inf` is 2 (the section it patches, `.text`).

Names are not in the headers. Each header holds an offset into a **string table**: a section of text in which each name ends with a zero byte. To read a name, take the bytes from that offset up to the next `0`. Clang's objects keep section names in `.strtab`, which is why `e_shstrndx` is 1 here. Other tools put them in `.shstrtab`.

### Symbols

A **symbol** is a name attached to an address. The `.symtab` section is an array of 24-byte entries, format `"<IBBHQQ"`.

| Field | Letter | Meaning |
|---|---|---|
| `st_name` | `I` | offset of the name in the string table that `sh_link` names |
| `st_info` | `B` | binding in the high 4 bits, type in the low 4 |
| `st_other` | `B` | visibility (ignored here) |
| `st_shndx` | `H` | index of the section that defines it, or 0 if undefined |
| `st_value` | `Q` | offset of the symbol in that section |
| `st_size` | `Q` | size in bytes |

The symbols of the `call helper` object:

```text
   Num: Value  Size Type    Bind   Ndx Name
     0: 0         0 NOTYPE  LOCAL  UND
     1: 0         0 NOTYPE  GLOBAL   2 start
     2: 0         0 NOTYPE  GLOBAL UND helper
```

`start` is **defined** in section 2 (`.text`) at offset 0. `helper` is **undefined**: its section index is 0, which means "someone else defines this". A **global** symbol (binding 1) is visible to other objects. A **local** symbol (binding 0) is not. Entry 0 is always a null symbol.

### Relocations

A relocation entry sits in a `.rela.text` section, as 24-byte records in the format `"<QQq"`: an offset, an info field, and a signed addend.

| Field | Meaning |
|---|---|
| `r_offset` | where in the patched section the hole is |
| `r_info` | the symbol's index in the high 32 bits, the relocation type in the low 32 |
| `r_addend` | a constant to add |

For the call above, `llvm-readelf -r` prints:

```text
    Offset             Info             Type               Symbol's Value  Symbol's Name + Addend
0000000000000001  0000000200000004 R_X86_64_PLT32         0000000000000000 helper - 4
```

The hole is at offset 1, just after the `e8` byte. `r_info = 0x0000000200000004` splits into symbol 2 (`helper`) and type 4 (`R_X86_64_PLT32`, a 32-bit address relative to the hole). The addend is -4.

The linker computes the value to store with one formula:

$$
\text{value} = S + A - P
$$

where $S$ is the final address of the symbol, $A$ is the addend, and $P$ is the final address of the hole. The CPU adds the displacement to the address of the next instruction, which is $P + 4$, since the hole is 4 bytes long and ends the instruction. The addend of -4 cancels that offset.

Here is a worked example. Put the object's code at address 0 and `helper` at address 16. The hole is at $P = 0 + 1 = 1$.

$$
\text{value} = 16 + (-4) - 1 = 11
$$

Check it the way the CPU does: the next instruction is at address 5, and $5 + 11 = 16$, the address of `helper`. The linker writes 11 as four little-endian bytes, `0b 00 00 00`, so the call becomes `e8 0b 00 00 00`.

## A toy linker

A real linker does a lot of work, but the core is short. Your linker takes a list of object files and produces one block of code.

1. **Place.** Copy each object's `.text` into one buffer, one after another. Start each at an offset that is a multiple of 16, as real linkers align functions. The offset where an object starts is its **base**.
2. **Collect symbols.** For each global symbol defined in a `.text`, the final address is its object's base plus its value. Two definitions of one name are an error.
3. **Patch.** For each relocation, look up the symbol, compute $S + A - P$, and write the result as a signed 32-bit little-endian integer at the hole. A symbol that nobody defines is an error.

The picture shows two objects placed in one buffer, with the hole filled in.

```text
  object A: start        object B: helper
  e8 00 00 00 00 c3      8d 04 3f c3          (before)

  linked buffer
  offset   0                              16
           e8 0b 00 00 00 c3 00 ... 00    8d 04 3f c3
              |-- 11 --|                  ^
              +--- next instruction (5) + 11 = 16
```

The result is a running program. In the exercise, the checks copy your linked bytes into executable memory in a child process and call the function. If a displacement is wrong, the call lands in the wrong place and the process crashes, which the check reports.

## Loading and what real linkers add

A linked executable still needs a **loader**. On Linux the kernel reads the ELF **program headers**, which describe **segments**: ranges of the file to map into memory with given permissions (read and execute for code, read and write for data). Section headers are for the linker and for tools. Program headers are for the loader, and an executable can omit the section table entirely.

Real linkers also handle things your toy does not.

- **Many sections.** Besides `.text`, there are `.data` (initialized globals), `.rodata` (constants), and `.bss` (zero-filled globals). The linker merges the same-named sections of all objects.
- **Many relocation types.** `R_X86_64_PLT32` is one of dozens. Others patch 64-bit absolute addresses and data references.
- **Shared libraries.** A call to a function in `libc.so` cannot be resolved until the program starts. The linker emits a small stub in the **procedure linkage table**, and the **dynamic loader** fills in the real address at run time.

## Try it on your own machine

Every command here runs on a Linux system with clang. The tools `readelf` and `nm` come from binutils, and `llvm-readelf` comes with LLVM.

1. Compile a file to an object and read its header. The type should say `REL (Relocatable file)` and the machine should say `Advanced Micro Devices X86-64`.

   ```bash
   printf 'int helper(int);\nint start(int x) { return helper(x) + 1; }\n' > a.c
   clang -c -O1 a.c -o a.o && readelf -h a.o
   ```

2. List the sections, symbols, and relocations. Look for `helper` marked `UND` in the symbol table and a `R_X86_64_PLT32` entry that mentions it.

   ```bash
   readelf -S -s -r a.o
   ```

3. Disassemble with relocations shown. The call's target prints as the symbol name, because the bytes still hold zero.

   ```bash
   objdump -dr -M intel a.o
   ```

4. Link two objects, then run `nm` on the result to see the final addresses of the symbols.

   ```bash
   printf 'int helper(int x) { return x * 2; }\n' > b.c
   printf 'int helper(int);\nint main(void) { return helper(21); }\n' > m.c
   clang m.c b.c -o prog && ./prog; echo $?; nm prog | grep -w -e main -e helper
   ```

   The program prints nothing and exits with 42.

## Build it step by step

Write the parsers first, then the linker, because the linker builds on all of them. Each function takes the bytes of an ELF file.

1. `parse_header(data)` checks that `data[:4]` is `b"\x7fELF"`, that the class byte (`data[4]`) is 2, and that the data byte (`data[5]`) is 1. Raise `ValueError` otherwise. Then read the fields with `struct.unpack_from("<16sHHIQQQIHHHHHH", data, 0)` and return the dict the starter describes. The common mistake is to forget that the first field is 16 bytes.
2. `read_cstring(data, offset)` finds the next zero byte with `data.index(b"\0", offset)` and decodes what lies between.
3. `parse_sections(data)` reads `shnum` headers of `shentsize` bytes starting at `shoff`. Read all headers first, because a name needs the string table section, which comes from the same table. Then fill `Section` objects with decoded names.
4. `section_bytes(data, section)` slices `data[offset : offset + size]`.
5. `parse_symbols(data)` finds the section whose type is `SYMTAB` (2). Its `link` field is the index of its string table. Unpack each 24-byte entry, split `info` into `info >> 4` and `info & 0xF`, and skip entry 0.
6. `relocations(data)` reads `.rela.text` with `"<QQq"`. Split `info` into `info >> 32` and `info & 0xFFFFFFFF`. The symbol index in `info` counts the null entry at index 0, but your `parse_symbols` leaves that entry out, so index `i` is `parse_symbols(data)[i - 1]`. Forgetting the shift is the common off-by-one mistake here.
7. `link(objects)` does place, collect, and patch from the section above. Write the patch with `struct.pack_into("<i", buffer, place, value)` into a `bytearray`. Return a `Linked` with the final `text` bytes and a dict of global names to offsets.

## Where this breaks

**Distance limits.** A 32-bit displacement reaches about 2 GiB in either direction. A program larger than that needs larger code models and different relocation types.

**Duplicate and missing symbols are the common failures.** `undefined reference to 'helper'` is the linker's message for your `UndefinedSymbol`. `multiple definition of 'helper'` is `DuplicateSymbol`. Real linkers let a few symbols be defined many times (weak symbols, inline functions), which your toy does not.

**Order matters for static libraries.** A linker scans archives (`.a` files) once, in command-line order, and pulls in only the members that resolve symbols it has already seen. Putting a library before the object that needs it fails.

**Interposition.** With shared libraries, a program can replace a library's function by defining the same name first. This is how `LD_PRELOAD` tools work, and it is why calls to global functions go through the procedure linkage table, instead of a direct jump.

**Your parser trusts the file.** It does not validate offsets or sizes, so a corrupt file raises a confusing `struct.error`. Production tools check every range.

## Further reading

- [The `elf(5)` manual page](https://man7.org/linux/man-pages/man5/elf.5.html) lists every field of the headers, sections, symbols, and relocations on Linux.
- [The ELF specification](https://refspecs.linuxfoundation.org/elf/elf.pdf) is the original document, short and readable.
- [The x86-64 System V ABI](https://gitlab.com/x86-psABIs/x86-64-ABI) defines the relocation types, such as `R_X86_64_PLT32`, and the procedure linkage table for x86-64.
- [`llvm-readelf`](https://llvm.org/docs/CommandGuide/llvm-readelf.html) is the tool whose output this lesson quoted.
- [Ian Lance Taylor's linker series](https://www.airs.com/blog/archives/38) walks through what a linker does, in twenty short posts by the author of the gold linker.

## The exercise

You write the ELF parsers and a linker, in this order: `parse_header`, `read_cstring`, `parse_sections`, `section_bytes`, `parse_symbols`, `relocations`, and `link`. The dataclasses `Section`, `Symbol`, `Reloc`, and `Linked`, and the exceptions `UndefinedSymbol` and `DuplicateSymbol`, are given.

The checks assemble small objects with `cputools.assemble_object` and test your parsers against known values: the header fields at their fixed offsets, the bytes of `.text` against `cputools.machine_code`, the symbols and their binding, and the relocation entries. The linker checks place two or three objects in every order, verify the patched displacement by hand (the value 11 in the example above), and then copy the linked bytes into executable memory in a forked child and call the function there. A wrong displacement crashes the child, which fails only that check.
