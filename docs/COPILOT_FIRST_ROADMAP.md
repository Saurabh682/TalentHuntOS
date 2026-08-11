# TalentHunt OS Copilot-First Roadmap

Status: In progress
Audit date: 2026-08-11
Primary principle: Copilot is the operating surface; pages are visual views over the same actions.

Implemented first slice (2026-08-11):

- Activated the registry with version, risk, scope, and durable execution metadata.
- Added persistent action idempotency and schema migration 2.
- Registered `candidates.get`, `candidates.update`, `discoveries.approve`,
  `discoveries.reject`, `pipeline.move`, and `hunts.archive`.
- Routed their Copilot adapters and matching UI mutation controls through one dispatcher.
- Added seven-day undo for Discovery rejection; Candidate update and Pipeline move reuse
  their tested inverse handlers.
- Added the first durable R3 approval card for Hunt archive. Its opaque token is issued
  only inside authenticated UI code, bound to the exact action/input/user/session/request,
  expires after ten minutes, and is consumed once.
- Added migration 5 and durable affected-resource leases for the representative mutations.
  Candidate, Discovery, Pipeline, and Hunt conflicts are rejected before execution; stale
  leases expire and lock-conflicted approvals return to the visible approval queue.
- Added migration 6 and structured, redacted tool-call records around every production
  Copilot tool. Registered actions link their tool call to the durable execution ledger.
- Generated typed LangChain adapters directly from the
  action registry; sensitive generated actions can create previews but cannot self-approve.
- Added migration 7 and the durable sourcing-job foundation: launch parameters, progress,
  heartbeats, cancellation, terminal results, and notifications now survive process memory.
  Startup truthfully marks orphaned runs interrupted and retryable instead of losing them.
- Added typed `jobs.retry` parity for Copilot and UI, immutable retry payload replay,
  attempt lineage, and durable approved-profile enrichment with restart reconciliation.
- Added Candidate/Discovery query parity: Candidate list/search, Discovery list/detail,
  and permanent Common Pool search now use bounded typed R0 actions.
- Added reversible Candidate archive, tag add/remove, and recruiter-note actions; matching
  UI controls use the same dispatcher and all four mutations support seven-day Undo.
- Added Candidate experience and education save/remove, structured profile merge/replace,
  resume application, and Rogue status actions. Matching UI controls share the dispatcher,
  and complete Candidate-state snapshots provide exact seven-day Undo.
- Added conservative Candidate duplicate detection and approval-gated canonical merge.
  Profile evidence and operational links move to the chosen survivor, the source remains
  archived as provenance, overlapping Hunt rows preserve activity, and Undo restores both.
- Added typed Candidate creation parity for UI and Copilot with identity-conflict refusal,
  optional Hunt enrollment, and dependency-aware Undo. Candidate detail now imports bounded
  local PDF/DOCX/TXT resumes into the reviewed profile-apply workflow without retaining the file.
- Automatic resume, migration of reports/outreach, and remaining domain parity are pending.

## 1. Product Definition

"Copilot can do everything" must not mean arbitrary database access or unrestricted code
execution. It means every supported OS workflow is exposed as a typed, policy-controlled
action that both Copilot and the visual UI call.

The finished system must provide:

1. Complete capability parity between Copilot and every authenticated UI command.
2. One action contract for UI, Copilot, scheduler, CLI, and future integrations.
3. A visible preview and explicit approval for risky or external actions.
4. Seven-day undo for every locally reversible mutation.
5. Durable progress, cancellation, retry, and recovery for long-running work.
6. Grounded results from canonical OS data, with no fabricated execution claims.
7. Clear disclosure when an external action cannot truly be undone.

## 2. Current Architecture

The production chat path is:

`copilot_panel.py -> streaming.py -> LangGraph ReAct agent -> audited LangChain tools -> action kernel/services`

The current strengths are:

- Persistent Hunt-scoped and general chat sessions.
- Hunt context injection for role, location, experience, skills, and Hunt ID.
- Streaming model responses with bounded output and incremental TTS.
- Background, cancellable sourcing while normal chat remains available.
- Useful tools for Hunt lifecycle, sourcing, pipeline triage, profile enrichment,
  intake review, connected-site status, and action-history undo.
- A seven-day action ledger with tested inverse operations for selected mutations.
- A typed action registry and `ActionContext` design containing identity, scopes,
  approval token, idempotency key, and undo metadata.

The main architectural problem is fragmentation:

- Eight typed actions are generated from the shared registry: six representative recruiting
  actions plus `actions.undo` and `jobs.retry`. Every production tool now has a structured call record, while
  the remaining legacy workflow tools still call services directly and return mostly
  untyped JSON strings.
