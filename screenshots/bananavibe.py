"""BananaVibe's screenshot: the dashboard of a real run, rendered from its terminal output.

SRC is a checkout (nothing to build). In a temporary directory, the real supervisor runs a small sample
project with two scripted stand-in agents, "worker" and "reviewer" (no model, no login, no network), for
two sessions and a checkpoint review. While the third session is under way, `bananavibe dashboard` runs in
a pseudo-terminal; its output goes through a terminal emulator (pyte) and the screen is drawn as HTML.
The run is then stopped, with autostart off, and the directory removed.
"""

from __future__ import annotations

import fcntl
import html
import json
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path

COLS, ROWS = 110, 32
NAME = "recipe-scaler"
GOAL = """# Mission

Make `scaler.py` scale a recipe to any number of servings.

## Definition of done

- Quantities such as `1 1/2` are read and written as fractions.
- `scale()` scales every ingredient and rejects a number of servings below one.
- `python3 scaler.py SERVINGS FILE` prints the scaled recipe.
- The tests cover all of it and pass.
"""
FILES = {
    "README.md": "# Recipe scaler\n\nScales the ingredients of a recipe to a number of servings.\n",
    "scaler.py": '"""Scale a recipe to a number of servings."""\n',
    "tests/__init__.py": "",
    "pancakes.txt": "serves 4\n1 1/2 cups flour\n2 eggs\n3/4 cup milk\n",
}
CONFIG = """[run]
name = "{name}"
workers = ["worker"]
reviewer = "reviewer"
checkpoint_every = 2
autostart = false

[[checks]]
name = "tests"
run = "{python} -m unittest -q"

[[checks]]
name = "syntax"
run = "{python} -m compileall -q ."

[agents.worker]
type = "custom"
command = ["{python}", "{agent}", "worker", "{{prompt_file}}"]

[agents.reviewer]
type = "custom"
command = ["{python}", "{agent}", "reviewer", "{{prompt_file}}"]
"""
TEST = ("import unittest\nfrom fractions import Fraction\n\nimport scaler\n\n\n"
        "class Test(unittest.TestCase):\n    def test(self):\n        {}\n")
# What the worker does, one plan item at a time: code added to scaler.py (or one line of it replaced) and a test.
STEPS = [
    {"item": "Read quantities such as `1 1/2` as fractions", "name": "parse",
     "code": "from fractions import Fraction\n\n\ndef parse_quantity(text):\n"
             "    return sum(Fraction(part) for part in text.split())\n",
     "test": 'self.assertEqual(scaler.parse_quantity("1 1/2"), Fraction(3, 2))'},
    {"item": "Write quantities back as mixed fractions", "name": "format",
     "code": "\n\ndef format_quantity(value):\n    whole, rest = divmod(Fraction(value), 1)\n"
             '    return " ".join(str(part) for part in (whole, rest) if part) or "0"\n',
     "test": 'self.assertEqual(scaler.format_quantity(Fraction(9, 4)), "2 1/4")'},
    {"item": "Read a recipe: its servings and its ingredient lines", "name": "read",
     "code": "\n\ndef read_recipe(lines):\n    items = []\n    for line in lines[1:]:\n        words = line.split()\n"
             "        n = 2 if words[1][0].isdigit() else 1\n"
             '        items.append((parse_quantity(" ".join(words[:n])), " ".join(words[n:])))\n'
             "    return int(lines[0].split()[1]), items\n",
     "test": 'self.assertEqual(scaler.read_recipe(["serves 4", "1 1/2 cups flour"]), '
             '(4, [(Fraction(3, 2), "cups flour")]))'},
    {"item": "Scale every ingredient to the servings asked for", "name": "scale",
     "code": "\n\ndef scale(items, servings, to):\n"
             "    return [(quantity * to / servings, name) for quantity, name in items]\n",
     "test": 'self.assertEqual(scaler.scale([(Fraction(3, 2), "cups flour")], 4, 6), '
             '[(Fraction(9, 4), "cups flour")])'},
    {"item": "Command line: `python3 scaler.py SERVINGS FILE` prints the scaled recipe", "name": "cli",
     "code": "\n\nif __name__ == \"__main__\":\n    import sys\n\n"
             "    servings, items = read_recipe(open(sys.argv[2]).read().splitlines())\n"
             "    for quantity, name in scale(items, servings, int(sys.argv[1])):\n"
             "        print(format_quantity(quantity), name)\n",
     "test": 'self.assertIn("scale(items, servings", open(scaler.__file__).read())'},
    {"item": "Describe the command in the README", "name": "readme",
     "readme": "\n```sh\npython3 scaler.py 6 pancakes.txt\n```\n"},
]
# What the reviewer finds at the checkpoint (by calling scale() with no servings), and how the worker fixes it.
FINDING = {"item": "Reject a number of servings below one (review finding)", "name": "servings",
           "replace": ["    return [(quantity * to",
                       "    if to < 1:\n        raise ValueError(\"servings must be at least 1\")\n"
                       "    return [(quantity * to"],
           "test": "self.assertRaises(ValueError, scaler.scale, [], 4, 0)"}
