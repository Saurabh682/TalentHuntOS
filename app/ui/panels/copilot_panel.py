"""Copilot Panel UI component for NiceGUI (Right-hand chat interface with Voice integration)."""

import asyncio
import json
import logging

from nicegui import ui
from app.copilot.conversation import conversation_manager
from app.copilot.streaming import stream_copilot_response
from app.config.settings import DATA_DIR

logger = logging.getLogger("talenthunt.ui.copilot_panel")

_INPUT_HISTORY_PATH = DATA_DIR / "copilot_input_history.json"
_MAX_INPUT_HISTORY = 80

# Survives page navigations (layout remounts the panel on every route change)
_COPILOT_STATE = {
    "session_id": "default",
    "input_history": [],
    "history_index": -1,
    "draft": "",
    "select_ready": False,
    "history_loaded": False,
}


def _load_input_history() -> list:
    """Load past prompts from disk + seed from saved chat user messages."""
    items: list = []
    try:
        if _INPUT_HISTORY_PATH.exists():
            raw = json.loads(_INPUT_HISTORY_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                items = [str(x).strip() for x in raw if str(x).strip()]
    except Exception as exc:
        logger.warning("Could not load copilot input history: %s", exc)

    # Seed from conversation store (user roles) so history isn't empty after restart
    try:
        seen = set(items)
        for _sid, msgs in (conversation_manager._store or {}).items():
            if not isinstance(msgs, list):
                continue
            for msg in msgs:
                if not isinstance(msg, dict) or msg.get("role") != "user":
                    continue
                text = (msg.get("content") or "").strip()
                if text and text not in seen:
                    items.append(text)
                    seen.add(text)
    except Exception:
        pass

    # Keep last N unique (order preserved, prefer newest at end)
    deduped: list = []
    seen2 = set()
    for text in items:
        if text in seen2:
            continue
        seen2.add(text)
        deduped.append(text)
    return deduped[-_MAX_INPUT_HISTORY:]


def _save_input_history(history: list) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _INPUT_HISTORY_PATH.write_text(
            json.dumps(history[-_MAX_INPUT_HISTORY:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Could not save copilot input history: %s", exc)


def _ensure_input_history_loaded() -> None:
    if _COPILOT_STATE.get("history_loaded"):
        return
    _COPILOT_STATE["input_history"] = _load_input_history()
    _COPILOT_STATE["history_loaded"] = True


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

    ui.add_head_html(r"""
    <script>
    window.thFreeVoice = {
        recognition: null,
        isListening: false,
        ttsEnabled: true,
        edgeVoice: '',
        _audio: null,
        _audioUrl: null,
        _speechAbort: null,
        _speechGeneration: 0,
        _speechSource: '',
        _speechBuffer: '',
        _speechQueue: [],
        _speechWorkerRunning: false,
        _audioUnlocked: false,
        voiceInputPending: false
    };

    function unlockCopilotAudio() {
        if (window.thFreeVoice._audioUnlocked) return;
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                window.thFreeVoice._audioContext = window.thFreeVoice._audioContext || new AudioContext();
                window.thFreeVoice._audioContext.resume();
            }
            const silent = new Audio('data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=');
            silent.volume = 0;
            const promise = silent.play();
            if (promise) promise.catch(() => {});
            window.thFreeVoice._audioUnlocked = true;
        } catch (e) {
            console.warn('Could not pre-authorize Copilot audio', e);
        }
    }

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
                const inputEl = document.querySelector('.th-copilot-input textarea') || document.querySelector('.th-copilot-input input');
                if (inputEl) {
                    window.thFreeVoice.voiceInputPending = true;
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
        if (!window.thFreeVoice.ttsEnabled) {
            stopCopilotSpeech();
        }
        return window.thFreeVoice.ttsEnabled;
    }

    function cleanCopilotSpeechText(text) {
        return (text || '')
            .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
            .replace(/https?:\/\/\S+/g, '')
            .replace(/[*#_`>|~]/g, '')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function chooseBrowserVoice(utterance) {
        const voices = window.speechSynthesis.getVoices();
        if (!voices || !voices.length) return;
        const prefer = [
            'Microsoft Jenny', 'Microsoft Aria', 'Microsoft Guy', 'Microsoft Neerja',
            'Google US English', 'Natural', 'Neural', 'Online', 'Samantha', 'Jenny'
        ];
        let chosen = null;
        for (const name of prefer) {
            chosen = voices.find(v => v.name.includes(name) && (v.lang || '').startsWith('en'));
            if (chosen) break;
        }
        utterance.voice = chosen || voices.find(v => (v.lang || '').startsWith('en')) || null;
    }

    function stopCopilotSpeech() {
        const state = window.thFreeVoice;
        state._speechGeneration += 1;
        state._speechQueue = [];
        state._speechSource = '';
        state._speechBuffer = '';
        if (state._speechAbort) {
            try { state._speechAbort.abort(); } catch (e) {}
        }
        state._speechAbort = null;
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
        if (state._audio) {
            try { state._audio.pause(); } catch (e) {}
            state._audio = null;
        }
        if (state._audioUrl) {
            try { URL.revokeObjectURL(state._audioUrl); } catch (e) {}
            state._audioUrl = null;
        }
    }

    function beginCopilotSpeechResponse() {
        stopCopilotSpeech();
        window.thFreeVoice._speechWorkerRunning = false;
    }

    function speakBrowserChunk(text, generation) {
        return new Promise((resolve) => {
            if (!('speechSynthesis' in window) || generation !== window.thFreeVoice._speechGeneration) {
                resolve();
                return;
            }
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 1.0;
            utterance.pitch = 1.0;
            chooseBrowserVoice(utterance);
            utterance.onend = resolve;
            utterance.onerror = resolve;
            window.speechSynthesis.speak(utterance);
        });
    }

    async function fetchSpeechChunk(text, generation) {
        const state = window.thFreeVoice;
        const controller = new AbortController();
        state._speechAbort = controller;
        const timeout = setTimeout(() => controller.abort(), 4500);
        try {
            const qs = new URLSearchParams({text, voice: state.edgeVoice || ''});
            const response = await fetch('/api/tts?' + qs.toString(), {signal: controller.signal});
            if (generation !== state._speechGeneration || !response.ok) return null;
            const blob = await response.blob();
            return blob && blob.size ? blob : null;
        } finally {
            clearTimeout(timeout);
            if (state._speechAbort === controller) state._speechAbort = null;
        }
    }

    function playSpeechBlob(blob, generation) {
        return new Promise((resolve, reject) => {
            const state = window.thFreeVoice;
            if (generation !== state._speechGeneration) {
                resolve();
                return;
            }
            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);
            state._audio = audio;
            state._audioUrl = url;
            const finish = () => {
                try { URL.revokeObjectURL(url); } catch (e) {}
                if (state._audio === audio) state._audio = null;
                if (state._audioUrl === url) state._audioUrl = null;
                resolve();
            };
            audio.onended = finish;
            audio.onerror = () => { finish(); reject(new Error('Audio playback failed')); };
            audio.play().catch((error) => { finish(); reject(error); });
        });
    }

    async function runCopilotSpeechQueue() {
        const state = window.thFreeVoice;
        if (state._speechWorkerRunning || !state.ttsEnabled) return;
        state._speechWorkerRunning = true;
        const generation = state._speechGeneration;
        try {
            while (state._speechQueue.length && generation === state._speechGeneration && state.ttsEnabled) {
                const chunk = state._speechQueue.shift();
                try {
                    const blob = await fetchSpeechChunk(chunk, generation);
                    if (blob) await playSpeechBlob(blob, generation);
                    else await speakBrowserChunk(chunk, generation);
                } catch (error) {
                    if (error && error.name !== 'AbortError') {
                        console.warn('Configured TTS unavailable; using browser voice for this sentence', error);
                    }
                    if (generation === state._speechGeneration) {
                        await speakBrowserChunk(chunk, generation);
                    }
                }
            }
        } finally {
            state._speechWorkerRunning = false;
            if (state._speechQueue.length && generation === state._speechGeneration) {
                runCopilotSpeechQueue();
            }
        }
    }

    function extractCopilotSpeechChunks(finalChunk) {
        const state = window.thFreeVoice;
        let buffer = state._speechBuffer.trimStart();
        while (buffer) {
            const sentence = buffer.match(/^(.{18,260}?[.!?])(?:\s+|$)/);
            if (sentence) {
                state._speechQueue.push(sentence[1].trim());
                buffer = buffer.slice(sentence[0].length);
                continue;
            }
            if (buffer.length > 260) {
                const splitAt = Math.max(buffer.lastIndexOf(' ', 260), 160);
                state._speechQueue.push(buffer.slice(0, splitAt).trim());
                buffer = buffer.slice(splitAt).trimStart();
                continue;
            }
            break;
        }
        if (finalChunk && buffer.trim()) {
            state._speechQueue.push(buffer.trim());
            buffer = '';
        }
        state._speechBuffer = buffer;
        runCopilotSpeechQueue();
    }

    function queueCopilotSpeechText(text, finalChunk = false) {
        const state = window.thFreeVoice;
        if (!state.ttsEnabled) return;
        const cleanText = cleanCopilotSpeechText(text).slice(0, 1800);
        if (!cleanText) return;
        if (!cleanText.startsWith(state._speechSource)) {
            state._speechSource = '';
            state._speechBuffer = '';
        }
        const delta = cleanText.slice(state._speechSource.length);
        state._speechSource = cleanText;
        if (delta) state._speechBuffer += delta;
        extractCopilotSpeechChunks(finalChunk);
    }

    function speakTextFree(text) {
        beginCopilotSpeechResponse();
        queueCopilotSpeechText(text, true);
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
                parentPanel.style.width = '320px';
                parentPanel.style.height = '100vh';
                parentPanel.style.maxWidth = '';
            }
        }
    }

    function thDisableCopilotAutofill() {
        document.querySelectorAll('.th-copilot-input textarea, .th-copilot-input input').forEach((el) => {
            el.setAttribute('autocomplete', 'off');
            el.setAttribute('autocorrect', 'off');
            el.setAttribute('autocapitalize', 'off');
            el.setAttribute('spellcheck', 'false');
            el.setAttribute('name', 'th_copilot_prompt_' + Date.now());
            el.setAttribute('data-lpignore', 'true');
            el.setAttribute('data-form-type', 'other');
            if (!el.dataset.voiceOriginTracking) {
                el.dataset.voiceOriginTracking = '1';
                el.addEventListener('keydown', (event) => {
                    if (event.isTrusted) window.thFreeVoice.voiceInputPending = false;
                    if (event.key === 'Enter' && !event.shiftKey) event.preventDefault();
                });
            }
        });
    }
    </script>
    """)
    # Seed the selected server-side voice from persistent settings.
    try:
        from app.config.settings import settings as _tts_settings
        from app.voice.preferences import load_tts_preferences
        load_tts_preferences()
        _v = (
            _tts_settings.tts_kokoro_voice
            if _tts_settings.tts_provider == "kokoro"
            else _tts_settings.tts_edge_voice
        ).replace("'", "")
        ui.run_javascript(f"window.thFreeVoice = window.thFreeVoice || {{}}; window.thFreeVoice.edgeVoice = '{_v}';")
    except Exception:
        pass

    BOT_AVATAR = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0iIzE5ZDNjNSI+PHBhdGggZD0iTTEyIDJhMiAyIDAgMCAxIDIgMnYxaDFhMyAzIDAgMCAxIDMgM3YyYTMgMyAwIDAgMSAzIDN2MmEzIDMgMCAwIDEtMyAzdjNhMyAzIDAgMCAxLTMgM0g5YTMgMyAwIDAgMS0zLTN2LTNhMyAzIDAgMCAxLTMtM3YtMmEzIDMgMCAwIDEgMy0zVjhhMyAzIDAgMCAxIDMtM2gxVjRhMiAyIDAgMCAxIDItMnptLTMgN2ExLjUgMS41IDAgMSAwIDAgMyAxLjUgMS41IDAgMCAwIDAtM3ptNiAwYTEuNSAxLjUgMCAxIDAgMCAzIDEuNSAxLjUgMCAwIDAgMC0zem0tNiA2YTEgMSAwIDAgMCAwIDJoNmExIDEgMCAxIDAgMC0ySDl6Ii8+PC9zdmc+"
    USER_AVATAR = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0iIzE5ZDNjNSI+PHBhdGggZD0iTTEyIDJhNSA1IDAgMSAxIDAgMTAgNSA1IDAgMCAxIDAtMTB6bTAgMTJjNS4zMyAwIDggMi42NyA4IDR2Mkg0di0yYzAtMS4zMyAyLjY3LTQgOC00eiIvPjwvc3ZnPg=="

    tts_active = {"enabled": True}
    chat_container_ref = {"el": None}
    input_field_ref = {"el": None}
    session_select_ref = {"el": None}
    busy_state = {"chat": False, "label": ""}
    busy_banner_ref = {"el": None, "label": None, "detail": None}
    approval_container_ref = {"el": None}
    approval_watch = {"ids": ()}
    completed_container_ref = {"el": None}
    completed_watch = {"state": ()}
    retry_container_ref = {"el": None}
    retry_watch = {"state": ()}
    send_btn_ref = {"el": None}
    sourcing_watch = {"seen_running": set(), "notified_ids": set()}

    # Bind to process-level history so Up/Down survives route changes
    _ensure_input_history_loaded()
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

    def begin_tts_response():
        if not tts_active["enabled"]:
            return
        ui.run_javascript('beginCopilotSpeechResponse();')

    def queue_tts_response(text: str, *, final: bool = False):
        if not tts_active["enabled"] or not text or text.startswith("Error"):
            return
        ui.run_javascript(
            f'queueCopilotSpeechText({json.dumps(text[:1800])}, {str(final).lower()});'
        )

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

    def _refresh_approval_cards():
        container = approval_container_ref["el"]
        if not container:
            return
        try:
            from app.actions.approvals import list_pending_approvals
            from app.infrastructure.auth import get_active_admin_id

            user_id = get_active_admin_id()
            pending = list_pending_approvals(user_id=user_id) if user_id else []
        except Exception:
            pending = []
        ids = tuple(item["approval_id"] for item in pending)
        if ids == approval_watch["ids"]:
            return
        approval_watch["ids"] = ids
        container.clear()
        container.set_visibility(bool(pending))
        if not pending:
            return

        with container:
            for item in pending:
                preview = item.get("preview") or {}
                approval_id = int(item["approval_id"])
                bound_session = item["session_id"]
                with ui.card().classes(
                    'w-full p-3 gap-2 bg-[#241a17] border border-red-500/60 rounded-md'
                ):
                    with ui.row().classes('w-full items-center justify-between gap-2'):
                        with ui.row().classes('items-center gap-2 min-w-0 grow'):
                            ui.icon('verified_user', size='xs', color='red-3')
                            ui.label(preview.get('title') or 'Approval required').classes(
                                'text-xs font-semibold text-red-100'
                            )
                        ui.badge('R3', color='red').classes('text-[9px]')
                    ui.label(preview.get('summary') or '').classes(
                        'text-[11px] text-slate-300 leading-tight'
                    )
                    if preview.get('pipeline_candidates') is not None:
                        ui.label(
                            f"{preview['pipeline_candidates']} pipeline enrollment(s) affected - "
                            f"undo for {preview.get('undo_window_days', 7)} days"
                        ).classes('text-[10px] text-slate-400')

                    def approve_card(aid=approval_id, sid=bound_session, p=preview):
                        from app.actions.api import approve_and_dispatch

                        result = approve_and_dispatch(aid, session_id=sid, actor_type='ui')
                        if not result.success:
                            ui.notify(result.error or 'Approval failed.', type='negative')
                        else:
                            ui.notify(
                                f"Archived {p.get('hunt_title') or 'Talent Hunt'}. Undo is available for seven days.",
                                type='positive',
                            )
                            conversation_manager.add_assistant_message(
                                f"Archived **{p.get('hunt_title') or 'Talent Hunt'}** after trusted UI approval. "
                                "The action is undoable for seven days.",
                                session_id=sid,
                            )
                            if sid == active_session_id["value"]:
                                render_history()
                            ui.timer(0.7, lambda: ui.navigate.reload(), once=True)
                        approval_watch["ids"] = ()
                        _refresh_approval_cards()

                    def cancel_card(aid=approval_id, sid=bound_session):
                        from app.actions.api import cancel_approval

                        result = cancel_approval(aid, session_id=sid)
                        ui.notify(
                            'Approval cancelled.' if result.success else (result.error or 'Cancel failed.'),
                            type='info' if result.success else 'negative',
                        )
                        approval_watch["ids"] = ()
                        _refresh_approval_cards()

                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('Cancel', on_click=cancel_card).props(
                            'flat dense no-caps'
                        ).classes('text-xs text-slate-400')
                        ui.button('Approve', icon='check', on_click=approve_card).props(
                            'dense no-caps'
                        ).classes('text-xs bg-red-600 text-white')

    def _refresh_completed_action_cards():
        container = completed_container_ref["el"]
        if not container:
            return
        try:
            from app.actions.history import list_recent_actions, serialize_action
            from app.infrastructure.db import SessionFactory

            with SessionFactory() as db:
                actions = [
                    serialize_action(item, db)
                    for item in list_recent_actions(
                        db,
                        days=7,
                        limit=1,
                        session_id=active_session_id["value"],
                    )
                ]
        except Exception:
            actions = []
        state = tuple(
            (item["id"], item["status"], item["undoable"], (item.get("target") or {}).get("url"))
            for item in actions
        )
        if state == completed_watch["state"]:
            return
        completed_watch["state"] = state
        container.clear()
        container.set_visibility(bool(actions))
        if not actions:
            return

        with container:
            with ui.row().classes('w-full items-center justify-between px-1'):
                ui.label('Recent action').classes('text-[10px] uppercase tracking-wide text-slate-500')
                ui.label('Undo for 7 days').classes('text-[10px] text-slate-600')
            for action in actions:
                target = action.get("target") or {}
                is_undone = action["status"] == "undone"
                with ui.element('div').classes(
                    'w-full p-2.5 bg-[#0e1b28] border border-[#1b3040] rounded-md'
                ):
                    with ui.row().classes('w-full items-center gap-2 no-wrap'):
                        ui.icon(
                            'undo' if is_undone else 'check_circle',
                            size='xs',
                            color='blue-grey-5' if is_undone else 'teal-4',
                        )
                        with ui.column().classes('gap-0 grow min-w-0'):
                            ui.label(action['summary']).classes(
                                'text-[11px] font-medium text-slate-200 leading-tight'
                            )
                            stamp = action['created_at'].replace('T', ' ')[:16]
                            status_label = 'Undone' if is_undone else 'Completed'
                            ui.label(f"#{action['id']} · {status_label} · {stamp}").classes(
                                'text-[9px] text-slate-500'
                            )

                        if target.get('url'):
                            def open_target(url=target['url']):
                                ui.navigate.to(url)

                            ui.button(icon='open_in_new', on_click=open_target).props(
                                'flat round dense'
                            ).classes('text-sky-400').tooltip(target.get('label') or 'Open affected record')

                        if action['undoable']:
                            def undo_card(aid=action['id']):
                                from app.actions.api import dispatch_action

                                result = dispatch_action(
                                    'actions.undo',
                                    {'action_id': aid},
                                    actor_type='ui',
                                    session_id=active_session_id["value"],
                                )
                                if result.success:
                                    ui.notify(result.data['message'], type='positive')
                                    completed_watch["state"] = ()
                                    _refresh_completed_action_cards()
                                    ui.timer(0.6, lambda: ui.navigate.reload(), once=True)
                                else:
                                    ui.notify(result.error or 'Undo failed.', type='negative')

                            ui.button(icon='undo', on_click=undo_card).props(
                                'flat round dense'
                            ).classes('text-[#19d3c5]').tooltip('Undo this action')

    def _refresh_retry_jobs():
        container = retry_container_ref["el"]
        if not container:
            return
        try:
            from app.jobs.service import list_retryable_jobs

            retryable = list_retryable_jobs(limit=1)
        except Exception:
            retryable = []
        state = tuple((item["id"], item["status"], item.get("attempt")) for item in retryable)
        if state == retry_watch["state"]:
            return
        retry_watch["state"] = state
        container.clear()
        container.set_visibility(bool(retryable))
        if not retryable:
            return
        job = retryable[0]
        with container:
            with ui.element('div').classes(
                'w-full px-2.5 py-2 bg-[#171c24] border border-amber-700/50 rounded-md'
            ):
                with ui.row().classes('w-full items-center gap-2 no-wrap'):
                    ui.icon('error_outline', size='xs').classes('text-amber-400')
                    with ui.column().classes('gap-0 grow min-w-0'):
                        ui.label(job.get('label') or 'Background job').classes(
                            'text-[11px] font-medium text-slate-200'
                        )
                        ui.label(
                            f"{job['status'].title()} - attempt {job.get('attempt') or 1}"
                        ).classes('text-[9px] text-slate-500')

                    def retry_failed_job(jid=job['id']):
                        from app.actions.api import dispatch_action

                        result = dispatch_action(
                            'jobs.retry',
                            {'job_id': jid},
                            actor_type='ui',
                            session_id=active_session_id["value"],
                        )
                        ui.notify(
                            'Retry started.' if result.success else (result.error or 'Retry failed.'),
                            type='positive' if result.success else 'negative',
                        )
                        retry_watch["state"] = ()
                        _refresh_retry_jobs()

                    ui.button(icon='refresh', on_click=retry_failed_job).props(
                        'flat round dense'
                    ).classes('text-amber-300').tooltip('Retry with the stored launch parameters')

    async def handle_send(e=None):
        args = getattr(e, "args", None) if e is not None else None
        if isinstance(args, dict) and args.get("shiftKey"):
            return
        input_el = input_field_ref["el"]
        chat_el = chat_container_ref["el"]
        if not input_el or not input_el.value.strip():
            return

        from app.hunts import sourcing_jobs
        from app.copilot.direct_actions import (
            parse_clear_and_source,
            parse_global_candidate_delete,
            parse_pending_hunt_clear_confirmation,
            run_clear_and_source,
            run_confirmed_hunt_clear,
            run_global_candidate_delete,
        )

        user_text = input_el.value.strip()
        global_delete = parse_global_candidate_delete(user_text)
        pending_hunt_clear = parse_pending_hunt_clear_confirmation(
            user_text,
            conversation_manager.get_messages(session_id=active_session_id["value"]),
        )
        direct = None if global_delete or pending_hunt_clear else parse_clear_and_source(user_text)
        low = user_text.lower()
        cancel_search = any(
            phrase in low
            for phrase in ("cancel search", "cancel sourcing", "cancel crawl", "stop search", "stop sourcing", "stop crawl")
        )
        force_new = bool(direct or global_delete or pending_hunt_clear or cancel_search)

        if busy_state["chat"] and not force_new:
            ui.notify(
                "Copilot is still answering. Wait a moment, or send a clear/cancel command.",
                type="warning",
            )
            return

        if not input_history or input_history[-1] != user_text:
            input_history.append(user_text)
            if len(input_history) > _MAX_INPUT_HISTORY:
                del input_history[:-_MAX_INPUT_HISTORY]
            _save_input_history(input_history)
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
        begin_tts_response()

        final_resp = ""
        try:
            # Deterministic path — don't rely on the LLM to call tools
            if cancel_search:
                cancelled = sourcing_jobs.cancel_all()
                final_resp = (
                    f"Cancelled **{cancelled}** active talent search."
                    if cancelled
                    else "There is no active talent search to cancel."
                )
                response_label.content = final_resp
                from app.copilot.conversation import conversation_manager as _cm
                _cm.add_user_message(user_text, active_session_id["value"])
                _cm.add_assistant_message(final_resp, active_session_id["value"])
                scroll_to_bottom()
            elif global_delete:
                final_resp = await asyncio.to_thread(
                    run_global_candidate_delete,
                    session_id=active_session_id["value"],
                    confirm=global_delete["confirm"],
                )
                refresh_candidates = "<!-- ui-refresh:candidates -->" in final_resp
                final_resp = final_resp.replace("<!-- ui-refresh:candidates -->", "").strip()
                response_label.content = final_resp
                from app.copilot.conversation import conversation_manager as _cm
                _cm.add_user_message(user_text, active_session_id["value"])
                _cm.add_assistant_message(final_resp, active_session_id["value"])
                scroll_to_bottom()
                if refresh_candidates:
                    ui.timer(0.8, lambda: ui.navigate.reload(), once=True)
            elif pending_hunt_clear:
                final_resp = await asyncio.to_thread(
                    run_confirmed_hunt_clear,
                    session_id=active_session_id["value"],
                    **pending_hunt_clear,
                )
                response_label.content = final_resp
                from app.copilot.conversation import conversation_manager as _cm
                _cm.add_user_message(user_text, active_session_id["value"])
                _cm.add_assistant_message(final_resp, active_session_id["value"])
                scroll_to_bottom()
            elif direct:
                final_resp = await asyncio.to_thread(
                    run_clear_and_source,
                    session_id=active_session_id["value"],
                    target=direct["target"],
                    clear=direct["clear"],
                    platforms=direct.get("platforms"),
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
                        queue_tts_response(accum_text)
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

        if final_resp:
            queue_tts_response(final_resp, final=True)
        render_history()

    def handle_up(e):
        if not input_history or not input_field_ref["el"]:
            return
        if history_state["history_index"] == -1 and (input_field_ref["el"].value or "").strip():
            return
        try:
            # Stop the cursor from jumping to start of the Quasar input
            ui.run_javascript(
                'const el=document.querySelector(".th-copilot-input textarea, .th-copilot-input input");'
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

    def open_action_history():
        from app.actions.history import list_recent_actions, serialize_action
        from app.actions.api import dispatch_action
        from app.infrastructure.db import SessionFactory

        with SessionFactory() as db:
            actions = [serialize_action(item, db) for item in list_recent_actions(db, days=7)]

        with ui.dialog() as action_dialog, ui.card().classes(
            'w-full max-w-lg p-4 th-card border border-teal-500/30 gap-3'
        ):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label('Action history').classes('text-base font-bold text-slate-100')
                ui.button(icon='close', on_click=action_dialog.close).props('flat round dense').classes('text-slate-400')
            ui.label('Last 7 days').classes('text-[11px] text-slate-500')
            if not actions:
                ui.label('No recorded actions yet.').classes('text-sm text-slate-400 py-4')
            with ui.column().classes('w-full gap-2 max-h-96 overflow-y-auto'):
                for action in actions:
                    with ui.row().classes('w-full items-center gap-2').style(
                        'padding:9px;border:1px solid #1b3040;border-radius:7px;background:#0e1b28'
                    ):
                        with ui.column().classes('gap-0 grow min-w-0'):
                            ui.label(action['summary']).classes('text-xs text-slate-200')
                            stamp = action['created_at'].replace('T', ' ')[:16]
                            ui.label(f"#{action['id']} · {stamp} · {action['status']}").classes('text-[10px] text-slate-500')
                        if action['undoable']:
                            def _undo(aid=action['id']):
                                result = dispatch_action(
                                    'actions.undo',
                                    {'action_id': aid},
                                    actor_type='ui',
                                    session_id=active_session_id["value"],
                                )
                                if result.success:
                                    ui.notify(result.data['message'], type='positive')
                                    action_dialog.close()
                                    completed_watch["state"] = ()
                                    _refresh_completed_action_cards()
                                    ui.timer(0.6, lambda: ui.navigate.reload(), once=True)
                                else:
                                    ui.notify(result.error or 'Undo failed.', type='negative')

                            ui.button(icon='undo', on_click=_undo).props('flat round dense').classes(
                                'text-[#19d3c5]'
                            ).tooltip('Undo this action')
        action_dialog.open()

    with ui.element('div').classes('th-copilot-inner'):
        with ui.element('div').style(
            'display:flex;align-items:center;justify-content:space-between;'
            'width:100%;margin-bottom:12px;flex-shrink:0;height:auto'
        ):
            ui.label('Copilot').style('font-weight:700;color:#edf5f7;font-size:13px;white-space:nowrap')
            with ui.element('div').style('display:flex;align-items:center;gap:2px;flex-shrink:0'):
                ui.button(
                    icon='manage_history',
                    on_click=open_action_history,
                ).props('flat round dense').classes('text-[#19d3c5]').tooltip('Action history and undo')

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
                tts_btn.on('pointerdown', js_handler='() => unlockCopilotAudio()')

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
            completed_watch["state"] = ()
            _refresh_completed_action_cards()

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

        approval_container_ref["el"] = ui.column().classes('w-full gap-2 mb-1 shrink-0')
        approval_container_ref["el"].set_visibility(False)
        _refresh_approval_cards()
        ui.timer(1.0, _refresh_approval_cards)

        completed_container_ref["el"] = ui.column().classes('w-full gap-2 mb-1 shrink-0')
        completed_container_ref["el"].set_visibility(False)
        _refresh_completed_action_cards()
        ui.timer(1.5, _refresh_completed_action_cards)

        retry_container_ref["el"] = ui.column().classes('w-full gap-1 mb-1 shrink-0')
        retry_container_ref["el"].set_visibility(False)
        _refresh_retry_jobs()
        ui.timer(2.0, _refresh_retry_jobs)

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

            # Track running → finished so we can show duration in chat + toast
            running_ids = {j["id"] for j in jobs}
            for jid in running_ids:
                sourcing_watch["seen_running"].add(jid)
            finished = sourcing_jobs.list_recently_finished(since_sec=180.0)
            for job in finished:
                jid = job.get("id")
                if not jid or jid in sourcing_watch["notified_ids"]:
                    continue
                if jid not in sourcing_watch["seen_running"] and not job.get("notified"):
                    # Job finished before this panel saw it running — still notify once
                    pass
                if job.get("notified"):
                    sourcing_watch["notified_ids"].add(jid)
                    continue
                sourcing_watch["notified_ids"].add(jid)
                sourcing_jobs.mark_notified(jid)
                elapsed = job.get("elapsed_label") or sourcing_jobs.format_duration(
                    job.get("elapsed_sec")
                )
                status = job.get("status") or "done"
                added = job.get("added", 0)
                scanned = job.get("scanned", 0)
                title = job.get("hunt_title") or job.get("label") or "Talent search"
                if status == "cancelled":
                    summary = (
                        f"**Talent search cancelled** for **{title}** "
                        f"after **{elapsed}** - found {added} for review, scanned {scanned}."
                    )
                    notify_type = "warning"
                elif status in {"error", "interrupted"}:
                    summary = (
                        f"**Talent search {'interrupted' if status == 'interrupted' else 'failed'}** "
                        f"for **{title}** "
                        f"after **{elapsed}**. {job.get('message') or ''}"
                    )
                    notify_type = "warning" if status == "interrupted" else "negative"
                else:
                    summary = (
                        f"**Talent search complete** for **{title}** in **{elapsed}** — "
                        f"found {added} for review, scanned {scanned}. "
                        f"{job.get('message') or ''} "
                        f"Open **Discoveries** to approve or reject them."
                    )
                    notify_type = "warning" if job.get("timed_out") or job.get("session_issue") else "positive"
                try:
                    conversation_manager.add_assistant_message(
                        summary, session_id=active_session_id["value"]
                    )
                    render_history()
                except Exception:
                    pass
                ui.notify(
                    f"Search finished in {elapsed} · found {added}",
                    type=notify_type,
                )

            if jobs:
                banner.set_visibility(True)
                job = jobs[0]
                title = job.get("label") or "Talent search"
                elapsed = job.get("elapsed_label") or ""
                detail = (
                    f"{job.get('message') or ''} · "
                    f"found {job.get('added', 0)} · scanned {job.get('scanned', 0)}"
                    f"{(' · ' + elapsed) if elapsed else ''}"
                )
                if busy_banner_ref["label"]:
                    busy_banner_ref["label"].set_text(title)
                if busy_banner_ref["detail"]:
                    busy_banner_ref["detail"].set_text(detail)
            else:
                banner.set_visibility(False)
            if send_btn_ref["el"]:
                if busy_state["chat"]:
                    send_btn_ref["el"].props("disable")
                else:
                    send_btn_ref["el"].props(remove="disable")

        def _cancel_busy():
            from app.hunts import sourcing_jobs
            n = sourcing_jobs.cancel_all()
            ui.notify(
                f"Cancel requested for {n} job(s)." if n else "No active crawl to cancel.",
                type="info",
            )
            _refresh_busy_banner()

        with ui.element('div').classes('w-full mb-1').style(
            'flex-direction:column;gap:2px;padding:5px 7px;'
            'background:#3d2a0f;border:1px solid #f0a020;'
            'border-radius:7px;flex-shrink:0'
        ) as busy_banner:
            busy_banner_ref["el"] = busy_banner
            busy_banner.set_visibility(False)
            with ui.row().classes('w-full items-center justify-between gap-2'):
                with ui.row().classes('items-center gap-1 grow min-w-0'):
                    ui.spinner(size='xs', color='orange')
                    with ui.column().classes('gap-0 grow'):
                        busy_banner_ref["label"] = ui.label('Working…').classes(
                            'text-[10px] font-semibold text-orange-200'
                        )
                        busy_banner_ref["detail"] = ui.label('').classes(
                            'text-[9px] text-orange-100/70 leading-tight'
                        )
                ui.button(icon='stop', on_click=_cancel_busy).props(
                    'flat round dense size=xs'
                ).classes('text-orange-100').tooltip('Cancel active search')

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

        with ui.element('div').classes('th-copilot-composer'):
            input_field_ref["el"] = ui.textarea(placeholder='Ask Copilot…').classes(
                'grow text-[#dce7eb] bg-transparent border-none th-copilot-input'
            ).props(
                'borderless dark autogrow rows=2 autocomplete=off autocorrect=off autocapitalize=off spellcheck=false'
            ).style(
                'font-size:14px;line-height:1.4'
            )

            input_field_ref["el"].on('keydown', handle_input_keydown)
            input_field_ref["el"].on('pointerdown', js_handler='() => unlockCopilotAudio()')
            input_field_ref["el"].on('keydown.enter', handle_send)
            ui.timer(0.2, lambda: ui.run_javascript('thDisableCopilotAutofill();'), once=True)

            def open_prompt_history():
                if not input_history:
                    ui.notify(
                        "No saved prompts yet. Send a few messages — they appear here and via ↑↓ keys.",
                        type="info",
                    )
                    return
                with ui.dialog() as hist_dlg, ui.card().classes(
                    'w-full max-w-md p-4 th-card border border-teal-500/30 gap-2'
                ):
                    ui.label('Recent prompts').classes('text-sm font-bold text-slate-100')
                    ui.label('Click to reuse · also use ↑ / ↓ in the input').classes(
                        'text-[11px] text-slate-500 mb-1'
                    )
                    with ui.column().classes('w-full gap-1 max-h-80 overflow-y-auto'):
                        # Newest first
                        for text in reversed(input_history[-40:]):
                            preview = text if len(text) <= 120 else text[:117] + "…"

                            def _pick(t=text):
                                if input_field_ref["el"]:
                                    input_field_ref["el"].value = t
                                    input_field_ref["el"].update()
                                hist_dlg.close()

                            ui.button(preview, on_click=_pick).props(
                                'flat dense no-caps align=left'
                            ).classes(
                                'w-full text-left text-xs text-slate-300 hover:bg-slate-800/80'
                            ).style(
                                'justify-content:flex-start;white-space:normal;height:auto;'
                                'min-height:32px;padding:6px 8px'
                            )
                    ui.button('Close', on_click=hist_dlg.close).props('flat').classes(
                        'text-slate-400 text-xs self-end'
                    )
                hist_dlg.open()

            ui.button(
                icon='history',
                on_click=open_prompt_history,
            ).props('flat round dense').classes(
                'th-copilot-composer-tool text-[#8195a5] hover:text-[#19d3c5]'
            ).tooltip(f'Prompt history ({len(input_history)}) · ↑↓ keys')

            ui.button(
                icon='mic',
                on_click=lambda: ui.run_javascript('toggleFreeVoiceRecording();')
            ).props('flat round dense').classes('th-copilot-composer-tool text-[#8195a5] hover:text-[#19d3c5]').tooltip('Voice input').on(
                'pointerdown', js_handler='() => unlockCopilotAudio()'
            )

            send_btn_ref["el"] = ui.button(
                icon='arrow_upward',
                on_click=handle_send
            ).props('round dense').classes('th-copilot-send').style(
                'background:#10a99f;color:#071019'
            )
            send_btn_ref["el"].on('pointerdown', js_handler='() => unlockCopilotAudio()')

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
