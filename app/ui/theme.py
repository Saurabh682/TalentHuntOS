"""Dark-mode-first premium theme for TalentHunt OS (Navy, Teal, Gold palette)."""

from nicegui import ui
from app.config.constants import (
    COLOR_BG, COLOR_SURFACE, COLOR_SURFACE_ELEVATED,
    COLOR_BORDER, COLOR_TEXT, COLOR_MUTED, COLOR_TEAL, COLOR_GOLD,
    COLOR_EMERALD, COLOR_DARK_GREEN
)

COLOR_SCHEMES = {
    "recruiter_os": {
        "name": "Minimal Mint Recruiter OS (Default)",
        "bg": "#050607",
        "surface": "#0B0D0F",
        "surface_elevated": "#121619",
        "border": "#1E2226",
        "text": "#E7E9EA",
        "muted": "#8A9096",
        "gradient": "linear-gradient(135deg, #3ED9A6 0%, #10241D 100%)",
        "accent": "#3ED9A6",
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
        "bot_bubble": "#0d2114",
        "bot_border": "#1fb138",
        "bot_text": "#f0faf2",
        "user_bubble": "linear-gradient(135deg, #1fb138 0%, #0d6b27 100%)",
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
        "bot_bubble": "#0d1b2a",
        "bot_border": "#00f2fe",
        "bot_text": "#f0f8ff",
        "user_bubble": "linear-gradient(135deg, #00f2fe 0%, #2563eb 100%)",
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
        "bot_bubble": "#261c0e",
        "bot_border": "#f59e0b",
        "bot_text": "#fefce8",
        "user_bubble": "linear-gradient(135deg, #fbbf24 0%, #b45309 100%)",
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
        "bot_bubble": "#1a153b",
        "bot_border": "#8b5cf6",
        "bot_text": "#faf5ff",
        "user_bubble": "linear-gradient(135deg, #a855f7 0%, #4338ca 100%)",
        "user_text": "#ffffff",
    },
}

CURRENT_THEME_KEY = "recruiter_os"

def get_theme_css(scheme_key: str = "recruiter_os") -> str:
    s = COLOR_SCHEMES.get(scheme_key, COLOR_SCHEMES["emerald"])
    return f"""
:root {{
  --th-bg: {s['bg']};
  --th-surface: {s['surface']};
  --th-surface-elevated: {s['surface_elevated']};
  --th-border: {s['border']};
  --th-text: {s['text']};
  --th-muted: {s['muted']};
  --th-teal: {s['accent']};
  --th-gold: {s['accent']};
  --th-emerald: {s['accent']};
  --th-gradient: {s['gradient']};
  --th-gradient-pill: {s['gradient']};
}}

html, body, #app, #q-app {{
  background: var(--th-bg) !important;
  color: var(--th-text) !important;
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
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

.th-card {{
  background: var(--th-surface);
  border: 1px solid var(--th-border);
  border-radius: 14px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
}}

.th-card-inner {{
  background: var(--th-surface-elevated) !important;
  color: var(--th-text) !important;
  border: 1px solid var(--th-border);
  border-radius: 10px;
}}

.th-nav-item {{
  color: #8A9096 !important;
  background: transparent !important;
  border: 0.5px solid transparent !important;
  border-radius: 7px !important;
  transition: all 0.15s ease;
}}

.th-nav-item *, .th-nav-item .q-btn__content * {{
  color: #8A9096 !important;
}}

.th-nav-item:hover {{
  background: #151A1D !important;
  border: 0.5px solid #1E2226 !important;
}}

.th-nav-item:hover *, .th-nav-item:hover .q-btn__content * {{
  color: #EDEFEF !important;
}}

.th-gold-btn, .th-teal-btn {{
  background: #3ED9A6 !important;
  color: #052A20 !important;
  font-weight: 500 !important;
  border-radius: 7px !important;
  box-shadow: none !important;
}}

.th-gold-btn *, .th-teal-btn *, .th-gold-btn .q-btn__content *, .th-teal-btn .q-btn__content * {{
  color: #052A20 !important;
}}

.th-slate-btn {{
  background: #151A1D !important;
  color: #C7CBCE !important;
  border: 0.5px solid #1E2226 !important;
  font-weight: 500 !important;
  border-radius: 7px !important;
}}

.th-slate-btn *, .th-slate-btn .q-btn__content * {{
  color: #C7CBCE !important;
}}

.th-select {{
  background: var(--th-surface-elevated) !important;
  border: 1px solid var(--th-border) !important;
}}

/* Technical UI/UX Typography Tokens */
.text-display, h1, .th-display {{
  font-size: 24px !important;
  line-height: 1.2 !important;
  font-weight: 700 !important;
}}

.text-subheading, h2, .th-subheading {{
  font-size: 18px !important;
  line-height: 1.4 !important;
  font-weight: 600 !important;
}}

.text-body, p, span, div, .th-body {{
  font-size: 14px !important;
  line-height: 1.5 !important;
}}

.text-caption, label, .q-field__label, .th-caption {{
  font-size: 12px !important;
  line-height: 1.5 !important;
}}

/* 48px Accessible Touch Targets & Interactive Component States */
button, .q-btn, input, .q-field__control {{
  min-height: 48px !important;
}}

.q-btn:focus-visible, input:focus-visible, .q-field--focused {{
  outline: 2px solid {s['accent']} !important;
  outline-offset: 2px !important;
}}

button:disabled, .q-btn--disabled, input:disabled {{
  opacity: 0.4 !important;
  cursor: not-allowed !important;
}}

/* Vertical Form Stacking */
.q-field__label {{
  position: relative !important;
  top: 0 !important;
  transform: none !important;
  margin-bottom: 6px !important;
  display: block !important;
}}

/* Quasar Chat Message Custom Styling */
.q-message-text {{
  border-radius: 14px !important;
  font-size: 14px !important;
  line-height: 1.5 !important;
  padding: 12px 16px !important;
}}

.q-message-text--received {{
  background: {s['bot_bubble']} !important;
  border: 1px solid {s['bot_border']} !important;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4) !important;
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
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3) !important;
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
  font-size: 12px !important;
}}

.q-message-stamp {{
  color: {s['muted']} !important;
  font-size: 12px !important;
  margin-top: 4px !important;
}}

/* Custom Sleek Scrollbar */
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
"""

ui.add_head_html('<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">', shared=True)

def apply_theme(scheme_key: str | None = None):
    """Inject active theme styles into NiceGUI."""
    global CURRENT_THEME_KEY
    if scheme_key and scheme_key in COLOR_SCHEMES:
        CURRENT_THEME_KEY = scheme_key
    ui.dark_mode(True)
    ui.add_head_html(f'<style>{get_theme_css(CURRENT_THEME_KEY)}</style>', shared=True)
