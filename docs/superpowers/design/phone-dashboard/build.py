#!/usr/bin/env python3
"""Generates the Phone Agent owner-dashboard artboards (Business Builders brand).

Every value comes from the BB token sheet (src/styles/bb-tokens.css): warm black
surfaces, cream text, orange primary with the brick hard shadow, pill tags,
Bricolage Grotesque body + Funnel Display caps. All call/message data on the
boards is SAMPLE data (555 numbers) — stated on the canvas note.
"""
import json
import pathlib

OUT = pathlib.Path(__file__).parent

FONTS = ("https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,300..800"
         "&family=Funnel+Display:wght@300..800&display=swap")

CSS = f"""
@import url('{FONTS}');
body {{ margin:0; background:#0a0a0a; color:#f5e6c8; font-family:'Bricolage Grotesque','Inter Tight',system-ui,sans-serif; font-size:15px; line-height:1.5; -webkit-font-smoothing:antialiased; }}
a {{ color:#4a9bc4; }} a:hover {{ color:#f5e6c8; }}
* {{ box-sizing:border-box; }}
.display {{ font-family:'Funnel Display','Bricolage Grotesque',sans-serif; font-weight:700; letter-spacing:-0.01em; }}
.eyebrow {{ font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.14em; color:#a89c80; }}
.muted {{ color:#c8b896; }} .subtle {{ color:#a89c80; }}
.card {{ background:#1c1812; border:1px solid rgba(245,230,200,.14); border-radius:8px; padding:20px; }}
.btn {{ display:inline-flex; align-items:center; justify-content:center; gap:8px; font-weight:700; font-size:13px; text-transform:uppercase; letter-spacing:.12em; padding:12px 20px; border-radius:4px; border:2px solid transparent; cursor:pointer; text-decoration:none; min-height:44px; font-family:inherit; }}
.btn-primary {{ background:#e85d1a; color:#0a0a0a; box-shadow:0 4px 0 #c23b22; }}
.btn-ghost {{ background:transparent; color:#f5e6c8; border-color:#f5e6c8; }}
.btn-quiet {{ background:transparent; color:#c8b896; border-color:rgba(245,230,200,.35); }}
.tag {{ display:inline-flex; align-items:center; gap:6px; font-weight:700; font-size:11px; text-transform:uppercase; letter-spacing:.14em; padding:5px 12px; border-radius:999px; white-space:nowrap; }}
.tag-orange {{ background:#e85d1a; color:#0a0a0a; }} .tag-teal {{ background:#1f6486; color:#fbf1d8; }} .tag-gold {{ background:#d4a847; color:#0a0a0a; }}
.tag-ghost {{ background:transparent; border:1px solid rgba(245,230,200,.35); color:#c8b896; }}
.tag-ok {{ background:rgba(107,163,104,.18); color:#a8dba4; border:1px solid rgba(107,163,104,.45); }}
.tag-warn {{ background:rgba(212,168,71,.16); color:#e6bf6a; border:1px solid rgba(212,168,71,.45); }}
.tag-bad {{ background:rgba(194,59,34,.18); color:#f5a07e; border:1px solid rgba(194,59,34,.5); }}
.input {{ width:100%; background:#14110d; border:1px solid rgba(245,230,200,.38); border-radius:4px; padding:12px 14px; color:#f5e6c8; font:inherit; min-height:44px; }}
textarea.input {{ min-height:120px; resize:vertical; }}
.label {{ display:block; font-size:13px; font-weight:600; color:#c8b896; margin-bottom:6px; }}
.hint {{ font-size:13px; color:#a89c80; margin-top:6px; }}
.rule {{ border:0; border-top:1px solid rgba(245,230,200,.12); margin:0; }}
.nav a {{ display:flex; align-items:center; gap:12px; padding:11px 14px; border-radius:6px; color:#c8b896; text-decoration:none; font-weight:600; font-size:15px; min-height:44px; }}
.nav a.active {{ background:rgba(232,93,26,.14); color:#f5e6c8; box-shadow:inset 3px 0 0 #e85d1a; }}
.nav a.sub {{ padding-left:46px; font-size:14px; font-weight:500; min-height:44px; }}
table {{ width:100%; border-collapse:collapse; }}
th {{ text-align:left; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.14em; color:#a89c80; padding:10px 12px; border-bottom:1px solid rgba(245,230,200,.14); }}
td {{ padding:14px 12px; border-bottom:1px solid rgba(245,230,200,.08); vertical-align:middle; }}
tr.row:hover td {{ background:rgba(245,230,200,.03); }}
.bar {{ background:#2a7fa8; border-radius:3px 3px 0 0; width:100%; }}
.bar.warn {{ background:#d4a847; }}
.bubble {{ max-width:70%; padding:12px 16px; border-radius:12px; line-height:1.45; }}
.bubble.caller {{ background:#2a2218; border:1px solid rgba(245,230,200,.12); border-bottom-left-radius:4px; }}
.bubble.agent {{ background:rgba(42,127,168,.18); border:1px solid rgba(74,155,196,.35); border-bottom-right-radius:4px; }}
.toggle {{ width:44px; height:26px; border-radius:999px; background:#e85d1a; position:relative; flex:none; }}
.toggle i {{ position:absolute; top:3px; right:3px; width:20px; height:20px; border-radius:50%; background:#0a0a0a; }}
.toggle.off {{ background:#4a4234; }} .toggle.off i {{ right:auto; left:3px; background:#c8b896; }}
.check {{ width:22px; height:22px; border-radius:4px; border:2px solid rgba(245,230,200,.45); flex:none; }}
.check.on {{ background:#e85d1a; border-color:#e85d1a; }}
.filter {{ display:inline-flex; align-items:center; gap:8px; min-height:44px; padding:0 16px; border-radius:999px; border:1px solid rgba(245,230,200,.35); color:#c8b896; font-weight:600; font-size:13px; text-decoration:none; }}
.filter.on {{ background:#e85d1a; color:#0a0a0a; border-color:#e85d1a; }}
.row44 {{ display:flex; align-items:center; gap:10px; min-height:44px; }}
"""

