# Frontend Design & UI Planning Rule

## Core Directive
Before starting any frontend code modification or UI component implementation:
1. **Plan the UI Layout First**: Thoroughly analyze the layout hierarchy, flexbox container constraints, element heights (`h-screen`, `max-h-screen`, `h-0 grow`), and overflow behavior (`overflow-y-auto`, `sticky`, `fixed`).
2. **Ensure High Contrast & Aesthetic Excellence**:
   - Never place dark text on dark backgrounds or light text on light backgrounds.
   - Use curated color palettes (e.g., Cyberpunk Cyan, Emerald Lime, Solar Gold, Royal Violet).
   - Ensure every typography element, timestamp, header, and body text has crisp contrast and readability.
3. **Verify Function & Callback Scope Order**:
   - Always define event handlers (`async def handle_send(...)`) before passing them to UI component props or event listeners (`on_click`, `on('keydown.enter')`) to prevent `UnboundLocalError`.
4. **Scrolled Containers & Sticky Controls**:
   - Ensure input bars and panel headers remain pinned (`shrink-0`), while content areas scroll smoothly inside bounded height flexbox containers (`h-0 grow overflow-y-auto`).
