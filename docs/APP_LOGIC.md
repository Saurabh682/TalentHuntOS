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
- Hunt-filtered KPI and outreach metrics count only communications and sequence enrollments
  for canonical Candidates actively enrolled in that Hunt. Hunt-filtered AI counts use only
  that Hunt's recorded AI activity rows.
- Owners: `app/analytics/service.py`, `app/ui/pages/analytics.py`,
  `app/ui/pages/dashboard.py`.
- Tests: `tests/test_analytics_integrity.py`, `tests/test_analytics_actions.py`.

### DATA-003: Copilot analytics are canonical, bounded, and provenance-bearing

- `analytics.kpi`, `analytics.funnel`, `analytics.time_to_fill`,
  `analytics.sourcing_quality`, `analytics.outreach`, `analytics.ai_cost`, and
  `analytics.trends` are typed R0 actions generated into the Copilot tool surface.
- Every action calls the corresponding `app.analytics.service` function used by the UI.
  Copilot does not maintain a second metric implementation.
- Results include canonical table names, the service function, Hunt/date filters,
  calculation time, and limitations such as missing provider cost telemetry or stage-entry
  timestamps.
- A Hunt filter must resolve to a real canonical Hunt. Trend windows are bounded to 1..365
  days. Invalid scopes fail instead of returning plausible zero-filled success.
- These reads create `ActionExecution` and `ActionToolCall` audit records but never
  `ActionHistory` mutations or Undo controls.
- Owners: `app/actions/recruiting.py`, `app/analytics/service.py`,
  `app/copilot/action_adapters.py`.
- Tests: `tests/test_analytics_actions.py`, `tests/test_generated_action_tools.py`.

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

### DATA-004: Schema changes are versioned and backed up

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
- Email delivery is an R4 registered action. Copilot and the Communications UI can create
  an immutable preview, but only the authenticated approval control can execute the exact
  reviewed sender, recipient, CC, subject, and body once.
- A durable `pending` communication is committed before SMTP is called. Provider message ID,
  final status, failure reason, retry eligibility, and a unique delivery key are then recorded.
- A `pending` attempt is treated as unresolved and cannot be retried automatically. A confirmed
  `sent` key cannot be delivered again; a failed attempt needs a fresh approval before retry.
- Missing or failed SMTP remains `not_configured`/`failed` and cannot advance outreach
  as delivered.
- External delivery is irreversible and has no Undo. Sequence progression occurs only after
  the provider confirms the send; failure pauses the enrollment.
- IMAP inbox synchronization is not implemented and returns no manufactured messages.
- Owners: `app/communications/email_service.py`,
  `app/actions/communications.py`, `app/communications/models.py`,
  `app/ui/pages/communications.py`, `app/ui/pages/settings.py`.
- Tests: `tests/test_email_service.py`, `tests/test_communications_delivery_actions.py`.

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

- Every sourcing run, approved-profile deep scan, interactive site login, and site-session
  verification is persisted in `background_jobs`
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
  stored launch parameters for supported sourcing, profile-enrichment, and connected-site
  jobs. It creates
  a new row linked by `parent_job_id`; it never rewrites the failed attempt.
- Typed R0 `jobs.list` and `jobs.get` actions expose bounded status, progress, counters,
  lineage, and available controls without returning immutable launch payloads to Copilot.
- Typed R2 `jobs.cancel` targets one exact durable ID. Sourcing cancellation is immediately
  terminal and signals the local worker. Profile enrichment may be cancelled while reading
  or extracting; an atomic phase transition blocks cancellation once canonical Candidate
  changes begin, so the OS never claims that already-applying work was stopped.
- Cancelled enrichment returns its Discovery match to `scan_failed`, preserves recruiter
  approval for Retry, and cannot create or update a Candidate after a pre-apply cancellation.
- Retry is available from a compact Copilot job strip, through the generated
  `retry_background_job` tool, the Copilot durable Jobs monitor, and failed Discovery deep
  scans. Unsupported kinds, successful jobs, and legacy rows without complete source
  parameters are rejected.