- Hunt archive now uses a trusted, action-bound UI approval. Other sensitive tools that
  still accept model-supplied confirmation must be migrated to the same policy.
- UI handlers and Copilot tools independently implement the same operations.
- The action ledger covers only selected mutations, so history is not a complete record.
- Sourcing jobs are held in process memory and disappear when the application restarts.
- Conversations are stored in a JSON file while actions live in SQLite and semantic
  memories live in ChromaDB, preventing one transactional execution timeline.
- A legacy three-intent orchestrator is disconnected from production and contains stale
  argument contracts.
- A separate legacy CrewAI path contains synthetic scraper responses and must never be
  allowed into production execution.

## 3. Capability Parity Audit

| Domain | Current Copilot coverage | Main missing capabilities |
| --- | --- | --- |
| App context and navigation | Hunt dropdown context only | Current page/entity context, open page, focus record, deep-link results |
| Hunts | Strong | Consistent typed previews, search configuration detail, durable launch job |
| Sourcing | Strongest area | Durable jobs, per-source controls, retry failed source, scheduled runs, result provenance query |
| Common Pool / Discoveries | Core single-record parity | Bulk review, richer provenance filters, retry source |
| Candidates | Strong single-record parity, create, resume import, duplicate review/merge | Bulk maintenance and richer artifact provenance |
| Pipeline | Partial to strong | List scoped rows/stages, add stage, remove one with undo, bulk move, score/reason updates |
| Playbook | Read-oriented | Add/edit insight, inspect candidate decision history, reuse a query explicitly |
| Communications | Draft only | Threads, templates, delivery, status updates, sequences, enroll/pause/resume, due-step processing |
| Intake | Good partial coverage | Resend/revoke/expire link, compare submission diff, batch review |
| Analytics | None | Query KPIs/funnels/quality/cost/trends, explain metrics, export CSV/PDF/Excel |
| Settings | Minimal | AI/TTS preferences, SMTP setup/test, feature flags, theme, model status, safe key management |
| Connected sites | Read/disconnect | Interactive connect, reconnect, verify, test session, explain failure and retry |
| Action history | Partial | Complete event coverage, per-step details, filtering, universal inverse/compensation |
| Background work | Sourcing only | General durable job manager for enrichment, reports, outreach, indexing, imports |
| Administration | Intentionally limited | Health diagnostics, backup/export, migration status; password reset stays local-only |

## 4. Safety Model

Every action receives one risk classification enforced outside the model:

| Level | Meaning | Execution policy |
| --- | --- | --- |
| R0 Read | Query or navigation | Execute immediately |
| R1 Draft | Produces content but causes no delivery | Execute immediately |
| R2 Reversible write | Single-record local mutation with tested inverse | Execute on a clear imperative; show Undo immediately |
| R3 Sensitive or bulk write | Archive, delete, replace, bulk move, disconnect | Show exact preview/diff and require UI approval token |
| R4 External side effect | Send email/message, publish, schedule delivery | Always require approval; record delivery receipt; offer compensation, not fake undo |
| R5 Secret/admin | Credentials, password reset, backup restore | Human-only UI or local CLI with re-authentication |

Approval tokens must be short-lived and bound to:

- authenticated user ID;
- action name and normalized parameters;
- target record IDs and previewed record count;
- session/request ID;
- expiration time and one-time use.

A plain chat message such as `yes` must never authorize an action unless it resolves to
one current, unchanged preview fingerprint.

## 5. Target Action Architecture

### 5.1 One action kernel

Finish the existing `app/actions/registry.py` design and make it authoritative.

Each action specification must include:

- stable action name and version;
- Pydantic input and output models;
- required scopes and risk level;
- preview handler for R3/R4 operations;
- execution handler;
- inverse or compensation handler;
- idempotency strategy;
- resource locks and background-job policy;
- audit redaction rules;
- ownership and enforcing tests.

LangChain tools should be generated as thin adapters over registered actions. UI buttons
must call the same dispatcher. No Copilot or page handler should mutate ORM rows directly.

### 5.2 Durable execution records

Expand action history into an execution ledger containing:

- request, preview, approval, start, progress, completion, failure, cancellation, undo;
- actor, session, Hunt, Candidate, and affected resource IDs;
- redacted input, structured output, before/after snapshots, and errors;
- idempotency key, parent plan ID, step number, duration, and model/tool metadata.

Store chat turns and pending approvals in SQLite. ChromaDB remains a retrieval index,
not the source of truth for conversations or permissions.

