"""BananaChat's screenshots: a conversation, the model picker, Appearance, a cloud session, the API
page, the external providers and a Claude Code subscription pool, from a throwaway instance.

SRC is a checkout built with
`python3 -m venv .venv && .venv/bin/python -m pip install -q --only-binary=:all: -r requirements.txt`.
This file is also the instance: `SRC/.venv/bin/python bananachat.py --serve DIR` builds the app on an
empty instance directory, seeds it through the app's own Python code and serves it on PORT. Nothing
real stands behind it: the model server and the sandbox runner are the imitations from the app's own
tests (tests/app/fake_ollama.py, fake_runner.py), and the Claude Code CLI is a small stand-in that
answers the login check, the model list and the usage report. No provider is ever contacted.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PORT = 3930
URL = f"http://127.0.0.1:{PORT}"
ADMIN, USER, PASSWORD = "anna", "amir", "sample-data-only-4821"

QUESTION = "Help me turn this launch into a clear plan for our team."
THINKING = ("The team needs a short plan they can act on this week. Three steps are enough: scope, owners "
            "and a rehearsal, then the date.")
ANSWER = """## This week

1. **Lock the scope.** Agree on the three things the launch must include, and park everything else for the next release.
2. **Name an owner for each task.** Every item gets one person and a date, so nothing waits on a vague "we".
3. **Rehearse the announcement.** Walk through the post, the email and the support answers together on Thursday.

Once these are in place, the team can ship on Friday with a short checklist instead of a long meeting."""
# Older conversations in the history: title, question, answer
HISTORY = [
    ("Notes from the team", "Summarise these notes from the team meeting in three points.",
     "1. The beta opens on Monday.\n2. Support answers are drafted.\n3. The pricing page needs one more review."),
    ("Research checklist", "What should I check before I cite a source?",
     "- Who wrote it, and when\n- Whether the claim appears in the original\n- Whether a second source agrees"),
]
MODELS = {  # the model server's models: name -> (display name, parameters, capabilities)
    "qwen3:8b": ("Qwen3 8B", "8.2B", ["completion", "thinking", "tools"]),
    "llama3.2:3b": ("Llama 3.2 3B", "3.2B", ["completion", "tools"]),
    "gemma3:12b": ("Gemma 3 12B", "12.2B", ["completion", "vision"]),
    "mistral-small:24b": ("Mistral Small 24B", "24B", ["completion", "tools"]),
}
PROVIDERS = [  # name, preset, model id, display name, reads images
    ("OpenRouter", "openrouter", "meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B", False),
    ("Anthropic", "anthropic", "claude-sonnet-4-5", "Claude Sonnet 4.5", True),
    ("OpenAI", "openai", "gpt-4.1-mini", "GPT-4.1 mini", True),
]
TASK = "Prepare release notes"
RELEASE = """# Release notes

## Highlights

- Faster answers from local models
- New developer API keys page
- Cloud sessions for longer tasks

## Fixes