def icon(name, size=20):
    paths = {
        "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
        "phone": '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
        "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
        "sliders": '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
        "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
        "hash": '<line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/>',
        "bell": '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
        "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/>',
        "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
        "search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.7" y2="16.7"/>',
        "arrow": '<path d="M5 12h14M12 5l7 7-7 7"/>',
        "check": '<path d="M20 6 9 17l-5-5"/>',
        "copy": '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
        "play": '<path d="M6 4v16l14-8z"/>',
        "warn": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
        "shield": '<path d="M12 22s8-4 8-10V5l-8-3-4 1.5"/><path d="M4 5v7c0 6 8 10 8 10"/>',
        "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><line x1="21" y1="12" x2="9" y2="12"/>',
    }
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths[name]}</svg>')

PAGE_HEIGHTS = {"Overview": 1060, "Calls": 900, "Call detail": 1040, "Messages": 1000, "Business settings": 1280, "Hours": 1040, "Brain": 960}
NAV_ITEMS = [("Overview", "grid"), ("Calls", "phone"), ("Messages", "inbox"), ("Settings", "sliders")]
SETTINGS_SUB = [("Business", "sliders"), ("Hours", "clock"), ("Numbers", "hash"), ("Notifications", "bell"), ("Brain", "cpu"), ("Activity", "activity")]

def sidebar(active, sub_active=None, messages_waiting=2):
    items = []
    for label, ic in NAV_ITEMS:
        cls = ' class="active"' if label == active and not sub_active else ''
        badge = (f'<span class="tag tag-orange" style="margin-left:auto; padding:2px 9px;">{messages_waiting}</span>'
                 if label == "Messages" and messages_waiting else '')
        items.append(f'<a href="#"{cls}>{icon(ic)}<span>{label}</span>{badge}</a>')
        if label == "Settings" and (active == "Settings"):
            for slabel, sic in SETTINGS_SUB:
                scls = ' class="sub active"' if slabel == sub_active else ' class="sub"'
                items.append(f'<a href="#"{scls}><span>{slabel}</span></a>')
    return f"""
<aside style="width:240px; flex:none; background:#14110d; border-right:1px solid rgba(245,230,200,.12); display:flex; flex-direction:column; padding:20px 16px; gap:8px;">
  <div style="display:flex; flex-direction:column; gap:6px; padding:4px 10px 18px;">
    <img src="bb-logo-navbar.png" alt="Business Builder" style="width:132px; height:auto; display:block;">
    <div class="eyebrow" style="color:#e85d1a; letter-spacing:.2em;">Phone Agent</div>
  </div>
  <nav class="nav" style="display:flex; flex-direction:column; gap:4px;">{''.join(items)}</nav>
  <div style="margin-top:auto; display:flex; flex-direction:column; gap:10px; padding-top:16px; border-top:1px solid rgba(245,230,200,.12);">
    <div style="display:flex; align-items:center; gap:10px; padding:8px 10px;">
      <div style="width:34px; height:34px; border-radius:6px; background:#2a2218; display:flex; align-items:center; justify-content:center; font-weight:700; color:#e85d1a; font-family:'Funnel Display',sans-serif;">BB</div>
      <div style="display:flex; flex-direction:column; line-height:1.2;">
        <span style="font-weight:600;">Business Builders</span>
        <span class="subtle" style="font-size:12px;">(508) 886-3046</span>
      </div>
    </div>
    <a href="#" class="nav" style="display:flex; align-items:center; gap:10px; color:#c8b896; text-decoration:none; padding:8px 10px; font-size:14px;">{icon("logout", 18)}<span>Sign out</span></a>
  </div>
</aside>"""

def page(title, body, width=1440, height=None, aside=""):
    height = height or PAGE_HEIGHTS.get(title, 900)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <style>{CSS}</style>
</helmet>
<div style="width:{width}px; min-height:{height}px; background:#0a0a0a; display:flex; align-items:stretch;">
  {aside}
  <main style="flex:1 1 auto; min-width:0; padding:32px 40px 48px; display:flex; flex-direction:column; gap:24px;">
    {body}
  </main>
</div>
</x-dc>
</body>
</html>
"""

def header(title, sub=None, actions=""):
    subhtml = f'<div class="muted" style="margin-top:4px;">{sub}</div>' if sub else ''
    return f"""<div style="display:flex; align-items:flex-start; justify-content:space-between; gap:24px;">
  <div><h1 class="display" style="margin:0; font-size:28px; line-height:1.15;">{title}</h1>{subhtml}</div>
  <div style="display:flex; gap:12px; align-items:center;">{actions}</div>
</div>"""

# ---------------------------------------------------------------- Overview
def overview():
    days = [("Thu", 4, 1), ("Fri", 6, 2), ("Sat", 2, 0), ("Sun", 1, 0), ("Mon", 7, 1), ("Tue", 5, 1), ("Wed", 3, 1)]
    mx = max(d[1] for d in days)
    bars = ''.join(
        f'<div style="display:flex; flex-direction:column; align-items:center; gap:8px; flex:1;">'
        f'<div style="height:96px; width:100%; display:flex; align-items:flex-end; gap:3px;">'
        f'<div class="bar" style="height:{int(96*(c-n)/mx)}px;"></div>'
        f'<div class="bar warn" style="height:{max(4,int(96*n/mx)) if n else 0}px; width:38%;"></div></div>'
        f'<span class="subtle" style="font-size:12px;">{lab}</span></div>'
        for lab, c, n in days)
    body = header("Overview", "Wednesday, August 27 · Business Builders",
                  '<span class="subtle" style="font-size:13px;">Checked 20 seconds ago</span>')
    body += f"""
<div style="display:flex; align-items:center; gap:16px; padding:18px 22px; border-radius:8px; background:rgba(194,59,34,.14); border:1px solid rgba(194,59,34,.55);">
  <span style="color:#f5a07e; flex:none;">{icon("warn", 24)}</span>
  <div style="display:flex; flex-direction:column; flex:1;">
    <span class="display" style="font-size:20px;">Your line is running on a test model that isn't licensed for business use.</span>
    <span class="muted" style="font-size:14px;">GLM-5.2 on a test plan is answering callers. Switch to the production brain before customers call.</span>
  </div>
  <a href="#" class="btn btn-primary">Switch brain</a>