### 5.3 Durable job manager

Replace the sourcing-only in-memory registry with a database-backed job model used by:

- sourcing and source retries;
- profile deep scans and enrichment;
- RAG reindexing;
- report generation;
- intake processing;
- outreach sequence processing;
- bulk imports and bulk edits.

Jobs need cooperative cancellation, heartbeat, progress, retry policy, ownership, and
startup recovery. Normal chat must remain available while jobs run.

Current status: sourcing and approved-profile enrichment use the shared durable schema and
persistence service. Restart recovery marks vanished workers `interrupted`, releases the
sourcing singleton, and reconciles visible Discovery state. Explicit Retry replays immutable
stored parameters into a linked attempt through `jobs.retry`. Automatic resume and the
remaining report/outreach/indexing job families are still open, so this section is not complete.

### 5.4 Copilot action UI

Render tool activity as compact action cards instead of embedding execution narration
inside assistant prose. Each card should support the applicable controls:

- Preview / proposed diff;
- Approve and Cancel;
- live progress and elapsed time;
- Stop for cancellable jobs;
- Retry after failure;
- Open affected record;
- Undo for reversible completed actions.

The composer remains available during jobs. Starting a conflicting job is blocked by
resource lock, while unrelated questions and actions remain usable.

## 6. Required Action Families

The registry should expose these families instead of accumulating unrelated manual tools:

- `app.context.*`: current page, selected Hunt/Candidate, navigation, health.
- `hunts.*`: list, get, create, update, status, archive, metrics, source, cancel, retry.
- `discoveries.*`: list, get, approve, reject, retry, bulk review, provenance.
- `candidates.*`: list, get, create, update, archive, merge, tags, notes, experience,
  education, resume, enrich, intake.
- `pipeline.*`: list stages/rows, assign, remove, move, keep, pass, bulk move, add stage.
- `playbook.*`: list, add insight, explain decision history, recommend queries.
- `communications.*`: threads, drafts, templates, send, delivery status, sequences,
  enrollment, pause/resume, process due steps.
- `analytics.*`: KPI, funnel, sourcing quality, outreach, cost, trends, exports.
- `connections.*`: list, verify, connect handoff, reconnect, disconnect.
- `settings.*`: read preferences, update non-secret preferences, model/TTS health.
- `actions.*`: list, get, preview, approve, cancel, retry, undo.

Secrets and password reset must not be exposed as ordinary model-callable tools.

## 7. Delivery Roadmap

### Phase 0: Stabilize the control plane

Goal: remove ambiguity before adding authority.

- Quarantine or delete the stale orchestrator and synthetic CrewAI scraper path.
- Freeze the current 29 tools and inventory every service/UI command.
- Add a parity manifest that maps UI commands to action names and risk levels.
- Add tests proving production chat uses only the supported action adapter.

Exit gate:

- No synthetic or dead agent path can be reached in production.
- Every current Copilot tool has an owner, risk class, and parity status.

### Phase 1: Activate the action kernel

Goal: establish one safe execution route.

- Add scopes, risk level, preview model, inverse handler, and version to `ActionSpec`.
- Implement signed, one-time approval tokens bound to preview fingerprints.
- Add idempotency persistence and affected-resource locks.
- Create structured action/tool-call tables and a durable pending-approval table.
- Generate LangChain adapters from the registry.
- Migrate five representative actions: Candidate read/update, discovery approve,
  pipeline move, and Hunt archive.

Exit gate:

- The same contract powers both the relevant UI buttons and Copilot.
- Replaying a request cannot duplicate a mutation.
- Altering parameters after approval invalidates the token.

### Phase 2: Core recruiting parity

Goal: Copilot can operate the complete internal recruiting workflow.

- Complete Hunts, Common Pool, Candidates, Pipeline, Playbook, and Intake action families.
- Add entity resolvers with ambiguity responses instead of first-match behavior.
- Add bulk previews with exact counts and bounded batches.
- Add universal seven-day undo for all reversible local mutations.
- Add current-page and selected-record context to Copilot sessions.

Exit gate:

- Every command available on these pages has a Copilot action and parity test.
- Every reversible mutation appears in Action History with a working Undo button.
- Dashboard and Pipeline refresh from canonical data after every action.

### Phase 3: Communications and external effects

Goal: Copilot can run outreach without silently crossing human boundaries.

- Add threads, templates, communication logs, sequences, and enrollment actions.
- Keep drafting R1; classify sending/scheduling as R4.
- Require approval cards showing recipients, channel, subject/body, and send count.
- Persist provider message IDs, delivery result, failure reason, and retry eligibility.
- Implement compensation actions where possible, such as pause sequence or send correction.

