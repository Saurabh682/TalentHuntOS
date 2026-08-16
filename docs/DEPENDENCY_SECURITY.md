# Dependency Security Decisions

Dependency audits are review gates, not automatic upgrade instructions. Run the raw audit
first so new findings are always visible:

```powershell
uv run pip-audit --progress-spinner off
```

## Active Exception: ChromaDB

- Advisory: `PYSEC-2026-311` / `CVE-2026-45829`
- Status: no patched Python release is identified by `pip-audit` as of 2026-08-14.
- Affected boundary: ChromaDB's network-accessible Python FastAPI server accepts a
  collection embedding configuration that can load untrusted remote model code.
- TalentHunt boundary: the app constructs only `chromadb.PersistentClient` inside the
  configured local data directory, disables anonymized telemetry, and does not launch or
  expose a Chroma HTTP server.
- Residual risk: a future code change could add a network client/server or pass untrusted
  embedding configuration. Chroma data is also a derived index and may be rebuilt.
- Required review: immediately before any Chroma upgrade and no later than 2026-11-12.

After reviewing the exception above, the accepted-risk audit is:

```powershell
uv run pip-audit --progress-spinner off --ignore-vuln PYSEC-2026-311
```

Do not add another ignored advisory without documenting its affected boundary, local
mitigation, residual risk, owner, and review date here.

## Removed Dependency

`llama-cpp-python` was removed from the application environment because TalentHunt uses an
OpenAI-compatible loopback model server and never imported the native Python package. This
also removes its vulnerable `diskcache` dependency and avoids unnecessary native build,
CPU, and storage cost.

## Approved Dependency: OpenPyXL

- Purpose: create real local XLSX analytics workbooks without an external office service.
- Boundary: TalentHunt creates new workbooks only; it does not load recruiter-supplied or
  downloaded workbooks with OpenPyXL.
- Data and network: workbook generation is local, requires no account, and performs no
  network request or telemetry upload.
- Guardrails: user-controlled text is written as inert cell values after formula-prefix
  neutralization; files remain in the fixed report directory and are size/checksum verified.
- Rollback: remove XLSX from the report action format enum, remove `openpyxl` from
  `pyproject.toml`, and regenerate `uv.lock`; CSV and PDF remain available.
- Tests: `tests/test_report_actions.py` opens generated files, checks expected sheets and
  values, and rejects formula injection.

## Approved Runtime: llama.cpp b10430 CPU x64

- Purpose: provide TalentHunt-owned local inference without LM Studio, Ollama, an account,
  an API key, or a paid service.
- License: MIT. The Windows CPU x64 release archive is pinned by version, exact size, and
  SHA-256 in `app/ai/embedded_manifest.json`.
- Packaging: the complete verified runtime directory is bundled. Required llama/ggml DLLs
  are never replaced by an arbitrary executable from PATH or another application.
- Network and privilege boundary: the server binds only to `127.0.0.1`, requires no elevated
  privileges, and performs no approved telemetry upload. TalentHunt stops only its own child.
- Integrity: safe extraction follows archive verification; an immutable installed-manifest
  hash protects per-file checksums and every launch performs full component verification.
- Rollback: stop the owned server, select External mode, and rebuild without this runtime.
  Recruiting data and action history do not depend on the inference executable.
- Review date: reverify the release, license, archive hash, and upstream maintenance before
  any runtime upgrade and no later than 2026-11-12.

## Approved Model: IBM Granite 4.1 3B GGUF Q4_K_M

- Purpose: broadly compatible default instruction and tool-calling model for local Copilot.
- License: Apache-2.0. The official IBM GGUF file is pinned to an immutable repository
  revision, exact size, quantization, and SHA-256 in `app/ai/embedded_manifest.json`.
- Distribution: weights are not embedded in the installer. The user explicitly starts the
  approximately 2.1 GB first-run download; a verified `.part` file can resume after Cancel.
- Resource boundary: embedded mode requires Windows x64 and at least 6 GB total RAM. Lite and
  Standard modes bound context, batch size, and CPU threads. No GPU is required or enabled.
- Authority boundary: model text and tool requests do not bypass scopes, resource locks,
  trusted confirmation, provider receipts, Action History, or Undo.
- Data boundary: after installation inference is loopback-only and offline. Prompts are not
  uploaded by the embedded runtime.
- Rollback: stop embedded AI, remove the verified model from private application storage, and
  use External or an explicitly configured cloud provider; recruiting records are unaffected.
- Review date: reverify the model card, license, checksum, and hardware benchmarks before any
  model change and no later than 2026-11-12.
