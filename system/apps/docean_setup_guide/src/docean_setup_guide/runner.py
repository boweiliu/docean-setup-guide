"""Walkthrough guide for setting up Imbue Studio on DigitalOcean.

Renders the setup guide markdown as navigable HTML, with a "copy" and "copy
to agent chat" button on every command block so the user can push the setup
along without retyping anything. The guide content itself syncs from the
``boweiliu/setup-docean-studio`` repo's ``main`` branch on its own: a request
triggers a background refresh when the cache is older than
``SYNC_INTERVAL_SECONDS``, and there's a manual "Sync now" button for an
immediate pull. ``assets/docs/`` ships a bundled copy as the day-one /
offline fallback, used until the first sync lands and again if GitHub is
unreachable.

Services run from /home/user/workspace (the repo root). Conventions:

- Persistent state: the synced copy of the guide, under ``DATA_DIR``
  (defined below). ``DATA_DIR`` defaults to ``data/.apps/docean-setup-guide/``
  but honors the ``DOCEAN_SETUP_GUIDE_DATA_DIR`` env var, so an editing agent
  can point a throwaway instance at a *copy* of the data instead of the live
  store. Never hardcode ``data/.apps/docean-setup-guide/`` at a call site.
- Static assets shipped alongside this file: ``assets/docs/*.md`` (the
  bundled fallback copy), read via ``Path(__file__).parent / "assets/docs/..."``.
- Listen port: bind ``PORT`` (defined below), which defaults to this app's
  assigned port but honors the ``DOCEAN_SETUP_GUIDE_PORT`` env var.

This is a synchronous Flask app served by the threaded Werkzeug server. The
app owns its own browser origin, so it serves at ``/`` and root-absolute
URLs, cookies, and service workers all work unmodified.
"""

import html
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from flask import Flask, Response, abort, redirect, send_file
from markdown_it import MarkdownIt
from werkzeug.serving import run_simple

PORT = int(os.environ.get("DOCEAN_SETUP_GUIDE_PORT", "8086"))

SOURCE_REPO = "https://github.com/boweiliu/setup-docean-studio"
ASSETS_DIR = Path(__file__).parent / "assets" / "docs"

DATA_DIR = Path(os.environ.get("DOCEAN_SETUP_GUIDE_DATA_DIR", "data/.apps/docean-setup-guide"))
CACHE_DOCS_DIR = DATA_DIR / "docs"
SYNC_MARKER = DATA_DIR / "last_synced"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/boweiliu/setup-docean-studio/main/"
# How long a synced copy is trusted before a page view triggers a background
# refresh. A fetch failure (offline, GitHub down) just keeps serving whatever
# is already cached -- the guide never breaks for lack of network.
SYNC_INTERVAL_SECONDS = 6 * 60 * 60
SYNC_FETCH_TIMEOUT_SECONDS = 6
_sync_lock = threading.Lock()

SHELL_STATIC_MODULES_DIR = Path("system/apps/system_interface/imbue/system_interface/static/_static")
SHELL_STATIC_MODULE_NAMES = ("app_contract.js", "context_menu.js")


class Page(NamedTuple):
    slug: str
    nav_title: str
    source_path: str  # relative to ASSETS_DIR, and to the source repo root


PAGES = [
    Page("overview", "Overview", "README.md"),
    Page("01-kvm-host", "1. KVM host", "runbooks/01-kvm-host.md"),
    Page("02-worker-slices", "2. Worker slices", "runbooks/02-worker-slices.md"),
    Page("03-webtop", "3. Webtop", "runbooks/03-webtop.md"),
    Page("04a-wire-webtop", "4a. Wire the webtop", "runbooks/04a-wire-webtop.md"),
    Page("04b-wire-desktop", "4b. Wire your desktop", "runbooks/04b-wire-desktop.md"),
    Page("05-production-ux", "5. Production UX (optional)", "runbooks/05-production-ux.md"),
    Page("what-we-tried", "What we tried that didn't work", "decisions/what-we-tried.md"),
    Page("parked-questions", "Parked questions", "decisions/parked-questions.md"),
]
PAGE_BY_SLUG = {page.slug: page for page in PAGES}
# basename (no extension) -> slug, so an in-repo markdown link like
# "runbooks/01-kvm-host.md" or "01-kvm-host.md" (same-dir relative) resolves
# regardless of which directory it's written relative to.
SLUG_BY_BASENAME = {Path(page.source_path).stem: page.slug for page in PAGES}


