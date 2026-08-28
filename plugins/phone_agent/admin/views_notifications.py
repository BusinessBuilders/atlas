"""Where a message goes the moment a caller leaves one — and proof that it does.

Push was an environment variable the old dashboard reported as the word "on".
An owner could not see where their messages went, could not change it, and
found out the push had been failing for a week by noticing that no messages had
arrived. This screen answers all three:

  * the push target for this business, with the line's own default filled in
    and labelled as the default rather than silently inherited;
  * **Send test**, which really sends — same address, same request, same
    ten-second timeout, same `notify_log` row as a caller's message — and shows
    what actually came back, including the failure;
  * the last twenty attempts, successes included, because "when did it stop
    working" is the question that matters at two in the morning.
"""
from __future__ import annotations

import asyncio
import logging
import time

from aiohttp import web

from . import config_edit as edit
from . import render

log = logging.getLogger("atlas-phone")

# The name this attempt is written down under, so a test is never mistaken for
# a caller's message in the delivery log.
TEST_TARGET = "ntfy_test"
LOG_ROWS = 20


def _targets(deps, profile: dict, *, whole_line: bool) -> dict:
    """Where this business's messages go, and whether it chose that itself.

    The address a message actually lands on (`live_url`/`live_topic`) is put in
    front of an owner only when it is theirs: either they see the whole line,
    or this business has an address of its own. On a shared line two businesses
    can both fall back to the line's own address, and naming it to the owner of
    one hands them the subscription to their neighbours' messages — the same
    leak the rest of these screens are scoped to prevent. They cannot change
    the line's default anyway; the fix is to give each business its own topic.
    """
    own_url = str(edit.setting(deps, profile, "ntfy_url")).strip()
    own_topic = str(edit.setting(deps, profile, "ntfy_topic")).strip()
    resolved = deps.delivery_targets(profile)
    using_default = not (own_url and own_topic)
    show_live = whole_line or not using_default
    return {
        "url": own_url, "topic": own_topic,
        "using_default": using_default,
        "live_url": str(resolved.ntfy_url or "") if show_live else "",
        "live_topic": str(resolved.ntfy_topic or "") if show_live else "",
        "anywhere": bool(resolved.ntfy_url and resolved.ntfy_topic),
    }


def _target_name(targets: dict) -> str:
    """What to call the address an alert went to. An owner who is not shown the
    line's own address is not shown it in the receipt either."""
    if targets["live_url"] and targets["live_topic"]:
        return f"{targets['live_url'].rstrip('/')}/{targets['live_topic']}"
    return "the line's own alert address"


def gather(deps, session, key: str, *, values=None) -> dict:
    profile = edit.profile_of(deps, key)
    targets = _targets(deps, profile, whole_line=session.sees_whole_line)
    rows, error = render.guarded_read("your alert history",
                                      deps.store.list_notify, [key],
                                      limit=LOG_ROWS)
    return {
        "business_key": key, "business": edit.business_name(deps, key),
        "businesses": edit.businesses(deps, session),
        "targets": targets,
        "values": values if values is not None else {"ntfy_url": targets["url"],
                                                     "ntfy_topic": targets["topic"]},
        "attempts": list(rows or []), "log_error": error,
        "version": edit.version(deps),
    }


async def _no_such_business(request, deps, session) -> web.Response:
    return await render.page(
        request, deps, "refused.html", session=session, status=404,
        reason=("That business is not on your line. It may have been removed, "
                "or it belongs to somebody else."))


async def _page(request, deps, session, key: str, *, status=200, error="",
                errors=None, values=None, result=None) -> web.Response:
    if not key:
        return await render.page(
            request, deps, "refused.html", session=session, status=404,
            reason="There is no business on your line to set alerts up for yet.")
    data = await asyncio.to_thread(gather, deps, session, key, values=values)
    return await render.page(
        request, deps, "notifications.html", session=session, status=status,
        error=error, errors=dict(errors or {}), result=result,
        flash=render.pop_flash(request, session), **data)


