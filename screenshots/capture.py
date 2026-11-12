"""Recapture an app's screenshots from a disposable instance and update the pages that show them.

    python3 screenshots/capture.py --outdated            # apps whose repository moved since their last capture
    python3 screenshots/capture.py bananagit --src DIR   # capture from a built checkout in DIR
    python3 screenshots/capture.py bananagit --src DIR --out /tmp/shots   # try a module, change nothing here

apps.json lists the apps: their repository, the commit the published screenshots were taken from, and
whether this directory has a capture module for them (NAME.py with a capture(src, page, shoot) function).
After a capture, every page's ?v= version and width/height for the changed images are rewritten, and
the commit is recorded. Needs Playwright with Chromium, and Pillow; BananaVibe's module also needs pyte.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
APPS = HERE / "apps.json"
VIEWPORT = {"width": 1280, "height": 800}


def _apps() -> dict:
    return json.loads(APPS.read_text(encoding="utf-8"))


def _head(repo: str) -> str:
    out = subprocess.run(["git", "ls-remote", f"https://github.com/{repo}.git", "HEAD"],
                         check=True, capture_output=True, text=True).stdout
    return out.split()[0]


def outdated() -> list[str]:
    """The apps whose repository's HEAD is not the commit their screenshots were taken from."""
    return [name for name, app in _apps().items() if _head(app["repo"]) != app.get("commit")]


def _compress(path: Path) -> None:
    from PIL import Image

    Image.open(path).save(path, optimize=True)
    if shutil.which("oxipng"):
        subprocess.run(["oxipng", "-q", "-o", "max", "--strip", "safe", str(path)], check=True)


def _png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def update_pages(names: list[str]) -> None:
    """Point every page at the new files: the ?v= version and the width and height of each image."""
    pages = [path for path in ROOT.rglob("*.html") if ".git" not in path.parts]
    for name in names:
        image = ROOT / "img" / name
        version = hashlib.sha256(image.read_bytes()).hexdigest()[:12]
        width, height = _png_size(image)
        ref = re.escape(f"img/{name}")
        for page in pages:
            html = page.read_text(encoding="utf-8")
            new = re.sub(rf"({ref}\?v=)[0-9a-f]{{12}}", rf"\g<1>{version}", html)
            new = re.sub(rf'(<img src="[^"]*{ref}\?[^"]*"[^>]*?) width="\d+" height="\d+"',
                         rf'\g<1> width="{width}" height="{height}"', new)
            if new != html:
                page.write_text(new, encoding="utf-8")


def capture(name: str, src: Path, out: Path | None = None) -> list[str]:
    from playwright.sync_api import sync_playwright

    module = importlib.import_module(name)
    target = out or ROOT / "img"
    target.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport=VIEWPORT, color_scheme="dark", locale="en-GB",
                                      timezone_id="Europe/Rome", device_scale_factor=1)
        page = context.new_page()

        def shoot(file: str, *, full_page: bool = False) -> None:
            """Save the page as img/FILE: the 1280x800 viewport, or the whole page at that width."""
            # Not "networkidle": apps that keep an event stream open never reach it
            page.wait_for_load_state("load")
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(750)
            page.screenshot(path=str(target / file), full_page=full_page, animations="disabled")
            written.append(file)

        try:
            module.capture(src.resolve(), page, shoot)
        finally:
            browser.close()
    for file in written:
        _compress(target / file)
    if out is None:
        update_pages(written)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("app", nargs="?")
    parser.add_argument("--src", type=Path, help="a built checkout of the app")
    parser.add_argument("--out", type=Path, help="write the images here and leave the site as it is")
    parser.add_argument("--outdated", action="store_true", help="list apps to recapture, as JSON")
    args = parser.parse_args()
    apps = _apps()
    if args.outdated:
        names = outdated()
        print(json.dumps({"capture": [name for name in names if apps[name]["module"]],
                          "no_module": [name for name in names if not apps[name]["module"]]}))
        return 0
    if args.app not in apps or not apps[args.app]["module"] or not args.src:
        parser.error("name an app that has a capture module, and --src")
    sys.path.insert(0, str(HERE))
    written = capture(args.app, args.src, args.out)
    if args.out:
        print(f"{args.app}: wrote {', '.join(written)} to {args.out}")
        return 0
    commit = subprocess.run(["git", "-C", str(args.src), "rev-parse", "HEAD"],
                            check=True, capture_output=True, text=True).stdout.strip()
    apps[args.app]["commit"] = commit
    APPS.write_text(json.dumps(apps, indent=2) + "\n", encoding="utf-8")
    print(f"{args.app}: wrote {', '.join(written)} from {commit[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
