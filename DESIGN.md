# TalentHunt OS Design Contract

This file is the project-native visual and interaction contract for people and coding
agents changing TalentHunt OS. It describes this product; it does not reproduce another
company's brand or design system.

## Product Character

TalentHunt OS is a dense recruiting workspace used repeatedly throughout a working day.
It should feel quiet, direct, trustworthy, and fast. Candidate evidence, job state, and
consequential actions matter more than decoration.

- Build the usable workspace first. Do not add marketing heroes or feature-tour copy.
- Prefer compact, scan-friendly layouts over decorative card grids.
- Keep the Copilot visibly present because it is an operating surface, not an add-on.
- Make action state honest: pending, approval required, running, cancelling, completed,
  failed, and undone must be visually distinct.
- Preserve human control for bulk, destructive, external, and credential-related work.

## Core Tokens

The default Modern Ocean palette uses neutral blue-black surfaces with teal, green, amber,
red, and blue carrying different meanings. New UI must not collapse these into a single
hue family.

| Token | Value | Purpose |
| --- | --- | --- |
| Canvas | `#071019` | Page background |
| Surface | `#08121d` | Navigation and Copilot panels |
| Elevated surface | `#0e1b28` | Toolbars and focused work areas |
| Border | `#1b3040` | Structural separation |
| Primary text | `#edf5f7` | Headings and critical values |
| Secondary text | `#8195a5` | Metadata and supporting copy |
| Primary teal | `#19d3c5` | Selection, focus, active state, primary commands |
| Success green | `#45d6a0` | Completed and healthy states |
| Warning amber | `#d8941e` | Background work, caution, and review states |
| Danger red | `#d65a68` | Irreversible risk and destructive confirmation |
| Link blue | `#73aff3` | External destinations and navigable records |

- Use flat surfaces. Gradients may appear only in small identity accents already present.
- Use a maximum `8px` radius for new cards, panels, fields, and command surfaces.
- Do not put cards inside cards. Sections are unframed bands separated by spacing or rules.
- Focus rings use a visible `2px` teal outline and must never rely on color alone.

## Typography

- Use Inter when available, then the system sans-serif stack.
- Page title: `25px`, weight 750, line height 1.2.
- Section heading: `14px`, weight 700.
- Body and input text: `13-14px`, line height at least 1.45.
- Supporting metadata: never smaller than `10px` when it communicates status or evidence.
- Letter spacing is `0`. Do not scale type from viewport width.
- Long names, URLs, titles, and skills must wrap or ellipsize without resizing the layout.

## Layout

Desktop uses the established three-panel operating shell:

1. Left navigation: fixed `220px`.
2. Main workspace: flexible `minmax(0, 1fr)` with local scrolling where needed.
3. Copilot: fixed `320px`, full-height, with a pinned header and composer.

- Hide the desktop Copilot below `1050px`; make it a full-width mobile overlay when opened.
- Replace the sidebar with the bottom mobile navigation below `700px`.
- Candidate review uses a list/detail split and collapses to one column below `850px`.
- Fixed-format boards, counters, toolbars, and profile panes require explicit dimensions so
  loading, hover, labels, and status updates do not shift the surrounding layout.
- Every mobile and desktop state must be checked for clipping, overlap, unreadable text,
  and unreachable controls.

## Components

- Use Material or Lucide-equivalent familiar icons for icon commands and add tooltips.
- Use text buttons only for clear commands such as Shortlist, Save, Cancel, or Undo.
- Use tabs for views, segmented controls for modes, switches for binary settings, selects
  for bounded option sets, and numeric inputs for quantities.
- Candidate source tags and profile links open the related destination in a new browser tab.
- Status chips are compact labels, not buttons, unless they directly change status.
- Candidate cards show identity, role, location, experience evidence, source, and current
  decision without hiding critical information behind hover.
- Empty, loading, error, disconnected, permission-denied, and cancelled states are designed
  states and must not be represented by blank space.

## Copilot

The Copilot panel has four stable regions: header and Hunt context, scrollable conversation,
optional background-job status, and composer.

- The composer is full width with a multiline typing area of at least `54px` and a maximum
  height that preserves conversation context.
- Normal chat never creates the amber background-job panel.
- Sourcing and enrichment show one compact amber status row with progress and immediate
  Cancel. Cancelling changes state promptly even if a worker is still unwinding.
- Background sourcing must not block ordinary questions. It only blocks starting another
  conflicting sourcing job.
- Confirmation prompts name the exact action, scope, affected records, reversibility, and
  approval expiry. A short `yes` applies only to the newest matching pending approval.
- Completed reversible actions expose Undo and its remaining retention period.
- Speech starts from stable streamed clauses and stops when the user disables audio,
  interrupts playback, navigates away, or sends a newer request.

## Accessibility

- All interactive controls require an accessible name and keyboard focus state.
- Icon-only controls require tooltips and an `aria-label` or equivalent rendered name.
- Forms require persistent labels; placeholder text is never the sole label.
- Do not encode success, warning, source, or pipeline state with color alone.
- Maintain WCAG AA contrast for ordinary text and meaningful controls.
- Respect reduced-motion preferences and avoid nonessential continuous animation.
- Validate desktop and mobile pages with the local Playwright plus axe-core audit and a
  manual keyboard pass described in `docs/ACCESSIBILITY.md`.

## Change Checklist

Before merging a UI change:

1. Verify the control uses the shared domain action when it mutates data.
2. Check loading, empty, failure, cancellation, approval, and Undo states.
3. Capture desktop and mobile screenshots from the real loopback application.
4. Run the local accessibility audit and complete the keyboard checklist.
5. Confirm no text overlaps, overflows its control, or becomes too small to read.
6. Update this document when a visual or interaction rule changes.