</div>
<div style="display:flex; align-items:center; gap:16px; padding:16px 22px; border-radius:8px; background:rgba(107,163,104,.14); border:1px solid rgba(107,163,104,.45);">
  <span style="width:12px; height:12px; border-radius:50%; background:#6ba368; box-shadow:0 0 0 4px rgba(107,163,104,.25); flex:none;"></span>
  <div style="display:flex; flex-direction:column;">
    <span style="font-weight:700; font-size:16px;">Your line is answering</span>
    <span class="muted" style="font-size:14px;">Answering calls · brain responding · phone network verified 4 min ago · notifications delivering</span>
  </div>
</div>
<div style="display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:16px;">
  <div class="card" style="display:flex; flex-direction:column; gap:6px;"><span class="eyebrow">Calls today</span><span class="display" style="font-size:36px; line-height:1;">3</span><span class="subtle" style="font-size:13px;">7-day average 4</span></div>
  <div class="card" style="display:flex; flex-direction:column; gap:6px;"><span class="eyebrow">Messages waiting</span><span class="display" style="font-size:36px; line-height:1; color:#e85d1a;">2</span><span class="subtle" style="font-size:13px;">Oldest 41 minutes</span></div>
  <div class="card" style="display:flex; flex-direction:column; gap:6px;"><span class="eyebrow">Couldn't help</span><span class="display" style="font-size:36px; line-height:1;">1</span><span class="subtle" style="font-size:13px;">Caller left without details</span></div>
  <div class="card" style="display:flex; flex-direction:column; gap:6px;"><span class="eyebrow">Avg call length · 7 days</span><span class="display" style="font-size:36px; line-height:1;">1:12</span><span class="subtle" style="font-size:13px;">Typical answer time 0.9 s</span></div>
</div>
<div style="display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:16px;">
  <div class="card" style="grid-column: span 2; display:flex; flex-direction:column; gap:16px;">
    <div style="display:flex; justify-content:space-between; align-items:center;"><span class="eyebrow">Calls · last 7 days</span>
      <span style="display:flex; gap:14px; font-size:12px;" class="subtle"><span><i style="display:inline-block; width:10px; height:10px; background:#2a7fa8; border-radius:2px; margin-right:6px;"></i>Handled</span><span><i style="display:inline-block; width:10px; height:10px; background:#d4a847; border-radius:2px; margin-right:6px;"></i>Couldn't help</span></span></div>
    <div style="display:flex; gap:14px; align-items:flex-end;">{bars}</div>
  </div>
  <div class="card" style="display:flex; flex-direction:column; gap:14px;">
    <span class="eyebrow">Needs attention</span>
    <div style="display:flex; gap:12px; align-items:flex-start;"><span style="color:#e6bf6a; flex:none;">{icon("warn", 18)}</span><div style="font-size:14px;"><div>Notification push failed · 11:15 today</div><div class="subtle" style="font-size:13px;">Message saved; retry sent to your phone.</div></div></div>
    <hr class="rule">
    <div style="display:flex; gap:12px; align-items:flex-start;"><span style="color:#e6bf6a; flex:none;">{icon("warn", 18)}</span><div style="font-size:14px;"><div>2 messages waiting · oldest 41 minutes</div><div class="subtle" style="font-size:13px;">Dana R. and Marcus T. are expecting a call back.</div></div></div>
    <a href="#" style="font-weight:600; font-size:14px; margin-top:auto;">Open messages →</a>
  </div>
</div>
<div class="card" style="padding:0; overflow:hidden;">
  <div style="display:flex; justify-content:space-between; align-items:center; padding:18px 20px 12px;"><span class="eyebrow">Latest messages</span><a href="#" style="font-size:14px; font-weight:600;">All messages →</a></div>
  <table>
    <tr class="row"><td style="width:150px;"><span style="font-weight:600;">10:46 today</span></td><td><span style="font-weight:600;">Dana R.</span> <span class="subtle">(774) 555-0142</span></td><td>Wants a quote for a 5-page website for a landscaping company; free Thursday afternoon.</td><td style="width:120px;"><span class="tag tag-orange">New</span></td></tr>
    <tr class="row"><td><span style="font-weight:600;">08:52 today</span></td><td><span style="font-weight:600;">Marcus T.</span> <span class="subtle">(508) 555-0177</span></td><td>Hosting renewal question — asked whether the invoice covers the domain too.</td><td><span class="tag tag-orange">New</span></td></tr>
    <tr class="row"><td><span class="muted">Yesterday</span></td><td><span style="font-weight:600;">Priya S.</span> <span class="subtle">(781) 555-0119</span></td><td>Asked about AI intake for a dental office; wants a call back after 3 pm.</td><td><span class="tag tag-ok">Done</span></td></tr>
  </table>
</div>"""
    return page("Overview", body, aside=sidebar("Overview"))

# ---------------------------------------------------------------- Sign in
def signin():
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <style>{CSS}</style>
</helmet>
<div style="width:1440px; min-height:900px; background:#0a0a0a; display:flex; align-items:center; justify-content:center; background-image: radial-gradient(ellipse at 50% 0%, rgba(232,93,26,.10), transparent 55%);">
  <div style="width:440px; display:flex; flex-direction:column; gap:28px; align-items:center;">
    <img src="bb-logo.png" alt="Business Builder" style="width:260px; height:auto; display:block;">
    <div class="card" style="width:100%; padding:32px; display:flex; flex-direction:column; gap:20px;">
      <div style="display:flex; flex-direction:column; gap:4px;">
        <span class="eyebrow" style="color:#e85d1a; letter-spacing:.2em;">Phone Agent</span>
        <h1 class="display" style="margin:0; font-size:26px;">Sign in to your phone line</h1>
        <p class="muted" style="margin:0; font-size:14px;">See every call, read every message, and change how your line answers.</p>
      </div>
      <div>
        <label class="label" for="code">Access code</label>
        <input id="code" class="input" type="password" value="••••••••••••••••" autocomplete="current-password">
        <div class="hint">The code from your setup email.</div>
      </div>
      <button class="btn btn-primary" style="width:100%;">Sign in</button>
      <div class="subtle" style="font-size:13px; text-align:center;">Lost your code? Email <a href="#">donovan@business-builder.online</a></div>
    </div>
    <div class="subtle" style="font-size:12px;">Answered by Business Builders · Private to your business</div>
  </div>
</div>
</x-dc>
</body>
</html>
"""

