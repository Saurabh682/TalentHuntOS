"""Copilot Panel UI component for NiceGUI (Right-hand chat interface with Voice integration)."""

import asyncio
from nicegui import ui
from app.copilot.conversation import conversation_manager
from app.copilot.streaming import stream_copilot_response


def render_copilot_panel():
    """Render the interactive Copilot chat side panel with real-time Voice Engine integration."""

    ui.add_head_html("""
    <script>
    window.thFreeVoice = {
        recognition: null,
        isListening: false,
        ttsEnabled: true
    };

    function toggleFreeVoiceRecording() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            alert('Web Speech API is not supported by your browser. Please use Google Chrome or Microsoft Edge for lifetime free voice recognition.');
            return;
        }

        if (!window.thFreeVoice.recognition) {
            const recognition = new SpeechRecognition();
            recognition.continuous = true;
            recognition.interimResults = true;
            recognition.lang = 'en-US';

            recognition.onresult = (event) => {
                let transcript = '';
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    transcript += event.results[i][0].transcript;
                }
                const inputEl = document.querySelector('.th-copilot-panel input');
                if (inputEl) {
                    inputEl.value = transcript;
                    inputEl.dispatchEvent(new Event('input', { bubbles: true }));
                }
            };

            recognition.onend = () => {
                window.thFreeVoice.isListening = false;
            };

            recognition.onerror = (err) => {
                console.error('Speech recognition error:', err);
                window.thFreeVoice.isListening = false;
            };

            window.thFreeVoice.recognition = recognition;
        }

        if (!window.thFreeVoice.isListening) {
            try {
                window.thFreeVoice.recognition.start();
                window.thFreeVoice.isListening = true;
            } catch(e) { console.error('Start recognition error:', e); }
        } else {
            window.thFreeVoice.recognition.stop();
            window.thFreeVoice.isListening = false;
        }
    }

    function toggleTTS() {
        window.thFreeVoice.ttsEnabled = !window.thFreeVoice.ttsEnabled;
        if (!window.thFreeVoice.ttsEnabled && 'speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }
        return window.thFreeVoice.ttsEnabled;
    }

    function speakTextFree(text) {
        if (!window.thFreeVoice.ttsEnabled) return;
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
            const cleanText = text.replace(/[*#_`]/g, '');
            const utterance = new SpeechSynthesisUtterance(cleanText);
            utterance.rate = 1.0;
            utterance.pitch = 1.0;
            const voices = window.speechSynthesis.getVoices();
            if (voices && voices.length > 0) {
                const natural = voices.find(v => (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Online') || v.name.includes('Neural') || v.name.includes('Samantha') || v.name.includes('Jenny')) && v.lang.startsWith('en'));
                if (natural) utterance.voice = natural;
            }
            window.speechSynthesis.speak(utterance);
        }
    }

    window.thCopilotFullscreen = false;
    function toggleCopilotFullscreen() {
        window.thCopilotFullscreen = !window.thCopilotFullscreen;
        const parentPanel = document.querySelector('.th-copilot-panel');
        if (parentPanel) {
            if (window.thCopilotFullscreen) {
                parentPanel.style.position = 'fixed';
                parentPanel.style.inset = '0';
                parentPanel.style.zIndex = '50';
                parentPanel.style.width = '100vw';
                parentPanel.style.height = '100vh';
                parentPanel.style.maxWidth = 'none';
            } else {
                parentPanel.style.position = '';
                parentPanel.style.inset = '';
                parentPanel.style.zIndex = '';
                parentPanel.style.width = '285px';
                parentPanel.style.height = '100vh';
                parentPanel.style.maxWidth = '';
            }
        }
    }
    </script>
    """)

    BOT_AVATAR = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0iIzE5ZDNjNSI+PHBhdGggZD0iTTEyIDJhMiAyIDAgMCAxIDIgMnYxaDFhMyAzIDAgMCAxIDMgM3YyYTMgMyAwIDAgMSAzIDN2MmEzIDMgMCAwIDEtMyAzdjNhMyAzIDAgMCAxLTMgM0g5YTMgMyAwIDAgMS0zLTN2LTNhMyAzIDAgMCAxLTMtM3YtMmEzIDMgMCAwIDEgMy0zVjhhMyAzIDAgMCAxIDMtM2gxVjRhMiAyIDAgMCAxIDItMnptLTMgN2ExLjUgMS41IDAgMSAwIDAgMyAxLjUgMS41IDAgMCAwIDAtM3ptNiAwYTEuNSAxLjUgMCAxIDAgMCAzIDEuNSAxLjUgMCAwIDAgMC0zem0tNiA2YTEgMSAwIDAgMCAwIDJoNmExIDEgMCAxIDAgMC0ySDl6Ii8+PC9zdmc+"
    USER_AVATAR = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0iIzE5ZDNjNSI+PHBhdGggZD0iTTEyIDJhNSA1IDAgMSAxIDAgMTAgNSA1IDAgMCAxIDAtMTB6bTAgMTJjNS4zMyAwIDggMi42NyA4IDR2Mkg0di0yYzAtMS4zMyAyLjY3LTQgOC00eiIvPjwvc3ZnPg=="

    tts_active = {"enabled": True}
    chat_container_ref = {"el": None}
    input_field_ref = {"el": None}

    input_history = []
    history_state = {"index": -1, "draft": ""}

    active_session_id = {"value": "default"}

    def get_hunt_options():
        options = {"default": "General Chat"}
        try:
            from app.infrastructure.db import SessionFactory
            from app.hunts.service import list_hunts
            with SessionFactory() as db:
                hunts = list_hunts(db, status="Active")
                for h in hunts:
                    options[f"hunt_{h.id}"] = h.title
        except Exception:
            pass
        return options

    try:
        if hasattr(ui, 'app') and hasattr(ui.app, 'storage') and 'active_session_id' in ui.app.storage.user:
            saved_sid = ui.app.storage.user['active_session_id']
            if saved_sid in get_hunt_options():
                active_session_id["value"] = saved_sid
    except Exception:
        pass

    def scroll_to_bottom():
        try:
            ui.run_javascript(
                'setTimeout(() => { const el = document.querySelector(".copilot-chat-container");'
                ' if(el) el.scrollTop = el.scrollHeight; }, 50);'
            )
        except Exception:
            pass

    def render_history():
        if not chat_container_ref["el"]:
            return
        chat_container_ref["el"].clear()
        with chat_container_ref["el"]:
            messages = conversation_manager.get_messages(session_id=active_session_id["value"])
            if not messages:
                with ui.chat_message(name='Copilot', stamp='now', avatar=BOT_AVATAR).classes('w-full'):
                    ui.markdown('Hello! I am TalentHunt Copilot. How can I help you hunt top talent today?')
            else:
                for msg in messages:
                    is_user = msg["role"] == "user"
                    name = "You" if is_user else "Copilot"
                    avatar = USER_AVATAR if is_user else BOT_AVATAR
                    stamp = msg.get("timestamp", "")
                    with ui.chat_message(name=name, stamp=stamp, avatar=avatar, sent=is_user).classes('w-full'):
                        ui.markdown(msg["content"])
        scroll_to_bottom()

    def clear_chat():
        conversation_manager.clear_session(session_id=active_session_id["value"])
        render_history()
        ui.notify("Conversation reset.")

    async def handle_send(e=None):
        input_el = input_field_ref["el"]
        chat_el = chat_container_ref["el"]
        if not input_el or not input_el.value.strip():
            return

        user_text = input_el.value.strip()

        if not input_history or input_history[-1] != user_text:
            input_history.append(user_text)
            if len(input_history) > 50:
                input_history.pop(0)
        history_state["index"] = -1
        history_state["draft"] = ""

        input_el.value = ""

        with chat_el:
            with ui.chat_message(name="You", stamp="now", avatar=USER_AVATAR, sent=True).classes('w-full'):
                ui.markdown(user_text)

            scroll_to_bottom()

            response_msg = ui.chat_message(name="Copilot", stamp="typing...", avatar=BOT_AVATAR).classes('w-full')
            with response_msg:
                response_label = ui.markdown("...")

        final_resp = ""
        try:
            async for accum_text in stream_copilot_response(user_text, session_id=active_session_id["value"]):
                response_label.content = accum_text
                final_resp = accum_text
                scroll_to_bottom()
        except Exception as exc:
            final_resp = f"Error during response streaming: {exc}"
            response_label.content = final_resp
            conversation_manager.add_assistant_message(final_resp, session_id=active_session_id["value"])

        render_history()
        import json
        if final_resp and not final_resp.startswith("Error"):
            ui.run_javascript(f'speakTextFree({json.dumps(final_resp)});')

    def handle_up(e):
        if not input_history:
            return
        if history_state["index"] == -1:
            history_state["draft"] = input_field_ref["el"].value
            history_state["index"] = len(input_history) - 1
        elif history_state["index"] > 0:
            history_state["index"] -= 1
        input_field_ref["el"].value = input_history[history_state["index"]]
        input_field_ref["el"].update()

    def handle_down(e):
        if not input_history or history_state["index"] == -1:
            return
        if history_state["index"] < len(input_history) - 1:
            history_state["index"] += 1
            input_field_ref["el"].value = input_history[history_state["index"]]
        else:
            history_state["index"] = -1
            input_field_ref["el"].value = history_state["draft"]
        input_field_ref["el"].update()

    with ui.element('div').classes('th-copilot-inner'):
        with ui.element('div').style(
            'display:flex;align-items:center;justify-content:space-between;'
            'width:100%;margin-bottom:12px;flex-shrink:0;height:auto'
        ):
            ui.label('Copilot').style('font-weight:700;color:#edf5f7;font-size:13px;white-space:nowrap')
            with ui.element('div').style('display:flex;align-items:center;gap:2px;flex-shrink:0'):
                ui.button(
                    icon='open_in_full',
                    on_click=lambda: ui.run_javascript('toggleCopilotFullscreen();')
                ).props('flat round dense').classes('text-[#8195a5]').tooltip('Expand Copilot Fullscreen')

                ui.button(
                    icon='refresh',
                    on_click=clear_chat
                ).props('flat round dense').classes('text-[#8195a5]').tooltip('Clear Conversation')

                def do_toggle_tts():
                    tts_active["enabled"] = not tts_active["enabled"]
                    ui.run_javascript('toggleTTS();')
                    tts_btn.props(f'icon={"volume_up" if tts_active["enabled"] else "volume_off"}')
                    ui.notify(f'Voice Reply (TTS) {"Enabled" if tts_active["enabled"] else "Muted"}')

                tts_btn = ui.button(
                    icon='volume_up',
                    on_click=do_toggle_tts
                ).props('flat round dense').classes('text-[#19d3c5]').tooltip('Toggle Voice Reply (TTS On/Mute)')

                ui.button(
                    icon='mic',
                    on_click=lambda: ui.run_javascript('toggleFreeVoiceRecording();')
                ).props('flat round dense').classes('text-[#d8941e]').tooltip('Browser Free Voice Input')

        def on_session_change(e):
            active_session_id["value"] = e.value
            try:
                if hasattr(ui, 'app') and hasattr(ui.app, 'storage'):
                    ui.app.storage.user['active_session_id'] = e.value
            except Exception:
                pass
            render_history()

        with ui.element('div').style('width:100%;margin-bottom:8px;flex-shrink:0'):
            ui.select(
                options=get_hunt_options(),
                value=active_session_id["value"],
                on_change=on_session_change
            ).classes('w-full text-xs').props('dense outlined dark').tooltip('Switch conversation context')

        ui.separator().classes('bg-[#1b3040] mb-3 shrink-0')

        chat_container_ref["el"] = ui.column().classes(
            'w-full p-3 overflow-y-auto mb-2 gap-3 custom-scrollbar copilot-chat-container items-stretch'
        ).style(
            'flex:1 1 auto;min-height:120px;border:1px solid #1b3040;border-radius:12px;background:#0b1724'
        )

        render_history()

        def send_quick_prompt(text: str):
            if input_field_ref["el"]:
                input_field_ref["el"].value = text
                asyncio.create_task(handle_send())

        with ui.element('div').style(
            'display:flex;gap:6px;width:100%;margin-bottom:8px;overflow-x:auto;flex-shrink:0;flex-wrap:nowrap'
        ):
            for chip_text in ["Draft outreach message", "Move top 5 to pipeline", "Show match scores"]:
                ui.button(
                    chip_text,
                    on_click=lambda t=chip_text: send_quick_prompt(t)
                ).props('flat dense no-caps').style(
                    'font-size:11px;color:#8195a5;background:#0e1b28;border:1px solid #1b3040;'
                    'border-radius:999px;padding:4px 10px;white-space:nowrap;min-height:28px;height:auto;width:auto'
                )

        with ui.element('div').style(
            'display:flex;align-items:center;gap:8px;width:100%;flex-shrink:0;'
            'background:#0e1b28;border:1px solid #1b3040;border-radius:9px;padding:6px'
        ):
            input_field_ref["el"] = ui.input(placeholder='Ask Copilot or click mic...').classes(
                'grow text-xs text-[#dce7eb] bg-transparent border-none'
            ).props('borderless dense dark')

            input_field_ref["el"].on('keydown.up', handle_up)
            input_field_ref["el"].on('keydown.down', handle_down)
            input_field_ref["el"].on('keydown.enter', handle_send)

            ui.button(
                icon='mic',
                on_click=lambda: ui.run_javascript('toggleFreeVoiceRecording();')
            ).props('flat round dense').classes('text-[#8195a5] hover:text-[#19d3c5]').tooltip('Voice input')

            ui.button(
                icon='arrow_upward',
                on_click=handle_send
            ).props('round dense').style(
                'background:#10a99f;color:#071019;width:28px;height:28px;min-height:28px'
            )

        # Auto-run pending Launch Hunt sourcing prompt (set by hunts/launch.py)
        async def _run_pending_launch_prompt():
            await asyncio.sleep(0.4)
            prompt = None
            try:
                if hasattr(ui, 'app') and hasattr(ui.app, 'storage'):
                    prompt = ui.app.storage.user.pop('pending_copilot_prompt', None)
            except Exception:
                prompt = None
            if not prompt or not input_field_ref["el"]:
                return
            input_field_ref["el"].value = prompt
            await handle_send()

        try:
            has_pending = False
            if hasattr(ui, 'app') and hasattr(ui.app, 'storage'):
                has_pending = bool(ui.app.storage.user.get('pending_copilot_prompt'))
            if has_pending:
                asyncio.create_task(_run_pending_launch_prompt())
        except Exception:
            pass
