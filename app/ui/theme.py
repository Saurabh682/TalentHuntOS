"""Dark-mode Modern Ocean theme for TalentHunt OS (design-pack aligned)."""

from nicegui import ui

COLOR_SCHEMES = {
    "modern_ocean": {
        "name": "Modern Ocean (Default)",
        "bg": "#071019",
        "surface": "#08121d",
        "surface_elevated": "#0e1b28",
        "border": "#1b3040",
        "text": "#edf5f7",
        "muted": "#8195a5",
        "gradient": "linear-gradient(135deg, #19d3c5 0%, #0e3a45 100%)",
        "accent": "#19d3c5",
        "primary": "#10a99f",
        "gold": "#d8941e",
        "bot_bubble": "#152738",
        "bot_border": "#285166",
        "bot_text": "#dce7eb",
        "user_bubble": "#123542",
        "user_border": "#19d3c5",
        "user_text": "#edf5f7",
    },
    "recruiter_os": {
        "name": "Minimal Mint Recruiter OS",
        "bg": "#050607",
        "surface": "#0B0D0F",
        "surface_elevated": "#121619",
        "border": "#1E2226",
        "text": "#E7E9EA",
        "muted": "#8A9096",
        "gradient": "linear-gradient(135deg, #3ED9A6 0%, #10241D 100%)",
        "accent": "#3ED9A6",
        "primary": "#3ED9A6",
        "gold": "#3ED9A6",
        "bot_bubble": "#121619",
        "bot_border": "#1E2226",
        "bot_text": "#C7CBCE",
        "user_bubble": "#10241D",
        "user_border": "#3ED9A6",
        "user_text": "#E7E9EA",
    },
    "emerald": {
        "name": "Vibrant Emerald & Lime",
        "bg": "#06120a",
        "surface": "#0b1c11",
        "surface_elevated": "#12291b",
        "border": "rgba(123, 225, 40, 0.25)",
        "text": "#f0faf2",
        "muted": "#81a889",
        "gradient": "linear-gradient(135deg, #84e42b 0%, #1fb138 60%, #074f20 100%)",
        "accent": "#84e42b",
        "primary": "#84e42b",
        "gold": "#9ef04d",
        "bot_bubble": "#0d2114",
        "bot_border": "#1fb138",
        "bot_text": "#f0faf2",
        "user_bubble": "linear-gradient(135deg, #1fb138 0%, #0d6b27 100%)",
        "user_border": "#1fb138",
        "user_text": "#ffffff",
    },
    "cyberpunk": {
        "name": "Electric Cyan & Blue",
        "bg": "#070c14",
        "surface": "#0d1524",
        "surface_elevated": "#152035",
        "border": "rgba(0, 242, 254, 0.25)",
        "text": "#f0f8ff",
        "muted": "#7ba4c7",
        "gradient": "linear-gradient(135deg, #00f2fe 0%, #4facfe 60%, #1e3a8a 100%)",
        "accent": "#00f2fe",
        "primary": "#00f2fe",
        "gold": "#4facfe",
        "bot_bubble": "#0d1b2a",
        "bot_border": "#00f2fe",
        "bot_text": "#f0f8ff",
        "user_bubble": "linear-gradient(135deg, #00f2fe 0%, #2563eb 100%)",
        "user_border": "#00f2fe",
        "user_text": "#ffffff",
    },
    "amber": {
        "name": "Solar Gold & Amber",
        "bg": "#140f07",
        "surface": "#1f170b",
        "surface_elevated": "#2d2212",
        "border": "rgba(251, 191, 36, 0.25)",
        "text": "#fefce8",
        "muted": "#ba9f70",
        "gradient": "linear-gradient(135deg, #fbbf24 0%, #d97706 60%, #78350f 100%)",
        "accent": "#fbbf24",
        "primary": "#fbbf24",
        "gold": "#fbbf24",
        "bot_bubble": "#261c0e",
        "bot_border": "#f59e0b",
        "bot_text": "#fefce8",
        "user_bubble": "linear-gradient(135deg, #fbbf24 0%, #b45309 100%)",
        "user_border": "#fbbf24",
        "user_text": "#1c1408",
    },
    "violet": {
        "name": "Royal Violet & Indigo",
        "bg": "#0c0a1d",
        "surface": "#151233",
        "surface_elevated": "#201c47",
        "border": "rgba(168, 85, 247, 0.25)",
        "text": "#faf5ff",
        "muted": "#9d8ec7",
        "gradient": "linear-gradient(135deg, #c084fc 0%, #7c3aed 60%, #312e81 100%)",
        "accent": "#c084fc",
        "primary": "#c084fc",
        "gold": "#c084fc",
        "bot_bubble": "#1a153b",
        "bot_border": "#8b5cf6",
        "bot_text": "#faf5ff",
        "user_bubble": "linear-gradient(135deg, #a855f7 0%, #4338ca 100%)",
        "user_border": "#8b5cf6",
        "user_text": "#ffffff",
    },
}

CURRENT_THEME_KEY = "modern_ocean"

