# Architecture Pattern Record

This document names patterns already justified by TalentHunt OS behavior. It is not a
catalog of patterns the project should add.

## Command And Policy Boundary

The action registry implements the Command pattern. UI controls and Copilot tools dispatch
the same typed command, while the dispatcher applies scope, risk, approval, idempotency,
resource locking, execution history, and error policy.

Use it when a user-visible operation changes state or starts external work. Do not create a
second mutation path in a page callback or model-specific Copilot tool.

## Memento And Compensation

Action history stores the minimum exact prior state needed for seven-day Undo. Pure local
mutations use inverse operations. External effects use explicit compensation when honest
compensation exists; otherwise they are marked irreversible before approval.

Undo must refuse when later state makes restoration unsafe. It must never report success
after a partial or guessed restoration.

## State Machines

Copilot routing and durable background jobs use explicit state machines. State names are
persisted and visible so restart recovery, cancellation, retry, and final messaging reflect
the real operation rather than the UI's last memory.

Do not represent running work with an in-memory Boolean when restart or cancellation
matters.

## Durable Job Runner

Long sourcing and enrichment work is recorded before execution and heartbeats while
running. One active sourcing lease prevents conflicting searches while ordinary Copilot
chat remains available. Cancellation is a durable request observed at bounded checkpoints.

Job payloads contain identifiers and safe parameters, not plaintext credentials or full
candidate profiles.

## Canonical Data And Replaceable Indexes

SQLite Candidate and Hunt records are operational truth. Discovery records retain the
permanent Common Pool. ChromaDB and SQLite FTS5 are derived retrieval indexes and can be
rebuilt without changing permissions, pipeline membership, or Dashboard counts.

Any new cache, report store, or analytics engine must follow the same rule.

## Transaction Boundary

A SQLAlchemy session is the unit of work for one domain action. Related candidate, Hunt,
Pipeline, Playbook, Intake, and audit changes commit together. Service functions may read
directly, but mutations must preserve the registered action's transaction and history.

## Pattern Adoption Rule

Add a pattern only when it removes observed complexity or protects a stated invariant.
Record the problem, owner, data boundary, failure mode, test, and rollback. Do not introduce
distributed-system patterns, event buses, or secondary sources of truth for hypothetical
scale.
