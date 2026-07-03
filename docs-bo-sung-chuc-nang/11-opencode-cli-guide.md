# OpenCode CLI Guide for Screen Watcher

> Last checked against the official OpenCode docs on 2026-07-03.
> References: [OpenCode Intro](https://opencode.ai/docs/), [CLI](https://opencode.ai/docs/cli/),
> [Config](https://opencode.ai/docs/config/), [Providers](https://opencode.ai/docs/providers/),
> [Server](https://opencode.ai/docs/server/).

## 1. Why OpenCode is only the middle layer

In this project, OpenCode CLI is not the "AI brain" by itself. It is the middle layer that lets
Screen Watcher call different LLM providers through one command-line interface.

```text
Screen Watcher Chat Orchestrator
  -> app.ai.opencode_adapter.OpenCodeAdapter
  -> opencode run --model <provider/model>
  -> OpenCode provider/auth/config layer
  -> Azure OpenAI | OpenAI | OpenRouter | Ollama/local model | other providers
```

This keeps the application independent from one provider SDK. If the team changes from
Azure OpenAI to OpenRouter or a local Ollama model, the intended change is config/env,
not rewriting the chat orchestration code.

## 2. Install OpenCode CLI

Official generic installer:

```bash
curl -fsSL https://opencode.ai/install | bash
```

Node.js install:

```bash
npm install -g opencode-ai
```

Windows options:

```powershell
choco install opencode
scoop install opencode
npm install -g opencode-ai
```

For Windows development, WSL is recommended by OpenCode for the smoothest terminal behavior.
If you stay on native PowerShell, the adapter in this repo still avoids the most common quoting
problem by sending prompts through stdin instead of putting long multiline prompts in argv.

Verify:

```bash
opencode --version
opencode --help
```

## 3. Connect a provider

Interactive login:

```bash
opencode auth login
opencode auth list
```

OpenCode stores provider credentials in its own auth/config area. The CLI can also read provider
keys from environment variables and project `.env` files. For this project, keep application-level
provider selection in `.chatbot.env` and non-secret runtime knobs in `config/rules.yaml`.

Common examples:

```bash
# OpenRouter
PROVIDER=OPENROUTER
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-4o-mini

# Azure OpenAI
PROVIDER=AZURE_OPENAI
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_MODEL=<deployment-name>
AZURE_OPENAI_API_VERSION=2024-06-01

# Local/Ollama-compatible endpoint
PROVIDER=LOCAL
LOCAL_LLM_ENDPOINT=http://localhost:11434/v1
LOCAL_LLM_MODEL=llama3.1
```

## 4. Core CLI commands

Start the terminal UI in the current project:

```bash
opencode
```

Initialize project instructions:

```text
/init
```

This creates an `AGENTS.md` file. Commit it when it contains useful project rules.

Run one non-interactive prompt:

```bash
opencode run "Explain how this project handles OCR and alert rules"
```

Select a model explicitly:

```bash
opencode run --model openrouter/openai/gpt-4o-mini "Summarize the latest watcher state"
opencode run --model azure/gpt-4o-mini "What failed in this OCR text?"
opencode run --model ollama/llama3.1 "Explain the rule matches"
```

List models:

```bash
opencode models
opencode models openrouter
opencode models --refresh
```

Manage sessions and cost/usage:

```bash
opencode session list
opencode stats
opencode export --sanitize
```

Run a headless OpenCode HTTP API server:

```bash
opencode serve
opencode run --attach http://localhost:4096 "Explain async/await"
```

By default, `opencode serve` listens on `127.0.0.1:4096`. It exposes OpenCode's
own HTTP API, not the Screen Watcher API. The API contract is available as an
OpenAPI 3.1 document at:

```text
http://localhost:4096/doc
```

Useful server endpoints include:

| Endpoint | Purpose |
| --- | --- |
| `GET /global/health` | Check server health and version. |
| `GET /provider` | List providers and connected provider state. |
| `GET /session` | List OpenCode sessions. |
| `POST /session` | Create a session. |
| `POST /session/{id}/message` | Send a message and wait for a response. |
| `GET /event` | Server-sent event stream. |
| `GET /doc` | OpenAPI 3.1 documentation/spec page. |

Use `OPENCODE_SERVER_PASSWORD` to protect `serve` and `web` with HTTP basic auth:

```bash
OPENCODE_SERVER_PASSWORD=your-password opencode serve
```

Start the web interface:

```bash
opencode web
```

Upgrade:

```bash
opencode upgrade
```

## 5. How this repo calls OpenCode

The implementation is in:

- `app/ai/opencode_adapter.py`
- `app/ai/provider_config.py`
- `tests/test_opencode_adapter.py`

The adapter builds this command shape:

```bash
opencode run --model <provider/model>
```

This repo currently uses the CLI subprocess path above. It does not call
OpenCode's HTTP server API directly. That is a possible future integration path:
run `opencode serve`, create/reuse sessions through the HTTP API, and call
`/session/{id}/message` instead of spawning `opencode run` for each request.

OpenCode's own source also treats the server API as a typed contract. In the
OpenCode repo, `packages/opencode/src/server/server.ts` exposes an `openapi()`
helper that returns `OpenApi.fromApi(PublicApi)`, and `PublicApi` is assembled
from `packages/opencode/src/server/routes/instance/httpapi/public.ts`.

By default, the prompt is passed through stdin:

```text
stdin = rendered watcher prompt
argv  = ["opencode", "run", "--model", "<provider/model>"]
```

This is intentional. On Windows, the npm `opencode.cmd` shim can mangle multiline prompts when
they are passed as command arguments, and command-line length is limited. Stdin is safer for
large OCR context blocks.

The adapter also:

- runs the CLI in `data/opencode_workdir` instead of the project root;
- applies the configured timeout;
- strips ANSI color codes from stdout/stderr;
- normalizes success, timeout, missing binary, empty output, and non-zero exit into `AIResponse`;
- never passes API keys directly to the subprocess.

## 6. Enable OpenCode engine in Screen Watcher

In `config/rules.yaml`, set:

```yaml
ai:
  provider: openrouter
  engine: opencode
  timeout_seconds: 120
  max_context_chars: 6000
  mock: false
```

If `engine` is missing from your local `config/rules.yaml`, add it under `ai`.

You can also switch live with an environment variable:

```powershell
$env:CHAT_ENGINE = "opencode"
```

Back to direct SDK mode:

```powershell
$env:CHAT_ENGINE = "sdk"
```

## 7. Model mapping used by the adapter

The project's provider name is mapped to the OpenCode `provider/model` format:

| Project provider | OpenCode model prefix | Example |
| --- | --- | --- |
| `openai` | `openai` | `openai/gpt-4o-mini` |
| `azure_openai` | `azure` | `azure/gpt-4o-mini` |
| `openrouter` | `openrouter` | `openrouter/openai/gpt-4o-mini` |
| `local` | `ollama` | `ollama/llama3.1` |

Override the final OpenCode model string when needed:

```powershell
$env:OPENCODE_MODEL = "azure/my-gpt-4o-mini-deployment"
```

Useful adapter env vars:

| Variable | Purpose |
| --- | --- |
| `OPENCODE_BIN` | Absolute path to the OpenCode executable if it is not on `PATH`. |
| `OPENCODE_MODEL` | Full `provider/model` override. |
| `OPENCODE_PROMPT_MODE` | `stdin` by default; set `arg` only for debugging the literal CLI form. |
| `CHAT_ENGINE` | Runtime switch: `sdk` or `opencode`. |

## 8. Recommended smoke test

First test OpenCode outside the app:

```bash
opencode auth list
opencode models --refresh
opencode run --model openrouter/openai/gpt-4o-mini "Reply with: opencode-ok"
```

Then test the project adapter path:

```powershell
$env:CHAT_ENGINE = "opencode"
$env:OPENCODE_MODEL = "openrouter/openai/gpt-4o-mini"
python -m pytest tests/test_opencode_adapter.py
```

If the unit tests use the fake CLI fixture, they do not prove your real provider credentials work.
They prove command construction, timeout handling, stdout/stderr parsing, and error normalization.
Use `opencode run ...` for the real credential smoke test.

## 9. Troubleshooting

`OpenCode CLI is not installed`

- Run `opencode --version`.
- If it works in your terminal but not in the app, set `OPENCODE_BIN` to the full executable path.

`OpenCode CLI failed (exit N): AuthError...`

- Run `opencode auth login`.
- Confirm the selected model exists with `opencode models --refresh`.
- Confirm `.chatbot.env` and `OPENCODE_MODEL` do not point to different providers by accident.

Empty reply

- Re-run the prompt directly with `opencode run --model ...`.
- Try another model.
- Check whether provider quota/rate limit is returning a non-standard empty response.

Timeout

- Increase `ai.timeout_seconds` in `config/rules.yaml`.
- Reduce `ai.max_context_chars` if OCR context is too large.
- Prefer a faster model for chatbox use.

Windows quoting or garbled multiline prompt

- Keep the default `OPENCODE_PROMPT_MODE=stdin`.
- Avoid `OPENCODE_PROMPT_MODE=arg` except for adapter tests or debugging.

## 10. Operational notes

- Do not commit API keys, provider tokens, or real auth files.
- Prefer `opencode export --sanitize` before sharing sessions.
- Keep `opencode serve` or `opencode web` bound to localhost unless you have explicit auth and network controls.
- For project-specific behavior, prefer `AGENTS.md` and `opencode.json` over ad hoc prompt text.
- For Screen Watcher runtime behavior, keep timeout/context/provider knobs in `config/rules.yaml` and `.chatbot.env`.
