# Technical UI/UX Directives for AI Generation

## 1. Typography & Hierarchy Rules
- **Font Family**: Use exactly one font family (`Inter`, `system-ui`, fallback `sans-serif`) across the entire application interface.
- **Strict 4-Level Typography Hierarchy**:
  - **Display / Heading**: `24px` (Bold, line-height: 1.2)
  - **Subheading**: `18px` (Semi-bold, line-height: 1.4)
  - **Body Text**: `14px` (Regular, line-height: 1.5)
  - **Captions / Labels**: `12px` (Regular, line-height: 1.5)
- **No Pure Black**: Never use pure `#000000`. Use high-contrast accessible dark colors (e.g., `#1A1A1A` on light, `#F0FAF2` / `#F0F8FF` on dark).

## 2. Layout, Spacing, & Alignment Rules
- **8pt Spatial System**: All padding, margins, gaps, and component dimensions must be divisible by 8 (e.g., `8px`, `16px`, `24px`, `32px`, `48px`, `64px`).
- **Responsive Viewport Breakpoints**:
  - **Mobile**: `370px` width (Single column layout).
  - **Tablet**: `768px` width (Max 2 columns layout).
  - **Desktop**: `1440px` width (Max 12-column grid, `24px` gutters, max-width container `1200px`).
- **White Space Preservation**: Ensure at least 35% of the total screen viewport remains empty, uncrowded negative space.

## 3. Color & Interaction State Rules
- **60-30-10 Color Rule**:
  - **60%** Canvas / Background (e.g., `#070C14` / `#FFFFFF`)
  - **30%** Structural elements, cards, borders, text (e.g., `#0D1524`, `#152035`)
  - **10%** Accent / Action color (e.g., `#00F2FE` / `#84E42B` / `#2563EB` for primary buttons & focus states)
- **Accessible Contrast**: Every text/background combination must strictly pass a minimum contrast ratio of 4.5:1 (WCAG AA compliant).
- **Five Component Interaction States**: Every interactive component must define:
  1. **Default**
  2. **Hover**
  3. **Focus** (Visible 2px outline)
  4. **Active / Pressed**
  5. **Disabled** (`opacity: 0.4`, `cursor: not-allowed`)

## 4. Forms, Input, & Error Handling Rules
- **Vertical Form Stacking**: Place form labels directly above input fields. Never place labels horizontally side-by-side.
- **Accessible Touch Targets**: Ensure all buttons, links, and form input fields have a minimum interactive area of `48x48px`.
- **Local Input Validation**: Display error messages instantly underneath the specific input field in red (`#DC2626`). Avoid pop-up alerts or global top-of-page summaries.
- **Structured Empty States**: Generate structured Empty States featuring a 48px descriptive icon, a short explanation sentence, and exactly one primary action button.