def get_theme_css(scheme_key: str = "modern_ocean") -> str:
    s = COLOR_SCHEMES.get(scheme_key, COLOR_SCHEMES["modern_ocean"])
    return (  # CSS interpolation; Bandit B608 is tracked as a report-only false positive.
        f"""
:root {{
  --th-bg: {s['bg']};
  --th-surface: {s['surface']};
  --th-surface-elevated: {s['surface_elevated']};
  --th-border: {s['border']};
  --th-text: {s['text']};
  --th-muted: {s['muted']};
  --th-teal: {s['accent']};
  --th-gold: {s['gold']};
  --th-emerald: {s['accent']};
  --th-primary: {s['primary']};
  --th-gradient: {s['gradient']};
  --th-gradient-pill: {s['gradient']};
}}

html, body, #app, #q-app {{
  background: var(--th-bg) !important;
  color: var(--th-text) !important;
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 13px;
  overflow-x: hidden;
}}

.q-layout, .q-page-container, .q-page {{
  background: transparent !important;
}}

.th-shell {{
  /* overridden below in layout stability block */
  background: var(--th-bg);
}}

.th-sidebar {{
  background: var(--th-surface);
  border-right: 1px solid var(--th-border);
}}

.th-copilot-panel {{
  background: var(--th-surface);
  border-left: 1px solid var(--th-border);
}}

.th-main {{
  /* overridden below in layout stability block */
  background: var(--th-bg);
}}

.th-card, .th-panel {{
  background: linear-gradient(145deg, #0e1b28, #0a1520);
  border: 1px solid var(--th-border);
  border-radius: 13px;
  box-shadow: none;
}}

.th-card-inner {{
  background: #0f1d2b !important;
  color: var(--th-text) !important;
  border: 1px solid var(--th-border);
  border-radius: 10px;
}}

.th-ey {{
  color: var(--th-teal);
  font-size: 10px !important;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-weight: 600;
}}

.th-title {{
  font-size: 25px !important;
  font-weight: 750 !important;
  color: var(--th-text) !important;
  margin: 5px 0 !important;
  line-height: 1.2 !important;
}}

.th-muted {{
  color: var(--th-muted) !important;
  font-size: 11px !important;
}}

.th-label {{
  color: #8296a7 !important;
  font-size: 10px !important;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}}

.th-num {{
  font-size: 25px !important;
  font-weight: 700 !important;
  margin: 8px 0 !important;
  color: var(--th-text) !important;
}}

.th-up {{
  color: #45d6a0 !important;
  font-size: 10px !important;
}}

.th-nav-item {{
  color: #8ea4b4 !important;
  background: transparent !important;
  border: none !important;
  border-radius: 9px !important;
  transition: all 0.15s ease;
}}

.th-nav-item *, .th-nav-item .q-btn__content * {{
  color: #8ea4b4 !important;
}}

.th-nav-item:hover {{
  background: #123542 !important;
}}

.th-nav-item:hover *, .th-nav-item:hover .q-btn__content * {{
  color: #ffffff !important;
}}

.th-nav-item-active {{
  background: #123542 !important;
  color: #ffffff !important;
  border-radius: 9px !important;
}}

.th-nav-item-active *, .th-nav-item-active .q-btn__content * {{
  color: #ffffff !important;
}}

.th-gold-btn, .th-teal-btn, .th-primary-btn {{
  background: var(--th-primary) !important;
  color: #071019 !important;
  font-weight: 650 !important;
  border-radius: 9px !important;
  border: 1px solid var(--th-teal) !important;
  box-shadow: none !important;
  font-size: 11px !important;
  min-height: 36px !important;
}}

.th-gold-btn *, .th-teal-btn *, .th-primary-btn *,
.th-gold-btn .q-btn__content *, .th-teal-btn .q-btn__content *, .th-primary-btn .q-btn__content * {{
  color: #071019 !important;
}}

.th-amber-btn {{
  background: var(--th-gold) !important;
  color: #071019 !important;
  font-weight: 650 !important;
  border-radius: 9px !important;
  border: none !important;
  min-height: 36px !important;
}}

.th-amber-btn *, .th-amber-btn .q-btn__content * {{
  color: #071019 !important;
}}

.th-slate-btn {{
  background: #0d1b28 !important;
  color: #dce7eb !important;
  border: 1px solid #1d3445 !important;
  font-weight: 650 !important;
  border-radius: 9px !important;
  font-size: 11px !important;
  min-height: 36px !important;
}}

.th-slate-btn *, .th-slate-btn .q-btn__content * {{
  color: #dce7eb !important;
}}

button.q-btn.th-slate-btn {{
  background: #0d1b28 !important;
  color: #dce7eb !important;
}}

.th-tab {{
  padding: 9px 11px !important;
  background: #0e1c29 !important;
  border-radius: 8px !important;
  color: #8ea4b4 !important;
  font-size: 11px !important;
  min-height: 32px !important;
}}

.th-tab-on {{
  background: #16434a !important;
  color: #bffff8 !important;
}}

button.q-btn.th-tab-on, button.q-btn.th-tab-on * {{ color: #bffff8 !important; }}
button.q-btn.bg-primary.text-white, button.q-btn.bg-primary.text-white * {{
  color: #071019 !important;
}}

.th-pill {{
  padding: 4px 7px;
  border-radius: 6px;
  background: #173342;
  color: #8de8df;
  font-size: 9px;
  display: inline-block;
}}

.th-pill-green {{
  background: #12382f;
  color: #74e3b0;
}}

.th-engine {{
  border: 1px solid var(--th-border);
  border-radius: 10px;
  padding: 12px;
  color: #8296a7;
  font-size: 11px;
}}

.th-engine b {{
  color: var(--th-teal);
  font-weight: 600;
}}

.th-funnel {{
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  background: #09131d;
  border: 1px solid #1a2d3c;
  border-radius: 9px;
  overflow: hidden;
}}

.th-funnel-stage {{
  padding: 13px;
  border-right: 1px solid #1a2d3c;
}}

.th-funnel-stage:last-child {{
  border-right: 0;
}}

.th-bar {{
  height: 4px;
  background: #263746;
  border-radius: 4px;
  overflow: hidden;
}}

.th-bar-fill {{
  display: block;
  height: 100%;
  background: var(--th-teal);
  border-radius: 4px;
}}

.th-chart-spark {{
  height: 115px;
  margin-top: 10px;
  background: linear-gradient(180deg, #19d3c515, transparent);
  clip-path: polygon(0 80%,8% 62%,16% 72%,25% 48%,34% 58%,44% 35%,54% 52%,63% 25%,72% 41%,82% 20%,91% 33%,100% 12%,100% 100%,0 100%);
  border-bottom: 2px solid var(--th-teal);
}}

.th-donut {{
  width: 125px;
  height: 125px;
  margin: 10px auto;
  border-radius: 50%;
  background: conic-gradient(#19d3c5 0 50%, #5b8cff 50% 76%, #9a6cff 76% 92%, #50647a 92%);
  position: relative;
}}

.th-donut::after {{
  content: attr(data-center);
  position: absolute;
  inset: 27px;
  border-radius: 50%;
  background: #0d1824;
  display: grid;
  place-items: center;
  font-size: 23px;
  color: var(--th-text);
}}

.th-insight {{
  border: 1px solid var(--th-border);
  border-radius: 9px;
  padding: 11px;
  margin: 7px 0;
}}

.th-kanban-col {{
  background: #091520;
  border: 1px solid var(--th-border);
  border-radius: 11px;
  padding: 10px;
  min-height: 0;
  height: 100%;
  max-height: 100%;
  display: flex;
  flex-direction: column;
  flex: 0 0 288px;
  width: 288px;
  box-sizing: border-box;
}}

.th-kanban-cards {{
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}}

/* Pipeline: keep board scroll inside the viewport (H-scrollbar under columns, not page bottom) */
.th-main:has(.th-pipeline-page) {{
  overflow: hidden !important;
  display: flex !important;
  flex-direction: column !important;
}}

.th-main > .th-pipeline-page {{
  display: flex !important;
  flex-direction: column !important;
  flex: 1 1 auto !important;
  height: 100% !important;
  max-height: 100% !important;
  min-height: 0 !important;
  width: 100% !important;
  gap: 0 !important;
}}

.th-pipeline-header {{
  flex: 0 0 auto !important;
  margin-bottom: 16px !important;
}}

.th-pipeline-board {{
  flex: 1 1 auto !important;
  min-height: 0 !important;
  width: 100% !important;
  max-width: 100% !important;
  overflow-x: auto !important;
  overflow-y: hidden !important;
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  align-items: stretch !important;
  gap: 9px !important;
  padding-bottom: 10px !important;
}}

.th-candidate-card {{
  background: #0f1d2b;
  border: 1px solid var(--th-border);
  border-radius: 8px;
  padding: 10px;
  margin: 8px 0;
}}

.th-avatar {{
  display: inline-grid;
  place-items: center;
  width: 27px;
  height: 27px;
  border-radius: 50%;
  background: linear-gradient(135deg, #19cbbd, #536cff);
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  color: #fff;
}}

.q-avatar .q-avatar__content {{
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  line-height: 1 !important;
}}

.th-select {{
  background: #091520 !important;
  border: 1px solid var(--th-border) !important;
}}

.th-table th {{
  font-size: 9px !important;
  color: #8195a5 !important;
  text-align: left;
  padding: 10px !important;
  border-bottom: 1px solid var(--th-border) !important;
  background: transparent !important;
}}

.th-table td {{
  padding: 12px 10px !important;
  border-bottom: 1px solid #152734 !important;
  font-size: 11px !important;
}}

.text-display, h1, .th-display {{
  font-size: 25px !important;
  line-height: 1.2 !important;
  font-weight: 750 !important;
}}

.text-subheading, h2, .th-subheading {{
  font-size: 13px !important;
  line-height: 1.4 !important;
  font-weight: 600 !important;
}}

.text-body, .th-body {{
  font-size: 13px !important;
  line-height: 1.5 !important;
}}

.text-caption, .th-caption {{
  font-size: 10px !important;
  line-height: 1.5 !important;
  color: #8da2b2 !important;
}}

button, .q-btn {{
  min-height: 36px !important;
}}

.q-btn:focus-visible, input:focus-visible, .q-field--focused {{
  outline: 2px solid {s['accent']} !important;
  outline-offset: 2px !important;
}}

button:disabled, .q-btn--disabled, input:disabled {{
  opacity: 0.4 !important;
  cursor: not-allowed !important;
}}

/* Let Quasar own floating/stacked labels — do NOT force relative positioning */
.q-field__label {{
  color: #8da2b2 !important;
}}

.q-field--outlined .q-field__control {{
  background: #091520 !important;
  border-radius: 8px !important;
  min-height: 40px !important;
}}

.q-field--outlined.q-field--dense .q-field__control {{
  min-height: 36px !important;
}}

.q-field--outlined .q-field__control:before {{
  border-color: var(--th-border) !important;
}}

.q-field--outlined .q-field__native,
.q-field--outlined .q-field__input,
.q-field--outlined .q-select__dropdown-icon {{
  color: var(--th-text) !important;
}}

.q-field--outlined .q-field__marginal {{
  height: auto !important;
}}

/* Native selects / placeholders must not collide with values */
.q-field__native, .q-placeholder {{
  line-height: 1.4 !important;
}}

.q-message-text {{
  border-radius: 12px !important;
  font-size: 13px !important;
  line-height: 1.5 !important;
  padding: 12px 14px !important;
}}

.q-message-text--received {{
  background: {s['bot_bubble']} !important;
  border: 1px solid {s['bot_border']} !important;
  box-shadow: none !important;
}}

.q-message-text--received,
.q-message-text--received *,
.q-message-text--received p,
.q-message-text--received span,
.q-message-text--received li,
.q-message-text-content--received {{
  color: {s['bot_text']} !important;
}}

.q-message-text--received strong,
.q-message-text--received b,
.q-message-text--received h1,
.q-message-text--received h2,
.q-message-text--received h3 {{
  color: {s['accent']} !important;
  font-weight: 700 !important;
}}

.q-message-text--received code {{
  background: {s['bg']} !important;
  color: {s['accent']} !important;
  padding: 2px 6px !important;
  border-radius: 4px !important;
}}

.q-message-text--sent {{
  background: {s['user_bubble']} !important;
  border: 1px solid {s['accent']} !important;
  box-shadow: none !important;
}}

.q-message-text--sent,
.q-message-text--sent *,
.q-message-text--sent p,
.q-message-text--sent span,
.q-message-text-content--sent {{
  color: {s['user_text']} !important;
  font-weight: 500 !important;
}}

.q-message-name {{
  color: {s['accent']} !important;
  font-weight: 700 !important;
  font-size: 11px !important;
}}

.q-message-stamp {{
  color: #91a8b7 !important;
  font-size: 10px !important;
  margin-top: 4px !important;
  opacity: 1 !important;
}}

.text-slate-500, .text-slate-600 {{ color: #91a8b7 !important; }}
.q-badge.q-badge.bg-teal, .q-badge.q-badge.bg-positive, .q-badge.q-badge.bg-orange,
.q-badge.q-badge.bg-primary {{ color: #071019 !important; }}
.q-badge.q-badge.bg-blue-grey {{ background: #344954 !important; }}
.q-badge.q-badge.bg-blue-grey.text-teal-300 {{ color: #a7f3e8 !important; }}
.q-badge.q-badge.q-badge--outline.text-blue-grey {{ color: #91a8b7 !important; }}

.custom-scrollbar::-webkit-scrollbar, ::-webkit-scrollbar {{
  width: 6px;
  height: 6px;
}}
.custom-scrollbar::-webkit-scrollbar-track, ::-webkit-scrollbar-track {{
  background: rgba(0, 0, 0, 0.3);
  border-radius: 4px;
}}
.custom-scrollbar::-webkit-scrollbar-thumb, ::-webkit-scrollbar-thumb {{
  background: {s['accent']};
  opacity: 0.5;
  border-radius: 4px;
}}

/* Layout stability — prevent Quasar flex stretch from breaking the shell */
.th-shell {{
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  align-items: stretch !important;
  width: 100% !important;
  height: 100vh !important;
  max-height: 100vh !important;
  overflow: hidden !important;
}}

.th-sidebar,
.th-copilot-panel {{
  flex: 0 0 auto !important;
  height: 100vh !important;
  max-height: 100vh !important;
  align-self: stretch !important;
}}

.th-main {{
  flex: 1 1 auto !important;
  min-width: 0 !important;
  height: 100vh !important;
  max-height: 100vh !important;
  overflow-x: hidden !important;
  overflow-y: auto !important;
  display: block !important;
  padding: 28px !important;
  background: var(--th-bg) !important;
}}

.th-main > * {{
  flex: none !important;
  height: auto !important;
  max-height: none !important;
  align-self: stretch !important;
}}

.th-page {{
  display: flex !important;
  flex-direction: column !important;
  align-items: stretch !important;
  width: 100% !important;
  height: auto !important;
  gap: 0 !important;
}}

.th-page-header {{
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  align-items: flex-start !important;
  justify-content: space-between !important;
  width: 100% !important;
  height: auto !important;
  margin-bottom: 22px !important;
  gap: 20px !important;
}}

.th-stats-row {{
  display: flex !important;
  flex-direction: row !important;
  flex-wrap: nowrap !important;
  align-items: stretch !important;
  width: 100% !important;
  height: auto !important;
  gap: 13px !important;
  margin-bottom: 13px !important;
}}

.th-stat-card {{
  flex: 1 1 0 !important;
  min-width: 0 !important;
  height: auto !important;
  align-self: flex-start !important;
  background: linear-gradient(145deg, #0e1b28, #0a1520) !important;
  border: 1px solid var(--th-border) !important;
  border-radius: 13px !important;
  padding: 16px !important;
}}

.th-primary-btn,
.th-teal-btn,
.th-gold-btn,
.th-slate-btn,
.th-amber-btn {{
  height: 36px !important;
  min-height: 36px !important;
  max-height: 40px !important;
  align-self: flex-start !important;
  flex: 0 0 auto !important;
  white-space: nowrap !important;
}}

.th-copilot-inner {{
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
  max-height: 100% !important;
  width: 100% !important;
  overflow: hidden !important;
}}

.th-copilot-panel .th-copilot-inner > div:first-child .q-btn {{
  min-height: 28px !important;
  height: 28px !important;
  width: 28px !important;
}}

.th-copilot-input,
.th-copilot-input .q-field__native,
.th-copilot-input input,
.th-copilot-input textarea {{
  font-size: 14px !important;
  line-height: 1.45 !important;
}}

.th-copilot-input .q-field__native::placeholder,
.th-copilot-input input::placeholder,
.th-copilot-input textarea::placeholder {{
  font-size: 14px !important;
  color: #8da2b2 !important;
  opacity: 1 !important;
}}

.th-copilot-composer {{
  display: grid !important;
  grid-template-columns: 30px 30px minmax(0, 1fr);
  align-items: center;
  gap: 4px;
  width: 100%;
  flex: 0 0 auto;
  padding: 7px;
  background: #0e1b28;
  border: 1px solid #274151;
  border-radius: 8px;
}}
.th-copilot-composer .th-copilot-input {{
  grid-column: 1 / -1;
  width: 100%;
  min-width: 0;
  padding: 0 3px;
  border-bottom: 1px solid #1b3040;
}}
.th-copilot-composer .th-copilot-input .q-field__control {{
  min-height: 62px !important;
  padding: 0 !important;
}}
.th-copilot-composer .th-copilot-input textarea {{
  min-height: 54px !important;
  max-height: 144px !important;
  padding: 7px 3px 8px !important;
  resize: none !important;
}}
.th-copilot-composer-tool {{
  width: 30px !important;
  height: 30px !important;
  min-height: 30px !important;
}}
.th-copilot-send {{
  grid-column: 3;
  justify-self: end;
  width: 32px !important;
  height: 32px !important;
  min-height: 32px !important;
}}

@media (max-width: 1050px) {{
  .th-copilot-panel {{ display: none !important; }}
}}

.th-mobile-nav {{ display: none !important; }}

.th-candidates-page {{ min-width: 0; }}

.th-candidate-toolbar {{
  display: grid !important;
  grid-template-columns: auto auto minmax(230px, 1fr);
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px;
  margin-bottom: 13px;
  background: #091620;
  border: 1px solid #1d3342;
  border-radius: 7px;
}}
.th-candidate-toolbar .q-btn-group {{
  flex-wrap: nowrap !important;
  padding: 3px;
  background: #07121c;
  border: 1px solid #172b39;
  border-radius: 6px;
  box-shadow: none !important;
}}
.th-candidate-toolbar .q-btn {{
  min-height: 30px !important;
  padding: 0 10px !important;
  border-radius: 4px !important;
  color: #8299aa !important;
  font-size: 10px !important;
  font-weight: 650 !important;
}}
.th-candidate-toolbar button.q-btn[aria-pressed="true"] {{
  color: #dffcf8 !important;
  background: #15505a !important;
}}
.th-candidate-search {{ width: 100%; min-width: 0; }}
.th-candidate-search .q-field__control {{ min-height: 38px !important; border-radius: 6px !important; }}

.th-candidate-workspace {{
  display: grid !important;
  grid-template-columns: minmax(350px, 36%) minmax(0, 1fr);
  width: 100%;
  height: calc(100vh - 205px);
  min-height: 580px;
  overflow: hidden;
  background: #08131e;
  border: 1px solid var(--th-border);
  border-radius: 7px;
}}

.th-candidate-list-pane,
.th-candidate-detail-pane {{ min-width: 0; min-height: 0; }}
.th-candidate-list-pane {{
  display: flex !important;
  flex-direction: column;
  border-right: 1px solid var(--th-border);
  overflow: hidden;
}}
.th-candidate-list-header {{
  width: 100%;
  min-height: 54px;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #1a2d3c;
  background: #0b1823;
}}
.th-candidate-count {{
  flex: 0 0 auto;
  color: #74d9cd;
  font-size: 10px;
  font-weight: 650;
}}
.th-candidate-list {{
  width: 100%;
  flex: 1 1 auto;
  gap: 0 !important;
  overflow-y: auto;
  overflow-x: hidden;
}}
.th-candidate-list-item {{
  width: 100%;
  min-height: 112px;
  padding: 13px 14px 11px;
  border-bottom: 1px solid #162837;
  border-left: 3px solid transparent;
  background: #091722;
  overflow: hidden;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}}
.th-candidate-list-item:hover {{ background: #0e1d29; }}
.th-candidate-list-item-selected {{
  background: #102534;
  border-left-color: var(--th-teal);
  box-shadow: inset 0 0 0 1px rgba(25, 211, 197, 0.18);
}}
.th-candidate-list-item-rogue {{ border-right: 3px solid #d8941e; }}
.th-candidate-row-name {{
  min-width: 0;
  overflow: hidden;
  color: #f0f6f8;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.th-candidate-row-score {{
  margin-left: auto;
  color: #8db0c4;
  font-size: 10px;
  white-space: nowrap;
}}
.th-candidate-row-role {{
  overflow: hidden;
  color: #c2d0d8;
  font-size: 11px;
  line-height: 17px;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.th-candidate-row-meta {{
  overflow: hidden;
  color: #91a8b7;
  font-size: 9px;
  line-height: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.th-candidate-row-footer {{
  width: 100%;
  min-height: 20px;
  align-items: center;
  gap: 5px;
  margin-top: 9px;
  padding-left: 50px;
  flex-wrap: nowrap !important;
  overflow: hidden;
}}
.th-candidate-mini-tag {{
  max-width: 92px;
  padding: 2px 7px;
  overflow: hidden;
  border: 1px solid #17524f;
  border-radius: 4px;
  color: #75dcd2;
  background: #0a302f;
  font-size: 9px;
  line-height: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.th-candidate-mini-tag-warn {{ border-color: #805b20; color: #f0bd57; background: #38270e; }}
.th-candidate-row-more {{ color: #607b8d; font-size: 9px; white-space: nowrap; }}
.th-candidate-hunt-label {{
  margin-left: auto;
  max-width: 120px;
  overflow: hidden;
  color: #809aab;
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

.th-linkedin-mark {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
  border-radius: 3px;
  background: #0a66c2;
  color: white !important;
  font-size: 9px;
  font-weight: 800;
  text-decoration: none !important;
}}

.th-candidate-detail-pane {{
  display: block !important;
  overflow-y: auto;
  background: #091520;
}}
.th-candidate-detail-header {{
  display: block;
  padding: 17px 20px 14px;
  background: #0f202e;
  border-bottom: 1px solid var(--th-border);
}}
.th-candidate-profile-top {{
  width: 100%;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: nowrap !important;
}}
.th-candidate-profile-identity {{
  min-width: 0;
  align-items: center;
  gap: 12px;
  flex-wrap: nowrap !important;
}}
.th-candidate-profile-name {{ color: #f4f8fa; font-size: 18px; font-weight: 750; line-height: 24px; }}
.th-candidate-profile-role {{ color: #c5d4dc; font-size: 12px; line-height: 18px; }}
.th-candidate-profile-meta {{ color: #6f8a9b; font-size: 10px; line-height: 16px; }}
.th-candidate-status-pill {{
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 700;
  line-height: 15px;
}}
.th-candidate-status-active {{ color: #78e1b3; background: #123b32; }}
.th-candidate-status-passive {{ color: #e6bc63; background: #3b2e13; }}
.th-candidate-status-mismatch {{ color: #f3b056; background: #40280d; }}
.th-candidate-header-actions {{ align-items: center; gap: 2px; flex: 0 0 auto; flex-wrap: nowrap !important; }}
.th-candidate-icon-btn {{ width: 34px !important; height: 34px !important; }}
.th-candidate-profile-facts {{
  width: 100%;
  align-items: center;
  gap: 7px;
  margin-top: 12px;
  flex-wrap: wrap !important;
}}
.th-candidate-fact {{
  display: inline-flex !important;
  align-items: center;
  gap: 5px;
  min-height: 25px;
  padding: 3px 8px;
  border: 1px solid #254052;
  border-radius: 4px;
  color: #9fb5c2;
  background: #0a1823;
  font-size: 10px;
  text-decoration: none !important;
}}
.th-candidate-fact-link {{ color: #73aff3 !important; }}
.th-candidate-fact-hunt {{ border-color: #17665d !important; color: #7ce1d5 !important; background: #0b302e !important; }}

.th-candidate-action-band {{
  padding: 12px 16px 14px;
  background: #08141e;
  border-bottom: 1px solid var(--th-border);
}}
.th-contact-grid {{
  display: grid !important;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}}
.th-contact-field {{
  display: flex !important;
  align-items: center;
  gap: 9px;
  min-width: 0;
  min-height: 43px;
  padding: 8px 10px;
  background: #0b1924;
  border: 1px solid #243b4b;
  border-radius: 6px;
}}
.th-contact-label {{ color: #91a8b7; font-size: 8px; text-transform: uppercase; }}
.th-contact-value {{ overflow: hidden; color: #d4e0e5; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }}
.th-decision-grid {{
  display: grid !important;
  grid-template-columns: 1.25fr 1fr 1fr;
  gap: 8px;
  margin-top: 9px;
}}
.th-decision-grid .q-btn {{
  width: 100%;
  min-height: 38px !important;
  border-radius: 6px !important;
  font-size: 11px !important;
  font-weight: 680;
}}
.th-decision-grid button.q-btn.th-decision-shortlist {{ background-color: #0b8066 !important; color: white !important; }}
.th-decision-grid button.q-btn.th-decision-maybe {{ border: 1px solid #9d7728 !important; background-color: #3a2d13 !important; color: #f0c96e !important; }}
.th-decision-grid button.q-btn.th-decision-mismatch {{ border: 1px solid #7f3843 !important; background-color: #321923 !important; color: #ee9ba4 !important; }}
.th-decision-grid button.q-btn.th-decision-shortlist * {{ color: white !important; }}
.th-decision-grid button.q-btn.th-decision-maybe * {{ color: #f0c96e !important; }}
.th-decision-grid button.q-btn.th-decision-mismatch * {{ color: #ee9ba4 !important; }}

.th-insight-section {{ padding: 16px 20px 18px; }}
.th-candidate-section-heading {{ width: 100%; align-items: center; justify-content: space-between; gap: 10px; }}
.th-candidate-section-title {{ color: #eef5f7; font-size: 14px; font-weight: 700; }}
.th-candidate-match-score {{ padding: 3px 7px; border-radius: 4px; color: #79dcd1; background: #123b38; font-size: 9px; }}
.th-insight-copy {{
  margin-top: 8px;
  color: #b9c9d2;
  font-size: 11px;
  line-height: 1.55;
}}
.th-insight-copy p {{ margin: 0; }}
.th-evidence-grid {{
  display: grid !important;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
  margin-top: 13px;
}}
.th-evidence-card {{
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid #1d3544;
  border-radius: 5px;
  background: #0b1a25;
}}
.th-evidence-value {{ overflow: hidden; color: #77dbd0; font-size: 10px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }}
.th-evidence-source {{ margin-top: 2px; color: #91a8b7; font-size: 8px; }}
.th-evidence-empty {{
  display: flex !important;
  grid-column: 1 / -1;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border: 1px dashed #294252;
  border-radius: 5px;
}}

.th-profile-history {{
  display: grid !important;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border-top: 1px solid var(--th-border);
}}
.th-history-column {{ min-width: 0; padding: 15px 20px 18px; }}
.th-history-column + .th-history-column {{ border-left: 1px solid var(--th-border); }}
.th-history-heading {{ width: 100%; align-items: center; gap: 7px; margin-bottom: 8px; flex-wrap: nowrap !important; }}
.th-history-count {{ margin-left: auto; color: #6e8999; font-size: 9px; }}
.th-history-item {{ min-width: 0; padding: 9px 0 9px 12px; border-left: 2px solid #1c5e59; }}
.th-history-item + .th-history-item {{ margin-top: 3px; }}
.th-history-role {{ color: #dce6ea; font-size: 10px; font-weight: 650; }}
.th-history-org {{ color: #72d5ca; font-size: 9px; }}
.th-history-period {{ color: #647f90; font-size: 8px; }}
.th-history-empty {{
  display: flex !important;
  align-items: center;
  gap: 8px;
  min-height: 54px;
  padding: 10px;
  border: 1px dashed #223949;
  border-radius: 5px;
  background: #091722;
}}

@media (max-width: 1180px) {{
  .th-candidate-toolbar {{ grid-template-columns: auto minmax(250px, 1fr); }}
  .th-candidate-status-toggle {{ grid-column: 1 / -1; grid-row: 2; }}
  .th-candidate-search {{ grid-column: 2; grid-row: 1; }}
  .th-candidate-workspace {{ grid-template-columns: minmax(320px, 41%) minmax(0, 1fr); }}
  .th-evidence-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}

@media (max-width: 1400px) and (min-width: 1051px) {{
  .th-candidate-workspace {{ grid-template-columns: 320px minmax(0, 1fr); }}
  .th-candidate-detail-header {{ padding: 15px 16px 13px; }}
  .th-candidate-profile-top {{ flex-direction: column; gap: 8px; }}
  .th-candidate-profile-identity {{ width: 100%; }}
  .th-candidate-header-actions {{ margin-left: 62px; }}
  .th-candidate-profile-facts {{ margin-top: 10px; }}
  .th-insight-section {{ padding: 15px 16px 17px; }}
  .th-history-column {{ padding: 14px 16px 17px; }}
}}

@media (max-width: 850px) {{
  .th-candidate-workspace {{ grid-template-columns: 1fr; height: auto; min-height: 0; overflow: visible; }}
  .th-candidate-list-pane {{ max-height: 480px; border-right: 0; border-bottom: 1px solid var(--th-border); }}
  .th-candidate-detail-pane {{ overflow: visible; }}
}}

@media (max-width: 560px) {{
  .th-candidate-toolbar {{ display: flex !important; flex-direction: column; align-items: stretch; padding: 7px; }}
  .th-candidate-mode-toggle,
  .th-candidate-status-toggle {{ width: 100%; overflow-x: auto; }}
  .th-candidate-toolbar .q-btn-group {{ width: max-content; min-width: 100%; }}
  .th-candidate-search {{ width: 100%; }}
  .th-candidate-list-header {{ padding: 9px 11px; }}
  .th-candidate-list-item {{ padding: 12px 11px 10px; }}
  .th-candidate-row-footer {{ padding-left: 0; }}
  .th-candidate-hunt-label {{ display: none; }}
  .th-candidate-detail-header {{ padding: 15px 13px 12px; }}
  .th-candidate-profile-top {{ flex-direction: column; gap: 8px; }}
  .th-candidate-profile-identity {{ width: 100%; }}
  .th-candidate-profile-name {{ font-size: 16px; }}
  .th-candidate-header-actions {{ gap: 0; margin-left: 62px; }}
  .th-candidate-action-band {{ padding: 10px 11px 12px; }}
  .th-contact-grid {{ grid-template-columns: 1fr; }}
  .th-decision-grid {{ grid-template-columns: 1fr 1fr; }}
  .th-decision-mismatch {{ grid-column: 1 / -1; }}
  .th-insight-section {{ padding: 15px 13px; }}
  .th-evidence-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .th-profile-history {{ grid-template-columns: 1fr; }}
  .th-history-column {{ padding: 14px 13px; }}
  .th-history-column + .th-history-column {{ border-left: 0; border-top: 1px solid var(--th-border); }}
}}

@media (max-width: 700px) {{
  .th-sidebar {{ display: none !important; }}
  .th-main {{
    width: 100% !important;
    padding: 16px 14px 72px !important;
  }}
  .th-mobile-nav {{
    position: fixed !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    z-index: 70 !important;
    height: 58px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: space-evenly !important;
    padding: 5px !important;
    background: #08121d !important;
    border-top: 1px solid var(--th-border) !important;
  }}
  .th-mobile-nav .q-btn {{
    width: 36px !important;
    min-width: 36px !important;
    height: 36px !important;
    min-height: 36px !important;
    color: #8ea4b4;
  }}
  .th-copilot-panel.th-mobile-open {{
    display: flex !important;
    position: fixed !important;
    inset: 0 0 58px 0 !important;
    z-index: 60 !important;
    width: 100% !important;
    height: auto !important;
    max-height: none !important;
    border-left: 0 !important;
  }}
  .th-page-header,
  .th-stats-row,
  .th-dashboard-lower,
  .th-main .nicegui-row {{
    flex-wrap: wrap !important;
  }}
  .th-page-header {{ gap: 12px !important; }}
  .th-stat-card {{
    flex: 1 1 calc(50% - 7px) !important;
    min-width: 140px !important;
  }}
  .th-dashboard-lower {{ flex-direction: column !important; }}
  .th-dashboard-side {{ width: 100% !important; }}
  .th-funnel {{
    grid-template-columns: repeat(6, minmax(92px, 1fr)) !important;
    overflow-x: auto !important;
  }}
  .th-main .w-64,
  .th-main .w-48,
  .th-main .w-32 {{
    width: 100% !important;
    max-width: 100% !important;
  }}
  .th-title {{ font-size: 22px !important; }}
  .th-candidate-workspace .nicegui-row.flex-nowrap {{ flex-wrap: nowrap !important; }}
  .th-contact-grid,
  .th-decision-grid,
  .th-profile-history {{ grid-template-columns: 1fr; }}
  .th-history-column + .th-history-column {{ border-left: 0; border-top: 1px solid var(--th-border); }}
  .th-evidence-head,
  .th-evidence-row {{ grid-template-columns: 1fr; gap: 7px; }}
}}
"""
    )

