"""Atlas phone agent — the owner dashboard.

A small aiohttp application served by the bridge process on a SEPARATE local
port. It shows the owner what their phone line did and lets them change how it
answers, through the same fail-closed validation the boot path uses: a bad edit
is refused with the reason and nothing changes.

Security model (do not weaken):
  * bound to 127.0.0.1 and published to the owner over a TAILNET-ONLY
    `tailscale serve` mapping — never on the public path Twilio uses;
  * the session cookie holds a random id, never an access code, and is
    `HttpOnly; Secure; SameSite=Strict` — which means the dashboard must be
    reached over the https address `tailscale serve` publishes. A plain-http
    visit straight to the loopback port cannot hold a session, by design;
  * every mutating form carries a per-session CSRF token AND the request's
    `Origin` must match;
  * every response carries `no-store`, `nosniff`, `no-referrer` and a
    Content-Security-Policy with no inline scripts, no inline styles and no
    third-party origin except the font stylesheet the reseller's branding asks
    for.

Nothing here reaches into the service: everything it reads is passed in as a
callable, so the dashboard always sees the config that is in force right now.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import os

from aiohttp import web

from . import auth as auth_module
from . import render, views_brain, views_calls, views_messages, views_overview

log = logging.getLogger("atlas-phone")

COOKIE = auth_module.COOKIE

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; frame-ancestors 'none'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com"
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
}
# The bundled assets. Read once at startup so a missing file is a loud failure
# then, and so no page load costs a disk read on the loop that carries calls.
BUNDLED = {
    "/static/app.css": ("app.css", "text/css"),
    "/static/app.js": ("app.js", "application/javascript"),
    "/static/htmx.min.js": ("htmx.min.js", "application/javascript"),
}


def _load_bundled() -> tuple:
    """(assets, version). The version is a digest of what was loaded, so an
    upgraded dashboard can never be drawn with the browser's cached copy of the
    previous build's stylesheet."""
    loaded, digest = {}, hashlib.sha256()
    for url, (name, content_type) in sorted(BUNDLED.items()):
        path = os.path.join(render.STATIC, name)
        with open(path, "rb") as f:
            body = f.read()
        loaded[url] = (body, content_type)
        digest.update(body)
    return loaded, digest.hexdigest()[:8]


@web.middleware
async def _security_headers(request: web.Request, handler):
    """Every answer this app gives, including the redirects and the errors."""
    try:
        response = await handler(request)
    except web.HTTPException as redirect_or_error:
        response = redirect_or_error
    response.headers.update(SECURITY_HEADERS)
    if request.path.startswith("/static/"):
        # Assets carry no owner data and are revalidated by the browser.
        response.headers.setdefault("Cache-Control", "private, max-age=300")
    else:
        response.headers["Cache-Control"] = "no-store"
    if isinstance(response, web.HTTPException):
        raise response
    return response


@web.middleware
async def _loud_failures(request: web.Request, handler):
    """An unexpected failure becomes a page that says so, not a blank 500.

    The owner still sees something is wrong AND what — and the traceback is in
    the journal. A dashboard that answers a bare "500 Internal Server Error"
    tells the person paying for it nothing at all.
    """
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as e:
        log.exception("dashboard: %s %s failed", request.method, request.path)
        deps = request.app[render.DEPS]
        return await render.page(
            request, deps, "refused.html", status=500,
            reason=f"Something went wrong on this page: {type(e).__name__}: {e}. "
                   "It has been written to the service log.")


