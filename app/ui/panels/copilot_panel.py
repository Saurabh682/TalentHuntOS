"""Copilot Panel UI component for NiceGUI (Right-hand chat interface with Voice integration)."""

import asyncio
from nicegui import ui
from app.copilot.conversation import conversation_manager
from app.copilot.streaming import stream_copilot_response

# Survives page navigations (layout remounts the panel on every route change)
_COPILOT_STATE = {
    "session_id": "default",
    "input_history": [],
    "history_index": -1,
    "draft": "",
    "select_ready": False,
}


def _persist_session(session_id: str) -> None:
    _COPILOT_STATE["session_id"] = session_id or "default"
    try:
        if hasattr(ui, "app") and hasattr(ui.app, "storage"):
            ui.app.storage.user["active_session_id"] = _COPILOT_STATE["session_id"]
    except Exception:
        pass


def _load_session_id(options: dict) -> str:
    """Prefer module memory, then user storage; keep hunt sessions even if not Active."""
    sid = _COPILOT_STATE.get("session_id") or "default"
    try:
        if hasattr(ui, "app") and hasattr(ui.app, "storage"):
            stored = ui.app.storage.user.get("active_session_id")
            if stored:
                sid = stored
                _COPILOT_STATE["session_id"] = sid
    except Exception:
        pass
    if sid not in options:
        # Keep a phantom option so the select doesn't snap to General Chat
        if sid.startswith("hunt_"):
            options[sid] = f"Hunt {sid.split('_', 1)[1]}"
        else:
            sid = "default"
            _COPILOT_STATE["session_id"] = "default"
    return sid


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
                const inputEl = document.querySelector('.th-copilot-input input') || document.querySelector('.th-copilot-panel input');
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
    session_select_ref = {"el": None}
    busy_state = {"chat": False, "label": ""}
    busy_banner_ref = {"el": None, "label": None, "detail": None}
    send_btn_ref = {"el": None}

    # Bind to process-level history so Up/Down survives route changes
    input_history = _COPILOT_STATE["input_history"]
    history_state = _COPILOT_STATE  # uses history_index + draft keys
    active_session_id = {"value": "default"}

    def get_hunt_options():
        options = {"default": "General Chat"}
        try:
            from app.infrastructure.db import SessionFactory
            from app.hunts.service import list_hunts
            with SessionFactory() as db:
                # Include Active + recent hunts so switching pages doesn't drop the selection
                hunts = list_hunts(db, limit=100)
                for h in hunts:
                    label = h.title or f"Hunt {h.id}"
                    if h.status and h.status != "Active":
                        label = f"{label} ({h.status})"
                    options[f"hunt_{h.id}"] = label
        except Exception:
            pass
        return options

    options = get_hunt_options()
    active_session_id["value"] = _load_session_id(options)
    _COPILOT_STATE["select_ready"] = False

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

        from app.hunts import sourcing_jobs
        from app.copilot.direct_actions import parse_clear_and_source, run_clear_and_source

        user_text = input_el.value.strip()
        direct = parse_clear_and_source(user_text)
        low = user_text.lower()
        force_new = bool(direct) or any(
            w in low for w in ("cancel", "stop crawl", "stop sourcing", "clear this hunt")
        )

        if busy_state["chat"] and not force_new:
            ui.notify(
                "Copilot is still answering. Wait a moment, or send a clear/cancel command.",
                type="warning",
            )
            return

        if sourcing_jobs.is_busy() and not force_new:
            ui.notify(
                "A LinkedIn crawl is running. Wait, click Cancel on the orange banner, "
                "or type: clear this hunt and look for 25 talents on LinkedIn",
                type="warning",
            )
            return

        if not input_history or input_history[-1] != user_text:
            input_history.append(user_text)
            if len(input_history) > 50:
                input_history.pop(0)
        history_state["history_index"] = -1
        history_state["draft"] = ""

        input_el.value = ""
        busy_state["chat"] = True
        busy_state["label"] = "Copilot is working…"
        _refresh_busy_banner()

        with chat_el:
            with ui.chat_message(name="You", stamp="now", avatar=USER_AVATAR, sent=True).classes('w-full'):
                ui.markdown(user_text)

            scroll_to_bottom()

            response_msg = ui.chat_message(name="Copilot", stamp="typing...", avatar=BOT_AVATAR).classes('w-full')
            with response_msg:
                response_label = ui.markdown("...")

        final_resp = ""
        try:
            # Deterministic path — don't rely on the LLM to call tools
            if direct:
                final_resp = await asyncio.to_thread(
                    run_clear_and_source,
                    session_id=active_session_id["value"],
                    target=direct["target"],
                    clear=direct["clear"],
                )
                response_label.content = final_resp
                from app.copilot.conversation import conversation_manager as _cm
                _cm.add_user_message(user_text, active_session_id["value"])
                _cm.add_assistant_message(final_resp, active_session_id["value"])
                scroll_to_bottom()
            else:
                last_push = {"text": "", "n": 0}
                async for accum_text in stream_copilot_response(
                    user_text, session_id=active_session_id["value"]
                ):
                    final_resp = accum_text
                    last_push["n"] += 1
                    if last_push["n"] % 8 == 0 or len(accum_text) - len(last_push["text"]) > 120:
                        response_label.content = accum_text
                        last_push["text"] = accum_text
                        scroll_to_bottom()
                if final_resp and final_resp != last_push["text"]:
                    response_label.content = final_resp
                    scroll_to_bottom()
        except Exception as exc:
            final_resp = f"Error during response streaming: {exc}"
            response_label.content = final_resp
            conversation_manager.add_assistant_message(
                final_resp, session_id=active_session_id["value"]
            )
        finally:
            busy_state["chat"] = False
            _refresh_busy_banner()

        render_history()
        import json
        if final_resp and not final_resp.startswith("Error") and len(final_resp) < 2500:
            ui.run_javascript(f'speakTextFree({json.dumps(final_resp[:1500])});')

    def handle_up(e):
        if not input_history or not input_field_ref["el"]:
            return
        try:
            # Stop the cursor from jumping to start of the Quasar input
            ui.run_javascript(
                'const el=document.querySelector(".th-copilot-input input");'
                'if(el){el.blur(); el.focus();}'
            )
        except Exception:
            pass
        if history_state["history_index"] == -1:
            history_state["draft"] = input_field_ref["el"].value or ""
            history_state["history_index"] = len(input_history) - 1
        elif history_state["history_index"] > 0:
            history_state["history_index"] -= 1
        input_field_ref["el"].value = input_history[history_state["history_index"]]
        input_field_ref["el"].update()

    def handle_down(e):
        if not input_history or not input_field_ref["el"] or history_state["history_index"] == -1:
            return
        if history_state["history_index"] < len(input_history) - 1:
            history_state["history_index"] += 1
            input_field_ref["el"].value = input_history[history_state["history_index"]]
        else:
            history_state["history_index"] = -1
            input_field_ref["el"].value = history_state.get("draft") or ""
        input_field_ref["el"].update()

    def handle_input_keydown(e):
        """Route Up/Down for command history (works across NiceGUI key event shapes)."""
        key = None
        args = getattr(e, "args", None)
        if isinstance(args, dict):
            key = args.get("key") or args.get("code")
        elif isinstance(args, list) and args:
            first = args[0]
            if isinstance(first, dict):
                key = first.get("key") or first.get("code")
            elif isinstance(first, str):
                key = first
        if not key and hasattr(e, "key"):
            key = e.key
        key = str(key or "")
        if key in ("ArrowUp", "Up"):
            handle_up(e)
        elif key in ("ArrowDown", "Down"):
            handle_down(e)

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
            new_val = e.value
            # Ignore spurious on_change during remount (was snapping back to General Chat)
            if not _COPILOT_STATE.get("select_ready"):
                if new_val != active_session_id["value"] and session_select_ref["el"]:
                    try:
                        session_select_ref["el"].value = active_session_id["value"]
                        session_select_ref["el"].update()
                    except Exception:
                        pass
                return
            if not new_val or new_val == active_session_id["value"]:
                return
            active_session_id["value"] = new_val
            _persist_session(new_val)
            render_history()

        with ui.element('div').style('width:100%;margin-bottom:8px;flex-shrink:0'):
            session_select_ref["el"] = ui.select(
                options=options,
                value=active_session_id["value"],
                on_change=on_session_change,
            ).classes('w-full text-xs').props('dense outlined dark').tooltip(
                'Switch conversation context (stays on this hunt when you navigate)'
            )

        def _mark_select_ready():
            _COPILOT_STATE["select_ready"] = True
            # Re-assert saved session after Quasar finishes mounting
            if session_select_ref["el"] and session_select_ref["el"].value != active_session_id["value"]:
                session_select_ref["el"].value = active_session_id["value"]
                session_select_ref["el"].update()

        ui.timer(0.35, _mark_select_ready, once=True)

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

        def _refresh_busy_banner():
            from app.hunts import sourcing_jobs
            jobs = sourcing_jobs.list_active_jobs()
            banner = busy_banner_ref["el"]
            if not banner:
                return
            if busy_state["chat"] or jobs:
                banner.set_visibility(True)
                job = jobs[0] if jobs else None
                title = (
                    job.get("label")
                    if job
                    else busy_state.get("label") or "Copilot is working…"
                )
                detail = ""
                if job:
                    detail = (
                        f"{job.get('message') or ''} · "
                        f"added {job.get('added', 0)} · scanned {job.get('scanned', 0)}"
                    )
                elif busy_state["chat"]:
                    detail = "Waiting for Copilot reply… Cancel stops LinkedIn crawls only."
                if busy_banner_ref["label"]:
                    busy_banner_ref["label"].set_text(title)
                if busy_banner_ref["detail"]:
                    busy_banner_ref["detail"].set_text(detail)
                if send_btn_ref["el"]:
                    send_btn_ref["el"].props("disable")
            else:
                banner.set_visibility(False)
                if send_btn_ref["el"]:
                    send_btn_ref["el"].props(remove="disable")

        def _cancel_busy():
            from app.hunts import sourcing_jobs
            n = sourcing_jobs.cancel_all()
            ui.notify(
                f"Cancel requested for {n} job(s)." if n else "No active crawl to cancel.",
                type="info",
            )
            _refresh_busy_banner()

        with ui.element('div').classes('w-full mb-2').style(
            'flex-direction:column;gap:6px;padding:8px 10px;'
            'background:#3d2a0f;border:1px solid #f0a020;'
            'border-radius:9px;flex-shrink:0'
        ) as busy_banner:
            busy_banner_ref["el"] = busy_banner
            busy_banner.set_visibility(False)
            with ui.row().classes('w-full items-center justify-between gap-2'):
                with ui.row().classes('items-center gap-2 grow'):
                    ui.spinner(size='sm', color='orange')
                    with ui.column().classes('gap-0 grow'):
                        busy_banner_ref["label"] = ui.label('Working…').classes(
                            'text-xs font-semibold text-orange-200'
                        )
                        busy_banner_ref["detail"] = ui.label('').classes(
                            'text-[10px] text-orange-100/70'
                        )
                ui.button('Cancel', icon='stop', on_click=_cancel_busy).props(
                    'flat dense'
                ).classes('text-xs text-orange-100')

        ui.timer(1.0, _refresh_busy_banner)

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
                'grow text-xs text-[#dce7eb] bg-transparent border-none th-copilot-input'
            ).props('borderless dense dark')

            input_field_ref["el"].on('keydown', handle_input_keydown)
            input_field_ref["el"].on('keydown.enter', handle_send)

            ui.button(
                icon='mic',
                on_click=lambda: ui.run_javascript('toggleFreeVoiceRecording();')
            ).props('flat round dense').classes('text-[#8195a5] hover:text-[#19d3c5]').tooltip('Voice input')

            send_btn_ref["el"] = ui.button(
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
