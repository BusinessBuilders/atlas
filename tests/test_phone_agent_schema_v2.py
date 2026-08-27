# tests/test_phone_agent_schema_v2.py — businesses.toml as the PRODUCT's
# schema: opening hours, compliance notices, ConversationRelay settings, the
# dashboard's owner logins and the vendor's branding.
#
# Everything here is fail-closed on purpose. This config decides what a
# stranger hears when they dial a real business: a typo that silently means
# "answer at 3am", "skip the AI disclosure" or "nobody can log in to read the
# messages" must stop the save, not surprise someone at 2am.
import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from test_phone_agent_plugin import _import_service

PLUGINS_DIR = Path(__file__).resolve().parents[1] / "plugins"

BASE = '''
[numbers]
"+15550001111" = "acme"

[profiles.acme]
business_name = "Acme Plumbing"
services = "drain cleaning"
owner_name = "Jo"
greeting = "Thanks for calling Acme Plumbing, this is Atlas. How can I help?"
'''


BASE_GREETING = ('greeting = "Thanks for calling Acme Plumbing, this is Atlas. '
                 'How can I help?"')


def _cfg(profile_extra: str = "", other: str = "", top: str = "",
         greeting: str | None = None) -> dict:
    """BASE with extra lines in [profiles.acme] (`profile_extra`), extra
    sections after it (`other`), and top-level keys before it (`top` — TOML
    puts bare keys in whatever table precedes them). `greeting` REPLACES the
    one BASE sets, since TOML refuses the same key twice."""
    base = BASE
    if greeting is not None:
        base = base.replace(BASE_GREETING, f"greeting = {greeting!r}".replace("'", '"'))
    return tomllib.loads(top + base + profile_extra + other)


@pytest.fixture
def svc(tmp_path, monkeypatch):
    return _import_service(tmp_path, monkeypatch)


def _err(svc, profile_extra="", other="", top="", greeting=None):
    """The refusal sentence for a config, or '' when it validates."""
    try:
        svc.parse_config(_cfg(profile_extra, other, top, greeting))
    except ValueError as e:
        return str(e)
    return ""


# ------------------------------------------------- every key has a default --

def test_every_documented_setting_has_a_default(svc):
    """A profile that sets none of the new keys still behaves — the defaults
    are the product's opinion, not None."""
    config = svc.parse_config(_cfg())
    profile = config.profiles["acme"]
    defaults = {k: svc.profile_setting(profile, k) for k in svc.PROFILE_DEFAULTS}
    assert defaults["after_hours"] == "message"
    assert defaults["ai_disclosure"] is True
    assert defaults["recording_notice"] is True
    assert defaults["ack_disclosure_waived"] is False
    assert defaults["language"] == "en-US"
    assert defaults["ignore_backchannel"] is True
    assert defaults["max_call_seconds"] == 600
    assert defaults["caller_turn_budget_per_hour"] == 60
    assert defaults["retention_days"] == 90
    assert defaults["hours"] == {} and defaults["holidays"] == []
    assert defaults["hints"] == [] and defaults["block_list"] == []
    assert defaults["voice"] == "" and defaults["brain"] == ""
    assert defaults["timezone"] == ""
    # empty on purpose: naming a provider here would change the voice every
    # existing caller hears the moment this ships
    assert defaults["tts_provider"] == "" and defaults["transcription_provider"] == ""


def test_a_default_list_cannot_be_mutated_into_every_other_profile(svc):
    """A shared mutable default would put one business's block list on all of
    them."""
    profile = svc.parse_config(_cfg()).profiles["acme"]
    svc.profile_setting(profile, "block_list").append("+15550009999")
    assert svc.profile_setting(profile, "block_list") == []


def test_every_default_is_a_setting_the_emitter_writes(svc):
    """A setting the emitter does not know about is a setting the next
    dashboard save quietly drops from the file."""
    assert set(svc.PROFILE_DEFAULTS) <= set(svc._PROFILE_KNOWN_KEYS)


def test_an_undocumented_setting_name_is_a_loud_mistake(svc):
    with pytest.raises(KeyError):
        svc.profile_setting({}, "no_such_setting")


# --------------------------------------------------------- unknown keys ----

def test_an_unknown_key_inside_a_brain_is_refused_with_a_sentence(svc, monkeypatch):
    monkeypatch.setenv("TEST_BRAIN_KEY", "k")
    error = _err(svc, top='active_brain = "cloud"\n', other='''
[brains.cloud]
base_url = "https://example.invalid/v1"
model = "m"
temperture = 0.2
''')
    assert "temperture" in error
    assert "cloud" in error


def test_an_unknown_key_in_branding_is_refused(svc):
    assert "vendor_nam" in _err(svc, other='\n[branding]\nvendor_nam = "X"\n')