def build_admin_app(*, get_state, get_brains, get_branding, get_owners,
                    get_health, get_brain_health, apply_config_text,
                    emit_business_toml, acknowledge_delivery_failure,
                    store) -> web.Application:
    """The owner dashboard, wired to one running bridge.

    `get_health` is the service's `health_snapshot()`: it answers
    `(picture, model_ok)` from the cache a background task keeps warm. Nothing
    on a request path probes a model.
    """
    if store is None:
        raise RuntimeError(
            "the owner dashboard needs the call store — it reads every call, "
            "message and sign-in from it")
    assets, asset_version = _load_bundled()
    deps = render.Deps(
        auth=auth_module.Auth(store=store, get_owners=get_owners,
                              get_state=get_state),
        env=render.make_env(), store=store, get_state=get_state,
        get_brains=get_brains, get_branding=get_branding, get_owners=get_owners,
        get_health=get_health, get_brain_health=get_brain_health,
        apply_config_text=apply_config_text,
        emit_business_toml=emit_business_toml,
        acknowledge_delivery_failure=acknowledge_delivery_failure,
        asset_version=asset_version,
    )

    # ------------------------------------------------------- sign in/out --

    async def sign_in_page(request: web.Request) -> web.Response:
        if deps.auth.session_for(request) is not None:
            raise web.HTTPFound("/")
        return await render.page(request, deps, "sign_in.html", error="", locked=0)

    async def sign_in(request: web.Request) -> web.Response:
        form = await request.post()
        ip = deps.auth.client_ip(request)
        locked = deps.auth.lock_remaining(ip)
        if locked:
            return await _locked_out(request, locked)
        owner = await asyncio.to_thread(deps.auth.owner_for_code,
                                        str(form.get("code", "")))
        if owner is None:
            locked = await asyncio.to_thread(deps.auth.note_failure, ip)
            if locked:
                return await _locked_out(request, locked)
            return await render.page(
                request, deps, "sign_in.html", status=401, locked=0,
                error="That access code was not recognised. Check it and try "
                      "again.")
        deps.auth.note_success(ip)
        session_id = await asyncio.to_thread(deps.auth.start_session, owner)
        log.info("dashboard: %s signed in from %s", owner.key, ip)
        try:
            store.add_event(None, None, "info", "dashboard_signin",
                            f"{owner.key} signed in from {ip}")
        except Exception:
            log.exception("call store: could not record the sign-in")
        response = web.HTTPSeeOther("/")
        deps.auth.set_cookie(response, session_id)
        return response

    async def _locked_out(request: web.Request, seconds: int) -> web.Response:
        response = await render.page(
            request, deps, "sign_in.html", status=429, locked=seconds,
            error=f"Too many wrong access codes. Try again in {seconds} "
                  f"second{'' if seconds == 1 else 's'}.")
        response.headers["Retry-After"] = str(seconds)
        return response

    async def sign_out(request: web.Request) -> web.Response:
        session = deps.auth.require(request)
        form = await request.post()
        reason = deps.auth.check_csrf(request, session, form)
        if reason:
            return await render.page(request, deps, "refused.html", session=session,
                               status=403, reason=reason)
        await asyncio.to_thread(store.delete_session, session.id)
        response = web.HTTPSeeOther(auth_module.SIGN_IN_PATH)
        deps.auth.clear_cookie(response)
        return response

    async def sign_out_all(request: web.Request) -> web.Response:
        session = deps.auth.require(request)
        form = await request.post()
        reason = deps.auth.check_csrf(request, session, form)
        if reason:
            return await render.page(request, deps, "refused.html", session=session,
                               status=403, reason=reason)
        gone = await asyncio.to_thread(store.delete_owner_sessions,
                                       session.owner_key)
        log.info("dashboard: %s signed out of %d device(s)",
                 session.owner_key, gone)
        response = web.HTTPSeeOther(auth_module.SIGN_IN_PATH)
        deps.auth.clear_cookie(response)
        return response

    # -------------------------------------------------------------- assets --

    async def asset(request: web.Request) -> web.Response:
        body, content_type = assets[request.path]
        return web.Response(body=body, content_type=content_type)

    # The three branded assets are generated from the live config, so they are
    # revalidated on every page rather than held for five minutes: an owner who
    # changes their colours or logo must see it immediately.
    def _branded(text: str, content_type: str) -> web.Response:
        return web.Response(text=text, content_type=content_type,
                            headers={"Cache-Control": "no-cache"})

    async def brand_css(request: web.Request) -> web.Response:
        return _branded(render.brand_css(get_branding()), "text/css")

    async def icon(request: web.Request) -> web.Response:
        return _branded(render.icon_svg(get_branding()), "image/svg+xml")

    async def logo(request: web.Request) -> web.Response:
        path = os.path.expanduser(str(get_branding().logo_path).strip())
        if not path:
            raise web.HTTPNotFound(text="no logo is configured for this line")
        try:
            body = await asyncio.to_thread(_read_file, path)
        except OSError as e:
            # Loud: a customer-facing page missing its logo is exactly the kind
            # of small broken detail that reads as "nobody is looking after
            # this".
            log.warning("[branding] could not read logo_path %s (%s) — the "
                        "dashboard is showing the product name instead",
                        path, e)
            raise web.HTTPNotFound(text="the configured logo could not be read")
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return web.Response(body=body, content_type=content_type,
                            headers={"Cache-Control": "no-cache"})

    app = web.Application(middlewares=[_security_headers, _loud_failures])
    app[render.DEPS] = deps
    # One slot per session for the receipt a redirect has to carry across (see
    # render.set_flash). Emptied by whoever reads it.
    app[render.FLASH] = {}
    app.router.add_get("/", views_overview.overview)
    app.router.add_get("/overview/status", views_overview.status_band)
    app.router.add_get("/health/detail", views_overview.health_detail)
    app.router.add_post("/acknowledge-delivery",
                        views_overview.acknowledge_delivery)
    app.router.add_get("/calls", views_calls.calls)
    app.router.add_get("/calls/{sid}", views_calls.call_detail)
    app.router.add_post("/callers/delete", views_calls.delete_caller)
    app.router.add_post("/calls/{sid}/note", views_calls.add_note)
    app.router.add_post("/calls/{sid}/handled", views_calls.mark_handled)
    app.router.add_get("/messages", views_messages.messages)
    app.router.add_get("/messages.csv", views_messages.messages_csv)
    app.router.add_post("/messages/{id}/status", views_messages.message_status)
    app.router.add_get("/brain", views_brain.brain)
    app.router.add_post("/brain", views_brain.switch_brain)
    app.router.add_get(auth_module.SIGN_IN_PATH, sign_in_page)
    app.router.add_post(auth_module.SIGN_IN_PATH, sign_in)
    app.router.add_post("/sign-out", sign_out)
    app.router.add_post("/sign-out-all", sign_out_all)
    for url in BUNDLED:
        app.router.add_get(url, asset)
    app.router.add_get("/static/brand.css", brand_css)
    app.router.add_get("/static/icon.svg", icon)
    app.router.add_get("/static/logo", logo)
    # Browsers ask for this whether or not the page links an icon; answering it
    # keeps a 404 out of the console of a page a customer is looking at.
    app.router.add_get("/favicon.ico", icon)
    _check_nav(app)
    return app


def _read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _check_nav(app: web.Application) -> None:
    """No navigation item may point at a route this build does not serve.

    The screens land task by task; this makes "the nav grew a link into a 404"
    a startup failure instead of something an owner discovers by clicking.
    """
    urls = {getattr(route.resource, "canonical", None)
            for route in app.router.routes()}
    for item in render.NAV:
        for entry in (item,) + tuple(item.children):
            if entry.url is not None and entry.url not in urls:
                raise RuntimeError(
                    f"dashboard navigation points at {entry.url!r}, which this "
                    "build does not serve")