# ---------------------------------------------------------------- Calls
def status_pill(s):
    if s == "New":
        return '<span class="tag tag-orange">New</span>'
    if s == "Done":
        return '<span class="tag tag-ghost">Done</span>'
    return '<span class="subtle">—</span>'


def calls():
    rows = [
        ("Today 10:46", "Dana R.", "(774) 555-0142", "1:48", "tag-ok", "Message taken", "New"),
        ("Today 08:52", "Marcus T.", "(508) 555-0177", "0:57", "tag-ok", "Message taken", "New"),
        ("Today 08:03", "Unknown", "(617) 555-0103", "0:21", "tag-warn", "Couldn't help", "—"),
        ("Yesterday 16:40", "Priya S.", "(781) 555-0119", "2:12", "tag-teal", "Transferred", "Done"),
        ("Yesterday 11:05", "Chris B.", "(978) 555-0156", "1:03", "tag-ok", "Message taken", "Done"),
        ("Mon 14:22", "Blocked", "(305) 555-0199", "0:04", "tag-bad", "Blocked", "—"),
    ]
    trs = ''.join(
        f'<tr class="row"><td style="width:140px; font-weight:600;">{t}</td><td><span style="font-weight:600;">{n}</span><br><span class="subtle" style="font-size:13px;">{p}</span></td>'
        f'<td style="width:80px;">{d}</td><td style="width:160px;"><span class="tag {c}">{o}</span></td>'
        f'<td style="width:110px;">{status_pill(s)}</td>'
        f'<td style="width:44px; color:#a89c80;">{icon("arrow", 18)}</td></tr>'
        for t, n, p, d, c, o, s in rows)
    body = header("Calls", "Every call your line answered · kept for 90 days",
                  '<a href="#" class="btn btn-quiet">Export CSV</a>')
    body += f"""
<div class="card" style="display:flex; gap:12px; align-items:center; padding:14px 16px;">
  <div style="display:flex; align-items:center; gap:10px; flex:1; background:#14110d; border:1px solid rgba(245,230,200,.38); border-radius:4px; padding:0 14px; min-height:44px; color:#a89c80;">{icon("search", 18)}<span>Search names, numbers, or what was said</span></div>
  <a href="#" class="filter on">Last 7 days</a><a href="#" class="filter">All outcomes</a><a href="#" class="filter">Has message</a>
  <label class="row44 subtle" style="font-size:13px;"><span class="check"></span>Show test calls</label>
</div>
<div class="card" style="padding:0; overflow:hidden;">
<table>
  <tr><th>When</th><th>Caller</th><th>Length</th><th>Outcome</th><th>Message</th><th></th></tr>
  {trs}
</table>
<div style="display:flex; justify-content:space-between; align-items:center; padding:14px 20px;" class="subtle"><span style="font-size:13px;">Showing the latest 6 of 28 calls this week</span><span style="font-size:13px;">Blocked and test calls are hidden unless you ask.</span></div>
</div>"""
    return page("Calls", body, aside=sidebar("Calls"))

# ---------------------------------------------------------------- Call detail
def call_detail():
    turns = [
        ("agent", "Thanks for calling Business Builders, this is Atlas — I'm the AI assistant for Business Builders, and this call may be recorded and transcribed. How can I help?"),
        ("caller", "Hi, I run a landscaping company and I need a website, maybe five pages. What do you charge?"),
        ("agent", "Happy to help with that. I can't quote pricing myself, but William can — can I get your name and the best number to reach you?"),
        ("caller", "Dana Ruiz, 774-555-0142. Thursday afternoon works best."),
        ("agent", "Got it, Dana — Thursday afternoon at 774-555-0142. William will follow up with a quote for a five-page site. Anything else?"),
        ("caller", "No, that's it. Thanks."),
        ("agent", "Thanks for calling, Dana. Goodbye."),
    ]
    bubbles = ''.join(
        f'<div style="display:flex; justify-content:{"flex-end" if r == "agent" else "flex-start"}; gap:10px;">'
        f'<div class="bubble {r}"><div class="eyebrow" style="margin-bottom:4px; color:{"#4a9bc4" if r == "agent" else "#a89c80"};">{"Atlas" if r == "agent" else "Caller"}</div>{t}</div></div>'
        for r, t in turns)
    body = header('Call with Dana R.', 'Today 10:46 · 1 min 48 s · Business Builders line',
                  '<a href="#" class="btn btn-quiet">Copy summary</a><a href="#" class="btn btn-primary">Mark handled</a>')
    body += f"""
<div style="display:grid; grid-template-columns: minmax(0, 1fr) 380px; gap:20px; align-items:start;">
  <div class="card" style="display:flex; flex-direction:column; gap:14px; padding:24px;">
    <span class="eyebrow">Transcript</span>
    {bubbles}
  </div>
  <div style="display:flex; flex-direction:column; gap:16px;">
    <div class="card" style="display:flex; flex-direction:column; gap:12px;">
      <span class="eyebrow">Message</span>
      <div style="display:flex; flex-direction:column; gap:8px; font-size:14px;">
        <div><span class="subtle">Name</span><br><span style="font-weight:600;">Dana Ruiz</span></div>
        <div><span class="subtle">Call back</span><br><a href="#" style="font-weight:600; font-size:16px;">(774) 555-0142</a> <span class="tag tag-ghost" style="margin-left:8px;">{icon("copy", 12)} copy</span></div>
        <div><span class="subtle">Best time</span><br>Thursday afternoon</div>
        <div><span class="subtle">Wants</span><br>Quote for a 5-page website for a landscaping company.</div>
      </div>
      <div style="display:flex; gap:8px; margin-top:4px;"><span class="tag tag-orange">New</span></div>
    </div>
    <div class="card" style="display:flex; flex-direction:column; gap:10px; font-size:14px;">
      <span class="eyebrow">How the call went</span>
      <div style="display:flex; justify-content:space-between;"><span class="subtle">Outcome</span><span class="tag tag-ok">Message taken</span></div>
      <div style="display:flex; justify-content:space-between;"><span class="subtle">Answered by</span><span>GLM-5.2 · cloud</span></div>
      <div style="display:flex; justify-content:space-between;"><span class="subtle">Answer speed</span><span>0.9 s typical · 1.6 s slowest</span></div>
      <div style="display:flex; justify-content:space-between;"><span class="subtle">Notification</span><span class="tag tag-ok">Delivered 10:48</span></div>
      <div style="display:flex; justify-content:space-between;"><span class="subtle">Promises made</span><span>None flagged</span></div>
    </div>
    <div class="card" style="display:flex; flex-direction:column; gap:10px;">
      <span class="eyebrow">Your note</span>
      <textarea class="input" style="min-height:80px;">Quote sent Thu — follow up Mon if no reply.</textarea>
    </div>
  </div>
</div>"""
    return page("Call detail", body, aside=sidebar("Calls"))