def test_an_unknown_key_in_an_owner_is_refused(svc, monkeypatch):
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "t")
    error = _err(svc, other='\n[owners.jo]\ntoken_env = "PHONE_OWNER_JO_TOKEN"\n'
                            'profiles = ["*"]\npasword = "hunter2"\n')
    assert "pasword" in error


def test_an_unknown_top_level_table_is_refused(svc):
    """`[owner.jo]` (singular) used to be silently ignored, and then silently
    dropped by the next dashboard save — the owner just could not log in."""
    error = _err(svc, other='\n[owner.jo]\ntoken_env = "X"\n')
    assert "owner" in error


def test_an_unknown_profile_key_survives_but_is_said_out_loud(svc, caplog):
    """Hand-added keys are deliberately KEPT (a dashboard save must not eat
    someone's notes), but a typo that means nothing must not be silent."""
    import logging
    with caplog.at_level(logging.WARNING):
        config = svc.parse_config(_cfg('hurs = "9 to 5"\n'))
    assert config.profiles["acme"]["hurs"] == "9 to 5"
    assert "hurs" in caplog.text


# ------------------------------------------------------ hours + timezone ----

def test_hours_need_a_timezone(svc):
    error = _err(svc, 'hours = { mon = "09:00-17:00" }\n')
    assert "timezone" in error


def test_holidays_need_a_timezone(svc):
    assert "timezone" in _err(svc, 'holidays = ["2026-12-25"]\n')


def test_the_timezone_must_be_a_real_zone(svc):
    error = _err(svc, 'timezone = "America/Nowhere"\n')
    assert "America/Nowhere" in error


def test_hours_must_be_written_as_a_range(svc):
    assert "09:00-17:00" in _err(
        svc, 'timezone = "America/New_York"\nhours = { mon = "9-5" }\n')


def test_an_unknown_day_name_is_refused(svc):
    error = _err(svc, 'timezone = "America/New_York"\n'
                      'hours = { monday = "09:00-17:00" }\n')
    assert "monday" in error


def test_a_bad_holiday_is_refused(svc):
    error = _err(svc, 'timezone = "America/New_York"\nholidays = ["Christmas"]\n')
    assert "Christmas" in error