- Chat titles no longer repeat the first answer
"""
STEPS = [  # what the model does in the cloud session, one reply per step
    {"content": "I will draft the release notes and check the workspace.",
     "tool_calls": [{"name": "write_file", "arguments": {"path": "/workspace/RELEASE.md", "content": RELEASE}}]},
    {"tool_calls": [{"name": "bash", "arguments": {"command": "wc -l RELEASE.md"}}]},
    {"tool_calls": [{"name": "finish", "arguments": {
        "summary": "Wrote **RELEASE.md** with the highlights and fixes for this release."}}]},
]
# The subscription pool: account, priority, 5-hour and weekly budget, % used of the 5-hour and weekly allowance
POOL = [
    ("Studio account", 10, 2_000_000, 12_000_000, 28, 42),
    ("Team account", 5, 1_500_000, 9_000_000, 59, 65),
    ("Backup account", 0, 800_000, 5_000_000, 6, 12),
]
CLAUDE_MODELS = [("claude-fable-5-1", "Claude Fable 5.1"), ("claude-opus-5-5", "Claude Opus 5.5"),
                 ("claude-sonnet-5-5", "Claude Sonnet 5.5"), ("claude-opus-4-1", "Claude Opus 4.1"),
                 ("claude-sonnet-4-5", "Claude Sonnet 4.5"), ("claude-haiku-4-5", "Claude Haiku 4.5")]
# Stands in for the Claude Code CLI: `auth status --json`, and the control requests the pool sends
# (initialize: the models; get_usage: the subscription's remaining allowance). Its answers are in
# cli.json in the profile's home.
CLAUDE_CLI = r'''
import json, os, sys
from pathlib import Path
if sys.argv[1:] == ["--version"]:
    print("0.0.0 (stand-in for the screenshots)")
    sys.exit(0)
answers = json.loads((Path(os.environ["HOME"]) / "cli.json").read_text())
if sys.argv[1:3] == ["auth", "status"]:
    print(json.dumps(answers["status"]))
    sys.exit(0)
for line in sys.stdin.read().splitlines():
    request = json.loads(line)
    print(json.dumps({"type": "control_response", "response": {
        "subtype": "success", "request_id": request["request_id"],
        "response": answers[request["request"]["subtype"]]}}), flush=True)
'''


# ── The instance (runs under SRC/.venv/bin/python, in SRC) ──────────────────


def _claude_pool(tmp: Path) -> dict:
    """Private profiles and a manifest for the stand-in CLI; returns the app's settings for them."""
    from datetime import datetime, timedelta, timezone

    binary = tmp / "claude"
    binary.write_text(f"#!{sys.executable}\n{CLAUDE_CLI}", encoding="utf-8")
    binary.chmod(0o700)
    now = datetime.now(timezone.utc)
    reset = lambda hours: (now + timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0).isoformat()
    models = [{"value": name, "resolvedModel": name, "displayName": display, "supportsEffort": True,
               "supportedEffortLevels": ["low", "medium", "high"]} for name, display in CLAUDE_MODELS]
    profiles = {}
    for number, (label, _, _, _, window, weekly) in enumerate(POOL, 1):
        home = tmp / "claude-profiles" / f"account-{number}"
        config = home / "config"
        config.mkdir(parents=True)
        home.chmod(0o700)
        config.chmod(0o700)
        (home / "cli.json").write_text(json.dumps({
            "status": {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty",
                       "subscriptionType": "max", "email": f"account-{number}@example.org"},
            "initialize": {"models": models},
            "get_usage": {"subscription_type": "max", "rate_limits_available": True, "rate_limits": {
                "five_hour": {"utilization": window, "resets_at": reset(3)},
                "seven_day": {"utilization": weekly, "resets_at": reset(96)}}},
        }), encoding="utf-8")
        # Where the CLI notes when it last fetched the usage
        cache = config / ".claude.json"
        cache.write_text(json.dumps({"cachedUsageUtilization": {"fetchedAtMs": int(time.time() * 1000)}}))
        cache.chmod(0o600)
        profiles[label] = {"home": str(home), "config_dir": str(config)}
    managed = tmp / "claude-managed"  # where profiles signed in from the page would go
    managed.mkdir(mode=0o700)
    manifest = tmp / "claude-code.json"
    manifest.write_text(json.dumps({"binary": str(binary), "profiles": profiles, "managed_root": str(managed)}),
                        encoding="utf-8")
    manifest.chmod(0o600)
    return {"BC_CLAUDE_EXTENSION": "bananachat.services.claude_code", "BC_CLAUDE_CODE_CONFIG": str(manifest)}


def _word_count(box, command: str, timeout) -> dict:
    """The imitation runner runs nothing; answer the session's one command from the sandbox's files."""
    words = command.split()
    data = box.files.get("/workspace/" + words[-1]) if words[:2] == ["wc", "-l"] else None
    if data is None:
        return {"exit_code": 127, "stderr": "command not found\n", "duration_ms": 1}
    return {"stdout": "%d %s\n" % (data.count(b"\n"), words[-1]), "duration_ms": 1}