# ---------------------------------------------------------------- Messages
def messages():
    cards = [
        ("Dana R.", "(774) 555-0142", "Today 10:46", "Wants a quote for a 5-page website for a landscaping company. Best time: Thursday afternoon.", "New", "tag-orange"),
        ("Marcus T.", "(508) 555-0177", "Today 08:52", "Hosting renewal question — does the invoice cover the domain too? Asked for the answer in writing.", "New", "tag-orange"),
        ("Priya S.", "(781) 555-0119", "Yesterday 16:40", "Asked about AI intake for a dental office. Call back after 3 pm.", "In progress", "tag-teal"),
        ("Chris B.", "(978) 555-0156", "Yesterday 11:05", "Wants the blog moved to the new site before September.", "Done", "tag-ghost"),
    ]
    items = ''.join(f"""
<div class="card" style="display:flex; gap:20px; align-items:flex-start;">
  <div style="width:46px; height:46px; border-radius:50%; background:#2a2218; display:flex; align-items:center; justify-content:center; font-weight:700; color:#f5e6c8; flex:none;">{n.split()[0][0]}{n.split()[1][0]}</div>
  <div style="flex:1; display:flex; flex-direction:column; gap:6px;">
    <div style="display:flex; justify-content:space-between; align-items:center; gap:12px;"><span style="font-weight:700; font-size:16px;">{n}</span><span class="subtle" style="font-size:13px;">{w}</span></div>
    <div>{m}</div>
    <div style="display:flex; gap:10px; align-items:center; margin-top:4px; flex-wrap:wrap;">
      <a href="#" class="btn btn-quiet" style="padding:8px 14px; min-height:44px;">{icon("phone", 16)} Call {p}</a>
      <a href="#" class="btn btn-quiet" style="padding:8px 14px; min-height:44px;">{icon("copy", 16)} Copy</a>
      <span style="margin-left:auto;" class="tag {c}">{s}</span>
    </div>
  </div>
</div>""" for n, p, w, m, s, c in cards)
    body = header("Messages", "2 waiting · newest first",
                  '<a href="#" class="filter on">New · 2</a><a href="#" class="filter">In progress</a><a href="#" class="filter">Done</a><a href="#" class="btn btn-quiet">Export CSV</a>')
    body += f'<div style="display:flex; flex-direction:column; gap:14px; max-width:920px;">{items}</div>'
    return page("Messages", body, aside=sidebar("Messages"))

# ---------------------------------------------------------------- Settings (business)
def settings():
    body = header("Business Builders", "How your line introduces itself and what it may say",
                  '<span class="tag tag-ok">Live</span>')
    body += f"""
<div style="display:grid; grid-template-columns: minmax(0, 1fr) 320px; gap:20px; align-items:start;">
<div style="display:flex; flex-direction:column; gap:16px;">
  <div class="card" style="display:flex; flex-direction:column; gap:16px; padding:24px;">
    <div style="display:flex; justify-content:space-between; align-items:center;"><span class="display" style="font-size:18px;">Greeting</span><span class="tag tag-ok">{icon("check", 12)} Saved · live on the next call</span></div>
    <div><label class="label" for="greet">What callers hear first</label><input id="greet" class="input" value="Thanks for calling Business Builders, this is Atlas. How can I help?"><div class="hint">68 characters · about 4 seconds</div></div>
    <div style="display:flex; flex-direction:column; gap:10px; padding:16px; background:#14110d; border-radius:6px; border:1px solid rgba(245,230,200,.12);">
      <span class="eyebrow">Exactly what a caller will hear</span>
      <div style="font-size:15px; line-height:1.55;">“Thanks for calling Business Builders, this is Atlas — <span style="color:#e6bf6a;">I'm the AI assistant for Business Builders, and this call may be recorded and transcribed.</span> How can I help?”</div>
      <div class="subtle" style="font-size:13px;">The notices are spoken before your closing question so callers hear them every time.</div>
      <div style="display:flex; gap:24px; margin-top:4px;">
        <label class="row44" style="font-size:14px;"><span class="toggle"><i></i></span>Say it's an AI assistant</label>
        <label class="row44" style="font-size:14px;"><span class="toggle"><i></i></span>Recording notice</label>
        <a href="#" class="btn btn-quiet" style="margin-left:auto; padding:8px 14px; min-height:44px;">{icon("play", 16)} Preview</a>
      </div>
    </div>
    <div style="display:flex; justify-content:flex-end; gap:12px;"><a href="#" class="btn btn-ghost" style="padding:10px 18px;">Discard</a><a href="#" class="btn btn-primary" style="padding:10px 18px;">Save greeting</a></div>
  </div>
  <div class="card" style="display:flex; flex-direction:column; gap:16px; padding:24px;">
    <div style="display:flex; justify-content:space-between; align-items:center;"><span class="display" style="font-size:18px;">What the agent may say</span><span class="subtle" style="font-size:13px;">The only facts it will state</span></div>
    <div style="display:flex; flex-direction:column; gap:10px;">
      <div style="display:flex; gap:10px;"><input class="input" value="Hours: Monday to Friday, 9 to 5 Eastern"><a href="#" class="btn btn-quiet" style="padding:0 14px;">Remove</a></div>
      <div style="display:flex; gap:10px;"><input class="input" value="Email: donovan@business-builder.online"><a href="#" class="btn btn-quiet" style="padding:0 14px;">Remove</a></div>
      <div style="display:flex; gap:10px;"><input class="input" value="We serve businesses across Massachusetts and remotely"><a href="#" class="btn btn-quiet" style="padding:0 14px;">Remove</a></div>
      <div style="display:flex; gap:10px;"><input class="input" placeholder="Add a fact — pricing posture, service area, parking…" value=""><a href="#" class="btn btn-quiet" style="padding:0 14px;">Add</a></div>
    </div>
    <div style="display:flex; justify-content:flex-end; gap:12px;"><a href="#" class="btn btn-primary" style="padding:10px 18px;">Save facts</a></div>
  </div>
  <div class="card" style="display:flex; flex-direction:column; gap:16px; padding:24px;">
    <div style="display:flex; justify-content:space-between; align-items:center;"><span class="display" style="font-size:18px;">Transfer to a person</span><label class="row44" style="font-size:14px;"><span class="toggle"><i></i></span>On</label></div>
    <div style="display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:16px;">
      <div><label class="label" for="fwd">Ring this number</label><input id="fwd" class="input" value="(774) 555-0100"><div class="hint">Atlas tells the person who's calling before it connects.</div></div>
      <div><label class="label">Only when a caller asks for</label><div style="display:flex; gap:8px; flex-wrap:wrap;"><a href="#" class="filter">a person</a><a href="#" class="filter">operator</a><a href="#" class="filter">talk to William</a><a href="#" class="filter">+ add</a></div></div>
    </div>
  </div>
</div>
<div style="display:flex; flex-direction:column; gap:16px;">
  <div class="card" style="display:flex; flex-direction:column; gap:10px;">
    <span class="eyebrow">Identity</span>
    <div><label class="label">Business name</label><input class="input" value="Business Builders"></div>
    <div><label class="label">What you do (one line)</label><input class="input" value="websites, hosting, automation, and AI systems"></div>
    <div><label class="label">Who takes messages</label><input class="input" value="William"></div>
    <div><label class="label">Assistant's name</label><input class="input" value="Atlas"></div>
    <a href="#" class="btn btn-primary" style="padding:10px 18px; margin-top:4px;">Save identity</a>
  </div>
  <div class="card" style="display:flex; flex-direction:column; gap:8px;">
    <span class="eyebrow">More</span>
    <a href="#" style="font-weight:600; font-size:14px;">Extra instructions</a>
    <a href="#" style="font-weight:600; font-size:14px;">Ending a call</a>
    <a href="#" style="font-weight:600; font-size:14px;">Name recognition</a>
    <a href="#" style="font-weight:600; font-size:14px;">Advanced</a>
  </div>
  <div class="card" style="border-color:rgba(194,59,34,.45); display:flex; flex-direction:column; gap:8px;">
    <span class="eyebrow" style="color:#f5a07e;">Danger zone</span>
    <span style="font-size:14px;" class="muted">Removing this business stops the line answering for it. You can restore it for 30 days.</span>
    <a href="#" class="btn btn-quiet" style="padding:8px 14px; color:#f5a07e; border-color:rgba(194,59,34,.5); align-self:flex-start;">Remove business…</a>
  </div>
</div>
</div>"""
    return page("Business settings", body, aside=sidebar("Settings", "Business"))

