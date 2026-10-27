---
title: "Functions, the stack, and the System V calling convention"
slug: 14-functions-and-the-calling-convention
part: "Part 2 — x86-64 assembly"
summary: Write recursive functions and callbacks in assembly, and keep the stack and the callee-saved registers correct.
minutes: 65
gpu: false
objectives:
  - Explain what call and ret do to the stack and the return address.
  - Say which registers a function must preserve and which a call may overwrite.
  - Write a prologue and epilogue that save registers and keep rsp 16-byte aligned at every call.
  - Write recursive functions and call a function pointer from assembly.
prereqs:
  - 13-memory-and-arrays-in-assembly
exercise: 14-functions-and-the-calling-convention
---

# Functions, the stack, and the System V calling convention

A function that never calls another function is easy. It uses registers freely and returns. The trouble starts when a function calls another one, because both want the same 16 registers. What stops the callee from destroying a value the caller was keeping? Where does the callee return to, if the caller itself was called from somewhere else?

The answer is a set of rules every compiler and every assembly programmer follows. The return address goes on the stack. Some registers belong to the caller and may be overwritten by any call. Others belong to the callee, which must put them back. The stack pointer sits on a 16-byte boundary at every call. Together these rules are the *calling convention*, and they are why code from different compilers, languages, and decades can call each other.

In this lesson you write recursive `fact` and `fib`, a function that calls a callback through a pointer, and a function that reads a seventh argument from the stack. The checks use a special harness that catches rule-breaking even when your answers are correct.

## What you already know

- The stack is a region of memory that grows toward lower addresses, and `push` and `pop` move the stack pointer `rsp` (lesson 7).
- `call` saves a return address, and `ret` jumps back to it (lesson 7).
- The first six integer arguments arrive in `rdi`, `rsi`, `rdx`, `rcx`, `r8`, and `r9`, and the result goes in `rax` (lesson 11).
- Loops use `cmp` and conditional jumps, with local labels (lesson 12).
- `[reg + displacement]` reads memory relative to a pointer (lesson 13).

## call, ret, push, and pop

Two instructions do all the work of a function call.

- `call target` pushes the address of the next instruction onto the stack, then jumps to `target`.
- `ret` pops an address off the stack and jumps to it.

Pushing means "subtract 8 from `rsp`, then store 8 bytes at `[rsp]`". Popping means "load 8 bytes from `[rsp]`, then add 8 to `rsp`". So `push rbx` is the same as these two lines:

```asm
    sub rsp, 8
    mov [rsp], rbx
```

When a function starts, `[rsp]` holds its return address. That is the entire contract of `ret`: it trusts that `[rsp]` points at a return address. If your function changes `rsp` and does not put it back before `ret`, the CPU jumps to garbage.

> [!KEY]
> At every `ret`, `rsp` must hold exactly the value it had when the function was entered. Every `push` needs its `pop`, and every `sub rsp, n` needs its `add rsp, n`.

## Who owns which register

If `main` keeps a loop counter in `rcx` and calls a function, can the function use `rcx`? Two answers are possible, and either works if everyone agrees. System V splits the 16 registers into two groups:

| Group | Registers | Rule |
|---|---|---|
| Caller-saved (scratch) | `rax`, `rcx`, `rdx`, `rsi`, `rdi`, `r8` to `r11` | A call may overwrite them. If the caller needs a value after the call, it saves it itself. |
| Callee-saved | `rbx`, `rbp`, `r12` to `r15` | A function that changes one must restore it before returning. |

Think of borrowing a colleague's desk. Some drawers are for scratch paper, and you may leave a mess. Others hold the owner's things, and if you use one, you put everything back before you leave.

The consequence for your code: a value that must survive a `call` lives either in a callee-saved register or in your own stack space. In `fact(n)`, you need `n` *after* `fact(n - 1)` returns. The register `rdi` holds `n` at entry, but the callee will overwrite `rdi` with its own argument. So you copy `n` into `rbx`, and because `rbx` is callee-saved, you save the caller's `rbx` first.

## Prologue and epilogue

The code at the start of a function that saves registers and makes room is the *prologue*. The code at the end that undoes it is the *epilogue*. Here is the shape for a function that needs one callee-saved register:

```asm
    push rbx            # prologue: save the caller's rbx
    ...                 # body: use rbx freely, and call other functions
    pop rbx             # epilogue: restore it, in reverse order of the pushes
    ret
```

With several registers, pop them in the reverse of the order you pushed them, because the stack returns the last item first.

## Stack alignment

There is one more rule. At the moment of a `call` instruction, `rsp` must be a multiple of 16. The reason is performance and correctness: vector instructions such as `movaps` require 16-byte-aligned memory, and library code like `printf` uses them for local data. A misaligned call can work for months and then crash inside a library function.

Count it. A function is entered by a `call` from an aligned `rsp`, so the call pushed 8 bytes, and at entry `rsp` is 8 more than a multiple of 16. Each `push` subtracts another 8. The next table shows the pattern:

