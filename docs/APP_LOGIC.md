# TalentHunt OS Application Logic

This document is the human-readable behavioral contract for TalentHunt OS.
Code and tests enforce these rules; Graphify remains the primary navigation map.

## Rule Format

Each rule has a stable ID, an invariant, implementation owners, and enforcing tests.
When behavior changes, update the rule, its source, and its tests in the same change.

## Candidate Lifecycle

### CAND-001: Discovery is not candidacy

- A public search hit is stored as a `DiscoveredProfile`.
- A discovered profile does not appear in Candidates, Pipeline, Dashboard, Analytics,
  RAG, Communications, or outreach counts.
- Only recruiter approval can create or update a canonical `Candidate` and enroll that
  candidate in a `TalentHunt` pipeline.
- Owners: `app/candidates/discovery.py`, `app/hunts/web_sourcing.py`.
- Tests: `tests/test_discovery_pool.py`, `tests/test_canonical_candidate_counts.py`.

### CAND-002: One public identity, many hunt matches

- Public identities are deduplicated globally by a normalized platform profile URL.
- A profile may have independent match records for multiple hunts.
- Repeated sightings update `last_seen_at`, `seen_count`, and source evidence rather
  than creating another identity.
- A repeated shortlist sighting does not increment the search run's newly-found count.

### CAND-003: Permanent common-pool retention

- Every unique public talent identity found during sourcing remains in the Common Pool.
- The pool has no age-based expiry; raw, filtered, rejected, approved, and imported
  identities are not automatically purged.
- Canonical candidates with a public LinkedIn, GitHub, or portfolio URL are linked into
  the same pool idempotently, without creating duplicate identities.
- Hunt-specific qualification and approval state is stored separately, so rejecting a
  profile for one Hunt never removes it from the global pool.

## Sourcing

### SRC-000: Requested quantity is preserved

- Copilot recognizes explicit one-, two-, and three-digit sourcing quantities.
- Direct commands, agent tools, and the sourcing engine share a maximum target of
  100 reviewable profiles per run.
- Requests above 100 are capped at 100. Every unique hit, including filtered profiles,
  still remains in the permanent Common Pool.

### SRC-001: One command, parallel platform discovery

- One Copilot hunt command fans out site-specific LinkedIn, Naukri, GitHub, and
  portfolio/web queries.
- Discovery uses at most three concurrent search workers.
- Browser verification uses the shared Playwright pool and at most two pages.
- A second talent hunt cannot start while another hunt is active; normal Copilot chat
  remains available and the active hunt remains cancellable.

### SRC-002: Discovery is lightweight

- Discovery stores snippets and source metadata without opening every profile.
- Search-result cache avoids repeating identical queries.
- The discovery pool avoids rescanning known profile identities.
- A thorough authenticated browser scan happens only after recruiter approval.

### SRC-003: Independent source health

- Each platform/provider has an independent timeout and failure result.
- One failed source does not discard successful results from other sources.
- Three consecutive provider failures open the discovery circuit and end the hunt
  quickly instead of consuming the full hunt deadline.

### SRC-004: Explicit and balanced source coverage

- A user-named source such as Naukri restricts the run to that source.
- Without an explicit source, LinkedIn, Naukri, GitHub, Behance, ArtStation, and
  Dribbble queries are interleaved so one platform cannot consume the scan budget.
- Completion messages report valid profile counts per source. Speed alone is not
  treated as proof of coverage; cached results remain identified by the same query.

### SRC-005: Common-pool capture

- Every valid person-profile URL found in a search batch is persisted before qualification.
- Role, location, experience, page-read, and target-cap skips are marked `filtered` with
  a reason and remain visible under `Discoveries -> Common Pool` permanently.
- Rejected and filtered discoveries never enter Candidates, Dashboard totals, or a hunt
  pipeline unless a recruiter later approves an eligible review item.

### SRC-006: Approved LinkedIn profile capture

- Recruiter approval triggers an authenticated deep scan of the main LinkedIn profile
  plus its complete Experience, Education, and Skills detail pages.