HOLD_SESSION = 3  # the worker session that waits, part done, while the dashboard is captured
# The stand-in agents: one script that follows BananaVibe's prompt protocol with the steps above. It makes the
# changes for real, runs the tests, ticks the plan and writes the handoff; as reviewer it tries the code.
AGENT = r'''
import json, re, shlex, subprocess, sys, time
from pathlib import Path

role, prompt = sys.argv[1], Path(sys.argv[2]).read_text()
here, run = Path(__file__).parent, Path(".bananavibe")
data = json.loads((here / "steps.json").read_text())
finding = data["finding"]


def say(text):
    print(text, flush=True)


def python(*args):
    say("$ python3 " + shlex.join(args))
    done = subprocess.run([sys.executable, *args], capture_output=True, text=True)
    lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip("-")]
    say("  " + " ".join(lines[-2:] if args[0] == "-m" else lines[-1:]))
    return done.returncode == 0


say(f"sample agent `{role}`: a scripted stand-in for a coding agent, no model involved")
if role == "reviewer":
    python("-m", "unittest", "-q")
    accepted = python("-c", "import scaler; print(scaler.scale([], 4, 0))")
    notes = [f"`scaler.py`: `scale()` accepts 0 servings. {finding['item'][:-17]}, and test it."] * accepted
    notes.append("The command line and the README are still open in the plan.")
    review = "VERDICT: CHANGES_REQUESTED\n\n" + "".join(f"{n}. {note}\n" for n, note in enumerate(notes, 1))
    (run / "REVIEW.md").write_text(review)
    say("wrote .bananavibe/REVIEW.md: changes requested, " + str(len(notes)) + " findings")
    sys.exit(0)
'''
AGENT += r'''
plan, steps = run / "PLAN.md", data["steps"]
text = plan.read_text()
if not re.search(r"(?m)^- \[", text):
    text += "\n" + "".join(f"- [ ] {step['item']}\n" for step in steps)
    say(f"audited the workspace and wrote the plan: {len(steps)} items")
if "Checkpoint review" in prompt and finding["item"] not in text:
    text = text.replace("- [ ] ", f"- [ ] {finding['item']}\n- [ ] ", 1)
    say("added the reviewer's finding to the plan")
plan.write_text(text)
notes = run / "NOTES.md"
if "unittest" not in notes.read_text():
    notes.write_text(notes.read_text() + "\nRun the tests with `python3 -m unittest -q`.\n")
session = int(re.search(r"session (\d+) of", prompt).group(1))
done = []
count = 3 if "Checkpoint review" in prompt else 2  # a review finding comes on top of the usual two items
for number, step in enumerate([s for s in [finding, *steps] if f"- [ ] {s['item']}" in text][:count]):
    say(f"next: {step['item']}")
    source = Path("scaler.py")
    if "code" in step:
        source.write_text(source.read_text() + step["code"])
    if "replace" in step:
        source.write_text(source.read_text().replace(*step["replace"]))
    if "readme" in step:
        Path("README.md").write_text(Path("README.md").read_text() + step["readme"])
    if "test" in step:
        Path(f"tests/test_{step['name']}.py").write_text(data["test"].format(step["test"]))
    say("edited " + ("README.md" if "readme" in step else f"scaler.py, tests/test_{step['name']}.py"))
    if session == data["hold"] and number == 2 and (here / "hold").exists():
        (here / "holding").touch()  # the dashboard is captured now, with this session part done
        for _ in range(600):
            if not (here / "hold").exists():
                break
            time.sleep(.2)
    if not python("-m", "unittest", "-q"):
        break
    text = text.replace(f"- [ ] {step['item']}", f"- [x] {step['item']}")
    plan.write_text(text)
    done.append(step["item"])
    say(f"ticked in the plan: {step['item']}")
left = re.findall(r"- \[ \] (.+)", text)
(run / "HANDOFF.md").write_text("Done and tested this session:\n" + "".join(f"- {item}\n" for item in done)
                                + "\nNext: " + (left[0] if left else "nothing, every item is done.") + "\n")
say("wrote .bananavibe/HANDOFF.md")
if not left:
    (run / "DONE.md").write_text("Every plan item is done. `python3 -m unittest -q` passes.\n")
    say("wrote .bananavibe/DONE.md")
'''


