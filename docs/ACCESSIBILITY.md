# Accessibility Verification

Accessibility is part of feature completion for TalentHunt OS. Automated results are a
starting point; keyboard, semantics, content, and visual behavior still require review.

## Local Automated Audit

Install the locked Python development group and the single local Node audit dependency:

```powershell
uv sync --group dev
npm install
```

Start TalentHunt OS at its fixed loopback address:

```powershell
uv run python -m app.main
```

In another terminal, audit the login page at desktop and mobile widths:

```powershell
uv run python scripts/accessibility_audit.py
```

Audit every core authenticated page using a short-lived local session:

```powershell
uv run python scripts/accessibility_audit.py --authenticated
```

Authenticated mode uses the active local administrator record to sign a temporary browser
session. It does not read, reset, or print the administrator password. A Playwright
storage-state file can still be supplied explicitly with `--storage-state` when needed.

The script injects `node_modules/axe-core/axe.min.js` locally. It does not download code at
runtime or send page content to an external service. Reports are written under
`output/accessibility/`, which is ignored by Git. Each run checks Axe WCAG rules and rejects
document-level horizontal overflow at the desktop and mobile viewports.

## Manual Keyboard Pass

For each changed page:

1. Navigate every command with Tab and Shift+Tab.
2. Confirm focus is visible and follows the visual reading order.
3. Activate buttons and links with Enter or Space as appropriate.
4. Open and close dialogs without losing focus or trapping the keyboard.
5. Use the Copilot composer, background-job Cancel, approval, and Undo without a mouse.
6. Confirm external candidate links communicate that they open a new tab.
7. Confirm errors are announced in text and do not rely on color alone.

## Visual And Responsive Pass

- Check `1440x900`, `1280x720`, `390x844`, and `360x800` viewports.
- Verify 200% browser zoom on core recruiting workflows.
- Check long candidate names, long skills, URLs, empty records, and large counts.
- Check light-sensitive animation with reduced motion enabled.
- Confirm contrast for primary, muted, success, warning, danger, focus, and disabled states.

## Acceptance

A UI change is ready only when no serious axe-core violations remain, every core command is
keyboard reachable, focus is visible, text is readable without overlap, and any accepted
exception is documented with an owner and follow-up.