def test_no_timezone_and_no_hours_is_allowed_but_warned_about(tmp_path, monkeypatch, caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        svc = _import_service(tmp_path, monkeypatch)
    assert "no timezone" in caplog.text
    assert svc.profile_setting(svc.PROFILES["acme"], "timezone") == ""


def test_a_profile_with_a_timezone_is_not_nagged(tmp_path, monkeypatch, caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        _import_service(tmp_path, monkeypatch,
                        cfg_extra='timezone = "America/New_York"\n')
    assert "no timezone" not in caplog.text


# ------------------------------------------------------- after-hours mode ---

def test_after_hours_must_be_one_of_the_three_modes(svc):
    assert "voicemail" in _err(svc, 'after_hours = "voicemail"\n')


def test_after_hours_transfer_needs_somewhere_to_transfer_to(svc):
    error = _err(svc, 'after_hours = "transfer"\n')
    assert "forward_to" in error


# ------------------------------------------------------------- compliance ---

def test_the_ai_disclosure_cannot_be_switched_off_quietly(svc):
    error = _err(svc, "ai_disclosure = false\n")
    assert "ack_disclosure_waived" in error


def test_the_recording_notice_cannot_be_switched_off_quietly(svc):
    error = _err(svc, "recording_notice = false\n")
    assert "ack_disclosure_waived" in error


def test_the_waiver_is_what_makes_it_possible(svc):
    assert _err(svc, "ai_disclosure = false\nack_disclosure_waived = true\n") == ""


def test_a_switch_must_be_a_true_or_false_not_the_word(svc):
    error = _err(svc, 'ai_disclosure = "false"\n')
    assert "ai_disclosure" in error and "true" in error


def test_a_notice_placeholder_that_does_not_exist_is_refused(svc):
    """{owner_first_name} would raise KeyError while a caller was on the line."""
    error = _err(svc, 'ai_disclosure_text = "I am {robot_name}."\n')
    assert "robot_name" in error


def test_an_empty_notice_text_is_refused(svc):
    assert "ai_disclosure_text" in _err(svc, 'ai_disclosure_text = "  "\n')


# ------------------------------------------------- ConversationRelay keys ---

def test_multi_language_needs_the_providers_that_support_it(svc):
    error = _err(svc, 'language = "multi"\n')
    assert "Deepgram" in error and "ElevenLabs" in error


def test_multi_language_is_allowed_with_those_providers(svc):
    assert _err(svc, 'language = "multi"\ntranscription_provider = "Deepgram"\n'
                     'tts_provider = "ElevenLabs"\n') == ""


def test_an_unsupported_tts_provider_is_refused(svc):
    assert "Vocalizer" in _err(svc, 'tts_provider = "Vocalizer"\n')


def test_an_unsupported_transcription_provider_is_refused(svc):
    assert "Whisper" in _err(svc, 'transcription_provider = "Whisper"\n')


def test_a_hint_with_a_comma_is_refused(svc):
    """Hints ride the TwiML as one comma-separated attribute; a comma inside
    one silently becomes two hints."""
    assert "comma" in _err(svc, 'hints = ["Acme, Inc"]\n')


def test_hints_must_be_text(svc):
    assert "hints" in _err(svc, "hints = [7]\n")


# --------------------------------------------------------- tenancy fields ---

def test_a_block_list_entry_must_be_a_real_number(svc):
    assert "block_list" in _err(svc, 'block_list = ["555-1234"]\n')


def test_the_call_length_cap_must_be_a_positive_whole_number(svc):
    assert "max_call_seconds" in _err(svc, "max_call_seconds = 0\n")
    assert "max_call_seconds" in _err(svc, 'max_call_seconds = "600"\n')
    assert "max_call_seconds" in _err(svc, "max_call_seconds = true\n")


def test_the_turn_budget_and_retention_window_must_be_positive(svc):
    assert "caller_turn_budget_per_hour" in _err(svc, "caller_turn_budget_per_hour = 0\n")
    assert "retention_days" in _err(svc, "retention_days = 0\n")


def test_a_per_profile_brain_must_name_a_brain_that_exists(svc):
    assert "nope" in _err(svc, 'brain = "nope"\n')


def test_a_per_profile_brain_that_exists_is_accepted(svc):
    assert _err(svc, 'brain = "local"\n', top='active_brain = "local"\n', other='''
[brains.local]
base_url = "http://127.0.0.1:11434/v1"
model = "qwen2.5:7b-instruct"
''') == ""


def test_a_per_business_push_target_needs_both_halves(svc):
    error = _err(svc, 'ntfy_url = "https://ntfy.example.test"\n')
    assert "ntfy_topic" in error


def test_forwarding_to_one_of_our_own_numbers_is_still_refused(svc):
    assert "loop" in _err(svc, 'forward_to = "+15550001111"\n')


# ------------------------------------------------------------- owners -------

def test_an_owner_whose_token_env_is_unset_is_refused(svc, monkeypatch):
    monkeypatch.delenv("PHONE_OWNER_JO_TOKEN", raising=False)
    error = _err(svc, other='\n[owners.jo]\ntoken_env = "PHONE_OWNER_JO_TOKEN"\n'
                            'profiles = ["acme"]\n')
    assert "PHONE_OWNER_JO_TOKEN" in error


def test_an_owner_with_a_set_token_env_is_parsed(svc, monkeypatch):
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "t")
    config = svc.parse_config(_cfg(other='\n[owners.jo]\n'
                                         'token_env = "PHONE_OWNER_JO_TOKEN"\n'
                                         'profiles = ["acme"]\n'))
    assert config.owners["jo"] == svc.Owner(key="jo",
                                            token_env="PHONE_OWNER_JO_TOKEN",
                                            profiles=["acme"])


def test_an_owner_cannot_be_given_a_business_that_does_not_exist(svc, monkeypatch):
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "t")
    error = _err(svc, other='\n[owners.jo]\ntoken_env = "PHONE_OWNER_JO_TOKEN"\n'
                            'profiles = ["ghost"]\n')
    assert "ghost" in error


def test_an_owner_must_be_given_at_least_one_business(svc, monkeypatch):
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "t")
    assert "profiles" in _err(svc, other='\n[owners.jo]\n'
                                         'token_env = "PHONE_OWNER_JO_TOKEN"\n')


def test_the_token_env_must_name_a_variable_not_hold_a_secret(svc):
    error = _err(svc, other='\n[owners.jo]\ntoken_env = "s3cr3t value"\n'
                            'profiles = ["*"]\n')
    assert "token_env" in error


def test_the_legacy_admin_token_becomes_an_owner_of_everything(svc, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "sesame")
    config = svc.parse_config(_cfg())
    assert config.owners["_admin"].profiles == ["*"]
    assert config.owners["_admin"].token_env == "ADMIN_TOKEN"


def test_without_the_legacy_token_there_is_no_implicit_owner(svc, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert svc.parse_config(_cfg()).owners == {}


def test_the_legacy_owner_name_is_reserved(svc, monkeypatch):
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "t")
    error = _err(svc, other='\n[owners._admin]\n'
                            'token_env = "PHONE_OWNER_JO_TOKEN"\nprofiles = ["*"]\n')
    assert "_admin" in error