# ---------------------------------------------------------------- Hours
CLOSED = '<span class="subtle">Closed</span>'


def tin(v):
    return '<input class="input" value="' + v + '">'


def hours():
    days = [("Monday", True, "9:00 AM", "5:00 PM"), ("Tuesday", True, "9:00 AM", "5:00 PM"), ("Wednesday", True, "9:00 AM", "5:00 PM"),
            ("Thursday", True, "9:00 AM", "5:00 PM"), ("Friday", True, "9:00 AM", "4:00 PM"), ("Saturday", False, "", ""), ("Sunday", False, "", "")]
    rows = ''.join(
        f'<div style="display:grid; grid-template-columns: 140px 70px minmax(0,1fr) 24px minmax(0,1fr); gap:14px; align-items:center; padding:10px 0; border-bottom:1px solid rgba(245,230,200,.08);">'
        f'<span style="font-weight:600; min-height:44px; display:flex; align-items:center;">{d}</span><span class="row44"><span class="toggle{"" if on else " off"}"><i></i></span></span>'
        f'{tin(o) if on else CLOSED}'
        f'<span class="subtle" style="text-align:center;">{"to" if on else ""}</span>'
        f'{tin(c) if on else "<span></span>"}</div>'
        for d, on, o, c in days)
    body = header("Hours & availability", "Your line answers 24/7 — this decides what it does after hours",
                  '<span class="tag tag-ok">Live</span>')
    body += f"""
<div style="display:grid; grid-template-columns: minmax(0, 1fr) 360px; gap:20px; align-items:start;">
  <div class="card" style="display:flex; flex-direction:column; gap:16px; padding:24px;">
    <div style="display:flex; justify-content:space-between; align-items:center; gap:16px;">
      <span class="display" style="font-size:18px;">Weekly hours</span>
      <div style="display:flex; align-items:center; gap:10px;"><span class="label" style="margin:0;">Time zone</span><span class="input" style="width:260px; display:inline-flex; align-items:center;">Eastern — New York</span></div>
    </div>
    <div>{rows}</div>
    <div style="display:flex; justify-content:flex-end;"><a href="#" class="btn btn-primary" style="padding:10px 18px;">Save hours</a></div>
  </div>
  <div style="display:flex; flex-direction:column; gap:16px;">
    <div class="card" style="display:flex; flex-direction:column; gap:12px;">
      <span class="eyebrow">After hours</span>
      <label class="row44" style="align-items:flex-start; font-size:14px; gap:12px;"><span class="check on" style="border-radius:50%;"></span><span><span style="font-weight:600;">Take a message</span><br><span class="subtle">Atlas explains you're closed and takes the details.</span></span></label>
      <label class="row44" style="align-items:flex-start; font-size:14px; gap:12px;"><span class="check" style="border-radius:50%;"></span><span><span style="font-weight:600;">Still offer a transfer</span><br><span class="subtle">Rings (774) 555-0100 even after hours.</span></span></label>
      <label class="row44" style="align-items:flex-start; font-size:14px; gap:12px;"><span class="check" style="border-radius:50%;"></span><span><span style="font-weight:600;">Answer the same way</span><br><span class="subtle">No difference day or night.</span></span></label>
      <div><label class="label">Closed greeting</label><textarea class="input" style="min-height:96px;">Thanks for calling Business Builders. We're closed right now, but I can take a message and William will call you back.</textarea></div>
    </div>
    <div class="card" style="display:flex; flex-direction:column; gap:10px;">
      <span class="eyebrow">Holidays</span>
      <div style="display:flex; justify-content:space-between; font-size:14px;"><span>Thanksgiving · Nov 26</span><a href="#" class="subtle">Remove</a></div>
      <div style="display:flex; justify-content:space-between; font-size:14px;"><span>Christmas · Dec 24–26</span><a href="#" class="subtle">Remove</a></div>
      <a href="#" class="btn btn-quiet" style="padding:8px 14px; align-self:flex-start; min-height:44px;">+ Add a closure</a>
    </div>
  </div>
</div>"""
    return page("Hours", body, aside=sidebar("Settings", "Hours"))

