"""Static checks over every screen of a RUNNING owner dashboard.

This is the half of the browser pass a machine can do on its own: it signs in
to a local instance, walks every screen both sign-ins can reach, and reports
the things a human eye misses on the twentieth read of the same page.

    # in one terminal
    PYTHONPATH=<worktree>:<worktree>/src \\
      python tests/e2e/run_dashboard_fixture.py /tmp/dash-work 8931
    # in another
    python tests/e2e/phone_dashboard_checks.py http://127.0.0.1:8931

No pytest, no Playwright, no requests. The filename does not start with
`test_`, so pytest never collects it; it is a tool you run and read, and it
exits non-zero when a check fails. It is standard library only bar one import:
it loads `run_dashboard_fixture` (beside it) to ask the dashboard app itself
which routes it serves, so the screen list cannot drift away from the router.

What it checks, and why each one is worth a machine's time:

  1. **Every GET screen is walked.** The list is not written out by hand: it
     comes from `app.router.routes()`, with the fixture's own business keys and
     CallSid put into `{profile}` and `{sid}`. A route that is neither walked
     nor in the commented skip list is a FAILURE — otherwise a screen added
     tomorrow is unchecked and the table still says PASS.
  2. **Owner vocabulary.** No screen may say `journalctl`, `TOML`, `env file`,
     `profile key`, `hot-apply` or `non-thinking`. Those are words from inside
     the machine; the person reading this dashboard owns a plumbing company.
  3. **Every control has a label.** Every `input`, `select` and `textarea`
     must be reachable by name — a `<label for=>`, a wrapping `<label>`, or an
     `aria-label`. A screen reader cannot guess.
  4. **Contrast.** Hint text must clear 4.5:1 and the outline of anything you
     can click must clear 3:1, computed from the CSS custom properties the
     browser actually resolves — including `color-mix()`, which is how this
     stylesheet derives most of its palette from two brand colours. The rules
     that USE those tokens are checked too: a `.hint` repointed at another
     custom property would otherwise leave this measuring a colour nothing on
     the page is painted with, and passing.
  5. **No inline script and no `style=` attributes.** The dashboard serves a
     Content-Security-Policy with no `unsafe-inline`; anything inline is
     refused by the browser, which means it is a feature that silently is not
     there.
  6. **Every link answers.** Every internal link on every screen is fetched
     and must come back 200. A link into a 404 is something a customer finds,
     not something we should.
  7. **The other business is invisible.** Every value belonging to the business
     the scoped login does not own, hunted for in the RAW HTML of that login's
     screens — not in the visible text. Most of a business's data reaches the
     page inside `value=` attributes, and a text-only view is blind to exactly
     the leak this check exists to catch.

It prints one PASS/FAIL line per check with the failures underneath.
"""
from __future__ import annotations

import pathlib
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

BANNED = re.compile(
    r"journalctl|TOML|env file|profile key|hot-apply|non-thinking",
    re.IGNORECASE)

# Controls that have nothing to label — the value is not typed by a person.
UNLABELLED_OK = {"hidden", "submit", "button", "image", "reset"}

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}


# ------------------------------------------------------------------ colour --

def _srgb(component: float) -> float:
    c = component / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    r, g, b = (_srgb(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg) -> float:
    """WCAG contrast ratio. `fg` may be translucent; it is composited on `bg`
    first, which is what the eye sees."""
    fg = over(fg, bg)
    a, b = luminance(fg), luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def over(top, bottom):
    """Composite a possibly-translucent colour onto an opaque one."""
    alpha = top[3] if len(top) > 3 else 1.0
    if alpha >= 1.0:
        return top[:3]
    return tuple(top[i] * alpha + bottom[i] * (1 - alpha) for i in range(3))


def parse_color(text: str):
    """`#rgb`, `#rrggbb`, `transparent`, or `rgb()/rgba()` → (r, g, b, a)."""
    text = text.strip()
    if text == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    if text.startswith("#"):
        hexes = text[1:]
        if len(hexes) == 3:
            hexes = "".join(c * 2 for c in hexes)
        if len(hexes) not in (6, 8):
            raise ValueError(f"cannot read the colour {text!r}")
        vals = [int(hexes[i:i + 2], 16) for i in range(0, len(hexes), 2)]
        alpha = vals[3] / 255.0 if len(vals) == 4 else 1.0
        return (float(vals[0]), float(vals[1]), float(vals[2]), alpha)
    m = re.match(r"rgba?\(([^)]*)\)", text)
    if m:
        parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(1)) if p.strip()]
        vals = [float(p.rstrip("%")) for p in parts]
        alpha = vals[3] if len(vals) > 3 else 1.0
        return (vals[0], vals[1], vals[2], alpha)
    raise ValueError(f"cannot read the colour {text!r}")


