"""Settings page for TalentHunt OS."""

from nicegui import ui
from app.ui.layout import create_layout
from app.config.settings import settings

def render_settings():
    """Render the configuration settings page."""
    with ui.column().classes('w-full gap-6 max-w-4xl'):
        with ui.column().classes('gap-1'):
            ui.label('Settings & Configuration').classes('text-2xl font-bold text-slate-100')
            ui.label('Manage AI provider keys, local model configurations, and system feature flags.').classes('text-sm text-slate-400')
        
        # Cloud AI Providers
        with ui.card().classes('w-full p-5 th-card'):
            ui.label('Cloud AI Providers').classes('text-lg font-semibold text-teal-400 mb-4')
            with ui.column().classes('w-full gap-4'):
                gemini_in = ui.input('Google Gemini API Key', value=settings.gemini_api_key, password=True).classes('w-full').props('outlined dark')
                openai_in = ui.input('OpenAI API Key', value=settings.openai_api_key, password=True).classes('w-full').props('outlined dark')
                anthropic_in = ui.input('Anthropic API Key', value=settings.anthropic_api_key, password=True).classes('w-full').props('outlined dark')
                with ui.row().classes('justify-end'):
                    def save_keys():
                        settings.gemini_api_key = gemini_in.value
                        settings.openai_api_key = openai_in.value
                        settings.anthropic_api_key = anthropic_in.value
                        ui.notify('Settings saved', type='positive')
                    ui.button('Save API Keys', icon='save', color='teal', on_click=save_keys).classes('th-teal-btn')

        # UI Color Theme Selector
        with ui.card().classes('w-full p-5 th-card'):
            with ui.row().classes('items-center justify-between w-full mb-3'):
                ui.label('UI Appearance & Color Palette').classes('text-lg font-semibold text-purple-400')
                ui.badge('4 Themes Available', color='purple').classes('text-xs')
            
            ui.label('Select your preferred app theme & color scheme.').classes('text-xs text-slate-400 mb-3')
            
            from app.ui.theme import COLOR_SCHEMES, apply_theme, CURRENT_THEME_KEY
            theme_options = {k: v["name"] for k, v in COLOR_SCHEMES.items()}
            
            def change_theme(e):
                apply_theme(e.value)
                ui.notify(f"Theme switched to: {COLOR_SCHEMES[e.value]['name']}", type='info')
            
            ui.select(theme_options, value=CURRENT_THEME_KEY, label='Active Color Theme', on_change=change_theme).classes('w-full').props('outlined dark')
        
        # Local AI Settings & LM Studio Connection
        with ui.card().classes('w-full p-5 th-card'):
            with ui.row().classes('items-center justify-between w-full mb-3'):
                ui.label('Local AI Server (LM Studio / llama-server)').classes('text-lg font-semibold text-amber-400')
                ui.badge('OpenAI Compatible', color='amber').classes('text-xs')
            
            with ui.column().classes('w-full gap-4'):
                ui.label('LM Studio runs locally on your PC. TalentHunt OS automatically connects to whatever model is currently loaded in LM Studio.').classes('text-xs text-slate-300')
                
                with ui.row().classes('w-full gap-4 items-center'):
                    host_in = ui.input('Server Host', value=settings.llama_server_host).classes('grow').props('outlined dark dense')
                    port_in = ui.input('Server Port', value=str(settings.llama_server_port)).classes('w-32').props('outlined dark dense')
                    
                    def save_local_config():
                        settings.llama_server_host = host_in.value
                        try:
                            settings.llama_server_port = int(port_in.value)
                        except ValueError:
                            pass
                        ui.notify('Local server configuration saved', type='positive')

                    ui.button('Save Port', icon='save', color='amber', on_click=save_local_config).props('dense').classes('th-gold-btn')
                
                with ui.row().classes('items-center justify-between w-full pt-2'):
                    ui.label('Enable Local AI Fallback').classes('text-sm text-slate-300')
                    ui.switch(value=settings.enable_local_ai, on_change=lambda e: setattr(settings, 'enable_local_ai', e.value))

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
        
        # Voice Engine Settings
        with ui.card().classes('w-full p-5 th-card'):
            ui.label('Voice Engine (Deepgram & ElevenLabs)').classes('text-lg font-semibold text-slate-200 mb-4')
            with ui.column().classes('w-full gap-4'):
                deepgram_in = ui.input('Deepgram API Key (STT)', value=settings.deepgram_api_key, password=True).classes('w-full').props('outlined dark')
                elevenlabs_in = ui.input('ElevenLabs API Key (TTS)', value=settings.elevenlabs_api_key, password=True).classes('w-full').props('outlined dark')
                
                with ui.row().classes('justify-end'):
                    def save_voice_keys():
                        settings.deepgram_api_key = deepgram_in.value
                        settings.elevenlabs_api_key = elevenlabs_in.value
                        ui.notify('Voice engine keys saved', type='positive')
                    
                    ui.button('Save Voice Keys', icon='save', color='teal', on_click=save_voice_keys).classes('th-teal-btn')

def settings_page():
    create_layout(render_settings)