- Automatic retry/resume remains disabled; retry requires an explicit UI or Copilot action.
- Owners: `app/jobs/models.py`, `app/jobs/service.py`,
  `app/jobs/runner.py`, `app/hunts/sourcing_jobs.py`, `app/actions/recruiting.py`,
  `app/ui/panels/copilot_panel.py`, `app/ui/pages/discoveries.py`, `app/main.py`.
- Tests: `tests/test_durable_background_jobs.py`,
  `tests/test_job_retry_actions.py`, `tests/test_job_control_actions.py`,
  `tests/test_sourcing_cancellation.py`, `tests/test_single_active_sourcing_job.py`.

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

### OPS-018: Talent Hunt lifecycle uses canonical typed actions

- `hunts.list` and `hunts.get` are bounded R0 reads shared with Copilot. They return Hunt
  fields, search configuration, ordered Pipeline stages, and metrics derived from canonical
  Pipeline rows. Read actions do not run tag reconciliation or mutate the database.
- `hunts.create` is the R2 local creation boundary. It validates and normalizes the title,
  role, location, skills, experience band, industry, platforms, and initial status, then
  creates the Hunt, search configuration, default Pipeline stages, and creation activity in
  one transaction under the global Hunt-creation lease.
- The Launch workflow calls `hunts.create` first and then retains the existing session,
  Copilot prompt, local-pool check, and asynchronous sourcing behavior. This keeps Hunt
  creation auditable without pretending that later web sourcing is part of a reversible
  database write.
- Creation Undo deletes only a still-pristine Hunt. It verifies the original stages,
  activity, configuration, and fields, and refuses after candidates, discoveries, intake,
  Playbook records, background jobs, custom stages, or later Hunt changes exist.
- `hunts.update` supports partial updates and distinguishes omitted fields from explicit
  clearing. Hunt details and search configuration are snapshotted together; Undo restores
  exact prior values and removes a configuration row if the action originally created it.
- `hunts.status.set` handles Active, Paused, Draft, and Completed with exact status Undo.
  Archived is intentionally excluded: archive remains the separate R3 `hunts.archive`
  action with immutable preview and authenticated approval.
- Create/Edit/Pause controls and the legacy Copilot Hunt lifecycle tools dispatch these
  registered actions. They no longer directly write `TalentHunt` or `HuntSearchConfig`.
- Owners: `app/actions/recruiting.py`, `app/actions/history.py`,
  `app/hunts/service.py`, `app/hunts/launch.py`, `app/ui/pages/hunts.py`,
  `app/copilot/tools.py`, `app/copilot/mgmt_tools.py`.
- Tests: `tests/test_hunt_actions.py`, `tests/test_action_kernel.py`,
  `tests/test_generated_action_tools.py`.

### OPS-019: Playbook and Candidate Intake share audited actions

- `playbook.list` is the bounded R0 source for the Playbook page and Copilot. It filters
  Keep, Pass, and Insight history by type, role, platform, and text without mutating data.
- `playbook.insights.add` is an R2 write protected by a global Playbook or Hunt lease.
  It records the author and search context; seven-day Undo deletes only that insight.
  Keep/Pass entries remain owned by the atomic Pipeline triage actions in OPS-017.
- `intake.requests.create` validates the canonical Candidate and optional Hunt, creates one
  expiring tokenized link, and returns a draft message. It never claims or attempts external
  delivery. Undo removes the request only while it has no Candidate submission.
- `intake.submissions.list` exposes bounded pending submissions. Recruiter acceptance or
  rejection uses `intake.submissions.review` under Intake, Candidate, and Hunt resource
  leases instead of model-supplied confirmation flags or direct ORM updates.
- Reviewed acceptance applies the selected experience, education, skills, summary, and
  experience total together with contact data, JD-fit note, request status, and submission
  status in one audited transaction. Exact Candidate state and review state are snapshotted;
  Undo restores both and removes only the note created by that application.
- Rejection is also reversible: Undo restores the prior request/submission states and
  review timestamp without changing the Candidate profile.
- The Candidate Detail review dialog dispatches this single Intake action. It no longer
  applies the profile first and flips Intake status in a separate direct transaction.