def _doc_path(relative_path: str) -> Path:
    """The synced copy if one exists yet, otherwise the bundled fallback."""
    cached = CACHE_DOCS_DIR / relative_path
    return cached if cached.is_file() else ASSETS_DIR / relative_path


def _sync_from_github() -> None:
    """Pull every page's markdown from the source repo's ``main`` branch.

    Runs synchronously; callers decide whether to run it inline (the manual
    "Sync now" button) or on a background thread (the automatic refresh). A
    page that fails to fetch (network down, file renamed upstream) just keeps
    whatever is already cached or bundled for it -- one bad fetch never takes
    the whole guide down.
    """
    CACHE_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for page in PAGES:
        try:
            with urllib.request.urlopen(
                GITHUB_RAW_BASE + page.source_path, timeout=SYNC_FETCH_TIMEOUT_SECONDS
            ) as response:
                text = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError):
            continue
        target = CACHE_DOCS_DIR / page.source_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    SYNC_MARKER.write_text(datetime.now(timezone.utc).isoformat())


def _seconds_since_sync() -> float:
    if not SYNC_MARKER.is_file():
        return float("inf")
    return time.time() - SYNC_MARKER.stat().st_mtime


def _maybe_sync_in_background() -> None:
    """Kick off a refresh if the cache is stale and nothing is syncing already."""
    if _seconds_since_sync() < SYNC_INTERVAL_SECONDS:
        return
    if not _sync_lock.acquire(blocking=False):
        return

    def _run() -> None:
        try:
            _sync_from_github()
        finally:
            _sync_lock.release()

    threading.Thread(target=_run, daemon=True).start()