# ---------------------------------------------------------------- Brain
def brain():
    def card(name, where, cost, status, badge, badge_cls, selected, note):
        border = "#e85d1a" if selected else "rgba(245,230,200,.14)"
        now_tag = '<span class="tag tag-orange">Answering now</span>' if selected else ""
        return f"""
<div class="card" style="display:flex; flex-direction:column; gap:12px; border-color:{border}; {"box-shadow:0 0 0 2px #e85d1a;" if selected else ""}">
  <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;"><span class="display" style="font-size:18px;">{name}</span>{now_tag}</div>
  <div style="display:flex; flex-direction:column; gap:6px; font-size:14px;">
    <div style="display:flex; justify-content:space-between;"><span class="subtle">Runs</span><span>{where}</span></div>
    <div style="display:flex; justify-content:space-between;"><span class="subtle">Cost</span><span>{cost}</span></div>
    <div style="display:flex; justify-content:space-between;"><span class="subtle">Reachable</span><span>{status}</span></div>
  </div>
  <span class="tag {badge_cls}" style="align-self:flex-start;">{badge}</span>
  <span class="subtle" style="font-size:13px;">{note}</span>
  <a href="#" class="btn {"btn-quiet" if selected else "btn-ghost"}" style="padding:10px 16px; margin-top:auto;">{"Current" if selected else "Use this brain…"}</a>
</div>"""
    body = header("Brain", "The model that answers every call · switching applies to the next call",
                  '<span class="subtle" style="font-size:13px;">Checked 20 seconds ago</span>')
    body += f"""
<div style="display:flex; align-items:center; gap:16px; padding:16px 22px; border-radius:8px; background:rgba(194,59,34,.14); border:1px solid rgba(194,59,34,.55);">
  <span style="color:#f5a07e; flex:none;">{icon("warn", 22)}</span>
  <div style="flex:1;"><span style="font-weight:700;">The brain answering now is marked test-only.</span> <span class="muted">Its provider's terms don't allow production use. Pick a production brain below.</span></div>
</div>
<div style="display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:16px;">
  {card("Private — on this machine", "Here, nothing leaves the building", "Free", "Yes · 0.4 s", "Approved for business use", "tag-ok", False, "Qwen 2.5 7B. Fast and private; a little less polished on tricky questions.")}
  {card("GLM-5.2 cloud · test", "Cloud (Z.AI) — test plan", "Subscription plan", "Yes · 1.4 s", "Test only — not licensed for production", "tag-bad", True, "Fine for trying things out. Not for a line customers call.")}
  {card("GLM-5.2 cloud · production", "Cloud (Z.AI)", "Pay as you go", "Needs account balance", "Approved for business use", "tag-ok", False, "Same quality as the test brain, on a metered account. Add balance to enable.")}
</div>
<div class="card" style="display:flex; flex-direction:column; gap:10px;">
  <span class="eyebrow">Last 7 days</span>
  <div style="display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap:16px; font-size:14px;">
    <div><span class="subtle">Calls answered</span><br><span class="display" style="font-size:24px;">28</span></div>
    <div><span class="subtle">Typical answer speed</span><br><span class="display" style="font-size:24px;">1.4 s</span> <span class="subtle">(slowest 2.8 s)</span></div>
    <div><span class="subtle">Provider errors</span><br><span class="display" style="font-size:24px;">0</span></div>
  </div>
</div>"""
    return page("Brain", body, aside=sidebar("Settings", "Brain"))

# ---------------------------------------------------------------- Mobile
def mobile_shell(title, body, active):
    tabs = ''.join(
        f'<a href="#" style="display:flex; flex-direction:column; align-items:center; gap:4px; flex:1; padding:10px 0 6px; text-decoration:none; color:{"#e85d1a" if l == active else "#a89c80"}; font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;">{icon(i, 22)}<span>{l}</span></a>'
        for l, i in NAV_ITEMS)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <style>{CSS}</style>
</helmet>
<div style="width:390px; height:844px; background:#0a0a0a; display:flex; flex-direction:column; overflow:hidden;">
  <div style="display:flex; align-items:center; justify-content:space-between; padding:18px 20px 12px;">
    <div style="display:flex; align-items:center; gap:10px;"><img src="bb-mark.png" alt="Business Builder" style="width:32px; height:32px; display:block;"><span class="eyebrow" style="color:#e85d1a; letter-spacing:.2em;">Phone Agent</span></div>
    <span class="subtle" style="font-size:12px;">Business Builders</span>
  </div>
  <main style="flex:1; overflow:hidden; padding:0 16px 16px; display:flex; flex-direction:column; gap:14px;">
    <h1 class="display" style="margin:0; font-size:24px;">{title}</h1>
    {body}
  </main>
  <nav style="display:flex; border-top:1px solid rgba(245,230,200,.12); background:#14110d; padding-bottom:8px;">{tabs}</nav>
</div>
</x-dc>
</body>
</html>
"""

def overview_mobile():
    body = f"""
<div style="display:flex; align-items:center; gap:12px; padding:14px 16px; border-radius:8px; background:rgba(107,163,104,.14); border:1px solid rgba(107,163,104,.45);">
  <span style="width:10px; height:10px; border-radius:50%; background:#6ba368; flex:none;"></span>
  <div style="display:flex; flex-direction:column;"><span style="font-weight:700;">Your line is answering</span><span class="subtle" style="font-size:12px;">Checked 20 s ago</span></div>
</div>
<div style="display:flex; gap:12px; padding:12px 14px; border-radius:8px; background:rgba(194,59,34,.14); border:1px solid rgba(194,59,34,.55); font-size:13px;">
  <span style="color:#f5a07e; flex:none;">{icon("warn", 18)}</span><span><span style="font-weight:700;">Running on a test model.</span> <a href="#">Switch brain</a></span>
