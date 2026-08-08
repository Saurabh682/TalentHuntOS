"""Settings page for TalentHunt OS."""

from nicegui import ui
from app.ui.layout import create_layout
from app.config.settings import settings

def render_settings():
    """Render the configuration settings page — Modern Ocean design."""
    with ui.column().classes('w-full gap-0 max-w-4xl'):
        with ui.column().classes('gap-0 mb-[22px]'):
            ui.label('System configuration').classes('th-ey')
            ui.label('Settings & Configuration').classes('th-title')
            ui.label('Manage AI providers, integrations, security and application preferences.').classes('th-muted')

        # Settings tabs strip (visual)
        with ui.row().classes('w-full gap-2 border-b border-[#1b3040] pb-[10px] mb-[15px] flex-wrap'):
            ui.element('span').classes('px-2 py-2 rounded-[7px] bg-[#123e43] text-[#8de8df] text-[11px]').text = 'AI Providers'
            for label in ['General', 'Integrations', 'Team', 'Security']:
                ui.element('span').classes('px-2 py-2 text-[#8da2b2] text-[11px]').text = label

        # Local AI first (free path)
        with ui.card().classes('w-full p-5 th-card mb-[13px]'):
            with ui.row().classes('items-center justify-between w-full mb-3'):
                ui.label('Local LLM / LM Studio').classes('text-[13px] font-semibold text-[#edf5f7]')
                ui.label('● Preferred (Free)').classes('text-[#45d6a0] text-[10px]')
            
            with ui.column().classes('w-full gap-4'):
                ui.label('Runs locally on your PC. No paid API required. Connect LM Studio or Ollama.').classes('th-muted')
                
                with ui.row().classes('w-full gap-4 items-end'):
                    with ui.column().classes('grow gap-1'):
                        ui.label('Server Host').classes('th-caption')
                        host_in = ui.input(value=settings.llama_server_host, placeholder='127.0.0.1').classes('w-full').props('outlined dark dense')
                    with ui.column().classes('w-32 gap-1'):
                        ui.label('Port').classes('th-caption')
                        port_in = ui.input(value=str(settings.llama_server_port), placeholder='1234').classes('w-full').props('outlined dark dense')
                    
                    def save_local_config():
                        settings.llama_server_host = host_in.value
                        try:
                            settings.llama_server_port = int(port_in.value)
                        except ValueError:
                            pass
                        ui.notify('Local server configuration saved', type='positive')

                    ui.button('Save', icon='save', on_click=save_local_config).classes('th-primary-btn')
                
                with ui.row().classes('items-center justify-between w-full pt-2'):
                    ui.label('Enable Local AI Fallback').classes('text-[12px] text-[#edf5f7]')
                    ui.switch(value=settings.enable_local_ai, on_change=lambda e: setattr(settings, 'enable_local_ai', e.value))

        # Optional cloud keys (paid — demoted)
        with ui.card().classes('w-full p-5 th-card mb-[13px]'):
            with ui.row().classes('items-center justify-between w-full mb-2'):
                ui.label('Cloud AI API Keys').classes('text-[13px] font-semibold text-[#edf5f7]')
                ui.label('Optional · Paid').classes('th-muted')
            ui.label('Leave empty to stay fully free with local LLM only.').classes('th-muted mb-3')
            with ui.column().classes('w-full gap-3'):
                with ui.column().classes('w-full gap-1'):
                    ui.label('Google Gemini API Key').classes('th-caption')
                    gemini_in = ui.input(value=settings.gemini_api_key, password=True, placeholder='Optional').classes('w-full').props('outlined dark dense')
                with ui.column().classes('w-full gap-1'):
                    ui.label('OpenAI API Key').classes('th-caption')
                    openai_in = ui.input(value=settings.openai_api_key, password=True, placeholder='Optional').classes('w-full').props('outlined dark dense')
                with ui.column().classes('w-full gap-1'):
                    ui.label('Anthropic API Key').classes('th-caption')
                    anthropic_in = ui.input(value=settings.anthropic_api_key, password=True, placeholder='Optional').classes('w-full').props('outlined dark dense')
                with ui.row().classes('justify-end'):
                    def save_keys():
                        settings.gemini_api_key = gemini_in.value
                        settings.openai_api_key = openai_in.value
                        settings.anthropic_api_key = anthropic_in.value
                        ui.notify('Settings saved', type='positive')
                    ui.button('Save API Keys', icon='save', on_click=save_keys).classes('th-slate-btn')

        # UI Color Theme Selector
        with ui.card().classes('w-full p-5 th-card mb-[13px]'):
            with ui.row().classes('items-center justify-between w-full mb-3'):
                ui.label('Appearance').classes('text-[13px] font-semibold text-[#edf5f7]')
                ui.label('Modern Ocean default').classes('th-muted')
            
            from app.ui.theme import COLOR_SCHEMES, apply_theme, CURRENT_THEME_KEY
            theme_options = {k: v["name"] for k, v in COLOR_SCHEMES.items()}
            
            def change_theme(e):
                apply_theme(e.value)
                ui.notify(f"Theme switched to: {COLOR_SCHEMES[e.value]['name']}", type='info')
            
            with ui.column().classes('w-full gap-1'):
                ui.label('Active Color Theme').classes('th-caption')
                ui.select(theme_options, value=CURRENT_THEME_KEY, on_change=change_theme).classes('w-full').props('outlined dark dense')


        # Recommended Local Models Download Arsenal
        with ui.card().classes('w-full p-5 th-card'):
            with ui.row().classes('items-center justify-between w-full mb-4'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('download', color='teal-4')
                    ui.label('Recommended Local GGUF Models & LM Studio').classes('text-lg font-semibold text-slate-100')
                ui.badge('Direct Download Links', color='teal').classes('text-xs')
            
            ui.label('Click any link below to download LM Studio or direct HuggingFace GGUF model files. Load them inside LM Studio to run offline with zero API cost.').classes('text-xs text-slate-400 mb-4')
            
            models_data = [
                {
                    "name": "LM Studio Desktop App",
                    "badge": "App Installer",
                    "color": "teal",
                    "size": "Desktop GUI",
                    "desc": "One-click local LLM runner for Windows/Mac with built-in server.",
                    "url": "https://lmstudio.ai"
                },
                {
                    "name": "Gemma 2 2B Instruct GGUF",
                    "badge": "Recommended",
                    "color": "emerald",
                    "size": "~1.5 GB",
                    "desc": "Google's ultra-fast compact model. Best balance of speed & quality for talent sourcing.",
                    "url": "https://huggingface.co/bartowski/gemma-2-2b-it-GGUF"
                },
                {
                    "name": "SmolLM 360M Instruct GGUF",
                    "badge": "Ultra Fast",
                    "color": "amber",
                    "size": "~250 MB",
                    "desc": "HuggingFace's micro-model. Instant classification & entity extraction on any CPU.",
                    "url": "https://huggingface.co/HuggingFaceTB/SmolLM-360M-Instruct-GGUF"
                },
                {
                    "name": "Qwen 2.5 0.5B Instruct GGUF",
                    "badge": "Compact",
                    "color": "indigo",
                    "size": "~400 MB",
                    "desc": "Alibaba's lightweight reasoning model. Excellent for fast JD parsing & resume summarization.",
                    "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF"
                },
                {
                    "name": "Phi-3.5 Mini Instruct GGUF",
                    "badge": "High Quality",
                    "color": "purple",
                    "size": "~2.2 GB",
                    "desc": "Microsoft's 3.8B reasoning powerhouse for complex candidate scoring.",
                    "url": "https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF"
                }
            ]
            
            with ui.column().classes('w-full gap-3'):
                for m in models_data:
                    with ui.row().classes('w-full items-center justify-between p-3 th-card-inner rounded-lg'):
                        with ui.column().classes('gap-0.5 grow'):
                            with ui.row().classes('items-center gap-2'):
                                ui.label(m["name"]).classes('font-bold text-sm text-slate-100')
                                ui.badge(m["badge"], color=m["color"]).classes('text-[10px] px-1.5 py-0.5')
                                ui.badge(m["size"], color='blue-grey').classes('text-[10px] px-1.5 py-0.5')
                            ui.label(m["desc"]).classes('text-xs text-slate-400')
                        
                        ui.link('Download ➜', target=m["url"], new_tab=True).classes(
                            'text-xs font-bold text-teal-300 hover:text-lime-400 px-3 py-1.5 border border-teal-800/40 rounded hover:bg-teal-900/30 transition-all'
                        )
        
        # Voice — free browser path primary
        with ui.card().classes('w-full p-5 th-card mt-[13px]'):
            with ui.row().classes('items-center justify-between w-full mb-2'):
                ui.label('Voice Engine').classes('text-[13px] font-semibold text-[#edf5f7]')
                ui.label('Browser Web Speech = Free').classes('text-[#45d6a0] text-[10px]')
            ui.label('Copilot already uses free browser STT/TTS. Deepgram & ElevenLabs below are optional paid.').classes('th-muted mb-3')
            with ui.column().classes('w-full gap-3'):
                with ui.column().classes('w-full gap-1'):
                    ui.label('Deepgram API Key (STT) — Optional Paid').classes('th-caption')
                    deepgram_in = ui.input(value=settings.deepgram_api_key, password=True, placeholder='Optional').classes('w-full').props('outlined dark dense')
                with ui.column().classes('w-full gap-1'):
                    ui.label('ElevenLabs API Key (TTS) — Optional Paid').classes('th-caption')
                    elevenlabs_in = ui.input(value=settings.elevenlabs_api_key, password=True, placeholder='Optional').classes('w-full').props('outlined dark dense')
                
                with ui.row().classes('justify-end'):
                    def save_voice_keys():
                        settings.deepgram_api_key = deepgram_in.value
                        settings.elevenlabs_api_key = elevenlabs_in.value
                        ui.notify('Voice engine keys saved', type='positive')
                    
                    ui.button('Save Voice Keys', icon='save', on_click=save_voice_keys).classes('th-slate-btn')

def settings_page():
    create_layout(render_settings)
