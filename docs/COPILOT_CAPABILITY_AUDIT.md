# Copilot Capability Audit

Last audited: 2026-08-14

This document maps visible TalentHunt OS workflows to the authoritative Copilot tool and action surfaces. It is a living coverage contract: when a UI workflow is added or changed, its row must be reviewed.

## Coverage Rules

- **Connected**: Copilot reaches the same service or registered action as the UI.
- **Partial**: Copilot can perform part of the workflow, but one or more UI operations are missing or bypass the action kernel.
- **Missing**: no supported Copilot route reaches the operation.
- **Gated**: intentionally not exposed because chat must not read, repeat, or silently use a secret or privileged capability.
- R2 mutations must be audited and undoable where compensation is possible.
- R3 destructive or broad operations require a trusted, session-bound confirmation preview.
- A Copilot success response is valid only after the underlying database transaction succeeds.

## Page And Domain Matrix

| Area | Status | Connected operations | Missing or gated operations |
|---|---|---|---|
| Dashboard | Connected | Canonical KPI, funnel, sourcing-quality, time-to-fill, AI-usage, outreach, and trend actions use the same services as the Dashboard and Analytics pages | None identified for current read-only Dashboard commands |
| Hunts | Connected | List, get, create, edit, pause/resume, archive, source, clear enrollment, and inspect/cancel/retry durable jobs | None identified for current Hunt controls |
| Discoveries | Connected | List/get matches, list Common Pool, approve and deep-scan, reject, archive filtered or entire visible Common Pool | No hard delete by design; archive is R3, preserves canonical Candidates, and is undoable for seven days |
| Candidates | Connected | List, search, get, create, edit, archive, merge, tags, notes, experience, education, reviewed profile apply, Rogue status, RAG questions | None identified for current Candidate UI commands |
| Pipeline | Connected | Read board, enroll, move, remove, keep/pass triage, add stage | Stage rename/reorder/delete is not implemented in either the UI or Copilot |
| Playbook | Partial | List decisions and add an insight | Edit, archive, or remove an insight is not exposed |
| Candidate Intake | Connected | Create intake link, list submissions, accept/apply, reject, undo | Sending the drafted intake message remains a separate human communication decision |
| Communications | Partial | Local logs/templates/sequences plus due-message review and one-recipient email delivery through 16 registered actions. Email send uses an exact R4 preview, trusted approval, durable provider receipt, and duplicate guard | IMAP/inbound sync and non-email provider adapters are not implemented; secrets remain gated |
| Analytics | Connected | Structured R0 actions expose KPI, funnel, sourcing quality, time-to-fill, outreach, AI usage/cost availability, and bounded daily trends with provenance; Analytics UI and Copilot share report creation | None identified for current analytics and export commands |
| Connected Sites | Connected | Sanitized status, non-blocking connect/reconnect, exact-job Save/Cancel/Retry, background verification, and approved disconnect with seven-day Undo use six registered actions shared with Settings | Passwords, cookies, headers, CAPTCHA handling, and credential values remain intentionally gated |
| Settings: local AI | Connected | Sanitized status, verified first-run install, Lite/Standard/External configuration, app-owned start/stop, exact-job Cancel/Retry, and seven-day configuration Undo use five registered actions shared with Settings | Artifact URLs and paths are fixed by the app; external endpoints are loopback-only; Copilot cannot stop a process TalentHunt does not own |
| Settings: credentials | Gated | None | API keys, SMTP passwords, voice keys, cookies, and admin passwords must never be returned to chat or tool output |
| Settings: voice | Missing | Copilot replies can use saved TTS preferences | Changing provider, voice, or keys is UI-only |
| Background jobs | Connected | Bounded history, exact status, progress, lineage, cancel-by-ID, and retry-by-ID cover sourcing, enrichment, interactive site login, site verification, and embedded AI install/start | Report, outreach, indexing, and import job families are not yet migrated to the durable manager |
| Reports and exports | Connected | Create CSV/XLSX/PDF from canonical analytics, list recent artifacts, inspect provenance, and use authenticated ID-only download links | Artifact deletion and scheduled/background report generation are not implemented |
| Action History | Connected | List recent actions and undo by ID or latest | Irreversible operations remain explicitly labelled and cannot pretend to be undoable |