# ------------------------------------------------------------- branding -----

def test_branding_is_optional_and_neutral_out_of_the_box(svc):
    branding = svc.parse_config(_cfg()).branding
    assert branding.vendor_name == "Atlas"
    assert branding.product_name == "Phone Agent"
    assert branding.logo_path == "" and branding.support_email == ""
    assert branding.colors == {} and branding.fonts == {}


def test_branding_values_come_from_the_config(svc):
    branding = svc.parse_config(_cfg(other='''
[branding]
vendor_name = "Acme Digital"
product_name = "Front Desk"
support_email = "help@acmedigital.test"
colors = { brand = "#e85d1a", ink = "#0a0a0a" }
fonts = { body = "Inter" }
''')).branding
    assert branding.vendor_name == "Acme Digital"
    assert branding.colors["brand"] == "#e85d1a"
    assert branding.fonts == {"body": "Inter"}


def test_a_support_email_that_is_not_an_address_is_refused(svc):
    assert "support_email" in _err(svc, other='\n[branding]\nsupport_email = "call us"\n')


def test_branding_colors_must_be_text(svc):
    assert "colors" in _err(svc, other="\n[branding]\ncolors = { brand = 3 }\n")


def test_a_colour_name_the_emitter_could_not_write_is_refused_at_boot(svc):
    """The emitter can only write these names plainly. Catching it here means
    the owner is not told on the day they press Save."""
    error = _err(svc, other='\n[branding]\ncolors = { "brand color" = "#e85d1a" }\n')
    assert "brand color" in error


def test_a_font_name_the_emitter_could_not_write_is_refused_at_boot(svc):
    assert "body font" in _err(
        svc, other='\n[branding]\nfonts = { "body font" = "Inter" }\n')


def test_a_logo_that_is_not_there_is_said_out_loud(svc, tmp_path, caplog):
    import logging
    missing = tmp_path / "no-such-logo.png"
    with caplog.at_level(logging.WARNING):
        svc.parse_config(_cfg(other=f'\n[branding]\nlogo_path = "{missing}"\n'))
    assert "logo" in caplog.text


# ---------------------------------------------------------- the emitter -----

def test_the_emitter_round_trips_every_new_setting(svc, monkeypatch):
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "t")
    original = svc.parse_config(_cfg('''
timezone = "America/New_York"
hours = { mon = "09:00-17:00", sat = "18:00-02:00" }
holidays = ["2026-12-24..2026-12-26"]
after_hours = "same"
after_hours_greeting = "We're closed."
recording_notice = false
ack_disclosure_waived = true
language = "en-GB"
tts_provider = "Amazon"
voice = "Joanna"
transcription_provider = "Deepgram"
hints = ["Acme Plumbing", "Atlas"]
ignore_backchannel = false
messages_file = "~/acme-messages.md"
ntfy_url = "https://ntfy.example.test"
ntfy_topic = "acme"
max_call_seconds = 900
caller_turn_budget_per_hour = 30
block_list = ["+15550009999"]
retention_days = 30
''', other='''
[branding]
vendor_name = "Acme Digital"
colors = { brand = "#e85d1a" }

[owners.jo]
token_env = "PHONE_OWNER_JO_TOKEN"
profiles = ["acme"]
'''))
    text = svc.emit_business_toml(
        original.numbers, original.profiles, original.brains,
        original.active_brain, original.branding, original.owners)
    again = svc.parse_config(tomllib.loads(text))

    assert again.profiles == original.profiles
    assert again.branding == original.branding
    assert again.owners == original.owners
    kept = again.profiles["acme"]
    assert kept["hours"] == {"mon": "09:00-17:00", "sat": "18:00-02:00"}
    assert kept["holidays"] == ["2026-12-24..2026-12-26"]
    assert kept["recording_notice"] is False
    assert kept["max_call_seconds"] == 900 and not isinstance(kept["max_call_seconds"], bool)
    assert kept["hints"] == ["Acme Plumbing", "Atlas"]


def test_a_save_cannot_lose_the_owner_logins(svc, monkeypatch):
    """Emitting without the owners would lock every owner out of the dashboard
    on the next save."""
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "t")
    config = svc.parse_config(_cfg(other='\n[owners.jo]\n'
                                         'token_env = "PHONE_OWNER_JO_TOKEN"\n'
                                         'profiles = ["acme"]\n'))
    text = svc.emit_business_toml(config.numbers, config.profiles, config.brains,
                                  config.active_brain, config.branding, config.owners)
    assert "PHONE_OWNER_JO_TOKEN" in text