</div>
<div style="display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:10px;">
  <div class="card" style="padding:14px; display:flex; flex-direction:column; gap:4px;"><span class="eyebrow">Calls today</span><span class="display" style="font-size:30px; line-height:1;">3</span></div>
  <div class="card" style="padding:14px; display:flex; flex-direction:column; gap:4px;"><span class="eyebrow">Waiting</span><span class="display" style="font-size:30px; line-height:1; color:#e85d1a;">2</span></div>
</div>
<div style="display:flex; justify-content:space-between; align-items:center;"><span class="eyebrow">Latest messages</span><a href="#" style="font-size:13px; font-weight:600;">All →</a></div>
<div class="card" style="padding:14px; display:flex; flex-direction:column; gap:6px;">
  <div style="display:flex; justify-content:space-between; align-items:center;"><span style="font-weight:700;">Dana R.</span><span class="tag tag-orange" style="padding:3px 9px;">New</span></div>
  <span style="font-size:14px;">Quote for a 5-page landscaping website. Thursday afternoon.</span>
  <a href="#" class="btn btn-quiet" style="padding:8px 12px; min-height:44px; align-self:flex-start; margin-top:4px;">{icon("phone", 16)} (774) 555-0142</a>
</div>
<div class="card" style="padding:14px; display:flex; flex-direction:column; gap:6px;">
  <div style="display:flex; justify-content:space-between; align-items:center;"><span style="font-weight:700;">Marcus T.</span><span class="tag tag-orange" style="padding:3px 9px;">New</span></div>
  <span style="font-size:14px;">Does the hosting invoice cover the domain too?</span>
</div>"""
    return mobile_shell("Overview", body, "Overview")

def messages_mobile():
    def card(n, w, m, p, s, c):
        return f"""
<div class="card" style="padding:14px; display:flex; flex-direction:column; gap:8px;">
  <div style="display:flex; justify-content:space-between; align-items:center;"><span style="font-weight:700;">{n}</span><span class="subtle" style="font-size:12px;">{w}</span></div>
  <span style="font-size:14px;">{m}</span>
  <div style="display:flex; gap:8px; align-items:center;"><a href="#" class="btn btn-quiet" style="padding:8px 12px; min-height:44px;">{icon("phone", 16)} Call</a><a href="#" class="btn btn-quiet" style="padding:8px 12px; min-height:44px;">Done</a><span class="tag {c}" style="margin-left:auto; padding:3px 9px;">{s}</span></div>
</div>"""
    body = f"""
<div style="display:flex; gap:8px;"><a href="#" class="filter on">New · 2</a><a href="#" class="filter">In progress</a><a href="#" class="filter">Done</a></div>
{card("Dana R.", "10:46", "Quote for a 5-page landscaping website. Thursday afternoon.", "(774) 555-0142", "New", "tag-orange")}
{card("Marcus T.", "08:52", "Does the hosting invoice cover the domain too?", "(508) 555-0177", "New", "tag-orange")}
{card("Priya S.", "Yesterday", "AI intake for a dental office — call back after 3 pm.", "(781) 555-0119", "In progress", "tag-teal")}"""
    return mobile_shell("Messages", body, "Messages")

FILES = {
    "Main.dc.html": overview(),
    "SignIn.dc.html": signin(),
    "Calls.dc.html": calls(),
    "CallDetail.dc.html": call_detail(),
    "Messages.dc.html": messages(),
    "Settings.dc.html": settings(),
    "Hours.dc.html": hours(),
    "Brain.dc.html": brain(),
    "OverviewMobile.dc.html": overview_mobile(),
    "MessagesMobile.dc.html": messages_mobile(),
}
for name, html in FILES.items():
    (OUT / name).write_text(html, encoding="utf-8")

W, GAP_X, GAP_Y = 1440, 120, 200
HEIGHTS = {"SignIn.dc.html": 900, "Main.dc.html": 1060, "Calls.dc.html": 900, "CallDetail.dc.html": 1040,
           "Settings.dc.html": 1280, "Hours.dc.html": 1040, "Brain.dc.html": 960, "Messages.dc.html": 1000}
row1 = ["SignIn.dc.html", "Main.dc.html", "Calls.dc.html", "CallDetail.dc.html"]
row2 = ["Settings.dc.html", "Hours.dc.html", "Brain.dc.html", "Messages.dc.html"]
H = max(HEIGHTS[f] for f in row1); H2 = max(HEIGHTS[f] for f in row2)
boards = []
for i, f in enumerate(row1):
    boards.append({"file": f, "x": i * (W + GAP_X), "y": 0, "w": W, "h": HEIGHTS[f], "title": f.replace(".dc.html", "").replace("Main", "Overview")})
for i, f in enumerate(row2):
    boards.append({"file": f, "x": i * (W + GAP_X), "y": H + GAP_Y, "w": W, "h": HEIGHTS[f], "title": f.replace(".dc.html", "")})
y3 = H + GAP_Y + H2 + GAP_Y
boards.append({"file": "OverviewMobile.dc.html", "x": 0, "y": y3, "w": 390, "h": 844, "title": "Overview · phone"})
boards.append({"file": "MessagesMobile.dc.html", "x": 390 + GAP_X, "y": y3, "w": 390, "h": 844, "title": "Messages · phone"})
canvas = {
    "artboards": boards,
    "annotations": [
        {"id": "brief", "x": 0, "y": -170, "w": 520,
         "text": "Phone Agent owner dashboard — Business Builders brand.\nBuilt from the BB token sheet (warm black, cream, sign-orange, brick shadow, Bricolage Grotesque + Funnel Display).\nAll callers, numbers (555) and figures are SAMPLE data. The red 'test model' banner reflects the line's real state today."},
        {"id": "row2", "x": 0, "y": H + GAP_Y - 110, "w": 420,
         "text": "Settings screens: each section saves on its own and never loses what you typed. Hours decide after-hours behaviour; Brain shows a production-use badge on every model."},
        {"id": "row3", "x": 0, "y": y3 - 110, "w": 420,
         "text": "Phone layout: bottom tabs, one-thumb actions (call back, mark done)."},
    ],
    "launch": {"view": "canvas"},
}
(OUT / "canvas.json").write_text(json.dumps(canvas, indent=2), encoding="utf-8")
print("wrote", len(FILES), "artboards + canvas.json")
