"""BananaGit's screenshots: a repository, its issues and a pull request, from a throwaway server.

SRC is a checkout built with `TAGS="sqlite sqlite_unlock_notify" make build`. The server gets its own
SQLite database and data in a temporary directory, one account and one sample repository.
"""

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PORT = 3917
URL = f"http://127.0.0.1:{PORT}"
USER, PASSWORD, EMAIL = "anna_ricci", "sample-data-only-4821", "anna@example.org"
REPO = "team-handbook"

README = """# Team handbook

The ideas, decisions and practical details that help us work well together.

## Start here

- [Getting started](docs/getting-started.md): set up your account and find your way around
- [Design principles](docs/design-principles.md): how we make product decisions
- [Release notes](docs/release-notes.md): what changed and what comes next

## Building the site

```sh
python3 build.py
python3 -m http.server --directory public
```
"""
FILES = {
    "docs/getting-started.md": "# Getting started\n\nAsk for an account, then read the pages under Start here.\n",
    "docs/design-principles.md": "# Design principles\n\n1. Write things down.\n2. Keep every revision.\n",
    "docs/release-notes.md": "# Release notes\n\n## This week\n\n- Reader experience: in progress\n",
    "build.py": '"""Builds the handbook into public/."""\n\nfrom pathlib import Path\n\n'
                'for page in sorted(Path("docs").glob("*.md")):\n    print("building", page)\n',
    ".gitignore": "public/\n__pycache__/\n",
}
ISSUES = [
    ("Add a page about how we review changes", "We explain it to every new person. It should be a page."),
    ("Release notes: link each item to its page", "Readers ask where to find the details."),
    ("Build fails when docs/ has a subfolder", "`build.py` only looks at the top level of `docs/`."),
    ("Dark theme for the built site", "Follow the reader's system setting."),
]
PATCH = ('"""Builds the handbook into public/."""\n\nfrom pathlib import Path\n\n'
         '# Pages can live in subfolders of docs/\n'
         'for page in sorted(Path("docs").rglob("*.md")):\n    print("building", page)\n')


def _api(token: str, method: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(f"{URL}/api/v1{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"token {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read() or b"{}")


def _wait() -> None:
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{URL}/api/v1/version").read()
            return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(.5)
    raise RuntimeError("BananaGit did not start")


def _seed(token: str) -> None:
    def put(path: str, content: str, **extra: str) -> None:
        _api(token, "POST", f"/repos/{USER}/{REPO}/contents/{path}",
             {"content": base64.b64encode(content.encode()).decode(), "message": f"Add {path}", **extra})

    _api(token, "POST", "/user/repos", {"name": REPO, "description": "How our team works: guides, decisions and "
                                        "release notes", "auto_init": True, "default_branch": "main"})
    for path, content in FILES.items():
        put(path, content)
    sha = _api(token, "GET", f"/repos/{USER}/{REPO}/contents/README.md")["sha"]
    _api(token, "PUT", f"/repos/{USER}/{REPO}/contents/README.md",
         {"content": base64.b64encode(README.encode()).decode(), "message": "Write the README", "sha": sha})
    for title, body in ISSUES:
        _api(token, "POST", f"/repos/{USER}/{REPO}/issues", {"title": title, "body": body})
    sha = _api(token, "GET", f"/repos/{USER}/{REPO}/contents/build.py")["sha"]
    _api(token, "PUT", f"/repos/{USER}/{REPO}/contents/build.py",
         {"content": base64.b64encode(PATCH.encode()).decode(), "message": "Build pages in subfolders of docs/",
          "sha": sha, "branch": "main", "new_branch": "build-subfolders"})
    _api(token, "POST", f"/repos/{USER}/{REPO}/pulls",
         {"head": "build-subfolders", "base": "main", "title": "Build pages in subfolders of docs/",
          "body": "Closes #3. `rglob` finds the pages in subfolders too."})


def capture(src: Path, page, shoot) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "app.ini"
        config.write_text(f"""
WORK_PATH = {tmp}
[server]
HTTP_ADDR = 127.0.0.1
HTTP_PORT = {PORT}
ROOT_URL = {URL}/
STATIC_ROOT_PATH = {src}
OFFLINE_MODE = true
[database]
DB_TYPE = sqlite3
PATH = {tmp}/bananagit.db
[security]
INSTALL_LOCK = true
[service]
DISABLE_REGISTRATION = true
[log]
LEVEL = Warn
""", encoding="utf-8")
        gitea = [str(src / "gitea"), "--config", str(config), "--work-path", tmp]
        run = lambda *args: subprocess.run([*gitea, *args], check=True, capture_output=True, text=True, cwd=src).stdout
        run("migrate")
        run("admin", "user", "create", "--username", USER, "--password", PASSWORD, "--email", EMAIL, "--admin",
            "--must-change-password=false")
        token = run("admin", "user", "generate-access-token", "--username", USER, "--scopes", "all", "--raw").strip()
        server = subprocess.Popen([*gitea, "web"], cwd=src, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            _wait()
            _seed(token.splitlines()[-1])
            page.goto(f"{URL}/user/login")
            page.fill("#user_name", USER)
            page.fill("#password", PASSWORD)
            page.press("#password", "Enter")
            page.wait_for_url(f"{URL}/")
            page.goto(f"{URL}/{USER}/{REPO}")
            shoot("bananagit.png")
            page.goto(f"{URL}/{USER}/{REPO}/issues")
            shoot("bananagit-issues.png")
            page.goto(f"{URL}/{USER}/{REPO}/pulls/5/files")
            shoot("bananagit-pull-request.png")
        finally:
            server.terminate()
            server.wait(timeout=30)