| State | `rsp` modulo 16 | Safe to `call` here? |
|---|---|---|
| At entry (return address pushed) | 8 | No |
| After 1 push | 0 | Yes |
| After 2 pushes | 8 | No: add `sub rsp, 8` |
| After 3 pushes | 0 | Yes |
| After 4 pushes | 8 | No: add `sub rsp, 8` |

An odd number of pushes lines up. An even number needs `sub rsp, 8` of padding, and a matching `add rsp, 8` before the pops.

## Recursion: fact

A recursive function calls itself. Each active call needs its own `n`, and the stack provides one slot per call. Here is factorial, where `n <= 1` returns 1 and everything else returns `n * fact(n - 1)`:

```asm
    .globl fact
fact:
    cmp rdi, 1
    jg .Lrecurse
    mov eax, 1              # base case: return 1
    ret
.Lrecurse:
    push rbx                # save caller's rbx; also aligns rsp for the call
    mov rbx, rdi            # keep n across the call
    lea rdi, [rdi - 1]      # argument = n - 1
    call fact               # rax = fact(n - 1)
    imul rax, rbx           # rax = n * fact(n - 1)
    pop rbx
    ret
```

The base case needs no frame, so it returns before the `push`. Trace `fact(3)`. Each level pushes a return address (by `call`) and a saved `rbx`:

```text
stack (high addresses at top)

  return into caller            <- fact(3) entered
  saved rbx (caller's value)    <- fact(3) pushed
  return into fact(3)           <- fact(3) called fact(2)
  saved rbx (holds 3)           <- fact(2) pushed
  return into fact(2)           <- fact(2) called fact(1)
                                   fact(1) hits the base case: no push
  rax = 1
```

Then the returns unwind. In `fact(2)`, `rbx` is 2 and `rax` is 1, so `imul` gives 2. In `fact(3)`, `rbx` is restored from the stack as 3, and `rax = 3 × 2 = 6`. Each level costs 16 bytes, so a default 8 MB stack holds about half a million levels before the program overflows it.

The Fibonacci function calls itself twice and needs two values to survive: `n` for the second call, and `fib(n - 1)` while the second call runs. It uses `rbx` and `r12`. Two pushes leave `rsp` misaligned, so it adds padding:

```asm
.Lrecurse:
    push rbx
    push r12
    sub rsp, 8              # padding: two pushes left rsp 8 off a multiple of 16
    mov rbx, rdi            # rbx = n
    lea rdi, [rbx - 1]
    call fib                # rax = fib(n - 1)
    mov r12, rax            # keep it across the next call
    lea rdi, [rbx - 2]
    call fib                # rax = fib(n - 2)
    add rax, r12
    add rsp, 8
    pop r12
    pop rbx
    ret
```

The base case, `n < 2`, returns `n` itself, since `fib(0) = 0` and `fib(1) = 1`. This version makes about 240,000 calls for `fib(25)`, and the checks run in a fraction of a second.

## Calling a function through a pointer

A *callback* is a function you receive as an argument and call later. In C, `long apply_twice(long (*fn)(long), long x)` takes a function pointer. At the machine level a function pointer is the address of its first instruction. You call it with a register: `call rbx` jumps to the address in `rbx` and pushes a return address, exactly like a call to a label.

```asm
    .globl apply_twice
apply_twice:
    push rbx
    mov rbx, rdi            # fn arrives in rdi; keep it for the second call
    mov rdi, rsi            # fn's argument is x
    call rbx                # rax = fn(x)
    mov rdi, rax
    call rbx                # rax = fn(fn(x))
    pop rbx
    ret
```

The checks give you a callback written to be hostile in two ways. It records whether `rsp` was aligned when it was called. And before it returns, it overwrites every caller-saved register (`rcx`, `rdx`, `rsi`, `rdi`, and `r8` to `r11`) with -1. A loop that keeps its counter in `rcx` across the call breaks at once. That is legal behaviour for a callee, and real functions do it constantly.

## Stack arguments and the frame

Only six integer arguments fit in registers. A seventh goes on the stack. The caller pushes it before the `call`, so at the callee's entry it sits directly above the return address:

```text
  [rsp + 16]  eighth argument (if any)
  [rsp + 8]   seventh argument
  [rsp]       return address       <- rsp at entry
```

So `sum7` adds the six register arguments and then `[rsp + 8]`, as long as it has not pushed anything first. After a `push`, the offset grows by 8 for each push.

A *stack frame* is the stack space one function call uses: its return address, its saved registers, and its local variables. Many functions create locals with `sub rsp, 16` and refer to them as `[rsp + 0]` or `[rsp + 8]`. At `-O0`, compilers also keep the *frame pointer*: they run `push rbp; mov rbp, rsp`, and then locals and arguments sit at fixed offsets from `rbp`, whatever `rsp` does. Each saved `rbp` points to the previous frame's, which forms a chain. A debugger follows that chain to print a backtrace.

## Try it on your own machine

