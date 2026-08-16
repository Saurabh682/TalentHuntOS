# Comparable Recruitment Platform Review

Reviewed on 2026-08-14. These repositories are product and architecture references, not
dependencies. TalentHunt does not copy code from repositories with absent, unclear, mixed,
source-available, or all-rights-reserved licensing.

## What TalentHunt adopts

- Keep one durable candidate activity timeline and explicit lifecycle states, following the
  mature workflow coverage visible in OpenCATS.
- Keep the lightweight split-pane and Kanban review ideas seen in mini-ats and The Talent App,
  while preserving NiceGUI and responsive TalentHunt components.
- Keep a four-stage evidence flow: retained Discovery, Hunt review, canonical Candidate, then
  recruiter-approved deep enrichment. TalentSol is a useful comparison for staged screening.
- Treat external integrations as typed resources with authentication boundaries, idempotency,
  webhook or provider receipts, and visible failures. The Greenhouse and Lever n8n nodes are
  reference contracts only.
- Keep resume and profile claims visible as evidence before canonical approval. readout is a
  useful data-minimization and parsing-transparency reference.
- Add privacy, retention, provenance, and governed-AI checks before broader automation.
  TalentSphere is a useful product-governance reference, not a scope target.
- Retain interview questions, evaluations, scheduling, and applicant portals as later roadmap
  modules. They must use the same action kernel, approval model, audit history, and local-first
  defaults as the rest of TalentHunt.

## Repository decisions

| Repository | License found | Decision | Useful reference |
| --- | --- | --- | --- |
| OmarNouih/SmartRecruit_LLM | Not declared | Watchlist, ideas only | Interview questions, evaluations, recruiter/candidate workflow |
| opencats/OpenCATS | MPL-2.0 plus CATS Public License 1.1a | Approved reference, ideas only | Mature ATS entities, activity history, submissions, reports |
| ynixt/simple-ats | Not declared; archived | Excluded from adoption | Basic ATS vocabulary only |
| DominikKanjuh/FER-bachelor-thesis | Not declared | Watchlist, ideas only | Resume editing and explainable suggestions |
| shvmpk/next-hire-ai | MIT | Watchlist reference | Job-description and resume comparison |
| TanushreeSarkar/HireLightATS | Not declared | Watchlist, ideas only | Score trends and skill recommendations |
| phun333/scoutly | Not declared | Watchlist, ideas only | Application evidence and risk presentation |
| Thelastpoet/africa-ats-directory | MIT | Low-priority reference | Public job-board endpoint taxonomy, not candidate scraping |
| youshen-lim/TalentSol---Applicant-Tracking-System-Application | MIT | Approved reference | Staged candidate data pipeline |
| Usman-N123/Procruit | Not declared | Watchlist, ideas only | Scheduling and structured technical assessment |
| shatakshisingh28/smart-resume-hire | Not declared | Watchlist, ideas only | Candidate evaluation presentation |
| kristinaxm/mini-ats | Apache-2.0 | Approved reference | Focused Kanban and candidate review interactions |
| Velocity-BPA/n8n-nodes-greenhouse | BUSL-1.1 | Watchlist, no installation | Integration resources, webhooks, GDPR operations |
| Velocity-BPA/n8n-nodes-lever | BUSL-1.1 | Watchlist, no installation | Auth modes, regional APIs, webhook and file contracts |
| Hazem-Soliman-dev/HireFlow | Not declared | Watchlist, ideas only | Role-aware Kanban and interview scheduling |
| khianvictorycalderon/Applicant-Tracking-System | Not declared | Watchlist, ideas only | Local-network HR workflow concepts |
| willianOliveira-dev/recruta-api | All rights reserved | Excluded from code use | Multi-tenant vocabulary only |
| ChinmayyK/TalentSync | Not declared | Watchlist, ideas only | Tenant-bound service boundaries |
| ctkrug/readout | MIT | Approved reference | Client-side parsing transparency and data minimization |
| armansyed0098-ux/ATSbeta | Not declared | Watchlist, ideas only | Staffing CRM workflow vocabulary |
| vikashsparxit/the-talent-app | MIT | Approved reference | Jobs, candidates, interviews, and applicant-portal completeness |
| ildrm/talentsphere-linkedin-clone | MIT | Approved governance reference | GDPR privacy, provenance, and governed AI |

## Current implementation consequence

The Communications R4 slice applies the most immediately useful shared pattern: an external
email is represented by a durable pending attempt, an exact human-reviewed message, one-time
approval, provider receipt, explicit failed or unknown state, and duplicate-send protection.
Successful external delivery is recorded as irreversible and never presented as Undo.
