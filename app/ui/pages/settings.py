"""Settings page for TalentHunt OS."""

from nicegui import ui

from app.config.preferences import save_app_preferences
from app.config.settings import settings
from app.ui.components.embedded_ai import render_embedded_ai_panel
from app.ui.layout import create_layout


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

        render_embedded_ai_panel()

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
                        save_app_preferences()
                        ui.notify('API keys encrypted and saved locally', type='positive')
                    ui.button('Save API Keys', icon='save', on_click=save_keys).classes('th-slate-btn')

        # UI Color Theme Selector
        with ui.card().classes('w-full p-5 th-card mb-[13px]'):
            with ui.row().classes('items-center justify-between w-full mb-3'):
                ui.label('Appearance').classes('text-[13px] font-semibold text-[#edf5f7]')
                ui.label('Modern Ocean default').classes('th-muted')
            
            from app.ui.theme import COLOR_SCHEMES, CURRENT_THEME_KEY, apply_theme
            theme_options = {k: v["name"] for k, v in COLOR_SCHEMES.items()}
            
            def change_theme(e):
                apply_theme(e.value)
                ui.notify(f"Theme switched to: {COLOR_SCHEMES[e.value]['name']}", type='info')
            
            with ui.column().classes('w-full gap-1'):
                ui.label('Active Color Theme').classes('th-caption')
                ui.select(theme_options, value=CURRENT_THEME_KEY, on_change=change_theme).classes('w-full').props('outlined dark dense')

        # Connect sourcing sites (encrypted local sessions)
        with ui.card().classes('w-full p-5 th-card mb-[13px]'):
            with ui.row().classes('items-center justify-between w-full mb-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('mail', color='teal-4', size='sm')
                    ui.label('Outbound email').classes('text-[13px] font-semibold text-[#edf5f7]')
                ui.label('SMTP · Encrypted').classes('text-[#45d6a0] text-[10px]')
            ui.label('Configure one recruiter account for real outreach delivery. Testing authenticates without sending mail.').classes('th-muted mb-3')

            from app.communications.email_service import verify_email_connection
            from app.communications.service import list_email_accounts, save_email_account
            from app.infrastructure.db import SessionFactory

            with SessionFactory() as db:
                existing_accounts = list_email_accounts(db)
                existing = existing_accounts[0] if existing_accounts else None
            account_state = {"id": existing.id if existing else None}

            with ui.column().classes('w-full gap-3'):
                with ui.row().classes('w-full gap-3 flex-wrap'):
                    email_in = ui.input(
                        'Email address', value=existing.email_address if existing else ''
                    ).classes('grow min-w-[220px]').props('outlined dark dense autocomplete=off name=talenthunt_smtp_email')
                    name_in = ui.input(
                        'Display name', value=(existing.display_name or '') if existing else ''
                    ).classes('grow min-w-[180px]').props('outlined dark dense autocomplete=off name=talenthunt_smtp_display_name')
                with ui.row().classes('w-full gap-3 flex-wrap'):
                    host_email_in = ui.input(
                        'SMTP host', value=(existing.smtp_host or '') if existing else 'smtp.gmail.com'
                    ).classes('grow min-w-[220px]').props('outlined dark dense autocomplete=off name=talenthunt_smtp_host')
                    port_email_in = ui.number(
                        'Port', value=existing.smtp_port if existing else 587, min=1, max=65535
                    ).classes('w-32').props('outlined dark dense')
                    secure_email_in = ui.switch(
                        'TLS / SSL', value=existing.use_ssl if existing else True
                    )
                with ui.row().classes('w-full gap-3 flex-wrap items-end'):
                    user_email_in = ui.input(
                        'SMTP username', value=(existing.smtp_username or '') if existing else ''
                    ).classes('grow min-w-[220px]').props('outlined dark dense autocomplete=off name=talenthunt_smtp_username')
                    password_email_in = ui.input(
                        'App password',
                        password=True,
                        password_toggle_button=True,
                        placeholder='Unchanged' if existing and existing.smtp_password else 'Required',
                    ).classes('grow min-w-[220px]').props('outlined dark dense autocomplete=new-password name=talenthunt_smtp_app_password')

                def save_smtp(show_notice=True):
                    if not email_in.value or '@' not in email_in.value or not host_email_in.value:
                        ui.notify('Enter a valid email address and SMTP host.', type='negative')
                        return None
                    with SessionFactory() as db:
                        account = save_email_account(
                            db,
                            account_id=account_state['id'],
                            email_address=email_in.value,
                            display_name=name_in.value,
                            smtp_host=host_email_in.value,
                            smtp_port=int(port_email_in.value or 587),
                            smtp_username=user_email_in.value,
                            smtp_password=password_email_in.value,
                            use_ssl=bool(secure_email_in.value),
                            is_default=True,
                        )
                    if not account:
                        ui.notify('Could not save SMTP configuration.', type='negative')
                        return None
                    account_state['id'] = account.id
                    password_email_in.value = ''
                    if show_notice:
                        ui.notify('SMTP configuration encrypted and saved locally.', type='positive')
                    return account

                def test_smtp():
                    account = save_smtp(show_notice=False)
                    if not account:
                        return
                    result = verify_email_connection(account.id)
                    if result['status'] == 'connected':
                        ui.notify(f"SMTP connected in {result['latency_ms']} ms. No email was sent.", type='positive')
                    else:
                        ui.notify(result.get('error') or 'SMTP connection failed.', type='negative')

                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Test connection', icon='lan', on_click=test_smtp).props('flat no-caps').classes('text-[#62aef7]')
                    ui.button('Save SMTP', icon='save', on_click=save_smtp).classes('th-primary-btn')

        # Connect sourcing sites (encrypted local sessions)
        with ui.card().classes('w-full p-5 th-card mb-[13px]'):
            with ui.row().classes('items-center justify-between w-full mb-2'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('lock', color='teal-4', size='sm')
                    ui.label('Connected sites').classes('text-[13px] font-semibold text-[#edf5f7]')
                ui.label('Local · Encrypted').classes('text-[#45d6a0] text-[10px]')
            ui.label(
                'Sign in once to LinkedIn, Naukri, and other sites you search. '
                'We store encrypted session cookies on this PC only — never your password.'
            ).classes('th-muted mb-3')
            from app.ui.components.connect_sites import render_connect_sites_panel
            render_connect_sites_panel()

        # Voice — local Kokoro primary, Edge/browser fallbacks
        with ui.card().classes('w-full p-5 th-card mt-[13px]'):
            with ui.row().classes('items-center justify-between w-full mb-2'):
                ui.label('Voice / TTS').classes('text-[13px] font-semibold text-[#edf5f7]')
                ui.label('Local · Persistent').classes('text-[#45d6a0] text-[10px]')
            ui.label(
                'Kokoro runs locally on CPU with a fixed voice. Edge neural and browser speech remain available as fallbacks.'
            ).classes('th-muted mb-3')

            from app.voice.preferences import load_tts_preferences, save_tts_preferences
            from app.voice.providers.edge_tts_provider import EdgeTTSProvider
            from app.voice.providers.kokoro_tts_provider import KokoroTTSProvider
            load_tts_preferences()
            edge_voice_opts = {v["id"]: v["label"] for v in EdgeTTSProvider.recommended_voices()}
            kokoro_voice_opts = {v["id"]: v["label"] for v in KokoroTTSProvider.recommended_voices()}
            provider_opts = {
                "kokoro": "Kokoro 82M (local CPU · stable)",
                "edge": "Edge neural (free · online)",
                "browser": "Browser Web Speech only",
            }

            with ui.column().classes('w-full gap-3'):
                with ui.column().classes('w-full gap-1'):
                    ui.label('TTS provider').classes('th-caption')
                    tts_provider_in = ui.select(
                        provider_opts,
                        value=settings.tts_provider if settings.tts_provider in provider_opts else "kokoro",
                    ).classes('w-full').props('outlined dark dense')
                with ui.column().classes('w-full gap-1'):
                    ui.label('Kokoro voice').classes('th-caption')
                    kokoro_voice_in = ui.select(
                        kokoro_voice_opts,
                        value=settings.tts_kokoro_voice if settings.tts_kokoro_voice in kokoro_voice_opts else "af_heart",
                    ).classes('w-full').props('outlined dark dense')
                with ui.column().classes('w-full gap-1'):
                    ui.label('Edge fallback voice').classes('th-caption')
                    edge_voice_in = ui.select(
                        edge_voice_opts,
                        value=settings.tts_edge_voice if settings.tts_edge_voice in edge_voice_opts else "en-US-JennyNeural",
                    ).classes('w-full').props('outlined dark dense')

                async def preview_tts():
                    sample = "Hi, I am TalentHunt Copilot. This is my selected voice."
                    use_kokoro = tts_provider_in.value == "kokoro"
                    if use_kokoro:
                        audio = await KokoroTTSProvider(voice=kokoro_voice_in.value).generate_speech(sample)
                        mime = "audio/wav"
                    else:
                        audio = await EdgeTTSProvider(voice=edge_voice_in.value).generate_speech(sample)
                        mime = "audio/mpeg"
                    if not audio:
                        ui.notify('Preview failed for the selected provider.', type='warning')
                        return
                    import base64
                    b64 = base64.b64encode(audio).decode('ascii')
                    ui.run_javascript(
                        f'(function(){{ const a = new Audio("data:{mime};base64,{b64}"); a.play(); }})();'
                    )
                    ui.notify('Playing preview…', type='info')

                with ui.row().classes('w-full justify-between items-center gap-2'):
                    ui.button('Preview voice', icon='volume_up', on_click=preview_tts).props('flat dense').classes(
                        'text-xs text-teal-300'
                    )

                    def save_tts_prefs():
                        save_tts_preferences(
                            provider=tts_provider_in.value or "kokoro",
                            edge_voice=edge_voice_in.value or "en-US-JennyNeural",
                            kokoro_voice=kokoro_voice_in.value or "af_heart",
                        )
                        selected_voice = kokoro_voice_in.value if tts_provider_in.value == "kokoro" else edge_voice_in.value
                        ui.run_javascript(
                            f'window.thFreeVoice = window.thFreeVoice || {{}};'
                            f'window.thFreeVoice.edgeVoice = {selected_voice!r};'
                        )
                        ui.notify('TTS preferences saved', type='positive')

                    ui.button('Save TTS', icon='save', on_click=save_tts_prefs).classes('th-primary-btn text-xs')

                ui.separator().classes('bg-slate-700/50 my-1')
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
                        save_app_preferences()
                        ui.notify('Voice engine keys encrypted and saved locally', type='positive')

                    ui.button('Save Voice Keys', icon='save', on_click=save_voice_keys).classes('th-slate-btn')

def settings_page():
    create_layout(render_settings)