def split_top_level(text: str, sep: str = ",") -> list:
    """Split on `sep`, ignoring anything inside parentheses."""
    out, depth, current = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            out.append(current)
            current = ""
        else:
            current += ch
    out.append(current)
    return [p.strip() for p in out]


class Palette:
    """The `:root` custom properties, resolved the way a browser resolves them.

    Later declarations win, `var()` chains are followed, and
    `color-mix(in srgb, A p%, B)` is mixed — which matters, because this
    stylesheet derives its text and line colours from two brand colours that
    way, and a check that read only the fallback line would be measuring a
    colour nobody sees.
    """

    def __init__(self, *stylesheets: str) -> None:
        self.raw: dict = {}
        for sheet in stylesheets:
            # Comments go first: a prose comment with a semicolon in it would
            # otherwise split a declaration in half.
            sheet = re.sub(r"/\*.*?\*/", "", sheet, flags=re.DOTALL)
            for block in re.findall(r":root\s*\{([^}]*)\}", sheet):
                for decl in block.split(";"):
                    if ":" not in decl:
                        continue
                    name, _, value = decl.partition(":")
                    name = name.strip()
                    if name.startswith("--"):
                        self.raw[name] = value.strip()

    def value(self, name: str, seen=()) -> str:
        if name in seen:
            raise ValueError(f"{name} refers to itself")
        text = self.raw[name]
        m = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", text)
        if m:
            return self.value(m.group(1), seen + (name,))
        return text

    def color(self, name: str):
        return self.resolve(self.value(name))

    def resolve(self, text: str):
        text = text.strip()
        m = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", text)
        if m:
            return self.color(m.group(1))
        if text.startswith("color-mix("):
            return self._mix(text[len("color-mix("):-1])
        return parse_color(text)

    def _mix(self, inner: str):
        parts = split_top_level(inner)
        if len(parts) != 3 or parts[0].strip() != "in srgb":
            raise ValueError(f"only `color-mix(in srgb, …)` is understood: {inner!r}")
        first, second = self._with_share(parts[1]), self._with_share(parts[2])
        (a, pa), (b, pb) = first, second
        if pa is None and pb is None:
            pa = pb = 0.5
        elif pa is None:
            pa = 1.0 - pb
        elif pb is None:
            pb = 1.0 - pa
        total = pa + pb
        if total <= 0:
            raise ValueError(f"color-mix percentages sum to zero: {inner!r}")
        pa, pb = pa / total, pb / total
        return tuple(a[i] * pa + b[i] * pb for i in range(4))

    def _with_share(self, text: str):
        m = re.search(r"(-?[\d.]+)%\s*$", text.strip())
        if m:
            return self.resolve(text[:m.start()]), float(m.group(1)) / 100.0
        return self.resolve(text), None


# -------------------------------------------------------------------- HTML --

