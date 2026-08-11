# TalentHunt OS Deep Audit

Audit date: 2026-08-11

## Outcome

TalentHunt OS is operational for local recruiting work at
`http://127.0.0.1:8080/`. Candidate Database, Hunt pipelines, Dashboard,
Analytics, discovery review, and RAG all follow the canonical Candidate model.
The live database is structurally sound, all authenticated pages render without
browser-console errors at desktop and 390 px widths, and the automated suite passes.

This is not a production-complete certification. SMTP delivery is implemented but
requires a recruiter account, all saved sourcing-site sessions are currently inactive,
and IMAP/operational telemetry remain incomplete.

## Verified

- Authentication, first-run setup, password visibility, local password recovery,
  protected HTTP/API routes, session cookies, and loopback-only binding.
- Candidate creation, master-detail selection, profile navigation, experience
  aggregation, canonical Hunt enrollment, stage movement, and count propagation.
- Seven-day action history and undo for global candidate archive, Hunt archive,
  pipeline movement, Hunt clearing, candidate approval/import, timeline correction,
  profile replacement, intake application, and site disconnect.
- Asynchronous sourcing, single-active-job enforcement, normal chat during sourcing,
  fast cancellation checks, per-source reporting, and raw discovery retention.
- Discovery review, Raw Pool visibility, rejection, approval, deep-scan orchestration,
  and no discovery leakage into canonical candidate counts.
- External profile links open in a new tab.
- Kokoro is selected and locally available; a real provider invocation produced an
  88,108-byte RIFF/WAV response.
- Connected-site secrets are Fernet-sealed; the status service now initializes all ORM
  models correctly even when called outside the normal app startup path.
- SMTP credentials are encrypted locally; connection testing sends no mail, real
  delivery reports success only after SMTP accepts the message, and failures cannot
  advance a drip step as delivered.
- SQLite upgrades use a numbered migration ledger and automatic pre-migration backup.
- `uv.lock` and `scripts/setup.ps1` provide an isolated, frozen project environment.
- All main routes were inspected at desktop and 390 x 844: Dashboard, Hunts,
  Discoveries, Candidates, Pipeline, Playbook, Communications, Analytics, Settings,
  and Candidate Detail. No horizontal overflow or off-screen controls were found.

## Database

Live database: `data/talenthunt.db`

- SQLite `integrity_check`: `ok`
- Foreign-key violations: `0`
- Journal mode: `WAL`
- ORM/schema parity: `30` tables, no missing or extra columns
- Candidates: `36` total, `8` visible, `28` archived
- Candidate profiles: `36`; all `8` visible profiles have vector document IDs
- Talent Hunts: `2` active
- Pipeline enrollments: `9` total, `6` visible, `3` hidden with archived masters
- Discoveries: `19` total; `18` raw and `1` shortlisted
- Duplicate normalized candidate emails: `0`
- Duplicate normalized LinkedIn URLs: `0`
- Orphan candidate/profile/pipeline/discovery records: `0`
- Chroma vectors: `36`; all `8` visible candidates indexed, `0` orphan vectors
- Durable actions: `2` live history rows, both inside their seven-day undo windows
- Browser sessions: `9` historical rows, all inactive; `3` non-empty cookie payloads
  are encrypted

Archived candidates intentionally keep their pipeline rows and vectors so an archive
can be undone; every canonical reader filters them out. The UI therefore correctly
shows `8` candidates and `6` candidates in the Spine Animator pipeline.

## Defects Fixed

- Removed fabricated AI operation totals, local/cloud allocation, token counts, cost
  savings, skill counts, stage durations, and zero-filled trend data from Analytics.
- Analytics now derives trends, skills, source channels, pipeline counts, and AI actions
  from stored records; provider/cost values remain zero and unattributed until telemetry
  exists.
- Normalized mixed `0..1` and `0..100` match scores and made missing scores explicitly
  unscored instead of silently assigning 75%.
- Fixed the Dashboard source-channel key mismatch and the blank AI operation chart.
- Time-to-fill no longer reports the age of an open Hunt as a completed fill. It remains
  unavailable until a hire exists.
- Reworded Dashboard and Analytics labels so all-time, unattributed activity is not
  claimed as today's local execution or cloud savings.
- Added a safe Forgot Password disclosure to Login. Recovery remains the local command
  `python -m app.infrastructure.password_recovery`; no anonymous reset endpoint exists.
- Fixed connected-site status outside app startup by explicitly initializing the model
  registry before ORM queries.

## Remaining Risks

### High

1. LinkedIn, Naukri, GitHub, and Indeed sessions are currently disconnected. Multi-site
   fan-out is implemented and tested, but a live search cannot use authenticated pages
   until the required sites are reconnected in Settings.
2. IMAP inbox synchronization and reply detection are not implemented. Outbound SMTP
   works when configured, but inbound email remains unavailable.

### Medium

1. Provider, token, and billing telemetry is not persisted. Analytics now reports that
   absence honestly, but cannot yet calculate real local/cloud spend or savings.
2. Stage-entry timestamps are not stored, so stage bottleneck durations cannot be
   calculated reliably.
3. `49` legacy URL-based snapshot folders predate the snapshot table. Only two match
   known candidate URLs and both candidates are archived; they remain unlinked until a
   provenance-safe migration is designed.
4. Live sourcing remains dependent on network access, search-provider behavior, and
   site authentication, so it cannot be fully deterministic in an offline suite.

### Low

1. A stale zero-byte `talenthunt.db` exists at the repository root; the active database
   is under `data/`.
2. Login has no explicit rate limiter. Exposure is reduced by loopback-only binding,
   strict session cookies, and PBKDF2 password hashing.
3. Disabled demo seed data remains as unreachable code in the candidate service and can
   be removed during a dedicated cleanup.

## Verification Evidence

- Automated tests: `116 passed` in `176.77s`
- Focused analytics/canonical workflow integration: passed
- Python compilation: passed
- Ruff critical checks (`E9`, `F63`, `F7`, `F82`): passed
- Git whitespace/error check: passed
- SQLite integrity, foreign keys, schema parity, duplicates, and orphan checks: passed
- Chroma/SQL candidate index reconciliation: passed
- Desktop and 390 px authenticated route audit: passed with no console errors
- Candidate selection, Raw Pool (`18` profiles), pipeline (`6` profiles), and external
  profile-link behavior: passed
- Kokoro provider generation: valid non-empty WAV

## Release Recommendation

The app is suitable for continued local functional use. Before a production label,
reconnect and smoke-test each intended sourcing site, configure and test the intended
SMTP account, add IMAP/reply handling, and persist provider plus stage-duration telemetry.