def test_a_save_does_not_write_the_legacy_owner_into_the_file(svc, monkeypatch):
    """`_admin` comes from the ADMIN_TOKEN env var. Writing it into the file
    would make the very next load refuse the config as using a reserved name —
    a dashboard save that bricks the line it is running on."""
    monkeypatch.setenv("ADMIN_TOKEN", "sesame")
    config = svc.parse_config(_cfg())
    assert "_admin" in config.owners
    text = svc.emit_business_toml(config.numbers, config.profiles, config.brains,
                                  config.active_brain, config.branding, config.owners)
    assert "_admin" not in text
    assert svc.parse_config(tomllib.loads(text)).owners["_admin"].profiles == ["*"]


def test_the_emitter_still_refuses_a_table_it_does_not_understand(svc):
    with pytest.raises(ValueError, match="departments"):
        svc.emit_business_toml({"+15550001111": "acme"},
                               {"acme": {"business_name": "A", "services": "s",
                                         "owner_name": "Jo", "greeting": "hi",
                                         "departments": {"sales": "+15550002222"}}})


def test_a_dashboard_save_keeps_the_hours_and_the_branding(svc, monkeypatch):
    """The whole live path: emit -> validate -> write -> hot-apply."""
    monkeypatch.setenv("PHONE_OWNER_JO_TOKEN", "t")
    config = svc.parse_config(_cfg('''
timezone = "America/New_York"
hours = { mon = "09:00-17:00" }
''', other='''
[branding]
vendor_name = "Acme Digital"

[owners.jo]
token_env = "PHONE_OWNER_JO_TOKEN"
profiles = ["acme"]
'''))
    text = svc.emit_business_toml(config.numbers, config.profiles, config.brains,
                                  config.active_brain, config.branding, config.owners)
    assert svc.apply_config_text(text) == []
    assert svc.PROFILES["acme"]["hours"] == {"mon": "09:00-17:00"}
    assert svc.BRANDING.vendor_name == "Acme Digital"
    assert svc.OWNERS["jo"].token_env == "PHONE_OWNER_JO_TOKEN"


# ------------------------------------------------------- the opening line ---

def _state(open_: bool):
    spec = importlib.util.spec_from_file_location(
        "phone_agent_hours_for_opening", PLUGINS_DIR / "phone_agent" / "hours.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.OpenState(open=open_, reason="hours" if not open_ else "always",
                            next_open=None)


def test_the_notices_come_before_the_question(svc):
    """A greeting that ends in a question must not have the disclosure tacked
    on AFTER it — the caller starts answering and talks over it."""
    profile = svc.parse_config(_cfg()).profiles["acme"]
    line = svc.opening_line(profile, _state(True))
    assert line == ("Thanks for calling Acme Plumbing, this is Atlas. "
                    "I'm the AI assistant for Acme Plumbing. "
                    "This call may be recorded and transcribed. "
                    "How can I help?")


def test_a_greeting_that_is_only_a_question_still_gets_the_notices_first(svc):
    profile = svc.parse_config(_cfg()).profiles["acme"]
    profile["greeting"] = "How can I help?"
    line = svc.opening_line(profile, _state(True))
    assert line.startswith("I'm the AI assistant for Acme Plumbing.")
    assert line.endswith("How can I help?")


def test_a_statement_greeting_gets_the_notices_appended(svc):
    profile = svc.parse_config(_cfg()).profiles["acme"]
    profile["greeting"] = "Thanks for calling Acme Plumbing."
    line = svc.opening_line(profile, _state(True))
    assert line == ("Thanks for calling Acme Plumbing. "
                    "I'm the AI assistant for Acme Plumbing. "
                    "This call may be recorded and transcribed.")


def test_a_greeting_without_punctuation_is_still_read_as_sentences(svc):
    profile = svc.parse_config(_cfg()).profiles["acme"]
    profile["greeting"] = "Thanks for calling Acme"
    assert svc.opening_line(profile, _state(True)).startswith(
        "Thanks for calling Acme. I'm the AI assistant")


def test_the_after_hours_greeting_is_used_when_the_line_is_closed(svc):
    config = svc.parse_config(_cfg(
        'timezone = "America/New_York"\n'
        'hours = { mon = "09:00-17:00" }\n'
        'after_hours_greeting = "Thanks for calling Acme Plumbing. '
        'We\'re closed right now, but I can take a message. What do you need?"\n'))
    line = svc.opening_line(config.profiles["acme"], _state(False))
    assert line.startswith("Thanks for calling Acme Plumbing. We're closed right now")
    assert "I'm the AI assistant for Acme Plumbing." in line
    assert line.endswith("What do you need?")