- Owners: `app/actions/recruiting.py`, `app/actions/history.py`,
  `app/candidates/intake_service.py`, `app/hunts/playbook.py`,
  `app/ui/pages/playbook.py`, `app/ui/pages/candidate_detail.py`,
  `app/ui/components/profile_review_dialog.py`.
- Tests: `tests/test_playbook_intake_actions.py`, `tests/test_action_history.py`,
  `tests/test_security_hardening.py`, `tests/test_generated_action_tools.py`.

### OPS-020: Candidate search uses a derived local full-text index

- SQLite Candidate and Discovered Profile rows remain canonical. FTS5 tables contain only
  derived searchable text and can be rebuilt without changing Candidate counts, Common
  Pool retention, Hunt membership, decisions, or permissions.
- Candidate and Common Pool insert, update, and delete triggers keep their respective FTS5
  indexes synchronized. Migration setup rebuilds both indexes for existing records.
- User search text is tokenized into literal prefix terms. Raw FTS operators are never
  accepted, preventing malformed or unexpectedly broad MATCH expressions.
- If the local SQLite build does not provide FTS5, the same service functions use their
  bounded `LIKE` filters. Search failure does not make the canonical pool unavailable.
- Owners: `app/candidates/fts.py`, `app/candidates/service.py`,
  `app/candidates/discovery.py`, `app/infrastructure/migrations.py`.
- Tests: `tests/test_candidate_fts.py`, `tests/test_migrations.py`.

### OPS-021: Local logs are structured and redacted at the handler boundary

- Every TalentHunt stdout record passes through one central filter after message arguments
  are rendered. Common passwords, tokens, authorization values, cookies, API-key shapes,
  and email addresses are replaced before console or JSON formatting.
- Console output remains the local default. `TALENTHUNT_LOG_FORMAT=json` enables JSON Lines
  containing timestamp, level, logger, message, and exception text for local diagnostics.
- Structured logging does not authorize logging candidate profiles, message bodies,
  credentials, browser sessions, or model prompts. Call sites should log identifiers and
  bounded operational state even though the handler provides defense in depth.
- Logs are never uploaded automatically. External collectors and telemetry remain disabled
  unless separately reviewed and approved.
- Owners: `app/infrastructure/logging_setup.py`, `app/main.py`.
- Tests: `tests/test_logging_setup.py`.

### OPS-022: Local model endpoints stay on loopback

- LM Studio, Ollama, and `llama-server` health checks accept only literal loopback hosts
  such as `127.0.0.1`, another `127.0.0.0/8` address, `::1`, or `localhost`.
- A hostname that merely contains `localhost`, an unspecified bind address, a LAN address,
  or a public hostname is rejected before network or process access.
- TalentHunt uses the model server's OpenAI-compatible HTTP boundary and does not require
  the native `llama-cpp-python` package in its own runtime.
- Owners: `app/ai/local_server.py`, `app/ai/engine.py`, `app/config/settings.py`.
- Tests: `tests/test_local_server_security.py`, `tests/test_security_hardening.py`.

### OPS-023: Common Pool removal is reversible archive

- `discoveries.common_pool.archive` is the authoritative pool-level removal action for Copilot.
- It requires a trusted R3 preview and preserves linked canonical Candidate records.
- Matching `DiscoveredProfile` and `DiscoveryHuntMatch` rows move to `archived`, so Discoveries queries and counts change immediately.
- Candidate backfill and repeated sourcing sightings do not revive an archived identity.
- The action records exact prior profile and match states for seven-day Undo.
- One action is bounded to 5,000 profiles; larger pools must be narrowed by Hunt or search text.
- Hard deletion is not exposed because it would break provenance, audit history, and compensation.
- Owners: `app/actions/recruiting.py`, `app/actions/history.py`, `app/candidates/discovery.py`.
- Tests: `tests/test_action_kernel.py`, `tests/test_discovery_pool.py`.

### OPS-024: Communications management is local, reversible, and separate from delivery

- Communication logs, templates, sequences, steps, and enrollments are controlled by the
  registered `communications.*` action family shared by Copilot and the Communications UI.
