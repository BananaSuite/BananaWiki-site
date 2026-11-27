"""BananaWiki's screenshots: the wiki home, the editor, the image options, Appearance, a board, a canvas, the
features page and the hosting dashboard, from a throwaway wiki and a throwaway hosting portal.

SRC is a checkout built with `python3 -m venv .venv && .venv/bin/python -m pip install -e .`. The wiki gets
its own instance directory in a temporary directory. Its owner is created with the app's command line; the
sample pages, board and canvas go in through the REST API, which the owner switches on in the browser.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PORT, PORTAL_PORT = 3920, 3921
URL, PORTAL_URL = f"http://127.0.0.1:{PORT}", f"http://127.0.0.1:{PORTAL_PORT}"
USER, PASSWORD = "anna_ricci", "sample-data-only-4821"
MEMBERS = ("marco_bianchi", "lena_weber", "tom_keller")
IMAGE_ALT = "The three layers of our workspace"

HOME = """Welcome to the team's handbook: the ideas, decisions and practical details that help us work well together.

## Start here

- [Getting started](/page/{Getting started}): set up your account and find your way around.
- [Design principles](/page/{Design principles}): how we make product decisions.
- [Release notes](/page/{Release notes}): what changed and what comes next.

## This week

We are refining the reading experience, simplifying everyday tools and making it easier to go from an idea \
to a useful page.

| Workstream | Owner | Status |
|---|---|---|
| Reader experience | Anna Ricci | In progress |
| Team handbook | Marco Bianchi | Ready for review |
| Release checklist | Lena Weber | Planned |

## Writing things down

Write while it is fresh, link related pages and keep decisions next to the work. The history of every page \
shows who changed what, and when.
"""
DESIGN = """## Make space for the work

Our interface should feel calm, clear and purposeful.

### Clarity comes first

Keep navigation predictable and actions close to their context.

### Details earn their place

Every border, label and control should help someone do their work.
"""
# Category, then its pages: title and Markdown
PAGES = {
    "Getting started": [
        ("Getting started", "## Your account\n\nAsk for an account, then read the pages under Start here.\n"),
        ("Find your way around", "## The sidebar\n\nPages and categories are on the left, the tools below them.\n"),
    ],
    "Product & design": [
        ("Design principles", DESIGN),
        ("Release notes", "## This week\n\n- Reader experience: in progress\n- Team handbook: ready for review\n"),
        ("Project notes", "## Open questions\n\n- Which pages do new people read first?\n"),
    ],
    "Engineering": [
        ("How we review changes", "## Before you ask\n\nSay what changed, and why.\n"),
        ("Release checklist", "## The day before\n\n1. Read the release notes.\n2. Try the real workflows.\n"),
    ],
    "Team handbook": [
        ("Working hours", "## Core hours\n\nWe overlap from ten to three.\n"),
    ],
}
BOARD = ("Workspace refresh", "The small improvements that make everyday work feel better.")
# Column, then its tickets; "@name" in a title assigns the ticket
TICKETS = {
    "To do": ["Polish page navigation @lena_weber", "Refresh the team handbook @marco_bianchi"],
    "In progress": ["Review mobile layouts @tom_keller", "Publish the November release @lena_weber"],
    "Done": ["Simplify editor controls @anna_ricci"],
}
CANVAS = {
    "title": "Product direction",
    "description": "A map of the ideas shaping our next release.",
    "data": {
        "nodes": [
            {"id": "idea", "type": "text", "x": 40, "y": 140, "width": 250, "height": 136, "layer": 1,
             "text_size": 19, "content": "## A calmer workspace\n\nClear navigation. Focused reading. Useful details."},
            {"id": "reading", "type": "text", "x": 380, "y": 60, "width": 240, "height": 116, "layer": 1,
             "content": "**Reading experience**\n\nLet the content lead. Keep actions close and quiet."},
            {"id": "tools", "type": "text", "x": 380, "y": 240, "width": 240, "height": 116, "layer": 1,
             "content": "**Everyday tools**\n\nCompact controls and predictable layouts."},
            {"id": "release", "type": "text", "x": 700, "y": 170, "width": 236, "height": 116, "layer": 1,
             "content": "**November release**\n\nReview the details, test real workflows and share the changes."},
        ],
        "edges": [
            {"id": "e1", "from": "idea", "to": "reading", "label": "clarity"},
            {"id": "e2", "from": "idea", "to": "tools", "label": "flow"},
            {"id": "e3", "from": "reading", "to": "release"},
            {"id": "e4", "from": "tools", "to": "release"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    },
}


# The hosting portal's wikis and the storage each one reports, in MB
HOSTED = {"team-handbook": 184, "onboarding": 46, "project-notes": 97}
HOSTED_USE = "The handbook, guides and notes of a small team."
BOOTSTRAP = "sample-data-only-first-account"
# Every hosted wiki is a Docker container that a privileged agent starts. This starts the portal with the
# in-memory runtime it ships for tests and demos instead: a wiki made on the New wiki form is recorded and
# reported as running, and no container exists. That runtime measures nothing, so the sizes come from HOSTED.
PORTAL = """
import json, sys
from bananawiki.hosting.app import create_app
from bananawiki.hosting.runtime.fake import FakeRuntime