def test_without_an_after_hours_greeting_the_normal_one_is_used(svc):
    config = svc.parse_config(_cfg('timezone = "America/New_York"\n'
                                   'hours = { mon = "09:00-17:00" }\n'))
    assert svc.opening_line(config.profiles["acme"], _state(False)) == \
        svc.opening_line(config.profiles["acme"], _state(True))


def test_a_waived_recording_notice_is_absent(svc):
    config = svc.parse_config(_cfg("recording_notice = false\n"
                                   "ack_disclosure_waived = true\n"))
    line = svc.opening_line(config.profiles["acme"], _state(True))
    assert "recorded" not in line
    assert "I'm the AI assistant for Acme Plumbing." in line


def test_both_notices_waived_leaves_the_greeting_alone(svc):
    config = svc.parse_config(_cfg("ai_disclosure = false\nrecording_notice = false\n"
                                   "ack_disclosure_waived = true\n"))
    profile = config.profiles["acme"]
    assert svc.opening_line(profile, _state(True)) == profile["greeting"]


def test_the_greeting_takes_the_placeholders_too(svc):
    """"Welcome to {business_name}." is the obvious thing an owner writes."""
    config = svc.parse_config(
        _cfg(greeting="Welcome to {business_name}. How can I help?"))
    line = svc.opening_line(config.profiles["acme"], _state(True))
    assert line.startswith("Welcome to Acme Plumbing.")
    assert "{business_name}" not in line


def test_the_after_hours_greeting_takes_them_as_well(svc):
    config = svc.parse_config(_cfg(
        'timezone = "America/New_York"\n'
        'hours = { mon = "09:00-17:00" }\n'
        'after_hours_greeting = "{business_name} is closed. {assistant_name} '
        'can take a message."\n'))
    line = svc.opening_line(config.profiles["acme"], _state(False))
    assert line.startswith("Acme Plumbing is closed. Atlas can take a message.")


def test_a_greeting_placeholder_that_does_not_exist_is_refused(svc):
    assert "town" in _err(svc, greeting="Hello from {town}.")


def test_an_after_hours_greeting_placeholder_that_does_not_exist_is_refused(svc):
    assert "town" in _err(svc, 'after_hours_greeting = "Closed in {town}."\n')


def test_the_notice_placeholders_are_substituted(svc):
    config = svc.parse_config(_cfg(
        'assistant_name = "Rex"\n'
        'ai_disclosure_text = "{assistant_name} is an AI answering for '
        '{business_name}."\n'))
    line = svc.opening_line(config.profiles["acme"], _state(True))
    assert "Rex is an AI answering for Acme Plumbing." in line


# ------------------------------------------------- ConversationRelay attrs ---

def test_relay_attributes_carry_the_profile_settings(svc):
    config = svc.parse_config(_cfg('''
language = "en-GB"
tts_provider = "ElevenLabs"
voice = "Rachel"
transcription_provider = "Deepgram"
hints = ["Acme Plumbing", "Atlas"]
ignore_backchannel = false
'''))
    attrs = svc.relay_attributes(config.profiles["acme"])
    assert attrs["language"] == "en-GB"
    assert attrs["ttsProvider"] == "ElevenLabs"
    assert attrs["voice"] == "Rachel"
    assert attrs["transcriptionProvider"] == "Deepgram"
    assert attrs["hints"] == "Acme Plumbing,Atlas"
    assert attrs["ignoreBackchannel"] == "false"
    assert attrs["dtmfDetection"] == "true"
    assert attrs["welcomeGreetingInterruptible"] == "none"


def test_empty_relay_settings_are_left_out_entirely(svc):
    """An empty voice="" attribute is not 'the provider default' to Twilio —
    it is a rejected TwiML document. Leaving the attribute out is also what
    stops this release changing the voice existing callers hear."""
    attrs = svc.relay_attributes(svc.parse_config(_cfg()).profiles["acme"])
    assert "voice" not in attrs
    assert "hints" not in attrs
    assert "ttsProvider" not in attrs
    assert "transcriptionProvider" not in attrs
    assert attrs["language"] == "en-US"       # the one that is always sent
    assert attrs["ignoreBackchannel"] == "true"


def test_a_default_profile_sends_no_provider_to_twilio(svc):
    """The cutover must not change how the line sounds: with nothing set, the
    TwiML names no provider and no voice at all."""
    xml = _incoming_twiml(svc, {"To": "+15550001111", "From": "+15550002222",
                                "CallSid": "CA4"})
    assert "ttsProvider" not in xml
    assert "transcriptionProvider" not in xml
    assert "voice=" not in xml
    assert 'language="en-US"' in xml