- Structured identity fields include name, pronouns, connection degree/count, contact
  details when visible, location, headline, current role/company, and profile photo URL.
- Highlights, About, top skills, every experience row, role-specific skills, and every
  education row are stored as structured candidate data alongside the raw snapshot.
- Experience totals are calculated from normalized, non-overlapping employment dates;
  an LLM-provided total never overrides reliable timeline evidence.

## Qualification

### QUAL-001: Experience uses unique worked months

- Employment date ranges are parsed independently, normalized to months, merged when
  they overlap, and then summed.
- LinkedIn-style start/end months are inclusive; adjacent roles form one continuous
  timeline without adding the overlapping handover month twice.
- Concurrent roles are not double-counted.
- Explicit durations are fallback evidence when reliable date ranges are unavailable.
- Structured employment rows override conflicting snippet or model-provided totals.
- Timeline corrections are recorded in the seven-day action history and restore the
  previous total, current role/company, and experience rows when undone.
- Values below zero or above 60 years are invalid.
- Owners: `app/hunts/experience.py`.
- Tests: `tests/test_experience_band.py`.

### QUAL-002: Qualification evidence is retained

- A hunt match stores role, location, experience, and rejection reasoning.
- A rejected profile remains discoverable in the Common Pool but is not shortlisted.

## Approval And Enrichment

### APR-001: Approval starts enrichment

- Approving a hunt match changes it to `enriching` and starts an asynchronous deep scan.
- Successful enrichment creates or updates the canonical candidate and enrolls that
  candidate in the approving hunt.
- Failed enrichment changes the match to `scan_failed` and keeps recruiter approval
  and retry capability intact.
- Enrichment interrupted by an app or worker restart becomes retryable automatically
  after ten minutes.

### APR-002: Deep scan evidence

- The approved profile scan expands available sections, scrolls lazy content, and saves
  readable text, HTML, a screenshot when available, final URL, and capture timestamp.
- Structured experience, education, skills, location, and summary are extracted from
  the captured evidence.
- Existing recruiter-entered candidate fields are not overwritten by empty or lower-
  confidence machine values.
- Repeated scans merge new structured evidence without duplicating identical experience,
  education, or skill entries.
- A post-import snapshot or audit-history failure never relabels an already imported
  candidate as a failed profile scan.

### APR-003: Approval is reversible

- Approval/import actions are recorded in the seven-day action history.
- Undo removes the approval-created hunt enrollment and restores the discovery state.
- A candidate created by that approval is removed when no later hunt depends on it.
- A pre-existing canonical candidate is not deleted by undo.

## Canonical Counts

### DATA-001: Candidate is the dashboard source of truth

- Candidate Database counts come only from visible canonical `Candidate` records.
- Pipeline counts come only from active `HuntCandidate` enrollments linked to canonical
  candidates.
- Discovery records never contribute to canonical counts.

### DATA-002: Analytics never invents operational data

- Dashboard and Analytics values are computed from canonical candidates, active hunt
  enrollments, communications, and explicitly recorded activity rows.
- Legacy match scores in the `0..1` range are normalized to percentages; missing scores
  remain unscored and are never replaced with a synthetic default.
- Provider, token, and cost values remain zero/unattributed until real execution telemetry
  is persisted. Time-to-fill remains unavailable for hunts with no hire.
- Owners: `app/analytics/service.py`, `app/ui/pages/analytics.py`,
  `app/ui/pages/dashboard.py`.
- Tests: `tests/test_analytics_integrity.py`.

## Copilot And Operations

### AUTH-001: Password recovery remains local

- Login and first-run setup expose password visibility controls.
- A forgotten administrator password is reset from the project folder with
  `python -m app.infrastructure.password_recovery`.
- Recovery replaces only the password hash and preserves candidates, hunts, settings,
  and history. There is no unauthenticated web reset endpoint.
- Owners: `app/infrastructure/auth_routes.py`,
  `app/infrastructure/password_recovery.py`.
- Tests: `tests/test_auth.py`.

### OPS-001: Background work does not block normal chat