Exit gate:

- Copilot never reports sent without a provider success receipt.
- Duplicate-recipient and duplicate-send guards are tested.
- No external send can be triggered by model-supplied `confirm=True` alone.

### Phase 4: Analytics, reports, settings, and connections

Goal: close remaining OS parity gaps.

- Add grounded analytics queries with metric provenance.
- Generate and expose report artifacts through action results.
- Add non-secret preference and TTS/model health actions.
- Add guided browser connection/reconnection handoffs with status monitoring.
- Keep API keys, SMTP passwords, and administrator recovery behind human-only controls.

Exit gate:

- Copilot can answer every Dashboard/Analytics number from the same service used by UI.
- Report links open/download correctly.
- Secret values are never returned to model context or action history.

### Phase 5: Multi-step Copilot plans

Goal: safely complete compound recruiting objectives.

- Add a planner that produces a visible, editable sequence of registered actions.
- Execute independent R0/R1 steps in parallel and serialize conflicting mutations.
- Pause at R3/R4 steps for approval without blocking normal chat.
- Persist plan checkpoints so interrupted plans resume after restart.
- Support cancel step, cancel plan, retry step, and undo completed reversible steps.

Exit gate:

- A compound command such as "find 25 profiles, shortlist the best five, draft outreach,
  and ask me before sending" survives restart and stops at the send approval.
- Plans cannot bypass action policy or invoke unregistered operations.

### Phase 6: Hardening and release gate

Goal: make broad Copilot authority dependable.

- Build an end-to-end parity suite covering every action from UI and Copilot adapters.
- Add adversarial confirmation, prompt-injection, stale-preview, duplicate-call, and
  cross-Hunt isolation tests.
- Add permission tests for every scope and risk level.
- Add job crash/restart/cancel and undo conflict tests.
- Track action success rate, P95 latency, cancellation latency, retry rate, approval
  abandonment, undo success, duplicate prevention, and grounding failures.

Exit gate:

- 100% authenticated UI command parity.
- 100% local mutation audit coverage.
- 100% reversible local mutations have tested inverse handlers.
- Zero destructive or external actions execute without required trusted approval.
- Zero fabricated success claims in the evaluation suite.

## 8. Recommended First Implementation Slice

Start with Phase 0 and Phase 1, not with more standalone LangChain tools.

The first vertical slice should deliver:

1. Registered `candidates.get` and `candidates.update` actions.
2. Registered `discoveries.approve` and `discoveries.reject` actions.
3. Registered `pipeline.move` action.
4. One trusted approval-card flow with a fingerprinted token.
5. One structured completed-action card with progress, Open, and Undo.
6. UI and Copilot parity tests for all six representative actions.

This slice proves the architecture across read, reversible write, background work,
approval, navigation, and undo before migrating the rest of the OS.

Initial slice status: complete. The six representative actions, typed resource-locked
`actions.undo`, execution ledger, idempotency, durable Hunt-archive approval,
affected-resource locks, generated typed adapters, structured redacted tool-call records,
latest completed-action card with Open/Undo controls, and parity/security tests are
implemented. Durable sourcing and enrichment jobs plus the core Candidate/Common Pool
single-record families are also implemented. The overall roadmap remains in progress:
Phase 0 cleanup, remaining Hunt/Pipeline/Playbook/Intake parity, communications, analytics,
multi-step plans, and release hardening are still separate work.

Pipeline parity update: complete. Copilot and UI now share typed actions for board reads,
stage moves, canonical Candidate enrollment/move, single removal, Keep/Pass triage, and
custom-stage creation. All local writes have tested seven-day inverses, preserve the Common
Pool Candidate, use affected-resource locks, and appear in the shared action history. The
remaining roadmap work is Hunt create/edit/status parity, broader Playbook and Intake
commands, Communications, Dashboard/Analytics reads, multi-step plans, and release hardening.

## 9. Definition Of Copilot-First Complete

TalentHunt OS is Copilot-first complete only when:

- every authenticated UI command maps to one registered action;
- Copilot discovers actions from the registry rather than a manually maintained tool list;
- all action results are structured and linked to affected records;
- risky actions use trusted previews and approval tokens;
- every reversible local write is undoable for seven days;
- long-running actions are durable, cancellable, retryable, and restart-safe;
- external effects are truthfully reported and never described as undoable when they are not;
- chat, action, job, and approval history form one queryable execution timeline;
- tests demonstrate cross-Hunt isolation, canonical-data integrity, and no fabricated success.