def serve(tmp: Path) -> None:
    sys.path.insert(0, os.getcwd())
    from tests.app.fake_ollama import FakeOllama
    from tests.app.fake_runner import TOKEN, FakeRunner

    from bananachat import create_app, db, security
    from bananachat.config import load_config
    from bananachat.db import access, catalog, chats, settings, tokens, users
    from bananachat.db import external_providers as provider_store
    from bananachat.db import subscription_pool as pool_store
    from bananachat.services import external_providers, ollama, provider_presets, subscription_pool
    from bananachat.services.agents import service as agents
    from bananachat.services.agents import settings as agent_settings

    fake = FakeOllama()
    fake.models = list(MODELS)
    fake.details = {name: {"parameter_size": size, "family": name.split(":")[0].rstrip("0123456789.")}
                    for name, (_, size, _) in MODELS.items()}
    fake.capabilities = {name: caps for name, (_, _, caps) in MODELS.items()}
    fake.reply, fake.thinking, fake.chunk_delay = ANSWER, THINKING, 0.005
    fake.tool_responder = lambda body: STEPS[min(sum(m["role"] == "tool" for m in body["messages"]), len(STEPS) - 1)]
    fake.start()
    runner = FakeRunner()
    runner.exec_handler = _word_count
    runner.start()
    token = tmp / "runner.token"
    token.write_text(TOKEN)
    token.chmod(0o600)

    app = create_app(load_config({
        "BC_INSTANCE_DIR": str(tmp / "instance"), "BC_OLLAMA_URL": fake.url, "BC_ENV": "testing",
        "BC_SECRET_KEY": "sample-data-only-0123456789abcdef0123456789abcdef", "BC_LOGGING_LEVEL": "minimal",
        "BC_MIN_FREE_MEMORY_MB": "0", "BC_DEFAULT_LANGUAGE": "en",
        "BC_AGENTS_RUNNER_URL": runner.url, "BC_AGENTS_RUNNER_TOKEN_FILE": str(token), **_claude_pool(tmp)}))
    with app.test_request_context():
        with db.transaction():
            admin = users.create(ADMIN, security.hash_password(PASSWORD), role="admin")
            user = users.create(USER, security.hash_password(PASSWORD))
            settings.update(setup_done=1, site_name="BananaChat")
        ollama.sync_catalog()
        for name, preset, model, display, vision in PROVIDERS:
            preset = provider_presets.get(preset)
            provider = provider_store.get(provider_store.save(
                None, name=name, preset=preset.key, protocol=preset.protocol, base_url=preset.base_url,
                auth_style=preset.auth_style, extra_headers="{}", enabled=1, secret_ref=None))
            external_providers.enroll(provider, model, display=display, vision=vision, manual=True)
        for model in catalog.list_models():
            if model["ollama_name"] in MODELS:
                catalog.update(model["id"], display_name=MODELS[model["ollama_name"]][0])
            catalog.set_rollout(model["id"], True)
        order = {name: place for place, name in enumerate(
            ["Claude Sonnet 4.5", "GPT-4.1 mini", "Llama 3.3 70B", *(display for display, _, _ in MODELS.values())])}
        catalog.reorder([model["id"] for model in sorted(catalog.list_models(),
                                                         key=lambda model: order[model["display_name"]])])
        qwen = catalog.get_by_name("qwen3:8b")
        for title, question, answer in HISTORY:
            session = chats.create(admin)
            chats.add_message(session, "user", question, user_id=admin, incognito=False)
            chats.add_message(session, "assistant", answer, user_id=admin, incognito=False, model_id=qwen["id"])
            chats.rename(session, title)
        keys = [tokens.create(user, name)[1] for name in ("Laptop script", "Course notebook")]
        agents.refresh_model_capabilities(force=True)
        agent_settings.save({"enabled": True, "access_mode": "custom"}, None)
        for person in (admin, user):
            access.add_membership("agents", 0, person, "allowlist", added_by=None)
        bindings = {}
        for label, priority, window, weekly, _, _ in POOL:
            bindings[str(pool_store.add_account(label, priority=priority, window_limit=window,
                                                weekly_limit=weekly))] = label
        from bananachat.services.claude_code import BINDINGS_KEY
        settings.state_set(BINDINGS_KEY, bindings)
        subscription_pool.invalidate("claude")
    for key in keys:  # use each API key once, so the API page has usage to show
        answer = app.test_client().post("/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json={
            "model": "llama3.2:3b", "messages": [{"role": "user", "content": QUESTION}]})
        assert answer.status_code == 200, answer.get_data(as_text=True)
    app.run(host="127.0.0.1", port=PORT, threaded=True, use_reloader=False)