- Sourcing and approved-profile enrichment run through durable SQLite job records while
  their worker threads remain local to the active process.
- Copilot may answer non-search questions while sourcing is active.
- Cancellation is terminal; late worker updates cannot revive a cancelled job.

### OPS-002: Logic documentation is part of completion

- Any change to lifecycle, sourcing, qualification, approval, counts, authentication,
  undo, or voice behavior must update this document and relevant tests.
- After code changes, refresh `graphify-out/` so symbol ownership remains current.

### OPS-003: Destructive commands are reversible

- Global candidate removal archives candidates rather than deleting rows.
- Talent Hunt removal changes the Hunt status to `Archived`; stages, enrollments,
  activities, discovery matches, and search configuration remain intact.
- Profile merge/replacement captures candidate, profile, experience, and education
  state before writing.
- Applying an intake submission captures the same profile state plus request/review
  status and any intake-generated note.
- Site disconnect deactivates sessions but retains encrypted cookies and headers.
  Permanent secret erasure must be a separate explicit operation.
- These actions remain undoable from the durable Copilot action history for seven days.
- Owners: `app/actions/history.py`, `app/hunts/service.py`,
  `app/candidates/service.py`, `app/candidates/intake_service.py`,
  `app/communications/service.py`.
- Tests: `tests/test_action_history.py`.

### DATA-003: Schema changes are versioned and backed up

- Startup applies ordered migrations recorded in `schema_migrations`.
- Before pending migrations touch an existing SQLite database, a consistent SQLite
  backup is written under `data/backups/`.
- Applied migration versions are idempotent and are not rerun at later startups.
- Owners: `app/infrastructure/migrations.py`, `app/infrastructure/db.py`.
- Tests: `tests/test_migrations.py`.

### COMM-001: Outbound delivery is truthful

- SMTP account passwords are Fernet-sealed before database storage; legacy plaintext
  values are sealed on first read.
- Connection testing authenticates and performs `NOOP`; it never sends a message.
- An outbound communication is reported `sent` only after SMTP `send_message` succeeds.
- Missing or failed SMTP remains `not_configured`/`failed` and cannot advance outreach
  as delivered.
- IMAP inbox synchronization is not implemented and returns no manufactured messages.
- Owners: `app/communications/email_service.py`,
  `app/communications/service.py`, `app/ui/pages/settings.py`.
- Tests: `tests/test_email_service.py`.

### OPS-004: Runtime dependencies are isolated and locked

- `uv.lock` is the canonical dependency resolution for local development and release.
- `scripts/setup.ps1` creates/synchronizes `.venv` from the frozen lock and installs
  Playwright Chromium without modifying global Python packages.
- The supported runtime is Python 3.12 or newer.

### OPS-005: Copilot speech starts incrementally

- Typed and dictated Copilot prompts use the same reply-to-speech path.
- A reply is divided into short sentence chunks while model text is still streaming;
  playback starts from the first complete sentence instead of waiting for the entire
  response to finish synthesizing.
- The selected local Kokoro model is warmed in a background startup thread. If any
  server-side speech chunk takes longer than 4.5 seconds, that chunk falls back to an
  available browser voice so the reply does not remain silent for tens of seconds.
- Starting a new reply or muting TTS cancels pending synthesis and queued playback.
- Owners: `app/ui/panels/copilot_panel.py`, `app/voice/tts_api.py`,
  `app/voice/providers/kokoro_tts_provider.py`.
- Tests: `tests/test_copilot_tts_trigger.py`, `tests/test_tts_preferences.py`.

### OPS-006: Short confirmations are scoped and revalidated

- Replies such as `yes` and `confirm` execute deterministically only when the latest
  assistant message is a recognized pending Hunt-removal preview.
- The preview stores or exposes the Hunt id and approved candidate count. Immediately
  before removal, Copilot compares that count with the live pipeline count.
- If the pipeline changed after preview, nothing is removed and Copilot requests fresh
  confirmation for the new count. A stale approval never expands its destructive scope.
- Successful Hunt removal affects pipeline enrollments only, preserves master candidate
  profiles, records an undoable action, and verifies that the pipeline is empty before
  reporting success.