1. Compile `long fact(long n) { return n <= 1 ? 1 : n * fact(n - 1); }` with `clang -O0 -S -masm=intel -fno-asynchronous-unwind-tables`. Find `push rbp`, `mov rbp, rsp`, the `call`, and the epilogue. Then use `-O2` and see whether the compiler turns the recursion into a loop.
2. Run `ulimit -s` in a shell. It prints your stack limit in kilobytes, usually 8192.
3. If `gdb` is installed, run a small program under it, stop in a function, and type `bt` for a backtrace and `info registers rsp rbp`. This needs gdb, which is not part of clang.
4. Open https://godbolt.org and write a function that calls another with seven arguments. Look for the `push` before the `call`: that is the seventh argument going on the stack.

## Build it step by step

Fill in `starter.py` in this order. The checks run your code through a harness that fills `rbx`, `rbp`, and `r12` to `r15` with known values, calls you, and then tells you which of them changed.

1. `fact_asm()` defines `fact(n)`. Handle `n <= 1` first, save `rbx`, call yourself, multiply, and restore. The check reads your text and fails if there is no `call fact`. The common mistake is using `rbx` without saving it: your answers are correct, and the harness reports that you changed `rbx`.
2. `fib_asm()` defines `fib(n)`, with two recursive calls. Keep `n` and the first result in callee-saved registers, and keep `rsp` aligned. The common mistake is a missing `pop`, which sends `ret` to a wrong address and crashes.
3. `apply_twice_asm()` defines `apply_twice(fn, x)`. Save `fn` in a callee-saved register and call it twice. The check reports a call made with `rsp` misaligned. Count your pushes.
4. `sum_map_asm()` defines `sum_map(fn, n)`, which adds `fn(0)`, `fn(1)`, up to `fn(n - 1)`. The loop counter, the total, `fn`, and `n` all live across calls, so they need four callee-saved registers. The common mistake is keeping the counter in `rcx`, because the callback overwrites it and the loop hangs.
5. `sum7_asm()` defines `sum7(a, b, c, d, e, f, g)`. Read `g` from `[rsp + 8]`. This one needs no pushes, so the offset stays 8.

## Where this breaks

- **Stack overflow.** Infinite or very deep recursion uses the stack until it runs into an unmapped page, and the process dies with `SIGSEGV`. Real programs limit recursion depth, or turn tail calls into loops, as clang does at `-O2`.
- **Overwritten return addresses.** A buffer on the stack that a program overruns can overwrite a saved return address, so `ret` jumps where an attacker chooses. Defences include stack canaries (a guard value checked before `ret`), non-executable stacks, and address randomisation.
- **Variadic functions.** `printf` takes a varying number of arguments. The convention requires `al` to hold the number of vector registers used. Forgetting it is a classic assembly bug.
- **Different ABIs.** Windows x64 passes four arguments in registers, keeps `rsi` and `rdi` callee-saved, and requires 32 bytes of "shadow space" above the return address. Code that follows System V breaks there.
- **The red zone.** System V lets a leaf function (one that calls nothing) use 128 bytes below `rsp` without moving `rsp`. A signal handler would not trample it, because the kernel skips that area. Your functions that call others must not rely on it.
- **Struct arguments and floats.** Small structs travel in registers by classification rules, and `float` and `double` arguments go in `xmm0` to `xmm7`. The full rules are in the ABI document.
- **Unwinding information.** Exceptions and debuggers need tables that describe each function's frame (`.cfi` directives). Hand-written assembly in this course leaves them out, which is fine for a C caller and not for debuggers or C++ exceptions.

## Further reading

- [The System V AMD64 ABI](https://gitlab.com/x86-psABIs/x86-64-ABI) is the specification of everything in this lesson, in section 3.2 (function calling sequence).
- [Agner Fog's "Calling conventions for different C++ compilers and operating systems"](https://www.agner.org/optimize/calling_conventions.pdf) compares System V and Windows and lists which registers each preserves.
- [Compiler Explorer](https://godbolt.org) shows the prologue, epilogue, and argument passing for any function you type. Add `-fno-omit-frame-pointer` to see the `rbp` chain at `-O2`.
- [Felix Cloutier's x86 reference](https://www.felixcloutier.com/x86/) documents `call`, `ret`, `push`, and `pop`, including exactly what each does to `rsp`.
- [Computer Systems: A Programmer's Perspective](https://csapp.cs.cmu.edu/) chapter 3, "Procedures", walks through stack frames and recursion with the same register conventions.

## The exercise

You write five functions in assembly: `fact_asm`, `fib_asm`, `apply_twice_asm`, `sum_map_asm`, and `sum7_asm`. Each returns Intel-syntax text with the symbol named in its docstring (`fact`, `fib`, `apply_twice`, `sum_map`, and `sum7`).

The checks call your code through a small assembly harness, in a child process. It sets `rbx`, `rbp`, and `r12` to `r15` to known values, calls your function, and reports any register you changed. It supplies callbacks that note a misaligned stack and clobber every caller-saved register. A wrong value, a changed register, a misaligned call, a crash, and a hang each produce a different message that names the input and the rule you broke.
