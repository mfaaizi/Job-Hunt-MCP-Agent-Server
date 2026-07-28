# job-agent MCP Server

A multi-agent job-hunt system exposed as an MCP (Model Context Protocol) server, built with FastMCP.
Runs locally, driven by local Ollama models (e.g. Qwen3, MiniMax) through an MCP client.

## Architecture

```
You (chat)
   -> MCP client (ollmcp)
        -> Ollama (qwen3 / minimax) -- does the reasoning, decides which tool to call
        -> job-agent MCP server (this project) -- executes the tool, returns the result
   <- response
```

Ollama does not natively speak MCP, so a bridge client (`ollmcp`) sits between the model and this
server. See "Running the server" below.

## Project status

| Component                                         | Status         |
|----------------------------------------------------|----------------|
| Project scaffold                                    | Done           |
| Resume parser (PDF/DOCX -> normalized JSON)          | Done           |
| SQLite schema (jobs / matches / applications)        | Done           |
| JSearch integration (job search)                     | Not started    |
| Matcher agent (embeddings)                            | Not started    |
| Writer agent (tailor resume / cover letter)            | Not started    |
| Pipeline tracking tools                                | Not started    |

## Project structure

```
job-agent-mcp/
├── requirements.txt
├── .env.example
├── data/
│   ├── resumes/        <- put your resume PDF/DOCX here; normalized JSON is stored here too
│   └── db/               <- SQLite database file
├── scripts/
│   └── test_tools.py     <- call MCP tools directly, without a client, for debugging
└── server/
    ├── config.py          <- loads .env, resolves storage paths
    ├── main.py              <- FastMCP entry point, registers all tools
    ├── tools/                <- MCP tool definitions (the functions the model calls)
    ├── agents/                <- internal logic tools call into (parsing, matching, writing)
    ├── models/                 <- Pydantic schemas
    └── db/                      <- SQLModel table definitions + session management
```

## Setup

### 1. Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) installed and running locally

### 2. Install Ollama + pull a model

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b   # or whatever model you're using
ollama list                # confirm it's there
```

### 3. Set up the project

```bash
cd job-agent-mcp
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

`sentence-transformers` (used by the matcher agent, not yet wired in) pulls in `torch`, which is a
few GB. Make sure you have disk space free.

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

| Variable            | Set to                                              | Needed now? |
|----------------------|------------------------------------------------------|-------------|
| `JSEARCH_API_KEY`      | leave as placeholder                                  | not yet — JSearch tool isn't built |
| `JSEARCH_API_HOST`      | leave default                                          | not yet |
| `OLLAMA_HOST`             | leave default unless Ollama runs elsewhere              | yes |
| `OLLAMA_MODEL`             | must exactly match a tag from `ollama list` (e.g. `llama3.2:3b`) | yes |
| `DATABASE_PATH`             | leave default                                            | yes |
| `RESUME_STORAGE_DIR`          | leave default                                              | yes |
| `EMBEDDING_MODEL`              | leave default                                                | not yet — matcher isn't built |

### 5. Put your resume in place

```bash
cp /path/to/your_resume.pdf data/resumes/
```

## Running the server

### Option A — Manual sanity check (no client, just Python)

Quick way to confirm the server boots and tools import cleanly:

```bash
python -m server.main
```

Or test tools directly as plain function calls (bypasses MCP entirely, fastest way to debug the
resume parser in isolation):

```bash
python scripts/test_tools.py
```

### Option B — Real usage, through an MCP client (ollama-mcp-bridge)

This is the actual way you'll use the system day to day — natural language in, the model decides
which tool to call.

> **Note on client choice**: `ollmcp` (a TUI client) does not work on Windows — it depends on
> `tty`/`termios`, which are POSIX-only and don't exist on Windows Python at all. We use
> **`ollama-mcp-bridge`** instead: a lightweight FastAPI proxy that sits in front of Ollama and
> injects MCP tools into `/api/chat`. Since it's a proxy, not a terminal UI reading raw keystrokes,
> it works identically on Windows, macOS, and Linux.

**Install the bridge:**

```bash
pip install ollama-mcp-bridge
```

**Config file** — `mcp-config.json` (already included in this project root):

```json
{
  "mcpServers": {
    "job-agent": {
      "command": "python",
      "args": ["-m", "server.main"]
    }
  }
}
```

**Run the bridge** (from the project root, venv active):

```bash
ollama-mcp-bridge --config mcp-config.json
```

This starts on `http://localhost:8000`, loads the job-agent MCP server, and connects to Ollama at
`http://localhost:11434`.

**Chat with it — two ways:**

*Option A — keep using the `ollama` CLI you already know, just point it at the bridge instead of
directly at Ollama:*

```bash
set OLLAMA_HOST=http://localhost:8000        # Windows (cmd)
# export OLLAMA_HOST=http://localhost:8000   # macOS/Linux

ollama run llama3.2:3b
```

The bridge transparently proxies every endpoint except `/api/chat` — and that's exactly the one
that gets MCP tools injected — so this behaves like a normal `ollama run` session, just now
tool-aware.

*Option B — direct API test with curl, useful for a first sanity check:*

```bash
curl -X POST "http://localhost:8000/api/chat" -H "Content-Type: application/json" -d "{\"model\": \"llama3.2:3b\", \"messages\": [{\"role\": \"user\", \"content\": \"What tools are available?\"}]}"
```

If it lists `ping`, `parse_resume`, `get_parsed_resume`, `list_resumes` — the whole chain (bridge ->
Ollama -> your MCP server) is wired correctly.

**First real test — confirm the wiring works before testing real tools:**

```
ping the server
```

Should return: `job-agent MCP server is alive.`

**Then try the resume parser:**

```
parse my resume at data/resumes/your_resume.pdf
```

Note: `parse_resume` internally makes its own separate call to Ollama (via `cv_structurer.py`) to
structure the resume text into JSON. So one request involves two rounds of model reasoning: the
outer `ollmcp` model deciding to call the tool, and the tool's own internal Ollama call doing the
structuring. Both can point at the same Ollama instance — that's expected, not a bug.

## Design notes

- **`get_active_cv()`** (in `server/agents/cv_store.py`) is the only interface other agents use to
  read resume data. The matcher and writer agents (once built) will never touch the original
  PDF/DOCX or call the parser directly.
- Resume bullets are extracted **verbatim**, not paraphrased, during parsing — this matters because
  the writer agent will tailor these later, and we don't want compounding rewrites drifting from
  the original wording.
- The JSON schema (`server/models/resume.py`) has an `extra_sections` catch-all field so future
  resume changes (certifications, publications, etc.) don't require a schema migration.
- `Job.external_job_id` is unique-indexed in SQLite to dedupe repeated JSearch results.