- For compound commands such as "remove all and add 25 new candidates", the approved
  source target remains attached to the pending confirmation. Discovery starts only
  after the revalidated removal succeeds.
- Owners: `app/copilot/direct_actions.py`, `app/ui/panels/copilot_panel.py`,
  `app/hunts/pipeline.py`.
- Tests: `tests/test_action_history.py`.

### OPS-007: UI and Copilot share the registered action kernel

- Candidate read/update, Discovery approve/reject, and Pipeline move are registered
  typed actions with stable names, versions, risk levels, and required scopes.
- The corresponding NiceGUI commands and Copilot adapters execute through the same
  dispatcher rather than maintaining separate mutation implementations.
- Every dispatched action receives a structured `ActionExecution` ledger row containing
  actor, session, request, validated input, result/error, duration, and risk metadata.
- A caller-supplied idempotency key is persisted and replays the first result instead of
  repeating a mutation. Reusing it for another action is rejected.
- These first-slice mutations are single-record R2 writes. Candidate updates, Discovery
  rejection, and Pipeline moves expose tested seven-day undo. Discovery approval starts
  an asynchronous scan whose completed import records its existing undo action.
- Owners: `app/actions/registry.py`, `app/actions/api.py`,
  `app/actions/recruiting.py`, `app/copilot/action_adapters.py`.
- Tests: `tests/test_action_kernel.py`, `tests/test_action_history.py`.

### OPS-008: Sensitive actions require trusted, action-bound approval

- `hunts.archive` is an R3 action. Copilot and the Hunts page may create its durable
  preview, but neither a model argument nor a plain chat `yes` can execute it.
- The authenticated UI approval control issues the raw token only in trusted adapter
  memory. SQLite stores only its SHA-256 hash; model-visible results never contain it.
- Approval is bound to the action/version, normalized input, authenticated user, Copilot
  session, and request ID. Parameter substitution, cross-session use, and replay fail.
- Pending approval expires after ten minutes, can be cancelled, and is consumed atomically
  before the mutation. The archived Hunt remains undoable for seven days.
- Owners: `app/actions/approvals.py`, `app/actions/registry.py`, `app/actions/api.py`,
  `app/actions/recruiting.py`, `app/ui/panels/copilot_panel.py`, `app/ui/pages/hunts.py`.
- Tests: `tests/test_action_kernel.py`, `tests/test_migrations.py`.

### OPS-009: Conflicting mutations are serialized by durable resource leases

- Registered mutations resolve canonical affected-resource keys before execution:
  `candidate:<id>`, `hunt:<id>`, `hunt-candidate:<id>`, and `discovery-match:<id>`.
- SQLite stores one active lease per resource. A conflicting action returns a structured
  busy result and does not run its handler; unrelated Copilot chat and actions remain usable.
- Dispatcher-owned cleanup releases every lease after success, handler failure, rejected
  approval, ledger failure, or idempotent replay. A crashed process leaves an expiring lease,
  which becomes recoverable after at most fifteen minutes.
- Hunt archive, Pipeline movement, and Discovery decisions share the Hunt key so their
  synchronous mutation phases cannot overlap. Candidate updates share the canonical
  Candidate key.
- A lock conflict occurs before an R3 token is consumed. Trusted UI approval is reopened,
  its discarded token hash is cleared, and the approval card remains available for retry.
- Background enrichment is currently protected only during its synchronous launch phase;
  holding leases for the full job lifetime belongs to the durable job-manager phase.
- Owners: `app/actions/locks.py`, `app/actions/models.py`, `app/actions/registry.py`,
  `app/actions/api.py`, `app/actions/recruiting.py`.
- Tests: `tests/test_action_kernel.py`, `tests/test_migrations.py`.

### OPS-010: Completed actions are visible, navigable, and undo through the kernel

- The Copilot panel shows the latest recorded action for the selected session as a compact
  card. The full seven-day list remains available from the Action History button.
- Cards expose only summary/status/time, a derived in-app destination, and Undo eligibility;
  raw action and inverse payloads are never rendered into the browser.