def test_a_named_provider_reaches_the_twiml(svc):
    profile = svc.PROFILES["acme"]
    profile["tts_provider"] = "ElevenLabs"
    profile["transcription_provider"] = "Deepgram"
    profile["voice"] = "Rachel"
    xml = _incoming_twiml(svc, {"To": "+15550001111", "From": "+15550002222",
                                "CallSid": "CA5"})
    assert 'ttsProvider="ElevenLabs"' in xml
    assert 'transcriptionProvider="Deepgram"' in xml
    assert 'voice="Rachel"' in xml


def test_multi_language_is_refused_when_the_providers_are_merely_unset(svc):
    """Empty providers mean Twilio's own, which cannot do multi-language. The
    refusal has to name the two values to write."""
    error = _err(svc, 'language = "multi"\ntts_provider = "ElevenLabs"\n')
    assert 'transcription_provider = "Deepgram"' in error
    assert 'tts_provider = "ElevenLabs"' in error


def test_an_empty_provider_is_a_valid_setting(svc):
    assert _err(svc, 'tts_provider = ""\ntranscription_provider = ""\n') == ""


def _incoming_twiml(svc, form) -> str:
    """Drive a correctly signed /voice/incoming through a real server and
    return the TwiML Twilio would receive."""
    import asyncio

    import aiohttp
    from aiohttp import web

    async def go():
        app = web.Application()
        app.router.add_post("/voice/incoming", svc.voice_incoming)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        port = runner.addresses[0][1]
        try:
            signature = svc._signature_for(svc.PUBLIC_BASE + "/voice/incoming", form)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"http://127.0.0.1:{port}/voice/incoming", data=form,
                        headers={"X-Twilio-Signature": signature}) as resp:
                    assert resp.status == 200
                    return await resp.text()
        finally:
            await runner.cleanup()

    return asyncio.run(go())


def test_the_twiml_carries_the_relay_attributes_and_the_opening_line(svc):
    """What Twilio is actually told."""
    profile = svc.PROFILES["acme"]
    profile["hints"] = ["Acme Co"]
    profile["voice"] = "Rachel"
    profile["tts_provider"] = "ElevenLabs"

    xml = _incoming_twiml(svc, {"To": "+15550001111", "From": "+15550002222",
                                "CallSid": "CA1"})
    assert 'ttsProvider="ElevenLabs"' in xml
    assert 'voice="Rachel"' in xml
    assert 'hints="Acme Co"' in xml
    assert 'dtmfDetection="true"' in xml
    assert 'welcomeGreetingInterruptible="none"' in xml
    assert 'ignoreBackchannel="true"' in xml
    assert "AI assistant for Acme Co" in xml
    assert "recorded and transcribed" in xml


def test_a_greeting_that_cannot_be_composed_never_drops_the_disclosure(svc):
    """If a notice text somehow reaches a live call unfillable, the caller
    hears the configuration error — not a greeting with the AI disclosure
    quietly missing from it."""
    svc.PROFILES["acme"]["ai_disclosure_text"] = "I work for {mystery}."
    xml = _incoming_twiml(svc, {"To": "+15550001111", "From": "+15550002222",
                                "CallSid": "CA3"})
    assert "isn&#39;t set up correctly" in xml or "isn't set up correctly" in xml
    assert "ConversationRelay" not in xml
    assert [e["kind"] for e in svc.RECENT_EVENTS] == ["greeting_failed"]


def test_the_greeting_is_escaped_into_the_attribute(svc):
    """A quote in the greeting would end the attribute early and an ampersand
    would make the document invalid — Twilio answers "application error"."""
    svc.PROFILES["acme"]["greeting"] = 'Ask for "Jo" & Co. How can I help?'
    xml = _incoming_twiml(svc, {"To": "+15550001111", "From": "+15550002222",
                                "CallSid": "CA6"})
    assert 'welcomeGreeting="Ask for &quot;Jo&quot; &amp; Co.' in xml
    assert 'for "Jo"' not in xml            # no raw quote inside the attribute
    assert "& Co" not in xml                # no raw ampersand anywhere


def test_the_twiml_greeting_follows_the_hours(svc, monkeypatch):
    """A caller who dials on a closed Sunday hears the after-hours greeting."""
    import datetime as dt

    errors = svc.apply_config_text(
        '[numbers]\n"+15550001111" = "acme"\n\n'
        '[profiles.acme]\nbusiness_name = "Acme Co"\nservices = "s"\n'
        'owner_name = "Jo"\ngreeting = "Thanks for calling Acme Co."\n'
        'timezone = "America/New_York"\n'
        'hours = { mon = "09:00-17:00" }\n'
        'after_hours_greeting = "Acme Co is closed right now."\n')
    assert errors == []

    # 2026-07-12 is a Sunday, and Sunday is not in the hours table.
    monkeypatch.setattr(svc, "_now",
                        lambda: dt.datetime(2026, 7, 12, 20, tzinfo=dt.timezone.utc))
    xml = _incoming_twiml(svc, {"To": "+15550001111", "From": "+15550002222",
                                "CallSid": "CA2"})
    assert "Acme Co is closed right now." in xml


