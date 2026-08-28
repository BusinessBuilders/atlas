"""The Brain screen: which model answers every call, and switching it safely.

Three safety rules, all of them learned the hard way:

  * A switch is **confirmed**, naming the model and saying it applies to the
    next call — never a radio button that changes the line on save.
  * A backend whose last check FAILED cannot be switched to unless the owner
    ticks the override. Answering with a model nobody can reach means every
    caller hears an apology.
  * The switch goes through the SAME fail-closed path as every other config
    change: the whole file is re-emitted, validated, backed up and hot-applied,
    so a switch cannot half-apply and a rejected one changes nothing.

The screen is line-wide, so it belongs to an owner of the whole line. A
business on a shared line does not get to change the model the other
businesses answer on.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging

from aiohttp import web

from . import render, status

log = logging.getLogger("atlas-phone")


def _reachability(state) -> dict:
    """One backend's last check, in the owner's words."""
    if not state or state.get("checked_at") is None:
        return {"level": "unknown", "text": "Not checked yet", "checked_at": None,
                "reachable": None}
    if state.get("reachable"):
        return {"level": "ok", "text": "Answering", "reachable": True,
                "checked_at": state["checked_at"]}
    why = str(state.get("probe_error", "")).strip()
    return {"level": "bad", "reachable": False,
            "text": f"Not answering ({why})" if why else "Not answering",
            "checked_at": state["checked_at"]}


def brain_cards(deps) -> list:
    """Every model this line can answer on, newest health first."""
    brains, active = deps.get_brains()
    health = deps.get_brain_health()
    cards = []
    for key, brain in brains.items():
        cards.append({
            "key": key,
            "label": brain.label.strip() or key,
            "model": brain.model,
            "runs": status.runs_where(brain),
            "test_only": status.is_test_only(brain),
            "active": key == active,
            "health": _reachability(health.get(key)),
        })
    cards.sort(key=lambda c: (not c["active"], c["label"].lower()))
    return cards


async def _require_whole_line(deps, request, session):
    """The Brain screen changes the model for every business on the line."""
    if session.sees_whole_line:
        return None
    return await render.page(
        request, deps, "refused.html", session=session, status=403,
        reason=("The model that answers calls is shared by every business on "
                "this line, so only the account that manages the whole line "
                "can change it."))


async def _page(request, deps, session, *, confirming=None, error="",
                switched="", already="", status_code=200):
    cards = brain_cards(deps)
    chosen = next((c for c in cards if c["key"] == confirming), None)
    # The confirmation names the model the owner recognises, not its key in the
    # config file — and resolving it against the real cards means the URL
    # cannot put words of its own on the page.
    just_switched = next((c["label"] for c in cards if c["key"] == switched), "")
    # Same resolution for "you already have that one": the message appears only
    # for a model that really exists AND is really the one answering.
    already_active = any(c["key"] == already and c["active"] for c in cards)
    return await render.page(
        request, deps, "brain.html", session=session, status=status_code,
        cards=cards, confirming=chosen, error=error, switched=just_switched,
        already=already_active, dialog_open=chosen is not None,
        active_card=next((c for c in cards if c["active"]), None))


async def brain(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    refused = await _require_whole_line(deps, request, session)
    if refused is not None:
        return refused
    return await _page(request, deps, session,
                       confirming=request.query.get("switch", "") or None,
                       switched=request.query.get("switched", ""),
                       already=request.query.get("already", ""))


async def switch_brain(request: web.Request) -> web.Response:
    deps = request.app[render.DEPS]
    session = deps.auth.require(request)
    refused = await _require_whole_line(deps, request, session)
    if refused is not None:
        return refused
    form = await request.post()
    reason = deps.auth.check_csrf(request, session, form)
    if reason:
        return await render.page(request, deps, "refused.html", session=session,
                           status=403, reason=reason)

    wanted = str(form.get("brain", "")).strip()
    override = str(form.get("override", "")) == "on"
    brains, active = deps.get_brains()
    if wanted not in brains:
        return await _page(
            request, deps, session, status_code=400,
            error="That model is not set up on this line any more. Reload the "
                  "page and pick one of the models below.")
    if wanted == active:
        # A page left open while somebody else switched can still offer "use
        # this model" for the model that is already answering. Redirecting in
        # silence looks exactly like a click that did nothing.
        raise web.HTTPSeeOther(f"/brain?already={wanted}")

    card = next(c for c in brain_cards(deps) if c["key"] == wanted)
    if card["health"]["reachable"] is False and not override:
        return await _page(
            request, deps, session, confirming=wanted,
            error=f"{card['label']} did not answer when it was last checked "
                  f"({card['health']['text']}). Switching to it now would mean "
                  "every caller hears an apology. Tick the box below if you "
                  "want to switch anyway.")

    error = await asyncio.to_thread(_apply_switch, deps, session, wanted, active)
    if error:
        return await _page(request, deps, session, confirming=wanted,
                           error="Nothing was changed. " + error)
    log.info("dashboard: %s switched the model that answers calls to %r",
             session.owner_key, wanted)
    raise web.HTTPSeeOther(f"/brain?switched={wanted}")


def _apply_switch(deps, session, wanted: str, previous: str):
    """Re-emit the whole config with a new active brain and apply it.

    The same one path every other settings save takes — `apply_config` emits
    the file, validates it fail-closed, backs the old one up, hot-applies it and
    writes the audit row. Runs in a thread: that is blocking work on the event
    loop streaming live calls.
    """
    config = dataclasses.replace(deps.get_config(), active_brain=wanted)
    return deps.apply_config(
        config, session.owner_key,
        f"Changed the model that answers calls from {previous} to {wanted}")