def _python() -> str:
    """An interpreter for BananaVibe, which needs Python 3.11: this one, or the newest on PATH."""
    if sys.version_info >= (3, 11):
        return sys.executable
    for minor in range(14, 10, -1):
        found = shutil.which(f"python3.{minor}")
        if found:
            return found
    raise RuntimeError("BananaVibe needs Python 3.11 or later")


def _wait(what: str, ready, seconds: float = 90) -> None:
    deadline = time.monotonic() + seconds
    while not ready():
        if time.monotonic() > deadline:
            raise RuntimeError(f"BananaVibe: {what} did not happen in {seconds:.0f} s")
        time.sleep(.2)


def _dashboard(command: list[str], env: dict, cwd: Path) -> bytes:
    """Everything `bananavibe dashboard` writes to a COLS x ROWS terminal in a few seconds, until `q` quits it."""
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=env, cwd=cwd,
                               start_new_session=True)
    os.close(slave)
    output, deadline, asked = b"", time.monotonic() + 30, False
    try:
        while process.poll() is None and time.monotonic() < deadline:
            if select.select([master], [], [], .2)[0]:
                try:
                    output += os.read(master, 65536)
                except OSError:  # Linux: the terminal closed
                    break
            # Two full frames, a second apart, then quit
            if not asked and output.count(b"\x1b[H") >= 3:
                os.write(master, b"q")
                asked = True
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        os.close(master)
    return output


FOREGROUND, BACKGROUND = "#d6d6d6", "#141414"
COLOURS = {"black": "#141414", "red": "#f1707b", "green": "#7fd88f", "brown": "#e5c07b", "blue": "#6cb6ff",
           "magenta": "#d7a1f9", "cyan": "#6fd3d8", "white": FOREGROUND, "brightblack": "#8b8b8b"}
PAGE = """<!doctype html><meta charset="utf-8"><style>
html, body {{ margin: 0; height: 100%; overflow: hidden; background: {background}; }}
pre {{ margin: 0; width: {cols}ch; color: {foreground}; transform-origin: 0 0; white-space: pre;
      font: {size:.2f}px/{line}px ui-monospace, "SFMono-Regular", Menlo, Consolas, "Liberation Mono", monospace; }}
pre div {{ height: {line}px; overflow: hidden; }}
i {{ display: inline-block; font-style: normal; text-align: center; vertical-align: top; }}
</style><pre>{rows}</pre>"""


def _colour(name: str, default: str) -> str:
    if name == "default":
        return default
    return COLOURS.get(name) or COLOURS.get(name.replace("bright", ""), "") or f"#{name}"


