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
| `backend/app/` | FastAPI app: content loader, auth, progress database, local runner, MCP server (`mcp_server.py`, `mcp_tokens.py`) |
| `backend/app/runner/` | `local.py` runs a submission in a limited subprocess; `harness.py` and `cpucheck.py` run and check it; `cputools.py` wraps clang and the LLVM tools |
| `frontend/` | React and Vite single-page app (reader, editor, check console) |
| `content/lessons/` | One Markdown file per lesson, with YAML front matter |
| `content/exercises/` | One directory per exercise: `meta.json`, `starter.py`, `solution.py`, `tests.py` |
| `backend/tests/` | Unit tests for the MCP server and its tokens |
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

To run the backend unit tests, which don't need clang:

```sh
python -m unittest discover -s backend/tests -t .
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

## MCP server for AI agents

The app serves a [Model Context Protocol](https://modelcontextprotocol.io)
server at `https://cpu.ifkash.dev/mcp`, over the Streamable HTTP transport. An
agent such as Claude Code can use it to read the course and work through it as
you.

The server exposes the following tools:

- `course_overview`, `list_lessons`, `get_lesson`, and `search` for the
  syllabus, lesson text, and full-text search over lessons, exercises, and
  course documents.
- `list_exercises`, `get_exercise`, and `get_solution` for an exercise's brief,
  hints, starter code, checks, and worked solution.
- `get_runner_info` for the runner's limits and which of clang and the LLVM
  tools it finds.
- `get_document` for `docs/CURRICULUM.md` and `docs/CONTENT_CONTRACT.md`.
- `get_progress`, `get_run_history`, `list_drafts`, `get_draft`, `save_draft`,
  and `set_progress` for your progress, runs, and drafts.
- `run_exercise`, which runs or checks code the same way the editor's **Run**
  and **Check** buttons do.

Lessons are also resources, at `cpu://lessons/SLUG`. Reading a lesson through
the server doesn't mark it started.

An agent can't complete the Authelia sign-in, so Caddy routes `/mcp` without
forward auth, and the server requires a bearer token instead. A token acts as
the reader who owns it. The server ignores the `Remote-User` and `X-SSO-Proxy`
headers.

**Caution:** A token can run code in the container, the same as a signed-in
reader. Treat it like a password, and revoke it when you no longer use it.

### Get a token

To create a token, do one of the following:

- On the site, open **Agent access** in the sidebar, at
  `https://cpu.ifkash.dev/agents`. Enter a name and click **Create token**. The
  page shows the token once, with ready-to-copy client configurations.
- On the VM, run the command line in the container:

  ```bash
  docker exec cpu python -m backend.app.mcp_tokens create USERNAME --name NAME
  ```

  Replace the following:

  - `USERNAME`: the reader the token acts as, after `SSO_USERS` mapping, for
    example `enderboi`.
  - `NAME`: a label that tells you where the token is used, for example
    `laptop`.

To see or revoke tokens on the VM, run
`docker exec cpu python -m backend.app.mcp_tokens list` or
`docker exec cpu python -m backend.app.mcp_tokens revoke ID`. The server stores
only a SHA-256 hash of each token, so a lost token can't be recovered; revoke
it and create another.

### Connect a client

To connect Claude Code, complete the following steps:

1. Put the token in an environment variable:

   ```bash
   export TOKEN=TOKEN_VALUE
   ```

   Replace `TOKEN_VALUE` with the token, which starts with `cpumcp_`.

2. Add the server:

   ```bash
   claude mcp add --transport http cpu https://cpu.ifkash.dev/mcp \
     --header "Authorization: Bearer $TOKEN"
   ```

For a client that reads an `mcpServers` configuration file, add the following
entry:

```json
{
  "mcpServers": {
    "cpu": {
      "type": "http",
      "url": "https://cpu.ifkash.dev/mcp",
      "headers": {
        "Authorization": "Bearer TOKEN_VALUE"
      }
    }
  }
}
```

The server is stateless and answers with plain JSON, so it needs no session
and works through a proxy that buffers responses. A `run_exercise` call returns
when the run finishes, which can take up to the exercise's timeout.

## Deploy

The app is one container (`docker-compose.yml`, project `cpu`, container `cpu`),
joined to the external `edge` network and published only on
`127.0.0.1:8099`. Caddy terminates TLS for `cpu.ifkash.dev` and proxies
`cpu:8000`, behind Authelia forward auth, and sends `X-SSO-Proxy`. See
`Caddyfile.example`, which also routes `/mcp` past forward auth. Copy
`.env.example` to `.env`, fill it in, then:

```sh
./scripts/deploy.sh     # git pull, then docker compose up -d --build
```

Progress lives in the `cpu-data` volume.

## Licence

See `LICENSE`.
