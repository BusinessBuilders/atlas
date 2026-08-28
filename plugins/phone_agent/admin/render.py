"""Templates, filters, and the reseller's brand as CSS.

Nothing in `templates/` names a colour, a font or a company. Everything the
dashboard looks like comes from `[branding]` in businesses.toml, served as a
tiny stylesheet of custom properties that `app.css` reads. An install with no
`[branding]` table gets the neutral dark palette below and the system font
stack — never this vendor's colours baked into the product.
"""
from __future__ import annotations

import html
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import jinja2
from aiohttp import web

log = logging.getLogger("atlas-phone")

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# The product's own look when nobody has branded it. Deliberately neutral: a
# reseller's palette is a setting, not a value compiled into this file.
#
# Measured against WCAG 2.2 AA on these surfaces: body text 15.4:1, secondary
# 9.3:1, hint 7.7:1, control borders 5.9:1, the focus ring 4.7:1 on a card, and
# the primary button's label 5.1:1 on the accent. The accent is a step lighter
# than the plan's #2563eb, which put that label at 3.66:1 — under the 4.5:1
# small text needs.
DEFAULT_COLORS = {
    "bg": "#0f1115",
    "bg_elevated": "#171a21",
    "fg": "#e8e8e8",
    "fg_muted": "#a6adb8",
    "accent": "#3b82f6",
    "accent_2": "#0e9f8a",
    "danger": "#dc2626",
    "warn": "#d97706",
    "ok": "#16a34a",
}
DEFAULT_FONTS = {
    "body": "",        # empty = the system stack in app.css
    "display": "",
    "wordmark": "",
}
SYSTEM_STACK = ("system-ui, -apple-system, 'Segoe UI', Roboto, "
                "'Helvetica Neue', Arial, sans-serif")

# A colour must be a colour. These values come from a config file the owner
# edits, and they are written into a stylesheet we serve: anything that is not
# plainly a colour is refused and the default used, loudly.
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3,8}$|^[a-zA-Z]{3,20}$")
# A font family name: letters, digits, spaces and hyphens. Quoted in the CSS.
_FONT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 -]{0,48}$")

GOOGLE_FONTS_BASE = "https://fonts.googleapis.com/css2"


def _colors(branding) -> dict:
    """The brand palette, defaults filled in and every value checked."""
    chosen = dict(DEFAULT_COLORS)
    configured = dict(getattr(branding, "colors", {}) or {})
    # A brand that names a gold but no warning colour means the gold IS the
    # warning colour — that is what it is used for on the boards.
    if "warn" not in configured and "gold" in configured:
        configured["warn"] = configured["gold"]
    for name, value in configured.items():
        text = str(value).strip()
        if not _COLOR_RE.match(text):
            log.warning("[branding] colors.%s = %r is not a colour the "
                        "dashboard can use — showing the default instead",
                        name, value)
            continue
        chosen[str(name)] = text
    return chosen


def _fonts(branding) -> dict:
    """The brand's font families, checked. Empty means the system stack."""
    chosen = dict(DEFAULT_FONTS)
    for name, value in dict(getattr(branding, "fonts", {}) or {}).items():
        text = str(value).strip()
        if not _FONT_RE.match(text):
            log.warning("[branding] fonts.%s = %r is not a font family name "
                        "the dashboard can use — showing the system font "
                        "instead", name, value)
            continue
        chosen[str(name)] = text
    return chosen


def google_fonts_url(branding) -> str:
    """The one stylesheet the page may load from off this machine, or "".

    Only families named in `[branding] fonts` are asked for, which is what the
    page's Content-Security-Policy allows: no font a reseller has not chosen,
    and no other third-party request of any kind.
    """
    families = sorted({name for key, name in _fonts(branding).items() if name})
    if not families:
        return ""
    query = "&".join(f"family={f.replace(' ', '+')}:wght@400;600;700"
                     for f in families)
    return f"{GOOGLE_FONTS_BASE}?{query}&display=swap"


def brand_css(branding) -> str:
    """`[branding]` as CSS custom properties — the whole design system's inputs."""
    colors = _colors(branding)
    fonts = _fonts(branding)
    lines = [
        "/* Generated from [branding] in businesses.toml. Edit the config, not",
        "   this: the dashboard rebuilds it on every request. */",
        ":root {",
    ]
    for name in sorted(colors):
        lines.append(f"  --brand-{name.replace('_', '-')}: {colors[name]};")
    for role in ("body", "display", "wordmark"):
        family = fonts.get(role, "")
        stack = f"'{family}', {SYSTEM_STACK}" if family else SYSTEM_STACK
        lines.append(f"  --font-{role}: {stack};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def icon_svg(branding) -> str:
    """The browser-tab mark: the vendor's initial on the brand accent.

    Generated rather than shipped, because the product has no logo of its own
    and a reseller's `logo_path` is a wordmark, not a square. A tab with a
    broken-image icon is the kind of small unfinished detail a customer reads
    as "nobody is looking after this".
    """
    colors = _colors(branding)
    initial = (str(branding.vendor_name).strip() or "?")[0].upper()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        f'<rect width="64" height="64" rx="14" fill="{colors["accent"]}"/>'
        f'<text x="32" y="45" text-anchor="middle" fill="{colors["bg"]}" '
        'font-family="system-ui, sans-serif" font-size="38" '
        f'font-weight="700">{html.escape(initial)}</text></svg>'
    )