async def notifications(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    key = edit.chosen_business(deps, session, request.query.get("business", ""))
    return await _page(request, deps, session, key)


async def _require_business(request, deps, session):
    key = request.match_info["profile"]
    if key not in set(session.profile_keys) or not edit.profile_of(deps, key):
        return "", await _no_such_business(request, deps, session)
    return key, None


async def notifications_for(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    key, refused = await _require_business(request, deps, session)
    if refused is not None:
        return refused
    return await _page(request, deps, session, key)


async def save(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    key, refused = await _require_business(request, deps, session)
    if refused is not None:
        return refused
    form = await request.post()
    reason = deps.auth.check_csrf(request, session, form)
    if reason:
        return await render.page(request, deps, "refused.html", session=session,
                                 status=403, reason=reason)
    if await asyncio.to_thread(edit.is_stale, deps, form):
        return await _page(request, deps, session, key, status=409,
                           error=edit.STALE_MESSAGE)
    values = {"ntfy_url": edit.text_of(form, "ntfy_url"),
              "ntfy_topic": edit.text_of(form, "ntfy_topic")}
    errors = _check(deps, values, edit.profile_of(deps, key), form)
    if errors:
        return await _page(request, deps, session, key, status=400,
                           values=values, errors=errors)
    updates = {"ntfy_url": values["ntfy_url"] or None,
               "ntfy_topic": values["ntfy_topic"] or None}
    error = await asyncio.to_thread(
        edit.save, deps, session,
        profiles=edit.profiles_with(deps, key, updates),
        summary=f"Changed where messages are sent for "
                f"{edit.business_name(deps, key)}")
    if error:
        return await _page(request, deps, session, key, status=400,
                           values=values, error=f"Nothing was changed. {error}")
    render.set_flash(request, session,
                     "Saved — the next message goes to this address.")
    raise web.HTTPSeeOther(f"/notifications/{key}")


def _check(deps, values: dict, profile: dict, form) -> dict:
    errors: dict = {}
    url, topic = values["ntfy_url"].rstrip("/"), values["ntfy_topic"]
    for name in ("ntfy_url", "ntfy_topic"):
        long = edit.too_long(name, values[name])
        if long:
            errors[name] = long
    if url and not url.startswith(("http://", "https://")):
        errors["ntfy_url"] = ("A push address starts with http:// or https:// "
                              "— it is the address of your ntfy server.")
    if bool(url) != bool(topic):
        missing = "ntfy_topic" if url else "ntfy_url"
        errors[missing] = ("The address and the topic are needed together — "
                           "one without the other sends your messages nowhere.")
    had = str(edit.setting(deps, profile, "ntfy_url")).strip()
    if had and not url and not edit.checked(form, "confirm_disable"):
        errors["confirm_disable"] = (
            "This business will go back to the line's own alert address. If "
            "the line has none, nobody is told when a caller leaves a message.")
    return errors


# ------------------------------------------------------------- send a test --

async def send_test(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    key, refused = await _require_business(request, deps, session)
    if refused is not None:
        return refused
    form = await request.post()
    reason = deps.auth.check_csrf(request, session, form)
    if reason:
        return await render.page(request, deps, "refused.html", session=session,
                                 status=403, reason=reason)
    profile = edit.profile_of(deps, key)
    targets = _targets(deps, profile, whole_line=session.sees_whole_line)
    name = edit.business_name(deps, key)
    if not targets["anywhere"]:
        return await _page(
            request, deps, session, key, status=400,
            error=("There is nowhere to send a test: neither this business nor "
                   "the line has a push address set up. Fill in the address "
                   "and the topic below, save, then try again."))
    stamp = time.strftime("%-I:%M %p on %A")
    # THE push — service.push_ntfy, the one a caller's message rides on. Same
    # address, same headers, same timeout, same "anything but 200 is a failure"
    # rule. The target is resolved by the service's own delivery_targets, so a
    # business with no address of its own is tested on the line's.
    sent, failure = await deps.push_ntfy(
        deps.delivery_targets(profile), title=f"{name} — test alert",
        body=f"This is a test alert from your phone line's settings screen, "
             f"sent at {stamp}. A real message from a caller arrives the same "
             f"way.")
    try:
        await asyncio.to_thread(deps.store.log_notify, key, TEST_TARGET,
                                sent, failure or None)
    except Exception:
        log.exception("call store: could not record the test alert")
    if sent:
        log.info("dashboard: %s sent a test alert for %s", session.owner_key, key)
    else:
        log.warning("dashboard: %s sent a test alert for %s and it FAILED: %s",
                    session.owner_key, key, failure)
    result = {
        "ok": sent,
        "target": _target_name(targets),
        "text": ("Sent. It should be on your phone now — if it is not, the push "
                 "server took it but your device is not subscribed to this "
                 "topic.") if sent
        else f"It did not go through: {failure}",
    }
    return await _page(request, deps, session, key,
                       status=200 if sent else 400, result=result)