- Open navigates to the affected Candidate, Hunt pipeline, Discoveries, Candidates, Hunts,
  Settings, or other supported canonical view derived from stored IDs.
- Undo is the typed R2 `actions.undo` action. Both the card, the history dialog, and the
  Copilot `undo_recent_action` tool dispatch it through validation, resource locking,
  execution logging, and the existing tested inverse handlers.
- The completed card updates to `Undone` and removes its Undo control after success. The
  underlying page reloads so canonical Candidate, Pipeline, Hunt, and Dashboard views agree.
- Owners: `app/actions/history.py`, `app/actions/recruiting.py`, `app/copilot/tools.py`,
  `app/ui/panels/copilot_panel.py`.
- Tests: `tests/test_action_history.py`, `tests/test_action_kernel.py`.

### OPS-011: Copilot tools are generated and audited at one boundary

- Model-callable adapters for registered actions are generated from the authoritative
  `ActionSpec` name, description, input model, risk, and Copilot tool name. Adding a
  registered action no longer requires a second handwritten mutation adapter.
- R3/R4 generated adapters create a durable trusted preview only; the model cannot call
  the execution path or obtain the raw approval token.
- `get_copilot_tools()` wraps every production tool, including legacy semantic/search
  helpers, with one structured `ActionToolCall` record. Calls move from `running` to
  `completed` or `failed`, retain session and duration, and link to `ActionExecution`
  whenever the tool dispatched a registered action.
- Inputs and outputs are JSON encoded, credential-like fields are recursively redacted,
  and stored outputs are bounded. A failure to finalize audit metadata is logged without
  converting a successful OS operation into a fabricated failure.
- Manual tools may remain as intent resolvers or long-running workflow adapters, but they
  must not duplicate a mutation already owned by the registered action kernel.
- Owners: `app/actions/registry.py`, `app/actions/tool_calls.py`,
  `app/copilot/action_adapters.py`, `app/copilot/tools.py`.
- Tests: `tests/test_generated_action_tools.py`, `tests/test_migrations.py`.

### OPS-012: Background jobs are durable, retryable, and restart-truthful

- Every sourcing run and approved-profile deep scan is persisted in `background_jobs`
  before its worker starts. The row stores Hunt ownership, label, immutable launch
  parameters, counters, structured progress, heartbeat, error, notification state,
  attempt number, parent-job lineage, and terminal timestamps.
- SQLite enforces one `running` sourcing job atomically. The process-local cancellation
  event only accelerates cooperative shutdown; the database status remains authoritative.
- Progress updates apply only while the row is `running`. Cancellation is immediately
  terminal, so late network results cannot revive or rewrite a cancelled run.
- Startup changes orphaned `running` rows from a previous process to `interrupted`,
  releases the singleton search slot, and changes an interrupted enrichment match from
  `enriching` to `scan_failed`. It never claims that vanished browser/network work resumed.
- The typed R2 `jobs.retry` action accepts only a durable job ID and replays the immutable
  stored launch parameters for supported sourcing and profile-enrichment jobs. It creates
  a new row linked by `parent_job_id`; it never rewrites the failed attempt.
- Retry is available from a compact Copilot job strip, through the generated
  `retry_background_job` tool, and on failed Discovery deep scans. Unsupported kinds,
  successful jobs, and legacy rows without complete source parameters are rejected.
- Automatic retry/resume remains disabled; retry requires an explicit UI or Copilot action.
- Owners: `app/jobs/models.py`, `app/jobs/service.py`,
  `app/jobs/runner.py`, `app/hunts/sourcing_jobs.py`, `app/actions/recruiting.py`,
  `app/ui/panels/copilot_panel.py`, `app/ui/pages/discoveries.py`, `app/main.py`.
- Tests: `tests/test_durable_background_jobs.py`,
  `tests/test_job_retry_actions.py`, `tests/test_sourcing_cancellation.py`,
  `tests/test_single_active_sourcing_job.py`.

### OPS-013: Candidate and Discovery reads and controls share one action source

