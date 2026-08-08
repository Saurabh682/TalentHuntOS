"""Dark-mode Modern Ocean theme for TalentHunt OS (design-pack aligned)."""

from nicegui import ui
from pathlib import Path

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
    return f"""
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
  min-height: 100vh;
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
  background: var(--th-bg);
  padding: 28px;
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
  min-height: 500px;
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
  color: #fff;
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

.text-caption, label, .q-field__label, .th-caption {{
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

.q-field__label {{
  position: relative !important;
  top: 0 !important;
  transform: none !important;
  margin-bottom: 6px !important;
  display: block !important;
}}

.q-field--outlined .q-field__control {{
  background: #091520 !important;
  border-radius: 8px !important;
}}

.q-field--outlined .q-field__control:before {{
  border-color: var(--th-border) !important;
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
  color: {s['muted']} !important;
  font-size: 10px !important;
  margin-top: 4px !important;
}}

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

@media (max-width: 1050px) {{
  .th-copilot-panel {{ display: none !important; }}
}}
"""

ui.add_head_html(
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">',
    shared=True,
)

def apply_theme(scheme_key: str | None = None):
    """Inject active theme styles into NiceGUI."""
    global CURRENT_THEME_KEY
    if scheme_key and scheme_key in COLOR_SCHEMES:
        CURRENT_THEME_KEY = scheme_key
    ui.dark_mode(True)
    ui.add_head_html(f'<style>{get_theme_css(CURRENT_THEME_KEY)}</style>', shared=True)

    # Also load design-pack stylesheet if present
    css_path = Path(__file__).resolve().parent / "static" / "styles.css"
    if css_path.exists():
        try:
            ui.add_css(css_path.read_text(encoding="utf-8"))
        except Exception:
            pass