# ── The capture ─────────────────────────────────────────────────────────────


def _wait(server: subprocess.Popen) -> None:
    for _ in range(240):
        if server.poll() is not None:
            raise RuntimeError("BananaChat stopped while starting")
        try:
            urllib.request.urlopen(f"{URL}/health").read()
            return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(.5)
    raise RuntimeError("BananaChat did not start")


def _sign_in(page, username: str) -> None:
    page.context.clear_cookies()
    page.goto(f"{URL}/login")
    page.fill("#username", username)
    page.fill("#password", PASSWORD)
    page.wait_for_timeout(600)  # the form refuses to be filled in faster than a person could
    page.click("button[type=submit]")
    page.wait_for_url(f"{URL}/chat/*")


def _conversation(page, shoot) -> None:
    """Ask the question in a new chat, let the answer stream in and name the chat."""
    page.click("#model-button")
    page.click("#model-list .model-option >> text=Qwen3 8B")
    page.fill("#chat-input", QUESTION)
    page.click("#send-button")
    page.wait_for_selector("#stop-button:not([hidden])")
    page.wait_for_selector("#send-button:not([hidden])", timeout=60000)
    page.click("#chat-menu-button")
    page.click("#popup-menu >> text=Rename")
    page.fill("#dialog-input", "Plan the launch")
    page.press("#dialog-input", "Enter")
    page.wait_for_selector("#dialog-input", state="detached")
    page.reload()
    page.wait_for_selector("#chat-messages .message")
    shoot("bananachat.png")
    page.click("#model-button")
    page.wait_for_selector("#model-popover:not([hidden])")
    shoot("bananachat-models.png")
    page.keyboard.press("Escape")


def _cloud_session(page, shoot) -> None:
    page.goto(f"{URL}/agents")
    page.fill("#task-prompt", TASK)
    page.select_option("#task-model", label="Llama 3.2 3B")
    page.click("#new-task-submit")
    page.wait_for_url(f"{URL}/agents/*")
    page.wait_for_selector("#task-status[data-status=finished]", timeout=60000)
    page.wait_for_selector(".ws-entry:has-text('RELEASE.md')", timeout=20000)
    page.reload()
    page.wait_for_selector(".ws-entry:has-text('RELEASE.md')", timeout=20000)
    page.click(".tool-call summary >> nth=0")
    page.wait_for_selector(".tool-body")
    # The message box sticks to the bottom of the window, and a full-page capture would leave it in the
    # middle of the activity: make the window as tall as the page instead
    size = page.viewport_size
    page.set_viewport_size({**size, "height": page.evaluate("document.documentElement.scrollHeight")})
    page.evaluate("window.scrollTo(0, 0)")
    shoot("bananachat-cloud-session.png")
    page.set_viewport_size(size)


def capture(src: Path, page, shoot) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # The pool refuses profile directories reached through a symbolic link (macOS's temporary directory)
        server = subprocess.Popen([str(src / ".venv" / "bin" / "python"), str(Path(__file__).resolve()), "--serve",
                                   str(Path(tmp).resolve())],
                                  cwd=src, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            _wait(server)
            _sign_in(page, ADMIN)
            _conversation(page, shoot)
            page.goto(f"{URL}/customize")
            shoot("bananachat-customize.png")
            _cloud_session(page, shoot)
            page.goto(f"{URL}/admin/models/providers")
            shoot("bananachat-providers.png", full_page=True)
            page.goto(f"{URL}/admin/models/claude")
            # Each account shows the allowance the CLI reported, or the page is not worth showing
            assert page.locator("text=5-hour remaining").count() == len(POOL), "the pool has no usage reports"
            shoot("bananachat-claude-pool.png", full_page=True)
            _sign_in(page, USER)
            page.goto(f"{URL}/developer")
            shoot("bananachat-api.png", full_page=True)
        finally:
            server.terminate()
            server.wait(timeout=30)


if __name__ == "__main__" and sys.argv[1:2] == ["--serve"]:
    serve(Path(sys.argv[2]))