- Copilot can list/search canonical Candidates, read a full Candidate, list Hunt-specific
  Discovery matches, inspect one match, and search the permanent Common Pool through typed
  R0 actions. Results are bounded structured records sourced from the same services as the
  visual pages; rejected and filtered identities remain visible in Common Pool results.
- Single-candidate archive, tag add/remove, and recruiter-note creation are typed R2 actions
  protected by the canonical `candidate:<id>` resource lease. Each records an exact inverse
  for seven-day Undo and appears in the shared execution/audit ledgers.
- The Candidates page archive control and Candidate detail tag/note controls dispatch these
  same actions. Archive changes only `Candidate.status`; it does not destroy the profile,
  evidence, notes, experience, or linked history.
- Owners: `app/actions/recruiting.py`, `app/actions/history.py`,
  `app/ui/pages/candidates.py`, `app/ui/pages/candidate_detail.py`,
  `app/candidates/discovery.py`.
- Tests: `tests/test_candidate_discovery_actions.py`, `tests/test_action_kernel.py`,
  `tests/test_generated_action_tools.py`.

### OPS-014: Candidate structured profile controls are reversible actions

- Work experience and education rows are exposed as typed save/remove R2 actions. Save
  accepts an optional row ID for editing; ownership is checked against the Candidate before
  any mutation. Experience writes recalculate total experience from non-overlapping career
  intervals and refresh current title/company from the timeline.
- Reviewed profile extraction uses `candidates.profile.apply` for both merge and replace
  modes. It can apply contact fields, headline, summary, resume text, skills, highlights,
  experience, and education without bypassing the action ledger.
- Every structured-profile mutation snapshots the complete recruiter-editable Candidate
  state before execution. Seven-day Undo restores exact profile fields and experience/
  education rows, including row IDs, dates, skills, and the previous experience total.
- Rogue status is a typed R2 action. Marking creates the Rogue tag and its Playbook record;
  clearing removes the tag. Undo restores the prior tag state and removes only the Playbook
  entry created by the action being reversed.
- Candidate detail Add Experience/Add Education, profile-section review, and Candidate-list
  Rogue controls dispatch the same actions available to Copilot.
- Owners: `app/actions/recruiting.py`, `app/actions/history.py`,
  `app/ui/pages/candidate_detail.py`, `app/ui/components/profile_review_dialog.py`,
  `app/ui/pages/candidates.py`.
- Tests: `tests/test_candidate_discovery_actions.py`, `tests/test_action_kernel.py`,
  `tests/test_generated_action_tools.py`.

### OPS-015: Duplicate Candidates merge into one canonical survivor without evidence loss

- `candidates.duplicates.list` is a bounded R0 query shared by Copilot and the Candidates
  page. It proposes pairs only from exact normalized email, phone, LinkedIn, GitHub, or
  portfolio identity, or from exact name plus company/location context. It never merges.
- `candidates.merge` is R3. The user chooses the survivor and source, then approves an
  immutable preview showing identity reasons, fields filled, moved-reference counts, and
  overlapping Hunt enrollments. Copilot can request the preview but cannot self-approve it.
- Merge fills missing survivor contact/profile fields, unions structured skills and profile
  evidence, copies non-duplicate experience, education, tags, and notes, and moves Common
  Pool, Pipeline, communications, outreach, intake, and Playbook references.
- When both records are already in one Hunt, their pipeline rows consolidate into the
  survivor row and all Hunt activities move with it. The source Candidate is retained as
  `Archived`; its profile and snapshots remain available as provenance.
- The inverse payload stores both exact Candidate states, every created evidence-row ID,
  every reassigned reference ID, and each collapsed Hunt row/activity mapping. Seven-day
  Undo restores both records, their unique email ownership, workflow links, and row IDs.
- Owners: `app/candidates/duplicates.py`, `app/actions/recruiting.py`,
  `app/actions/history.py`, `app/ui/pages/candidates.py`.
- Tests: `tests/test_candidate_merge_actions.py`, `tests/test_action_kernel.py`,
  `tests/test_generated_action_tools.py`.

