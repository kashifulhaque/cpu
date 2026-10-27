"""C for the curious: pointers, struct layout, and undefined behaviour.

Some functions here return C source text, which the checks compile with
cputools.compile_c and call through ctypes. Two functions are plain Python:
they predict how the C compiler lays out a struct in memory.

x86-64 Linux sizes and alignments are in SIZE_ALIGN, given in full.
"""

import ctypes

import cputools

# type name -> (size in bytes, alignment in bytes) on x86-64 Linux
SIZE_ALIGN = {
    "char": (1, 1),
    "short": (2, 2),
    "int": (4, 4),
    "float": (4, 4),
    "long": (8, 8),
    "double": (8, 8),
    "void*": (8, 8),
}


def sum_ptr_c() -> str:
    """C source defining `long sum_ptr(const long *begin, const long *end)`.

    Add up the values from `begin` up to, not including, `end`, walking a
    pointer. Do not index with `[ ]`. With begin == end the sum is 0.
    """
    return """
long sum_ptr(const long *begin, const long *end) {
    long total = 0;
    for (const long *p = begin; p < end; p++) {
        total += *p;
    }
    return total;
}
"""


def swap_c() -> str:
    """C source defining `void swap(int *a, int *b)`, which exchanges the two ints.

    swap(&x, &y) with x = 1 and y = 2 leaves x = 2 and y = 1. Calling swap(&x, &x) leaves x unchanged.
    """
    return """
void swap(int *a, int *b) {
    int t = *a;
    *a = *b;
    *b = t;
}
"""


def array_vs_pointer_c() -> str:
    """C source defining two functions that return a `sizeof`, as a long:

    long local_array_size(void)   declares `int a[10]` and returns sizeof a  (40)
    long param_size(int a[10])    returns sizeof a for its parameter         (8)
    """
    return """
long local_array_size(void) {
    int a[10];
    return sizeof a;
}

long param_size(int a[10]) {
    /* The parameter type is really int *, so this is the size of a pointer. */
    return sizeof a;
}
"""


def struct_layout(types: list[str]) -> dict:
    """Lay out a C struct whose fields have the given types, in order.

    Return {"offsets": [offset of each field], "size": sizeof the struct,
    "align": the struct's alignment}. Use SIZE_ALIGN for sizes and alignments.

    struct_layout(["char", "int", "char"]) is
    {"offsets": [0, 4, 8], "size": 12, "align": 4}.
    """
    # BEGIN
    offsets = []
    pos = 0
    struct_align = 1
    for name in types:
        size, align = SIZE_ALIGN[name]
        # Round the running position up to a multiple of this field's alignment.
        pos = (pos + align - 1) // align * align
        offsets.append(pos)
        pos += size
        struct_align = max(struct_align, align)
    # The size is rounded up so that an array of these structs keeps every element aligned.
    size = (pos + struct_align - 1) // struct_align * struct_align
    return {"offsets": offsets, "size": size, "align": struct_align}
    # END


def best_order(types: list[str]) -> list[str]:
    """Return the same types reordered so the struct has the smallest possible size.

    best_order(["char", "int", "char"]) is ["int", "char", "char"], which has size 8.
    """
    # BEGIN
    # Largest alignment first means each field lands on a boundary with no gap.
    return sorted(types, key=lambda name: SIZE_ALIGN[name][1], reverse=True)
    # END


def wrap_add_c() -> str:
    """C source defining `int wrap_add(int a, int b)`: a + b wrapped to 32 bits, with no undefined behaviour.

    wrap_add(2147483647, 1) is -2147483648. Signed overflow is undefined in C,
    so do the addition in unsigned arithmetic, which wraps by definition.
    """
    return """
int wrap_add(int a, int b) {
    unsigned int sum = (unsigned int)a + (unsigned int)b;
    return (int)sum;
}
"""


def safe_div_c() -> str:
    """C source defining `int safe_div(int a, int b, int *out)`.

    If b is 0, or a is INT_MIN and b is -1 (the result would not fit), return 0
    and leave *out alone. Otherwise store a / b in *out and return 1.
    C division truncates toward zero: safe_div(-7, 2, &q) stores -3.
    """
    return """
#include <limits.h>

int safe_div(int a, int b, int *out) {
    if (b == 0) return 0;
    if (a == INT_MIN && b == -1) return 0;
    *out = a / b;
    return 1;
}
"""


if __name__ == "__main__":
    fields = ["char", "int", "char"]
    print("layout", fields, "->", struct_layout(fields))
    better = best_order(fields)
    print("best order", better, "->", struct_layout(better))
    src = "#include <stddef.h>\nstruct s { char a; int b; char c; };\nunsigned long size(void) { return sizeof(struct s); }\n"
    lib = cputools.compile_c(src)
    lib.size.restype = ctypes.c_ulong
    print("real sizeof from clang:", lib.size())