- Recording a communication is history-only. It may store a user-reported `sent` status, but
  it never invokes an email, browser, messaging, or voice provider and returns `sent: false`.
- New sequence enrollments always start `paused`. Setting an enrollment to `active` updates
  local due state only; it does not process a due step or contact the Candidate.
- Template removal is soft archive. Local writes have resource leases, Action History entries,
  and exact seven-day inverses with dependency/progression checks where later work could make
  deletion unsafe.
- `send_email()` and `process_due_outreach_steps()` are not called from the page or exposed as
  ordinary unapproved Copilot tools. The registered delivery action is the only page/Copilot
  route to `send_email()`.
- Owners: `app/actions/communications.py`, `app/actions/history.py`,
  `app/ui/pages/communications.py`, `app/copilot/action_adapters.py`.
- Tests: `tests/test_communications_actions.py`, `tests/test_generated_action_tools.py`.

### OPS-025: External email delivery is immutable, approved, and non-undoable

- `communications.deliveries.due.list` renders due sequence steps for review and never sends.
- `communications.delivery.send` is R4 and always requires a trusted one-time approval token.
  Its persisted preview contains the exact sender, recipient, CC, subject, body, and send count.
- Execution reads the immutable persisted preview instead of trusting model-supplied rendered
  text. Candidate email or sequence-content drift invalidates the approval.
- The delivery key prevents confirmed duplicate sends. `pending` means unknown and blocks retry;
  `failed` is retryable only through a new preview and approval.
- SMTP receipts and failures are canonical `Communication` fields. Successful sequence delivery
  advances one step exactly once; failure pauses it without pretending delivery occurred.
- External delivery is written to Action History without an inverse and is visibly labelled as
  irreversible in the Copilot approval card.
- Owners: `app/actions/communications.py`, `app/actions/approvals.py`,
  `app/actions/registry.py`, `app/communications/email_service.py`,
  `app/ui/panels/copilot_panel.py`, `app/ui/pages/communications.py`.
- Tests: `tests/test_communications_delivery_actions.py`, `tests/test_migrations.py`.

### OPS-026: Connected-site control is asynchronous and secret-safe

- `sites.list` is the R0 source for Settings and Copilot. It returns only platform, status,
  encryption and verification flags, bounded verification detail, timestamps, available
  controls, and sanitized active-job state. Cookies, headers, passwords, and internal browser
  session rows are never returned.
- `sites.connect` and `sites.reconnect` start a durable `site_connect` job and return immediately.
  A visible Chromium-family browser handles the login directly, so normal Copilot chat remains
  available and TalentHunt never receives or stores the site password.
- Only one interactive login window may run at a time. A saved session is replaced only after
  the new browser state passes platform-specific login checks and is encrypted locally.
- `sites.connect.save` targets one exact job ID. Save is still rejected while the browser is on
  a login/auth page or lacks the required authentication cookie.
- `sites.verify` starts a durable `site_verify` job. Cancellation prevents verification metadata
  from being changed after the browser check returns; late completion cannot revive a cancelled
  job.
- Site jobs appear in the shared Work History monitor and support exact-ID Cancel and Retry.
  Application restart marks vanished work `interrupted`; it never claims a browser session kept
  running.
- `sites.disconnect` is R3. Settings and Copilot create the same trusted preview, and only an
  authenticated UI approval deactivates the session. Encrypted data remains available for
  seven-day Undo.
- Reading connection status does not update the saved session's last-used timestamp. Tool and
  action audit records contain no credential material.
- Owners: `app/actions/sites.py`, `app/browser/connection_jobs.py`,
  `app/browser/session_auth.py`, `app/jobs/runner.py`,
  `app/ui/components/connect_sites.py`, `app/ui/panels/copilot_panel.py`.
- Tests: `tests/test_site_actions.py`, `tests/test_generated_action_tools.py`,
  `tests/test_security_hardening.py`, `tests/test_action_history.py`.

### OPS-027: Analytics report artifacts are canonical, bounded, and authenticated

- `reports.analytics.create`, `reports.list`, and `reports.get` are the authoritative
  report actions shared by Analytics UI controls and Copilot-generated tools.