def _sync_status_text() -> str:
    age = _seconds_since_sync()
    if age == float("inf"):
        return "Not synced yet -- showing the bundled copy."
    minutes = int(age // 60)
    if minutes < 1:
        when = "just now"
    elif minutes < 60:
        when = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        hours = minutes // 60
        when = f"{hours} hour{'s' if hours != 1 else ''} ago"
    return f"Synced from GitHub {when}."


KNOWN_ISSUES = [
    ("runbooks/05-production-ux.md", "the Goal paragraph's line wrap starts a line "
     "with \"+ finish-notifs)\", which both GitHub and this page's renderer read as "
     "a bullet list rather than running text -- confirmed against GitHub's own "
     "markdown API. Cosmetic only; the content underneath is unaffected."),
]

# The script every page serves: it connects the page to the shell (so the
# element context menu and window-reopen-at-same-path work), then wires up
# every rendered command block's copy buttons. "Copy to agent chat" uses the
# shell's draft-text contract: it drops the command into the user's open
# chat, unsent, so they can review it before an agent runs it.
PAGE_SCRIPT = """<script type="module">
  import { connectToShell } from "/_static/app_contract.js";
  import { installElementContextMenu } from "/_static/context_menu.js";
  let handshake = null;
  const connection = connectToShell({
    onHandshake: (received) => {
      handshake = received;
      connection.location(location.pathname + location.search, document.title);
    },
  });
  installElementContextMenu({ connection, handshake: () => handshake });

  function flash(button, label) {
    const original = button.textContent;
    button.textContent = label;
    button.disabled = true;
    setTimeout(() => { button.textContent = original; button.disabled = false; }, 1400);
  }

  document.querySelectorAll("pre > code").forEach((code) => {
    const pre = code.parentElement;
    const wrapper = document.createElement("div");
    wrapper.className = "code-block";
    const toolbar = document.createElement("div");
    toolbar.className = "code-toolbar";

    const copyBtn = document.createElement("button");
    copyBtn.className = "code-btn";
    copyBtn.textContent = "Copy";
    copyBtn.onclick = () => {
      navigator.clipboard.writeText(code.textContent).then(() => flash(copyBtn, "Copied"));
    };

    const chatBtn = document.createElement("button");
    chatBtn.className = "code-btn code-btn-chat";
    chatBtn.textContent = "Copy to agent chat";
    chatBtn.onclick = () => {
      connection.draftText(code.textContent);
      flash(chatBtn, "Sent to chat");
    };

    toolbar.appendChild(copyBtn);
    toolbar.appendChild(chatBtn);
    pre.parentElement.insertBefore(wrapper, pre);
    wrapper.appendChild(toolbar);
    wrapper.appendChild(pre);
  });
</script>"""

PAGE_CSS = """<style>
  :root { color-scheme: light dark; }
  body {
    margin: 0; display: flex; min-height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0f1115; color: #d8dbe3;
  }
  nav {
    width: 220px; flex: none; padding: 20px 14px; box-sizing: border-box;
    border-right: 1px solid #262a33; overflow-y: auto;
  }
  nav .source-link { display: block; font-size: 12px; color: #8b93a3; margin-bottom: 16px; text-decoration: none; }
  nav .source-link:hover { color: #d8dbe3; }
  nav a.nav-link {
    display: block; padding: 7px 10px; margin-bottom: 2px; border-radius: 6px;
    color: #b7bdc9; text-decoration: none; font-size: 13.5px; line-height: 1.3;
  }
  nav a.nav-link:hover { background: #1b1f28; color: #fff; }
  nav a.nav-link.active { background: #2a3550; color: #fff; }
  main { flex: 1; min-width: 0; padding: 36px 48px 80px; max-width: 760px; }
  article h1 { font-size: 26px; margin-top: 0; }
  article h2 { font-size: 19px; border-top: 1px solid #262a33; padding-top: 22px; margin-top: 30px; }
  article p, article li { line-height: 1.6; font-size: 15px; }
  article a { color: #6fa8ff; }
  article code { background: #1b1f28; padding: 2px 5px; border-radius: 4px; font-size: 13px; }
  .code-block { margin: 14px 0; border: 1px solid #262a33; border-radius: 8px; overflow: hidden; }
  .code-toolbar {
    display: flex; gap: 6px; justify-content: flex-end; padding: 6px 8px;
    background: #161a22; border-bottom: 1px solid #262a33;
  }
  .code-btn {
    font-size: 12px; padding: 4px 10px; border-radius: 5px; border: 1px solid #333a47;
    background: #1f2430; color: #d8dbe3; cursor: pointer;
  }
  .code-btn:hover { background: #2a3040; }
  .code-btn-chat { border-color: #3a4f8f; }
  .code-block pre { margin: 0; padding: 14px; overflow-x: auto; }
  .code-block pre code { background: none; padding: 0; }
  .known-issues {
    border: 1px solid #5a4a1f; background: #241f12; border-radius: 8px;
    padding: 14px 18px; margin: 20px 0 30px;
  }
  .known-issues h2 { border-top: none; margin-top: 0; padding-top: 0; font-size: 15px; }
  .known-issues ul { padding-left: 20px; margin: 8px 0 0; }
  .known-issues li { margin-bottom: 8px; font-size: 13.5px; }
  .known-issues code { font-size: 12px; }
  .run-everything {
    border: 1px solid #3a4f8f; background: #141c2e; border-radius: 8px;
    padding: 14px 18px; margin: 20px 0;
  }
  .run-everything h2 { border-top: none; margin-top: 0; padding-top: 0; font-size: 15px; }
  .run-everything pre { white-space: pre-wrap; }
  .sync-status {
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    font-size: 12.5px; color: #8b93a3; margin: 4px 0 18px;
  }
  .sync-status form { margin: 0; }
</style>"""

_MD = MarkdownIt("commonmark").enable("table")


def _rewrite_link(match: re.Match) -> str:
    href = match.group(1)
    if href.startswith(("http://", "https://", "#", "mailto:")):
        return match.group(0)
    if href.endswith(".md"):
        basename = Path(href.split("#")[0]).stem
        slug = SLUG_BY_BASENAME.get(basename)
        if slug:
            return f'href="/guide/{slug}"'
    # Anything else relative (scripts/, provider/, decisions/ as a directory,
    # ...) isn't a rendered page -- send it to the source repo instead.
    return f'href="{SOURCE_REPO}/tree/main/{href.rstrip("/")}" target="_blank" rel="noopener"'


def _render_markdown(relative_path: str) -> str:
    text = _doc_path(relative_path).read_text()
    rendered = _MD.render(text)
    return re.sub(r'href="([^"]+)"', _rewrite_link, rendered)


def _nav_html(current_slug: str) -> str:
    items = []
    for page in PAGES:
        cls = "nav-link active" if page.slug == current_slug else "nav-link"
        items.append(f'<a class="{cls}" href="/guide/{page.slug}">{page.nav_title}</a>')
    return (
        f'<a class="source-link" href="{SOURCE_REPO}" target="_blank" rel="noopener">'
        f"setup-docean-studio on GitHub &#8599;</a>" + "".join(items)
    )


FULL_RUN_PROMPT = """Follow the setup guide at https://github.com/boweiliu/setup-docean-studio \
end to end and verify it actually works, not just that commands exit 0.

1. Check for a `.env` file with DIGITALOCEAN_API_KEY set (see .env.example). If it's missing, \
ask me for a DigitalOcean API key before doing anything else.
2. Run runbooks 01 through 05 in order: 01-kvm-host, 02-worker-slices, 03-webtop, then 04a-wire-webtop \
and 04b-wire-desktop (these two can run in parallel -- do both so both client paths are proven), then \
05-production-ux.
3. After each runbook's Steps, run that runbook's Verify commands before moving to the next one. \
Compare the actual output against what the runbook says to expect.
4. If a Verify step doesn't match what's expected, stop, tell me exactly what failed and what you \
saw instead, and wait for me before continuing -- don't silently move to the next runbook.
5. When all five are done, summarize what now exists (droplet IPs, slice names, DNAT ports, the \
webtop URL) and fill in the inventory/ files in the repo with it.

Treat "it ran" and "it works" as different things -- confirm the real thing (a slice reachable over \
SSH, the webtop showing the app past "loading workspace") before calling a step done."""


def _known_issues_html() -> str:
    items = "".join(f"<li><code>{path}</code> &mdash; {note}</li>" for path, note in KNOWN_ISSUES)
    return (
        '<div class="known-issues"><h2>Known issues in this guide</h2>'
        "<p>Found while reviewing the scripts; not yet fixed in the source repo.</p>"
        f"<ul>{items}</ul></div>"
    )


def _run_everything_html() -> str:
    escaped = html.escape(FULL_RUN_PROMPT)
    return (
        '<div class="run-everything"><h2>Run the whole thing</h2>'
        "<p>Hand this to an agent to run runbooks 01 through 05 end to end and "
        "verify each one actually worked, not just that the commands exited "
        "cleanly.</p>"
        f"<pre><code>{escaped}</code></pre></div>"
    )


def _sync_status_html() -> str:
    return (
        '<div class="sync-status">'
        f"<span>{html.escape(_sync_status_text())}</span>"
        '<form method="post" action="/sync">'
        '<button class="code-btn" type="submit">Sync now</button>'
        "</form></div>"
    )


def _page_html(page: Page) -> str:
    body = _render_markdown(page.source_path)
    issues = (
        (_sync_status_html() + _run_everything_html() + _known_issues_html())
        if page.slug == "overview"
        else ""
    )
    return (
        "<!doctype html><html><head>"
        f"<title>{page.nav_title} - Studio on DO Setup Guide</title>"
        '<meta charset="utf-8">'
        f"{PAGE_CSS}</head><body>"
        f"<nav>{_nav_html(page.slug)}</nav>"
        f"<main><article>{issues}{body}</article></main>"
        f"{PAGE_SCRIPT}</body></html>"
    )


app = Flask("docean_setup_guide", static_folder=None)


@app.route("/")
def index() -> Response:
    return _guide(PAGES[0].slug)


@app.route("/guide/<slug>")
def _guide(slug: str) -> Response:
    page = PAGE_BY_SLUG.get(slug)
    if page is None:
        abort(404)
    _maybe_sync_in_background()
    return Response(_page_html(page), mimetype="text/html")


@app.route("/sync", methods=["POST"])
def sync_now() -> Response:
    _sync_from_github()
    return redirect("/guide/overview")


@app.route("/_static/<basename>")
def shell_module(basename: str) -> Response:
    if basename not in SHELL_STATIC_MODULE_NAMES:
        abort(404)
    module_path = SHELL_STATIC_MODULES_DIR / basename
    if not module_path.is_file():
        abort(404)
    return send_file(module_path.absolute(), mimetype="text/javascript")


@app.route("/health")
def health() -> Response:
    return Response('{"status": "ok"}', mimetype="application/json")


def main() -> None:
    _maybe_sync_in_background()
    run_simple("127.0.0.1", PORT, app, threaded=True, use_reloader=False, use_debugger=False)


if __name__ == "__main__":
    main()