class SampleRuntime(FakeRuntime):
    def provision(self, spec, **options):
        super().provision(spec, **options)
        self.tenants[spec.data_dir_name].usage = json.loads(sys.argv[2]).get(spec.slug, 0) * 1024 * 1024


create_app(runtime=SampleRuntime()).run(host="127.0.0.1", port=int(sys.argv[1]))
"""


def _api(token: str, method: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(f"{URL}/api/v1{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{method} {path}: {error.code} {error.read().decode(errors='replace')}") from None


def _wait(url: str) -> None:
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{url}/login").read()
            return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(.5)
    raise RuntimeError(f"{url} did not start")


def _token(page) -> str:
    """Switch the REST API on, as its owner does under Admin, and create a token for the sample data."""
    page.goto(f"{URL}/admin/plugins")
    page.click('form[action$="/admin/plugins/api_service/enable"] button')
    page.wait_for_load_state("load")
    page.goto(f"{URL}/settings/api-tokens")
    form = page.locator('form[action$="/settings/api-tokens/create"]')
    form.locator('input[name="name"]').fill("Sample data")
    for scope in form.locator('input[name="scopes"]').all():
        scope.check()
    form.locator('button[type="submit"]').click()
    page.wait_for_load_state("load")
    return page.locator(".alert--success code").inner_text().strip()


def _seed(token: str) -> dict:
    """Fill the wiki; returns the board's id, the canvas's slug and the slug of the page the editor opens."""
    for name in MEMBERS:
        _api(token, "POST", "/users", {"username": name, "password": PASSWORD})
    home = next(page["slug"] for page in _api(token, "GET", "/pages")["pages"] if page["is_home"])
    slugs = {}
    for category, pages in PAGES.items():
        category_id = _api(token, "POST", "/categories", {"name": category})["category"]["id"]
        for title, content in pages:
            slugs[title] = _api(token, "POST", "/pages", {"title": title, "content": content,
                                                          "category_id": category_id})["page"]["slug"]
    _api(token, "POST", "/pages", {"title": "Meeting notes", "content": "## Monday\n\n- Plan the week.\n"})
    _api(token, "PUT", f"/pages/{home}", {"title": "Our shared workspace", "content": HOME.format(**slugs)})
    # Keep the board private; the screenshots are taken by its administrator owner.
    board = _api(token, "POST", "/kanban/boards", {"title": BOARD[0], "description": BOARD[1],
                                                   "default_columns": False})["board"]["id"]
    for name, tickets in TICKETS.items():
        column = _api(token, "POST", f"/kanban/boards/{board}/columns", {"title": name})["column"]["id"]
        for title in tickets:
            _api(token, "POST", f"/kanban/columns/{column}/tickets", {"title": title})
    canvas = _api(token, "POST", "/canvas", CANVAS)["canvas"]["slug"]
    return {"board": board, "canvas": canvas, "design": slugs["Design principles"]}


def _picture(path: Path) -> None:
    """The sample picture of the design page: a window with a title bar, a panel and a round control."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (960, 400), "#1f2433")
    draw = ImageDraw.Draw(image)
    for x in range(0, 960, 40):
        draw.line([(x, 0), (x, 400)], fill="#262c3d")
    for y in range(0, 400, 40):
        draw.line([(0, y), (960, y)], fill="#262c3d")
    draw.rectangle([180, 60, 780, 340], fill="#e6bd2e")
    draw.rectangle([215, 95, 745, 145], fill="#1f2433")
    draw.rectangle([215, 175, 495, 300], fill="#f7dd88")
    draw.ellipse([545, 180, 720, 290], fill="#f7dd88")
    image.save(path)