- Report data is read from `get_all_analytics_data()`, the same canonical analytics
  service used by Dashboard and Analytics. Optional Hunt and date-window filters are
  stored in the artifact provenance.
- Creation accepts only `csv`, `xlsx`, or `pdf`. Callers cannot provide a filesystem
  path: files are written atomically beneath the configured local `data/reports`
  directory and are limited to 25 MB.
- CSV and XLSX cells neutralize spreadsheet formulas from untrusted database text. PDF
  text is escaped before rendering. XLSX files are real workbooks rather than CSV bytes
  with a misleading extension.
- Each completed artifact stores its media type, size, SHA-256 digest, scope, actor,
  session, and renderer provenance in SQLite. Downloads recheck size and digest before
  serving the file.
- Action and tool results expose an opaque artifact ID and authenticated `/api/reports/`
  download URL, never an internal path. The route accepts no path input and remains
  covered by the existing `/api/*` authentication middleware.
- Report creation is additive and is recorded in the action execution ledger. It does
  not create an Undo entry because it does not mutate recruiting records or cause an
  external effect.
- Owners: `app/actions/reports.py`, `app/analytics/artifacts.py`,
  `app/analytics/reports.py`, `app/analytics/routes.py`, `app/ui/pages/analytics.py`.
- Tests: `tests/test_report_actions.py`, `tests/test_generated_action_tools.py`,
  `tests/test_migrations.py`, `tests/test_security_hardening.py`.

### OPS-028: Embedded local AI is verified, loopback-only, and action-controlled

- Desktop builds bundle the complete pinned llama.cpp `b10430` Windows CPU x64 runtime,
  including its required DLLs. They do not treat the small `llama-server.exe` loader as a
  standalone executable.
- The default model is IBM Granite 4.1 3B GGUF Q4_K_M at one immutable Hugging Face revision.
  The roughly 2.1 GB model is an explicit first-run download rather than installer payload.
- Runtime and model downloads use app-owned HTTPS URLs, resume through a `.part` file, enforce
  exact byte size, verify SHA-256, and move into private storage only after verification.
  Runtime extraction rejects traversal, symlinks, nested paths, unknown executables, and
  oversized archives.
- Redirects remain deny-by-default and accept only GitHub release delivery or Hugging Face's
  documented HTTPS storage/CDN endpoints. Arbitrary `hf.co` subdomains and lookalike domains
  are rejected before any artifact bytes are trusted.
- Each runtime launch verifies the protected installed-component manifest. Each model startup
  rehashes the full GGUF before process launch. Settings/status calls use cached verification
  metadata so ordinary page rendering does not hash 2.1 GB.
- Lite uses a 2,048-token context and bounded CPU workers; Standard uses 4,096. Machines below
  6 GB total RAM are directed to External mode. Hardware output is aggregate and exposes no
  process list or filesystem details.
- `ai.runtime.status`, `.install`, `.start`, `.stop`, and `.configure` are authoritative for
  both Settings and Copilot. Install/start are durable jobs with exact-ID Cancel and Retry.
  Restart can autostart verified artifacts but never silently downloads them.
- TalentHunt binds its server to its app-owned `127.0.0.1:18081` endpoint, refuses an occupied
  embedded port, and stops only the subprocess it launched. External mode retains a separate
  literal loopback endpoint (commonly `127.0.0.1:1234`) and never takes ownership of LM Studio,
  Ollama, or a custom service.
- Configuration is a seven-day Undo action. Artifact installation is retained after Cancel;
  partial downloads may be resumed, while model output remains subject to the normal action,
  scope, approval, audit, confirmation, and Undo kernel.
- Owners: `app/ai/embedded_runtime.py`, `app/ai/embedded_jobs.py`,
  `app/ai/local_server.py`, `app/actions/ai_runtime.py`,
  `app/ui/components/embedded_ai.py`, `scripts/build_installer.py`.
- Tests: `tests/test_embedded_runtime.py`, `tests/test_ai_runtime_actions.py`,
  `tests/test_local_server_security.py`, `tests/test_generated_action_tools.py`.