## Fixed In This Audit

### Deterministic Discoveries Archive

Broad requests such as `delete all the candidates in discoveries` bypass the LLM and
create a trusted `discoveries.common_pool.archive` preview. The user must approve the R3
action in the UI; canonical Candidate records are preserved and the Common Pool archive
remains undoable for seven days. This route works even when no AI model is running.

### Embedded Local Copilot Runtime Parity

Copilot now receives `get_embedded_ai_status`, `install_embedded_ai`,
`start_embedded_ai`, `stop_embedded_ai`, and `configure_embedded_ai` from registered
`ai.runtime.*` actions shared with Settings.

- Install is a durable, cancellable, retryable job and requires explicit acknowledgement of
  the approximately 2.1 GB first-run download. Normal chat stays available.
- The app controls immutable runtime/model URLs, versions, sizes, and SHA-256 values; callers
  cannot supply paths or artifact URLs, and status output exposes neither.
- The complete pinned llama.cpp runtime is bundled for desktop builds. Every launch verifies
  its protected component manifest; the model is fully hashed before startup.
- Lite and Standard use the app-owned `127.0.0.1:18081` endpoint. External accepts only a
  separate literal loopback endpoint and TalentHunt never terminates an external process.
- Mode, endpoint, and autostart changes are audited and exactly undoable for seven days.
- Model output still has no direct authority over recruiting mutations, external sends,
  approval, history, or Undo; those remain action-kernel decisions.

### Connected-Site Action And Background-Job Parity

Copilot now receives `list_connected_sites`, `connect_site_login`,
`reconnect_site_login`, `verify_site_login`, `save_site_login`, and
`disconnect_site` from registered `sites.*` actions.

- Status output is explicitly whitelisted and omits cookies, headers, credential values,
  internal session IDs, and immutable job launch payloads.
- Connect and Reconnect open the real visible browser in a durable background job, returning
  immediately so normal chat stays responsive. Only one interactive login window can run.
- Save, Cancel, status, and Retry target one exact durable job ID. Login-page or incomplete
  cookie jars are still rejected by platform-specific checks.
- Verify is a cancellable background job; cancellation prevents late verification metadata
  writes and cannot be overwritten by a late browser result.
- Settings no longer calls browser-session mutations directly. It dispatches the same actions,
  shows the exact job ID, and polls canonical job state.
- Disconnect is R3 and uses a trusted approval card. The old model-supplied `confirm=true`
  route is rejected; successful disconnect remains undoable for seven days.

### Durable Background-Job Control Parity

Copilot now receives `list_background_jobs`, `get_background_job`,
`cancel_background_job`, and `retry_background_job` from registered `jobs.*` actions.

- List and detail are bounded R0 reads and omit immutable launch payloads from model-visible
  output, preventing session metadata or future provider secrets from leaking through job status.
- Cancel is an R2 exact-ID mutation protected by the job, Hunt, and Discovery resource keys.
  The Copilot banner no longer calls a global sourcing cancel bypass.
- Sourcing cancellation remains immediately terminal and cooperative; late worker updates cannot
  revive the row.
- Profile enrichment has an atomic `reading` to `applying` phase gate. Cancellation before
  `applying` retains approval as `scan_failed` for Retry and prevents Candidate mutation.
  Cancellation after `applying` begins is refused instead of reporting a false stop.
- Retry still creates a new attempt linked through `parent_job_id` and replays only the persisted
  launch parameters.
- The Copilot header now opens a compact durable Jobs monitor with status filtering, exact IDs,
  progress, errors, related-page navigation, and per-job Cancel/Retry controls.

### Communications Action And Approved-Delivery Parity

Copilot now receives 16 generated `communications.*` tools for local management and
approval-gated email delivery.

