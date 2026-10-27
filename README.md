# CPUs, assembly, and LLVM

A hands-on course in low-level computing, from zero. Twenty-five lessons take a
reader who has never studied how a computer works to the point where they can
read and write x86-64 assembly, explain what a CPU does with each instruction
and why some code is fast, follow C down to machine code, and write, optimize,
and generate LLVM IR.

The app is a reader on the left, a code editor on the right, a Run button, and a
Check button. Every lesson ends in an exercise; Check runs the reader's code
against tests that say exactly what is right and what is not. Early exercises
build models in Python: number encodings, an adder and ALU, a toy CPU, a RISC-V
encoder, a pipeline, a cache, and a branch predictor. From Part 2 on, the reader
writes real x86-64 assembly, C, and LLVM IR, and the checks hand it to clang 19,
`opt`, `llc`, and `lli` (through `backend/app/runner/cputools.py`) and call the
result.

## Who it is for

Anyone who can read a little code and is curious how a computer works. No
background in hardware, assembly, C, or compilers is assumed, and Part 0 teaches
the Python the course needs.

## Layout

| Path | What is there |
| --- | --- |
| `backend/app/` | FastAPI app: content loader, auth, progress database, local runner |
| `backend/app/runner/` | `local.py` runs a submission in a limited subprocess; `harness.py` and `cpucheck.py` run and check it; `cputools.py` wraps clang and the LLVM tools |
| `frontend/` | React and Vite single-page app (reader, editor, check console) |
| `content/lessons/` | One Markdown file per lesson, with YAML front matter |
| `content/exercises/` | One directory per exercise: `meta.json`, `starter.py`, `solution.py`, `tests.py` |
| `docs/` | `CONTENT_CONTRACT.md` (the content format) and `CURRICULUM.md` (the plan) |
| `scripts/` | `check_content.py` validates content, `harness.sh` and `Dockerfile.toolchain` run exercises with the runner's toolchain, `check_math.mjs` compiles lesson math, `deploy.sh` redeploys |
| `Dockerfile`, `docker-compose.yml` | The single container that serves the API and the built frontend |
| `Caddyfile.example` | The reverse proxy block for the deployment |

## The curriculum

0. **Getting started**: the Python you need; bits, binary, and hex; integers,
   two's complement, and overflow; logic gates and adders.
1. **How a CPU works**: a toy CPU; instruction encoding (RISC-V); memory, the
   stack, and endianness; pipelining; caches; branch prediction and
   out-of-order execution.
2. **x86-64 assembly**: first assembly; flags and control flow; memory and
   arrays; functions and the System V calling convention.
3. **From C to machine code**: C for the curious; how a compiler turns C into
   assembly; object files, linking, and loading.
4. **Compilers and LLVM IR**: lexing and parsing; LLVM IR basics; control flow
   and SSA; memory in IR and `mem2reg`; optimization passes; generating LLVM IR
   from your own language.
5. **The back end and performance**: instruction selection and register
   allocation; performance, vectorization, and SIMD.

The full lesson list with exercise sketches is in `docs/CURRICULUM.md`.

## Run it locally

You need Python 3.12, Node 22, and clang and LLVM on an x86-64 Linux machine
(Debian or Ubuntu: `apt install clang llvm`). Without them, use the toolchain
image for exercises (below).

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt pyyaml

cd frontend && npm ci && npm run build && cd ..
```

Authentication is by headers from a trusted proxy, so for local use set a secret
and send the headers yourself, or put the app behind any proxy that does:

```sh
export SSO_PROXY_SECRET=dev-secret
uvicorn backend.app.main:app --reload
curl -H 'X-SSO-Proxy: dev-secret' -H 'Remote-User: me' localhost:8000/api/lessons
```

For frontend work, `npm run dev` in `frontend/` serves the UI on port 5173 and
proxies `/api` to port 8000. A browser extension that adds the two headers makes
the dev server usable.

To validate content, build the toolchain image once, then run the checker. It
runs every exercise's checks against its solution and its starter, inside the
image when this machine has no clang:

```sh
docker build -t cpu-toolchain:local -f scripts/Dockerfile.toolchain scripts
python3 scripts/check_content.py
scripts/harness.sh check content/exercises/<id> content/exercises/<id>/solution.py
```

`node scripts/check_math.mjs` compiles the lesson math after `npm ci` in
`frontend/`.

## How a run works

`POST /api/run` copies the reader's code and the exercise's `tests.py` into a
scratch directory and starts `harness.py` as a separate process in its own
process group, under CPU-time, file-size, and process-count limits. The
reader's assembly, C, and IR are compiled by clang and LLVM inside that process. Output streams back as server-sent events.
When the wall clock runs out the whole group is killed. This is a resource
boundary, not a security boundary: the app is for signed-in readers only.

## Authentication

There is no login form. Caddy forwards every request through Authelia and, on
success, sets `Remote-User` and `X-SSO-Proxy`. The app trusts `Remote-User` only
when `X-SSO-Proxy` equals `SSO_PROXY_SECRET`. `SSO_USERS` (`portal:progress`
pairs, comma separated) maps portal usernames to progress identities.

## Deploy

The app is one container (`docker-compose.yml`, project `cpu`, container `cpu`),
joined to the external `edge` network and published only on
`127.0.0.1:8099`. Caddy terminates TLS for `cpu.ifkash.dev` and proxies
`cpu:8000`, behind Authelia forward auth, and sends `X-SSO-Proxy`. See
`Caddyfile.example`. Copy `.env.example` to `.env`, fill it in, then:

```sh
./scripts/deploy.sh     # git pull, then docker compose up -d --build
```

Progress lives in the `cpu-data` volume.

## Licence

See `LICENSE`.