def _html(output: bytes) -> str:
    """The terminal's screen after OUTPUT, as a page: one row per line, colours, bold and reverse kept."""
    import pyte

    screen = pyte.Screen(COLS, ROWS)
    # Up to where it leaves the full-screen view; pyte has no dim text, so that becomes grey
    pyte.ByteStream(screen).feed(output.split(b"\x1b[?1049l")[0].replace(b"\x1b[2m", b"\x1b[90m"))
    rows = []
    for y in range(ROWS):
        row, last = "", None
        for x in range(COLS):
            cell = screen.buffer[y][x]
            if not cell.data:  # the second half of a wide character
                continue
            fg, bg = _colour(cell.fg, FOREGROUND), _colour(cell.bg, BACKGROUND)
            if cell.reverse:
                fg, bg = bg, fg
            style = f"color:{fg};background:{bg}" + (";font-weight:bold" if cell.bold else "")
            if style != last:
                row += ("</span>" if last else "") + f'<span style="{style}">'
                last = style
            text = html.escape(cell.data)
            # Anything but ASCII gets a box as wide as its cells, whatever font ends up drawing it
            wide = x + 1 < COLS and not screen.buffer[y][x + 1].data
            row += text if cell.data.isascii() else f'<i style="width:{2 if wide else 1}ch">{text}</i>'
        rows.append(f"<div>{row}</span></div>")
    return PAGE.format(rows="".join(rows), cols=COLS, line=800 // ROWS, size=1280 / COLS / .6, foreground=FOREGROUND,
                       background=BACKGROUND)


def _stop(run: Path) -> None:
    """Kill whatever supervisor or guardian of this run is still alive (after `stop`, none should be)."""
    for file in ("guardian.json", "heartbeat.json", "state.json"):
        try:
            pid = json.loads((run / file).read_text(encoding="utf-8")).get("pid")
            os.kill(int(pid), signal.SIGKILL)
        except (OSError, ValueError, TypeError):
            pass


def capture(src: Path, page, shoot) -> None:
    python = _python()
    # In /tmp where there is one, for a short path in the picture
    with tempfile.TemporaryDirectory(prefix="bananavibe-", dir="/tmp" if Path("/tmp").is_dir() else None) as tmp:
        work, agent = Path(tmp) / NAME, Path(tmp) / "agent.py"
        # The dashboard names the machine it runs on: give the run a sample name, so that the picture
        # never shows the name of whoever's computer or CI runner took it
        site = Path(tmp) / "site"
        site.mkdir()
        (site / "sitecustomize.py").write_text('import socket\n\nsocket.gethostname = lambda: "devbox"\n',
                                               encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": f"{site}{os.pathsep}{src}", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
               "TERM": "xterm-256color", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
               # Nothing outside the temporary directory: no state in the home directory, no systemd or cron
               "BANANAVIBE_STATE_DIR": f"{tmp}/state", "BANANAVIBE_AUTOSTART_KIND": "none",
               "GIT_AUTHOR_NAME": "Sample", "GIT_AUTHOR_EMAIL": "sample@example.org",
               "GIT_COMMITTER_NAME": "Sample", "GIT_COMMITTER_EMAIL": "sample@example.org"}
        env.pop("NO_COLOR", None)
        run = lambda *args: subprocess.run(args, check=True, capture_output=True, text=True, cwd=work, env=env)
        vibe = [python, "-m", "bananavibe"]
        for path, content in {**FILES, ".gitignore": "__pycache__/\n"}.items():
            (work / path).parent.mkdir(parents=True, exist_ok=True)
            (work / path).write_text(content, encoding="utf-8")
        agent.write_text(AGENT, encoding="utf-8")
        (Path(tmp) / "steps.json").write_text(json.dumps(
            {"steps": STEPS, "finding": FINDING, "test": TEST, "hold": HOLD_SESSION}), encoding="utf-8")
        (Path(tmp) / "hold").touch()
        run("git", "init", "-q", "-b", "main")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "Start the recipe scaler")
        run(*vibe, "init", "--name", NAME, "--goal", GOAL)
        (work / ".bananavibe" / "config.toml").write_text(
            CONFIG.format(name=NAME, python=python, agent=agent), encoding="utf-8")
        try:
            run(*vibe, "start", "--no-autostart")
            _wait(f"session {HOLD_SESSION}", (Path(tmp) / "holding").exists)
            output = _dashboard([*vibe, "dashboard"], env, work)
        finally:
            subprocess.run([*vibe, "stop", "--now", "--wait", "--wait-timeout", "60"], capture_output=True,
                           cwd=work, env=env)
            _stop(work / ".bananavibe")
    page.set_content(_html(output))
    # Stretch the text to the viewport's width exactly, whichever of the fonts was found
    page.evaluate("""() => { const pre = document.querySelector("pre");
        pre.style.transform = `scaleX(${innerWidth / pre.getBoundingClientRect().width})`; }""")
    shoot("bananavibe.png")