### OPS-016: Candidate creation and resume import use reviewed canonical actions

- `candidates.create` is the single R2 creation path for the Candidates page and Copilot's
  `add_candidate_to_database` tool. Input is typed and bounded; an optional Hunt ID creates
  the canonical Candidate and pipeline enrollment under one creation/Hunt resource lease.
- Before writing, creation checks conservative identity signals. A likely existing person
  returns a conflict with the existing Candidate ID and reasons; it does not silently enrich
  or upsert that record. Recruiters can review or use the explicit R3 merge workflow.
- Creation records the exact initial profile, tags, optional Hunt row, and initial Hunt
  activity. Seven-day Undo deletes only the newly created entity. It refuses when the
  Candidate later gains profile edits, tags, notes, snapshots, communications, discoveries,
  outreach, intake, Playbook history, additional Hunt enrollment, or pipeline activity.
- Candidate detail accepts PDF, DOCX, and TXT resumes up to 8 MB. Extraction is bounded to
  200,000 characters and occurs locally in memory; the uploaded artifact is not retained.
  Password-protected, unreadable, unsupported, oversized, and low-text files are rejected.
- Extracted text enters the existing editable profile-review dialog. Nothing reaches the
  Candidate until the recruiter applies the draft through `candidates.profile.apply`; that
  action stores the reviewed raw resume text and structured evidence with exact Undo.
- Owners: `app/actions/recruiting.py`, `app/actions/history.py`,
  `app/candidates/resume_import.py`, `app/ui/pages/candidates.py`,
  `app/ui/pages/candidate_detail.py`, `app/ui/components/profile_review_dialog.py`.
- Tests: `tests/test_candidate_create_action.py`, `tests/test_resume_import.py`,
  `tests/test_action_kernel.py`, `tests/test_generated_action_tools.py`.

### OPS-017: Pipeline board commands share one reversible action source

- `pipeline.get` is the bounded R0 board query used by Copilot. It reads the same
  `get_pipeline_data` service that renders the Kanban and returns Hunt metadata, ordered
  stages, stage counts, and canonical Candidate/enrollment IDs.
- Stage movement, existing-Candidate enrollment, single-enrollment removal, Keep/Pass
  triage, and custom-stage creation are typed R2 actions protected by Hunt, enrollment,
  and canonical Candidate resource leases. The Pipeline and Candidates pages dispatch
  these actions instead of directly changing ORM rows.
- A Pipeline removal deletes only the `HuntCandidate` enrollment. The canonical Candidate
  and permanent Common Pool identity remain intact. Undo restores the exact enrollment
  ID, stage, fields, timestamps, and Hunt activities.
- Keep advances to the next stage and writes a Playbook entry. Pass writes a Playbook
  entry, removes the enrollment, and removes that Hunt's tag. Both execute in one database
  transaction and seven-day Undo removes only the generated Playbook/activity records and
  restores the exact prior stage, enrollment, activity, and tag state.
- `pipeline.enroll` is the shared Candidates-page/Copilot assignment path. Optional move
  mode snapshots all prior Hunt enrollments, activities, and Hunt tags before moving the
  canonical Candidate. Target rows are inserted before prior rows are removed to prevent
  SQLite identity reuse. Undo refuses if later Pipeline work makes removal unsafe.
- A custom stage can be undone only while empty. Once a Candidate enters it, Undo requires
  moving the Candidate out first, preserving Pipeline history rather than orphaning rows.
- Manual Pipeline creation now calls `candidates.create` with a Hunt ID. The person enters
  the canonical Candidates pool and the Hunt Pipeline together, with conflict detection
  and one reversible history record; manually invented AI match scores are no longer used.
- Owners: `app/actions/recruiting.py`, `app/actions/history.py`,
  `app/hunts/pipeline.py`, `app/hunts/playbook.py`, `app/ui/pages/pipeline.py`,
  `app/ui/pages/candidates.py`, `app/copilot/mgmt_tools.py`.
- Tests: `tests/test_pipeline_actions.py`, `tests/test_action_kernel.py`,
  `tests/test_generated_action_tools.py`.