def _editor(page, shoot, slug: str, tmp: Path) -> None:
    """Upload the picture at the top of the design page, then open its options from the preview."""
    picture = tmp / f"{IMAGE_ALT}.png"  # the editor takes the alternative text from the file's name
    _picture(picture)
    page.goto(f"{URL}/page/{slug}/edit")
    page.locator("#editor-content").evaluate("text => { text.focus(); text.setSelectionRange(0, 0); }")
    page.set_input_files("[data-image-input]", str(picture))
    image = page.locator("#editor-preview img")
    image.wait_for()
    page.keyboard.press("Enter")  # the cursor is after the picture: a blank line before the first heading
    page.locator("#editor-content").blur()
    shoot("editor.png")
    image.click()
    page.locator("dialog#dlg-image[open] [data-crop-box]:not([hidden])").wait_for()
    # The backdrop would dim the top bar. The wiki's content security policy refuses a <style> element,
    # so the rule goes in through a constructed style sheet
    page.evaluate("""() => {
        const sheet = new CSSStyleSheet();
        sheet.replaceSync("dialog::backdrop { background: transparent !important; backdrop-filter: none !important; }");
        document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
    }""")
    shoot("editor-images.png")
    page.click("dialog#dlg-image [data-image-apply]")
    page.click('main button[type="submit"]:not([formaction])')
    page.wait_for_url(f"{URL}/page/{slug}")


def _hosting(python: str, src: Path, tmp: Path, page, shoot) -> None:
    """The portal's dashboard: its first account, which is the administrator, with three wikis."""
    env = {**os.environ, "HOSTING_ENV": "development", "HOSTING_DATABASE_PATH": f"{tmp}/hosting/hosting.db",
           "HOSTING_SECRET_KEY_PATH": f"{tmp}/hosting/.secret_key", "INSTANCES_DIR": f"{tmp}/instances",
           "HOSTING_IMPORT_TEMP_DIR": f"{tmp}/imports", "HOSTING_EXPORT_TEMP_DIR": f"{tmp}/exports",
           "HOSTING_BOOTSTRAP_TOKEN": BOOTSTRAP, "BASE_DOMAIN": "example.org", "INSTANCE_URL_SUFFIX": "wikis"}
    server = subprocess.Popen([python, "-c", PORTAL, str(PORTAL_PORT), json.dumps(HOSTED)], cwd=src, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait(PORTAL_URL)
        page.goto(f"{PORTAL_URL}/signup?bootstrap_token={BOOTSTRAP}")
        page.fill('input[name="username"]', MEMBERS[0])
        page.fill('input[name="password"]', PASSWORD)
        page.fill('input[name="confirm_password"]', PASSWORD)
        page.check('input[name="accept_terms"]')
        page.wait_for_timeout(2000)  # the portal refuses a sign-up form sent within 1.5 seconds
        page.click('form[action$="/signup"] button[type="submit"]')
        page.wait_for_url(f"{PORTAL_URL}/dashboard")
        for name in HOSTED:
            page.goto(f"{PORTAL_URL}/instances/create")
            page.fill('input[name="subdomain"]', name)
            page.fill('textarea[name="declared_use_case"]', HOSTED_USE)
            page.check('input[name="compliance_declared"]')
            page.click('main form button[type="submit"]')
            page.wait_for_load_state("load")
        page.goto(f"{PORTAL_URL}/dashboard")
        shoot("hosting-dashboard.png")
    finally:
        server.terminate()
        server.wait(timeout=30)


def capture(src: Path, page, shoot) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "BW_INSTANCE_DIR": f"{tmp}/instance", "BW_MIN_FORM_SECONDS": "0"}
        python = str(src / ".venv" / "bin" / "python")
        wiki = [python, "-m", "bananawiki.cli"]
        run = lambda *args, **more: subprocess.run([*wiki, *args], check=True, capture_output=True, text=True,
                                                   cwd=src, env=env, **more)
        run("migrate")
        run("create-admin", USER, "--owner", input=PASSWORD + "\n")
        server = subprocess.Popen([*wiki, "serve", "--port", str(PORT)], cwd=src, env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            _wait(URL)
            page.goto(f"{URL}/login")
            page.fill('input[name="username"]', USER)
            page.fill('input[name="password"]', PASSWORD)
            page.press('input[name="password"]', "Enter")
            page.wait_for_url(f"{URL}/")
            made = _seed(_token(page))
            page.mouse.move(700, 24)  # off the buttons it clicked, onto the empty part of the top bar
            page.goto(f"{URL}/")
            shoot("wiki-home.png")
            page.goto(f"{URL}/kanban/{made['board']}")
            shoot("kanban.png")
            page.goto(f"{URL}/canvas/{made['canvas']}")
            shoot("canvas.png")
            page.goto(f"{URL}/admin/plugins")
            shoot("plugins.png")
            page.goto(f"{URL}/settings/display")
            shoot("wiki-customize.png")
            _editor(page, shoot, made["design"], Path(tmp))
        finally:
            server.terminate()
            server.wait(timeout=30)
        _hosting(python, src, Path(tmp), page, shoot)
