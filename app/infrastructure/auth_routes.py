"""HTTP authentication boundary and first-run recruiter login screen."""

from __future__ import annotations

import html
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.infrastructure.auth import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    authenticate,
    create_admin,
    create_session_token,
    has_admin,
    is_authenticated,
)

PUBLIC_EXACT_PATHS = {"/login", "/auth/login", "/auth/setup", "/favicon.ico"}
PUBLIC_PREFIXES = ("/intake/", "/_nicegui/")


def _safe_next(value: str | None) -> str:
    candidate = value or "/"
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    return candidate


def _is_public(path: str) -> bool:
    return path in PUBLIC_EXACT_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


class RecruiterAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if _is_public(path) or is_authenticated(request.cookies.get(SESSION_COOKIE)):
            return await call_next(request)

        if path.startswith("/api/") or path.startswith("/profile-snapshots"):
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        next_path = path
        if request.url.query:
            next_path += f"?{request.url.query}"
        return RedirectResponse(f"/login?next={quote(next_path, safe='')}", status_code=303)


def _login_html(*, setup: bool, next_path: str) -> str:
    title = "Create recruiter account" if setup else "Welcome back"
    subtitle = (
        "Set up the local administrator for this TalentHunt OS installation."
        if setup
        else "Sign in to access candidates, campaigns, and connected sourcing sessions."
    )
    endpoint = "/auth/setup" if setup else "/auth/login"
    def password_field(field_id: str, label: str, autocomplete: str) -> str:
        return (
            f'<label for="{field_id}">{label}</label><div class="password-wrap">'
            f'<input id="{field_id}" type="password" autocomplete="{autocomplete}" '
            'required minlength="12">'
            f'<button class="password-toggle" type="button" data-password-toggle="{field_id}" '
            f'aria-label="Show {label.lower()}" aria-pressed="false">SHOW</button></div>'
        )

    password_control = password_field(
        "password", "Password", "new-password" if setup else "current-password"
    )
    confirm_field = password_field("confirm", "Confirm password", "new-password") if setup else ""
    button = "Create account" if setup else "Sign in"
    safe_next = html.escape(next_path, quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | TalentHunt OS</title><style>
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#071019;color:#edf5f7;font-family:Inter,Segoe UI,sans-serif}}
main{{width:min(420px,calc(100% - 32px));padding:32px;border:1px solid #1b3947;background:#0b1823;border-radius:8px;box-shadow:0 20px 55px rgba(0,0,0,.28)}}
.brand{{font-size:15px;font-weight:800}}.brand span{{color:#19d3c5}}h1{{font-size:25px;margin:28px 0 8px;letter-spacing:0}}p{{font-size:13px;line-height:1.55;color:#91a8b7;margin:0 0 24px}}
label{{display:block;font-size:12px;font-weight:650;color:#b8cad4;margin:14px 0 7px}}input{{width:100%;height:44px;border:1px solid #294453;border-radius:6px;background:#07131d;color:#fff;padding:0 12px;outline:none}}input:focus{{border-color:#19d3c5;box-shadow:0 0 0 3px rgba(25,211,197,.12)}}
.password-wrap{{position:relative}}.password-wrap input{{padding-right:64px}}.password-toggle{{position:absolute;right:4px;top:4px;width:56px;height:36px;margin:0;padding:0;border:0;background:transparent;color:#75dcd3;font-size:10px;font-weight:800;letter-spacing:0}}.password-toggle:hover{{background:#102b35}}.password-toggle:focus-visible{{outline:2px solid #19d3c5;outline-offset:-2px}}
button{{width:100%;height:44px;margin-top:22px;border:0;border-radius:6px;background:#16a99f;color:#071019;font-weight:750;cursor:pointer}}button:hover{{background:#19bdb1}}button:disabled{{opacity:.6;cursor:wait}}
#error{{min-height:20px;margin:12px 0 0;color:#ff8d8d;font-size:12px}}.privacy{{margin-top:22px;padding-top:18px;border-top:1px solid #18303d;font-size:11px;color:#708997}}
.recovery-toggle{{width:auto;height:auto;margin:8px 0 0;padding:4px 0;background:transparent;color:#75dcd3;font-size:11px;text-align:left}}
.recovery-toggle:hover{{background:transparent;color:#9ff2eb}}.recovery{{display:none;margin-top:10px;padding:12px;border:1px solid #294453;border-radius:6px;background:#07131d;color:#91a8b7;font-size:11px;line-height:1.55}}
.recovery.visible{{display:block}}code{{display:block;margin-top:7px;padding:8px;border-radius:4px;background:#030b11;color:#d8f7f3;overflow-wrap:anywhere}}
</style></head><body><main><div class="brand">TalentHunt <span>OS</span></div><h1>{title}</h1><p>{subtitle}</p>
<form id="auth"><label for="username">Username</label><input id="username" autocomplete="username" required minlength="3">
{password_control}{confirm_field}
  <button id="submit" type="submit">{button}</button><div id="error" role="alert"></div></form>
  {'' if setup else '<button id="recovery-toggle" class="recovery-toggle" type="button" aria-expanded="false">Forgot password?</button><div id="recovery" class="recovery">From the TalentHunt OS project folder, run this local recovery command. It replaces only the administrator password and keeps all recruiter data.<code>python -m app.infrastructure.password_recovery</code></div>'}
<div class="privacy">Local-only access. Recruiter data and credentials remain on this computer.</div></main>
<script>const form=document.getElementById('auth'),button=document.getElementById('submit'),error=document.getElementById('error');
  document.querySelectorAll('[data-password-toggle]').forEach((toggle)=>{{toggle.addEventListener('click',()=>{{const input=document.getElementById(toggle.dataset.passwordToggle);const showing=input.type==='text';input.type=showing?'password':'text';toggle.textContent=showing?'SHOW':'HIDE';toggle.setAttribute('aria-label',(showing?'Show ':'Hide ')+(input.id==='confirm'?'confirm password':'password'));toggle.setAttribute('aria-pressed',String(!showing));}})}});
  const recoveryToggle=document.getElementById('recovery-toggle');if(recoveryToggle)recoveryToggle.addEventListener('click',()=>{{const recovery=document.getElementById('recovery');const open=recovery.classList.toggle('visible');recoveryToggle.setAttribute('aria-expanded',String(open));}});
form.addEventListener('submit',async(e)=>{{e.preventDefault();error.textContent='';const password=document.getElementById('password').value;
const confirm=document.getElementById('confirm');if(confirm&&password!==confirm.value){{error.textContent='Passwords do not match.';return}}
button.disabled=true;try{{const response=await fetch('{endpoint}',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{username:document.getElementById('username').value,password}})}});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Authentication failed');window.location.href='{safe_next}';}}catch(err){{error.textContent=err.message;button.disabled=false}}}});</script></body></html>"""


def register_auth(app) -> None:
    app.add_middleware(RecruiterAuthMiddleware)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        next_path = _safe_next(request.query_params.get("next"))
        if is_authenticated(request.cookies.get(SESSION_COOKIE)):
            return RedirectResponse(next_path, status_code=303)
        return HTMLResponse(_login_html(setup=not has_admin(), next_path=next_path))

    @app.post("/auth/setup")
    async def setup_admin(request: Request):
        body = await request.json()
        ok, message = create_admin(str(body.get("username", "")), str(body.get("password", "")))
        if not ok:
            return JSONResponse({"detail": message}, status_code=400)
        response = JSONResponse({"status": "success"})
        response.set_cookie(
            SESSION_COOKIE,
            create_session_token(str(body["username"]).strip()),
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            samesite="strict",
            secure=False,
        )
        return response

    @app.post("/auth/login")
    async def login(request: Request):
        body = await request.json()
        username = str(body.get("username", ""))
        if not authenticate(username, str(body.get("password", ""))):
            return JSONResponse({"detail": "Invalid username or password"}, status_code=401)
        response = JSONResponse({"status": "success"})
        response.set_cookie(
            SESSION_COOKIE,
            create_session_token(username.strip()),
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            samesite="strict",
            secure=False,
        )
        return response

    @app.get("/auth/logout")
    async def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response