# ----------------------------------------------------------------- filters --

def fmt_phone(number) -> str:
    """A phone number the way the owner reads it out loud.

    North American numbers become (508) 886-3046; anything else is left in the
    international form it arrived in, which is still dialable.
    """
    text = str(number or "").strip()
    if not text:
        return "no number"
    digits = re.sub(r"\D", "", text)
    if text.startswith("+1") and len(digits) == 11:
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    if not text.startswith("+") and len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:]}"
    return text


def fmt_duration(seconds) -> str:
    """How long a call lasted, as minutes and seconds."""
    if seconds is None:
        return "not recorded"
    total = int(round(float(seconds)))
    return f"{total // 60}:{total % 60:02d}"


def fmt_local(ts) -> str:
    """A moment in the owner's own words: today, yesterday, or the date."""
    if ts is None:
        return "unknown"
    moment = datetime.fromtimestamp(float(ts)).astimezone()
    today = datetime.now().astimezone().date()
    if moment.date() == today:
        return moment.strftime("%-I:%M %p today")
    if moment.date() == today - timedelta(days=1):
        return moment.strftime("Yesterday %-I:%M %p")
    return moment.strftime("%b %-d, %-I:%M %p")


def fmt_ago(ts, *, now=None) -> str:
    """How long ago something happened, in one phrase."""
    if ts is None:
        return "never"
    seconds = (time.time() if now is None else float(now)) - float(ts)
    if seconds < 0:
        seconds = 0
    if seconds < 90:
        count, unit = int(seconds), "second"
    elif seconds < 5400:
        count, unit = int(seconds // 60), "minute"
    elif seconds < 172800:
        count, unit = int(seconds // 3600), "hour"
    else:
        count, unit = int(seconds // 86400), "day"
    return f"{count} {unit}{'' if count == 1 else 's'} ago"


@dataclass(frozen=True)
class NavItem:
    """One row in the navigation.

    `url` is None for a group heading, so a screen that has not been built yet
    is simply absent — the owner never clicks a link into nothing.
    """
    label: str
    icon: str
    url: str | None
    whole_line_only: bool = False
    children: tuple = ()


# Only screens that exist are listed. Calls, Messages, Hours, Numbers,
# Notifications and Activity join this list in the tasks that build them.
NAV = (
    NavItem("Overview", "grid", "/"),
    NavItem("Settings", "sliders", None, children=(
        NavItem("Brain", "cpu", "/brain", whole_line_only=True),
    )),
)


def nav_for(session) -> list:
    """The navigation this owner can actually use.

    An owner of one business is not shown the line-wide controls: the model
    that answers is shared by every business on the line, so it is not theirs
    to change.
    """
    visible = []
    for item in NAV:
        if item.whole_line_only and not session.sees_whole_line:
            continue
        children = tuple(c for c in item.children
                         if not (c.whole_line_only and not session.sees_whole_line))
        if item.url is None and not children:
            continue
        visible.append(NavItem(item.label, item.icon, item.url,
                               item.whole_line_only, children))
    return visible


@dataclass(frozen=True)
class Deps:
    """Everything the dashboard reads the live service through.

    Callables, not snapshots: a config save (or a brain switch) replaces the
    service's state, and a dashboard holding copies from boot would show the
    owner settings that are no longer in force.
    """
    auth: object
    env: jinja2.Environment
    store: object
    get_state: object
    get_brains: object
    get_branding: object
    get_owners: object
    get_health: object
    get_brain_health: object
    apply_config_text: object
    emit_business_toml: object
    acknowledge_delivery_failure: object
    # Stamped into every asset URL so an upgraded dashboard is never rendered
    # with the browser's copy of the previous build's stylesheet.
    asset_version: str = ""


# The one key the app stores on itself, typed so aiohttp can check it.
DEPS = web.AppKey("deps", Deps)


def base_context(request, deps: Deps, session=None) -> dict:
    branding = deps.get_branding()
    return {
        "vendor_name": branding.vendor_name,
        "product_name": branding.product_name,
        "support_email": branding.support_email,
        "has_logo": bool(str(branding.logo_path).strip()),
        "fonts_url": google_fonts_url(branding),
        "asset_version": deps.asset_version,
        "session": session,
        "nav": nav_for(session) if session is not None else [],
        "csrf": deps.auth.csrf_token(session) if session is not None else "",
        "path": request.path,
    }


def page(request, deps: Deps, template: str, *, session=None, status: int = 200,
         **context):
    """Render one whole page. The security headers are added by the app's
    middleware, so nothing here can forget them."""
    body = deps.env.get_template(template).render(
        **base_context(request, deps, session), **context)
    return web.Response(text=body, status=status, content_type="text/html")


def partial(request, deps: Deps, template: str, *, session=None, **context):
    """Render one panel, for the pieces htmx swaps in place."""
    body = deps.env.get_template(template).render(
        **base_context(request, deps, session), **context)
    return web.Response(text=body, content_type="text/html")


def make_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES),
        autoescape=jinja2.select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=jinja2.StrictUndefined,   # a missing value is a loud error
    )
    env.filters.update(fmt_phone=fmt_phone, fmt_duration=fmt_duration,
                       fmt_local=fmt_local, fmt_ago=fmt_ago)
    return env
