# Local Quality Workflow

The quality workflow is free, local, and review-first. Checks do not upload source code,
candidate records, credentials, or reports.

## Setup

```powershell
uv sync --group dev
npm install
uv run pre-commit install
```

`npm install` is used only for the pinned local `axe-core` audit package. Node is not part
of the TalentHunt runtime.

## Fast Checks

```powershell
uv run ruff check app tests scripts --select E9,F63,F7,F82
uv run pytest
python ..\scripts\validate_technology_catalog.py --check-markdown
```

The commit gate starts with Ruff's syntax and undefined-name correctness rules. The wider
lint and format scans below expose existing cleanup work without rewriting unrelated code:

```powershell
uv run ruff check app tests scripts
uv run ruff format --check app tests scripts
```

Coverage is diagnostic and does not replace behavior assertions:

```powershell
uv run pytest --cov=app --cov-report=term-missing
```

## Review-Only Audits

These commands report findings. They do not authorize automatic deletion, suppression, or
dependency upgrades:

```powershell
uv run bandit -c pyproject.toml -r app
uv run pip-audit
uv run deptry .
uv run vulture app tests
```

Review [Dependency Security Decisions](DEPENDENCY_SECURITY.md) before using the narrowly
accepted-risk audit command. The raw command above must remain visible so new advisories
cannot be hidden by an old exception.

When the standalone Gitleaks binary is available:

```powershell
gitleaks detect --source . --config .gitleaks.toml --redact --no-banner
```

Do not upload secret-scan reports. Rotate a real credential immediately if one is found;
deleting it from the latest file does not remove it from Git history.

Set `TALENTHUNT_LOG_FORMAT=json` to emit structured local JSON logs. Both console and JSON
formats pass messages through the same credential and email redaction filter.

## Optional Local Services

Mailpit is never installed or started automatically. With a reviewed Mailpit v1.30.0 or
newer binary available on `PATH`, start the bounded loopback instance:

```powershell
.\scripts\start_mailpit.ps1
```

The helper disables version checks, binds both ports to `127.0.0.1`, limits retained mail,
blocks remote CSS and fonts, and does not configure forwarding, relay, webhooks, or public
listeners.

In a second terminal, run the opt-in application delivery check:

```powershell
$env:RUN_MAILPIT_TESTS = "1"
uv run pytest tests/test_mailpit_integration.py -q
```

TalentHunt permits passwordless SMTP only for literal loopback hosts. Any remote SMTP host
still requires a stored encrypted password.

## Baseline On 2026-08-14

The strict correctness gate and all tests pass. The broader tools remain report-only while
the existing repository debt is reduced in focused changes:

| Check | Baseline | Treatment |
| --- | ---: | --- |
| Ruff full rules | 236 findings | Mostly import order and unused imports; do not bulk-fix dirty feature files |
| Bandit | 0 high, 1 medium, 49 low | Medium is a low-confidence SQL heuristic on the CSS theme interpolator |
| Deptry | 58 findings | Review direct/transitive and optional-provider dependencies as one dependency-pruning task |
| Vulture at 90% | 6 candidates | Review call paths before removing anything |
| pip-audit | 0 unaccepted, 1 documented exception | See `DEPENDENCY_SECURITY.md` |
| Gitleaks | Configuration ready; binary not installed | Run the reviewed standalone binary locally when available |

The complete suite currently creates many full SQLite schemas and takes roughly 12 minutes
on this Windows workstation. Optimize fixture reuse separately; do not remove behavioral
coverage to make the number smaller.