- Communication logging records history only and returns `sent: false`; it never calls the
  email provider. Auto-created threads and status corrections have exact seven-day Undo.
- Templates are created and updated through the same action kernel as the UI. Removal is a
  reversible archive instead of hard deletion, preserving references from sequence steps.
- Sequences, draft steps, and Candidate enrollments are registered, resource-locked actions.
  New enrollments start paused, and resume changes local due state without processing a send.
- The Communications page no longer calls `send_email()` or
  `process_due_outreach_steps()`. Sequence and enrollment pause/resume controls dispatch the
  same actions available to Copilot.
- Due outreach is a read-only rendered-message list. Each item requires its own R4 approval.
- Direct and sequence email sends freeze sender, recipient, CC, subject, body, and send count in
  the persisted preview. The model receives no raw token and cannot invoke SMTP directly.
- A pending delivery record exists before SMTP. Confirmed sends retain provider message IDs and
  cannot be duplicated; unresolved pending attempts block retry; failures require a new approval.
- External sends are recorded as irreversible and never display an Undo option.

### Analytics Read Parity

Copilot now receives seven generated R0 tools from registered `analytics.*` actions.

- KPI, funnel, sourcing quality, time-to-fill, outreach, AI usage/cost availability, and
  daily trends call the same `app.analytics.service` functions used by the UI.
- Every response identifies its canonical tables, service function, Hunt/date filters,
  calculation time, and known data limitations.
- Hunt-scoped KPI and outreach results include only communications and sequence enrollments
  belonging to canonical Candidates in that Hunt.
- AI operation counts can be scoped to one Hunt; unavailable provider, token, billing, and
  per-stage duration telemetry remains explicitly unavailable instead of being estimated.
- Unknown Hunt IDs and trend windows outside `1..365` are rejected before calculation.
- Read actions create execution/tool-call audit records but never mutation history or Undo
  entries.

### Analytics Report Artifact Parity

Copilot now receives `create_analytics_report`, `list_report_artifacts`, and
`get_report_artifact` from registered `reports.*` actions.

- Analytics page export controls dispatch the same creation action; neither surface calls a
  renderer directly.
- CSV, real XLSX, and PDF outputs are generated from canonical analytics under a fixed local
  reports directory. Hunt and date filters plus renderer identity are retained as provenance.
- Callers cannot select a path. Artifact IDs are opaque and authenticated download requests
  resolve only stored relative paths that remain inside the reports directory.
- Stored size and SHA-256 are checked before download. Spreadsheet text is neutralized against
  formula execution and PDF text is escaped before markup rendering.
- Report creation is additive, bounded to 25 MB, and audited through the action execution
  ledger. It does not claim an Undo operation or mutate recruiting data.

### Discoveries Common Pool Archive

Copilot now has `archive_discoveries_common_pool`, generated from the registered `discoveries.common_pool.archive` action.

- Omitting Hunt and search filters targets the whole visible Common Pool.
- A Hunt ID or search string narrows the selection.
- The action creates a trusted R3 approval preview with counts and sample names.
- Canonical Candidate records are preserved.
- Common Pool profiles and their Hunt-match rows are hidden immediately after approval.
- Candidate backfill and later search sightings do not silently resurrect archived identities.
- Exact prior profile and Hunt-match states are retained for seven-day Undo.
- One action is bounded to 5,000 profiles; larger pools must be narrowed into reviewed batches.

## Next Implementation Order

1. Add non-secret preference and TTS/model health actions without exposing provider keys.
2. Add a CI check that compares known UI mutation calls with registered action coverage.
3. Add inbound mail only after a truthful IMAP synchronization contract and privacy review.

## Intentional Boundaries

Copilot must not reveal stored passwords, API keys, SMTP credentials, browser cookies, or recovery secrets. It must not bypass CAPTCHA, use stealth automation, silently send outreach, hard-delete canonical records, start a second sourcing job while one is active, expose the local database publicly, or execute an R3 operation without trusted confirmation.