class Page(HTMLParser):
    """One rendered screen, pulled apart into the things worth checking."""

    def __init__(self, url: str, body: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.url = url
        # The bytes the browser was served, kept whole. The tenancy check reads
        # THIS, not `text`: a leak arrives in an input's `value=`, a hidden
        # field or an `href` far more often than in a text node.
        self.body = body
        self.text_parts: list = []
        self.controls: list = []       # (tag, attrs dict, wrapped_in_label)
        self.label_targets: set = set()
        self.inline_scripts = 0
        self.style_attrs: list = []
        self.links: set = set()
        # The same links in the order they appear, so "the first row's link"
        # means the first row and not the alphabetically-first CallSid.
        self.link_order: list = []
        self._skip = 0
        self._label_depth: list = []
        self._open: list = []
        self._script_src = None
        self._script_text = ""

    # -- structure
    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        if tag not in VOID:
            self._open.append(tag)
        if "style" in a:
            self.style_attrs.append((tag, a.get("class", ""), a["style"]))
        if tag == "script":
            self._script_src = a.get("src")
            self._script_text = ""
            self._skip += 1
        elif tag == "style":
            self._skip += 1
        elif tag == "label":
            self._label_depth.append(len(self._open))
            if a.get("for"):
                self.label_targets.add(a["for"])
        elif tag in ("input", "select", "textarea"):
            self.controls.append((tag, a, bool(self._label_depth)))
        elif tag == "a" and a.get("href"):
            self.links.add(a["href"])
            self.link_order.append(a["href"])
        # Words a person reads that are not text nodes.
        for key in ("placeholder", "aria-label", "title", "alt"):
            if a.get(key):
                self.text_parts.append(a[key])
        if tag == "input" and a.get("type") in ("submit", "button") and a.get("value"):
            self.text_parts.append(a["value"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "script":
            if not self._script_src and self._script_text.strip():
                self.inline_scripts += 1
            self._script_src = None
            self._skip = max(0, self._skip - 1)
        elif tag == "style":
            self._skip = max(0, self._skip - 1)
        if tag in VOID:
            return
        while self._open and self._open[-1] != tag:
            self._open.pop()
            while self._label_depth and self._label_depth[-1] > len(self._open):
                self._label_depth.pop()
        if self._open:
            self._open.pop()
        while self._label_depth and self._label_depth[-1] > len(self._open):
            self._label_depth.pop()

    def handle_data(self, data):
        if self._script_src is None and self._skip and self._open[-1:] == ["script"]:
            self._script_text += data
        if not self._skip:
            self.text_parts.append(data)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.text_parts))

    def unlabelled(self) -> list:
        """Controls a screen reader would announce as nothing at all."""
        bad = []
        for tag, a, wrapped in self.controls:
            if tag == "input" and a.get("type", "text").lower() in UNLABELLED_OK:
                continue
            if a.get("aria-label") or a.get("aria-labelledby"):
                continue
            if wrapped:
                continue
            if a.get("id") and a["id"] in self.label_targets:
                continue
            bad.append(f"<{tag} name={a.get('name', '')!r} id={a.get('id', '')!r}>")
        return bad


# ------------------------------------------------------------------ client --

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are followed by hand, because the cookie that signs you in
    arrives ON the 303 and urllib would swallow that response's headers."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    """A signed-in session. The cookie is carried by hand because the
    dashboard marks it `Secure` and `http.cookiejar` will not send a Secure
    cookie back over plain http — which the browser does do for 127.0.0.1."""

    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.cookie = ""
        self.opener = urllib.request.build_opener(_NoRedirect)

    def request(self, path: str, data=None, method=None, follow: bool = True):
        url = path if path.startswith("http") else self.base + path
        body = urllib.parse.urlencode(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method)
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with self.opener.open(req) as r:
                self._remember(r)
                status, text, headers = r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            self._remember(e)
            status, text, headers = e.code, e.read(), e.headers
        if follow and status in (301, 302, 303, 307, 308) and headers.get("Location"):
            return self.request(urllib.parse.urljoin(url, headers["Location"]))
        return status, text.decode("utf-8", "replace"), headers

    def _remember(self, response) -> None:
        for value in response.headers.get_all("Set-Cookie") or []:
            name_value = value.split(";", 1)[0]
            if name_value.split("=", 1)[0].strip():
                self.cookie = name_value

    def sign_in(self, code: str) -> None:
        status, body, _ = self.request("/sign-in", {"code": code}, follow=False)
        if status not in (200, 303):
            raise SystemExit(f"sign-in with {code!r} answered {status}")
        if not self.cookie:
            raise SystemExit(f"sign-in with {code!r} handed back no session")
        status, body, _ = self.request("/")
        if status != 200 or 'action="/sign-in"' in body:
            raise SystemExit(f"sign-in with {code!r} did not stick ({status})")

    def page(self, path: str) -> Page:
        status, body, headers = self.request(path)
        if status != 200:
            raise SystemExit(f"{path} answered {status}")
        page = Page(path, body)
        page.feed(body)
        return page


# ------------------------------------------------------------------ checks --

class Report:
    def __init__(self) -> None:
        self.rows: list = []

    def add(self, name: str, failures: list, detail: str = "") -> None:
        self.rows.append((name, list(failures), detail))

    def print(self) -> int:
        width = max(len(name) for name, _, _ in self.rows)
        print()
        print(f"  {'check'.ljust(width)}  result")
        print(f"  {'-' * width}  ------")
        for name, failures, detail in self.rows:
            verdict = "PASS" if not failures else f"FAIL ({len(failures)})"
            note = f"  {detail}" if detail and not failures else ""
            print(f"  {name.ljust(width)}  {verdict}{note}")
        broken = [r for r in self.rows if r[1]]
        for name, failures, _ in broken:
            print(f"\n  {name} —")
            for line in failures:
                print(f"    · {line}")
        print()
        return 1 if broken else 0


# GET routes that are not screens. Everything here is deliberate and stays
# short: a route is walked unless there is a reason in writing.
#
#   * the three bundled assets and the two generated ones are files, not pages
#     — no words a person reads, no controls to label. `app.css` and
#     `brand.css` ARE fetched, by the contrast check, which is where a
#     stylesheet belongs;
#   * `/static/logo` answers 404 unless the line configures a logo, and this
#     fixture does not;
#   * `/favicon.ico` is the same image as `/static/icon.svg`.
SKIPPED_ROUTES = {
    "/static/app.css", "/static/app.js", "/static/htmx.min.js",
    "/static/brand.css", "/static/icon.svg", "/static/logo", "/favicon.ico",
}
# The placeholders this knows how to fill. A route with any other placeholder
# is left un-walked ON PURPOSE, so the route-coverage check fails and says so
# rather than this guessing a value and reporting a pass.
KNOWN_PLACEHOLDERS = {"profile", "sid"}
# The businesses the fixture gives each sign-in. `riverside` belongs to the
# whole line only — asking for it as the scoped owner is a 404, which is the
# tenancy control working and not a screen to check.
PROFILES = {True: ("acme", "riverside"), False: ("acme",)}
# Screens that are a query away from a route rather than a route of their own.
# These are states a customer really reaches, so they are walked too; they are
# not part of route coverage, because the router does not know about them.
QUERY_STATES = ("/calls?show_test=on", "/messages?status=new")


def newest_call_path(client: Client) -> str:
    """The link on the first row of the call log — the newest call.

    The order is the page's, not `sorted()`: the log is newest first, so the
    first `/calls/<sid>` link in the document is the newest call. A fixture
    with no calls, or a link shape that has changed, stops this dead rather
    than quietly dropping Call detail out of the walk and still saying PASS.
    """
    for href in client.page("/calls").link_order:
        if re.fullmatch(r"/calls/[A-Za-z0-9]+", href):
            return href
    raise SystemExit("no call-detail link on /calls — the fixture is not seeded")


def restore_dialog_path(client: Client) -> str:
    """The Activity screen with a restore confirm open on it."""
    for href in client.page("/activity").link_order:
        if re.fullmatch(r"/activity\?restore=\d+", href):
            return href
    raise SystemExit("no restore link on /activity — the fixture is not seeded")


def screens(client: Client, whole_line: bool, routes) -> list:
    """Every screen this sign-in can reach, derived from the app's own routes.

    Nothing here is a hand-written path. `{profile}` becomes each business this
    login owns and `{sid}` becomes the newest call; the query-string states go
    on the end. `/sign-in` is walked signed OUT, by `main`.
    """
    sid_path = newest_call_path(client)
    paths = []
    for canonical in routes:
        if canonical in SKIPPED_ROUTES or canonical == "/sign-in":
            continue
        if not whole_line and canonical == "/brain":
            # Choosing the model is the line's to do, so this login gets a 403.
            # That refusal is a tenancy control with its own test; it is not a
            # screen, and walking it here would only stop the checker.
            continue
        placeholders = set(re.findall(r"\{(\w+)\}", canonical))
        if not placeholders <= KNOWN_PLACEHOLDERS:
            continue
        if "{profile}" in canonical:
            paths += [canonical.replace("{profile}", key)
                      for key in PROFILES[whole_line]]
        elif "{sid}" in canonical:
            paths.append(sid_path)
        else:
            paths.append(canonical)
    paths += list(QUERY_STATES)
    if whole_line:
        paths.append(restore_dialog_path(client))
    return paths


def route_coverage(routes, walked) -> list:
    """Routes that were neither walked nor skipped, in writing.

    This is the check that keeps the rest honest: add a screen tomorrow and,
    without this, every other row still prints PASS over a list that never
    heard of it.
    """
    patterns = []
    for path in walked:
        bare = path.split("?", 1)[0]
        patterns.append(bare)
    missed = []
    for canonical in routes:
        if canonical in SKIPPED_ROUTES:
            continue
        shape = re.escape(canonical)
        for name in re.findall(r"\{(\w+)\}", canonical):
            shape = shape.replace(re.escape("{" + name + "}"), r"[^/]+")
        if not any(re.fullmatch(shape, bare) for bare in patterns):
            missed.append(f"{canonical} — never walked, and not in the "
                          f"skip list")
    return missed


def rule_declares(css: str, selector: str, token: str) -> bool:
    """Does the rule for exactly `selector` mention `token`?

    The contrast figures below are computed from custom properties. This is
    what ties them to the page: if `.hint` is ever repointed at a different
    property, measuring `--fg-quiet` would keep passing while the hint text on
    screen went unmeasured.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    for selectors, block in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        names = [s.strip() for s in selectors.split(",")]
        if selector in names and token in block:
            return True
    return False


def dashboard_get_routes() -> list:
    """The GET routes the dashboard serves, from the app itself.

    Built in a throwaway directory beside the running fixture, which is why
    this file is not quite standard-library-only. Cheap next to being wrong:
    the alternative is a list of screens typed out by hand that stops matching
    the router the first time somebody adds one.
    """
    here = pathlib.Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    import run_dashboard_fixture

    with tempfile.TemporaryDirectory(prefix="dashboard-routes-") as tmp:
        return run_dashboard_fixture.get_routes(pathlib.Path(tmp))


def main(argv) -> int:
    base = argv[1] if len(argv) > 1 else "http://127.0.0.1:8931"
    report = Report()
    routes = dashboard_get_routes()

    # The sign-in screen is the first thing every customer sees and the only
    # thing a stranger sees, so it is walked with no session at all.
    stranger = Client(base)
    line = Client(base)
    line.sign_in("line-code")
    scoped = Client(base)
    scoped.sign_in("acme-code")

    walks = (("stranger", stranger, ["/sign-in"]),
             ("line", line, screens(line, True, routes)),
             ("acme", scoped, screens(scoped, False, routes)))
    walked = [path for _who, _client, paths in walks for path in paths]

    pages, banned, unlabelled, inline, styles = {}, [], [], [], []
    for who, client, paths in walks:
        for path in paths:
            page = client.page(path)
            pages[(who, path)] = page
            for word in sorted({m.group(0) for m in BANNED.finditer(page.text)}):
                near = page.text[max(0, page.text.lower().index(word.lower()) - 40):][:110]
                banned.append(f"{who} {path}: {word!r} — …{near.strip()}…")
            for control in page.unlabelled():
                unlabelled.append(f"{who} {path}: {control}")
            if page.inline_scripts:
                inline.append(f"{who} {path}: {page.inline_scripts} inline <script>")
            for tag, cls, value in page.style_attrs:
                styles.append(f"{who} {path}: <{tag} class={cls!r} style={value!r}>")

    report.add("every GET route walked", route_coverage(routes, walked),
               f"{len(routes)} routes, {len(SKIPPED_ROUTES)} of them assets")
    report.add("owner vocabulary", banned,
               f"{len(pages)} screens, none of the six words")
    report.add("every control labelled", unlabelled,
               f"{sum(len(p.controls) for p in pages.values())} controls")
    report.add("no inline <script> (CSP)", inline)
    report.add("no style= attributes (CSP)", styles)

    # -- links
    clients = {"stranger": stranger, "line": line, "acme": scoped}
    seen, dead = set(), []
    for (who, path), page in pages.items():
        client = clients[who]
        for href in sorted(page.links):
            target = urllib.parse.urljoin(path, href)
            if not target.startswith("/") or (who, target) in seen:
                continue
            seen.add((who, target))
            status, _, _ = client.request(target)
            if status != 200:
                dead.append(f"{who} {path} → {target} answered {status}")
    report.add("every link answers 200", dead, f"{len(seen)} links")

    # -- contrast, from the stylesheets the browser is actually served
    _, brand_css, _ = line.request("/static/brand.css")
    _, app_css, _ = line.request("/static/app.css")
    palette = Palette(brand_css, app_css)
    page_bg = palette.color("--brand-bg")
    card_bg = palette.color("--surface-card")
    rail_bg = palette.color("--surface-rail")
    surfaces = {"page": page_bg, "card": card_bg, "rail": rail_bg}

    contrast_fails, measured = [], []
    for token, minimum, what in (("--fg-quiet", 4.5, "hint text"),
                                 ("--fg-soft", 4.5, "secondary text"),
                                 ("--fg", 4.5, "body text"),
                                 ("--line-control", 3.0, "control borders")):
        colour = palette.color(token)
        for surface_name, surface in surfaces.items():
            ratio = contrast(colour, surface[:3])
            measured.append(f"{what} on {surface_name}: {ratio:.2f}:1")
            if ratio < minimum:
                contrast_fails.append(
                    f"{what} ({token}) on the {surface_name}: {ratio:.2f}:1, "
                    f"needs {minimum}:1")
    report.add("contrast", contrast_fails, "; ".join(measured[:2]))

    # -- and the rules those tokens are measured FOR still use them
    unused = [f"{selector} does not use {token}"
              for selector, token in ((".hint", "var(--fg-quiet)"),
                                      (".btn-ghost", "var(--line-control)"),
                                      (".input", "var(--line-control)"),
                                      (".tag-ghost", "var(--line-control)"),
                                      (".filter", "var(--line-control)"))
              if not rule_declares(app_css, selector, token)]
    report.add("the measured tokens are the painted ones", unused,
               "hint text and four control outlines")

    # -- tenancy: the other business is nowhere on the scoped owner's screens.
    # The RAW body, not the visible text: settings, hours and notifications
    # render most of a business's data into `value=` attributes, which a
    # text-only view never sees — and an attribute is where a leak lands.
    leaks = []
    for (who, path), page in pages.items():
        if who != "acme":
            continue
        for secret in ("Riverside", "riverside", "Toni Vasquez",
                       "+15550002222", "(555) 000-2222", "Sam Okafor"):
            if secret in page.body:
                leaks.append(f"acme {path}: says {secret!r}")
    report.add("the other business is invisible", leaks,
               "no Riverside Dental value in the HTML of any Acme screen")

    print("\nmeasured contrast (from the served CSS, color-mix resolved):")
    for line_text in measured:
        print(f"  {line_text}")

    return report.print()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