def apply_theme(scheme_key: str | None = None):
    """Inject active theme styles into NiceGUI."""
    global CURRENT_THEME_KEY
    if scheme_key and scheme_key in COLOR_SCHEMES:
        CURRENT_THEME_KEY = scheme_key
    ui.dark_mode(True)
    ui.add_head_html(f'<style>{get_theme_css(CURRENT_THEME_KEY)}</style>', shared=True)
    ui.add_head_html(
        r"""<script>
(() => {
  document.documentElement.lang = 'en';
  if (window.__talenthuntAccessibilityObserver) return;
  const iconLabels = {
    add: 'Add', arrow_back: 'Go back', arrow_forward: 'Move forward',
    arrow_upward: 'Send message', auto_awesome: 'Run AI action',
    check: 'Confirm', close: 'Close', content_copy: 'Copy', dashboard: 'Dashboard',
    delete: 'Delete', delete_outline: 'Delete', edit: 'Edit', forum: 'Communications',
    group: 'Candidates', history: 'Prompt history', insights: 'Analytics',
    manage_history: 'Action history and undo', menu_book: 'Playbook',
    mic: 'Voice input', more_vert: 'More actions', open_in_full: 'Expand Copilot',
    open_in_new: 'Open related page in a new tab', pause: 'Pause',
    person_search: 'Discoveries', play_arrow: 'Resume', refresh: 'Clear conversation',
    settings: 'Settings', smart_toy: 'Open Copilot', stop: 'Cancel active work',
    travel_explore: 'Hunts', undo: 'Undo action', view_kanban: 'Pipeline',
    volume_off: 'Enable voice replies', volume_up: 'Mute voice replies'
  };
  const nameIconButtons = (root = document) => {
    const buttons = root.querySelectorAll ? root.querySelectorAll('button:not([aria-label])') : [];
    buttons.forEach((button) => {
      const content = button.querySelector('.q-btn__content');
      const icon = content?.querySelector('.q-icon');
      if (!icon) return;
      const visibleLabel = content.querySelector('.block')?.textContent?.trim();
      if (visibleLabel) return;
      const iconName = icon.textContent?.trim();
      if (!iconName) return;
      const tooltip = button.querySelector('.q-tooltip')?.textContent?.trim();
      const fallback = iconName.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase());
      button.setAttribute('aria-label', tooltip || iconLabels[iconName] || fallback);
    });
    root.querySelectorAll?.('.q-table__middle:not([tabindex])').forEach((region) => {
      region.tabIndex = 0;
      region.setAttribute('role', 'region');
      region.setAttribute('aria-label', 'Scrollable data table');
    });
  };
  nameIconButtons();
  window.__talenthuntAccessibilityObserver = new MutationObserver(() => nameIconButtons());
  window.__talenthuntAccessibilityObserver.observe(document.documentElement, {
    childList: true, subtree: true
  });
})();
</script>""",
        shared=True,
    )
    # NOTE: Do NOT inject the raw design-pack styles.css — generic .btn/.card/.main
    # selectors collide with Quasar/NiceGUI and stretch the layout.