# ------------------------------------------------------------- --check ------

def _run_service(args, config_path, tmp_path, extra_env=None):
    env = dict(os.environ)
    for key in ("NTFY_URL", "NTFY_TOPIC", "MESSAGES_FILE", "ADMIN_TOKEN"):
        env.pop(key, None)
    env.update(
        TWILIO_ACCOUNT_SID="ACtest", TWILIO_AUTH_TOKEN="t", BRIDGE_PORT="1",
        PUBLIC_BASE="https://example.test/phone", WS_TOKEN="w",
        OLLAMA_URL="http://127.0.0.1:1/v1", MODEL="m",
        BUSINESS_CONFIG=str(config_path),
        PHONE_DATA_DIR=str(tmp_path / "phone-data"),
        **(extra_env or {}),
    )
    return subprocess.run(
        [sys.executable, str(PLUGINS_DIR / "phone_agent" / "service.py"), *args],
        env=env, capture_output=True, text=True, timeout=60,
    )


def test_check_says_yes_to_a_good_config(tmp_path):
    config = tmp_path / "businesses.toml"
    config.write_text(BASE, encoding="utf-8")
    done = _run_service(["--check"], config, tmp_path)
    assert done.returncode == 0, done.stderr
    assert "acme" in done.stdout


def test_check_opens_no_store_and_no_socket(tmp_path):
    """A config check on a laptop must not create the production data
    directory, and must not fight the running bridge for its port."""
    config = tmp_path / "businesses.toml"
    config.write_text(BASE, encoding="utf-8")
    done = _run_service(["--check"], config, tmp_path)
    assert done.returncode == 0, done.stderr
    assert not (tmp_path / "phone-data").exists()


def test_check_refuses_a_broken_config_with_the_boot_sentence(tmp_path):
    config = tmp_path / "businesses.toml"
    config.write_text(BASE + 'hours = { mon = "9-5" }\n', encoding="utf-8")
    done = _run_service(["--check"], config, tmp_path)
    assert done.returncode == 1
    assert "09:00-17:00" in done.stderr


def test_check_refuses_an_owner_whose_token_is_not_in_the_environment(tmp_path):
    config = tmp_path / "businesses.toml"
    config.write_text(BASE + '\n[owners.jo]\ntoken_env = "PHONE_OWNER_JO_TOKEN"\n'
                             'profiles = ["acme"]\n', encoding="utf-8")
    done = _run_service(["--check"], config, tmp_path)
    assert done.returncode == 1
    assert "PHONE_OWNER_JO_TOKEN" in done.stderr


def test_an_unknown_flag_does_not_quietly_start_the_bridge(tmp_path):
    config = tmp_path / "businesses.toml"
    config.write_text(BASE, encoding="utf-8")
    done = _run_service(["--chek"], config, tmp_path)
    assert done.returncode == 2
    assert "--chek" in done.stderr


@pytest.mark.parametrize("args", [[], ["--check"]], ids=["boot", "check"])
@pytest.mark.parametrize("body,expected", [
    (None, "does not exist"),
    ("[numbers\n", "not valid TOML"),
], ids=["missing", "unparseable"])
def test_a_config_that_cannot_be_read_stops_the_boot(tmp_path, args, body, expected):
    """A config that is missing or unreadable stops the process itself, with
    the reason on stderr — at boot and under --check alike, one code path."""
    config = tmp_path / "businesses.toml"
    if body is not None:
        config.write_text(body, encoding="utf-8")
    done = _run_service(args, config, tmp_path)
    assert done.returncode == 1
    assert expected in done.stderr


# --------------------------------------------------- the shipped example ----

def test_the_example_config_validates(svc):
    """An owner copies businesses.example.toml and starts the service. If the
    example has drifted from the schema, they meet a refusal on day one."""
    text = (PLUGINS_DIR / "phone_agent" / "businesses.example.toml").read_text(
        encoding="utf-8")
    config = svc.parse_config(tomllib.loads(text))
    assert config.profiles and config.numbers
    # and it shows the new schema, not just the four required keys
    example = next(iter(config.profiles.values()))
    assert svc.profile_setting(example, "timezone")
    assert svc.profile_setting(example, "hours")
    assert svc.profile_setting(example, "holidays")
    # and it survives a dashboard save unchanged
    again = svc.parse_config(tomllib.loads(svc.emit_business_toml(
        config.numbers, config.profiles, config.brains, config.active_brain,
        config.branding, config.owners)))
    assert again.profiles == config.profiles
