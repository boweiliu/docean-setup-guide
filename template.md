---
title: "DigitalOcean Studio Setup Guide"
description: "A walkthrough app for running Imbue Studio on your own DigitalOcean droplets, built alongside the boweiliu/setup-docean-studio guide it renders"
thumbnail: "template.svg"
version: v2
format: v2
---

# DigitalOcean Studio Setup Guide

This file is the manifest for the **DigitalOcean Studio Setup Guide** template (slug:
`docean-setup-guide`). It is the one document a future agent reads to understand,
present, and adapt this template. If you are an agent in a mind that was
created from this template, this file is your script: read all of it, then
follow "How to adapt it" below.

## What it is

A walkthrough app for running Imbue Studio on your own DigitalOcean droplets, built alongside the boweiliu/setup-docean-studio guide it renders

This template packages a guide-reader app. It renders a bundled copy of the
`boweiliu/setup-docean-studio` GitHub repo's markdown setup guide (a guide for
running Imbue Studio on self-hosted DigitalOcean droplets via nested-KVM and
mngr) as navigable HTML, instead of making the reader bounce between GitHub
tabs and a terminal. A sidebar lists the guide's 9 pages in reading order: the
overview, five numbered runbooks (including the parallel 4a/4b pair), and two
decision-log pages. Every command or code block in the guide gets a small
toolbar with a "Copy" button (clipboard) and a "Copy to agent chat" button,
which drops the command straight into the user's open chat, unsent, so an
agent can run or adapt it for them instead of the user retyping it by hand.
The Overview page also carries a single prompt block that hands an agent the
whole guide to run end to end, runbook by runbook, checking each one's Verify
output before moving on rather than assuming success, and a "Sync now" button:
the app keeps its copy of the guide up to date on its own (a background
refresh whenever the cache is more than 6 hours old, plus the manual button
for an immediate pull), falling back to a bundled offline copy if GitHub is
unreachable.

## How it works

The snapshot includes these paths (each is a repo-root-relative path copied
from the original mind onto a clean default-workspace-template base):

- `system/apps/docean_setup_guide`
- `system/supervisord.conf.d/docean-setup-guide.conf`

- `system/apps/docean_setup_guide` is the whole app: a Flask lib (one route,
  `/guide/<slug>`, plus the standard `/`, `/health`, and the shared shell
  static modules, plus `/sync`) that renders the guide markdown with
  `markdown-it-py`, served by the threaded Werkzeug dev server. The bundled
  copy at `src/docean_setup_guide/assets/docs/` (a copy of
  `setup-docean-studio`'s `README.md`, `runbooks/*.md`, and `decisions/*.md`)
  is the day-one / offline fallback; the app otherwise keeps a synced copy
  under its `DATA_DIR` (`data/.apps/docean-setup-guide/docs/` by default),
  refreshed from `raw.githubusercontent.com/boweiliu/setup-docean-studio/main/`
  in a background thread whenever a page view finds the cache older than 6
  hours (`SYNC_INTERVAL_SECONDS` in `runner.py`), or immediately via the
  Overview page's "Sync now" button. A fetch failure for any one page (offline,
  GitHub down, a file renamed upstream) just keeps whatever was already
  cached or bundled for that page -- one bad fetch never takes the guide
  down. In-guide markdown links between runbooks are rewritten
  to the app's own `/guide/<slug>` routes; links to paths the app does not
  render (`scripts/`, `provider/`, `decisions/` as a directory) are rewritten
  to point at the source GitHub repo instead. The Overview page also carries a
  small "Known issues in this guide" callout, hardcoded in `runner.py`'s
  `KNOWN_ISSUES` list, naming bugs found in the source repo's scripts during
  the review that produced this app -- see "Adaptation" below, since that list
  will go stale once (if) those are fixed upstream.
- `system/supervisord.conf.d/docean-setup-guide.conf` is the one supervisord
  program block that starts the app and registers its origin with the
  workspace's `forward_port.py` forwarder, so it opens as a normal window at
  `http://docean-setup-guide.<workspace-host>/`.

## Recipe

This template is version `v2`. It is not a fork of the
workspace it came from -- it is DERIVED from it by a recipe: include these
paths, leave these out, apply these published-version rules. An update re-runs
the recipe against the current workspace and publishes the result as the next
version, so anything excluded stays excluded even though it still exists in the
source workspace.

The recipe is machine-read, so it lives in the sibling
[`template.toml`](template.toml) -- its `[recipe]` table -- along with
the structured requirements and the environment this template needs
installed. That file is authoritative for all of it; this one holds the prose.

## Requirements

Everything the adopting mind must deal with before this template is really
theirs. Two kinds of entry, handled at different times:

- **Activation** -- what must be SET UP before anything runs, in the
  machine-readable `requires_` forms below. The adopting agent acts on these
  ITSELF, first, before asking anything.
- **Adaptation** -- what must be DECIDED or REWIRED, in prose. Worked through
  interactively with the user, after activation.


**Activation:** none. The app makes unauthenticated GET requests to
`raw.githubusercontent.com` to sync the guide, which needs no permission grant
or secret -- GitHub serves public raw file content with no credential. It
needs no latchkey permission and declares no secrets. "No requirements --
runs as published, with no external permissions or secrets."

**Adaptation:**

- This template is specific to the `boweiliu/setup-docean-studio` DigitalOcean
  deployment guide: its bundled markdown, its page order, and its "Known
  issues" callout are all written against that one guide. Adopting it is
  useful if you are following (or adapting) that same guide, or if you want to
  reuse the renderer -- markdown source bundling + markdown-it-py + the
  Copy / Copy-to-agent-chat button pattern -- for a different guide or runbook
  set of your own (swap `src/docean_setup_guide/assets/docs/` for your own
  markdown and update the `PAGES` list in `runner.py`).
- The Overview page's "Known issues in this guide" callout
  (`KNOWN_ISSUES` in `runner.py`) lists bugs found in `setup-docean-studio`'s
  scripts at the time this template was published. It is a hardcoded snapshot,
  not a live check -- delete or update it once (if) those bugs are fixed
  upstream, or it will mislead a reader.
- The app syncs only from `boweiliu/setup-docean-studio`'s `main` branch,
  hardcoded as `GITHUB_RAW_BASE` in `runner.py`. Pointing it at a different
  guide (see the first bullet) means changing that constant too, not just the
  bundled fallback copy.

## Environment

What this template needs INSTALLED, beyond what the template already has.
Declared in `template.toml`'s `[environment]` table; an adopting mind
converges it at ITS OWN pinned apt snapshot timestamp, so package versions come
out consistent with the rest of that mind's environment rather than frozen to
whatever this publisher happened to have.

Nothing extra -- runs on the stock workspace environment. The app's own
Python dependency (`markdown-it-py`) is declared in
`system/apps/docean_setup_guide/pyproject.toml` and installed the normal way
every scaffolded app's dependencies are (`uv sync --all-packages` / `uv tool
install -e`), not through this template-level `[environment]` mechanism.

## How to adapt it

Instructions for the NEXT agent -- the one adapting this template into a
new mind. This is the `use-template` skill's template path; in short:

1. Read this entire file first, especially "Requirements" below. It holds two
   kinds of entry and they are handled at different times: the machine-readable
   `requires_` lines are ACTIVATION (set them up before anything runs), and
   the prose bullets are ADAPTATION (decide or rewire them afterwards).
2. Present the template to the user in plain, non-technical language: what
   it is, what it does, and what it needs from them (name the activation
   requirements).
3. Ask whether they want to use the same connectors (e.g. their own Slack).
   If YES: ACTIVATE FIRST -- initiate every `requires_permission` line NOW
   via a latchkey permission request (see the `latchkey` skill; the request
   opens the approval/login flow in the minds app), wire up any
   `requires_secret` values, start the services, and get the app showing
   THE USER'S OWN DATA. Done for a data-backed app means the user can open it
   and see their own data -- NOT that a service starts or an endpoint returns
   200. Then tell them it is live and to take a look.
4. Only AFTER that (or immediately, if they chose different connectors -- the
   swap is then the first adaptation) ask: "How do you want to adapt it?"
5. Work through each requirement interactively, one at a time. Translate each
   into plain language, ask for a decision only when you genuinely need one,
   and resolve the obvious ones yourself.
6. When done, append a dated entry to "Adaptation history" below (never
   rewrite earlier entries) and commit.

## Publication history

This template's changelog: what each published version changed. The PUBLISHER
appends one entry per version (newest last); earlier entries are never rewritten.
This is distinct from "Adaptation history" below, which is the ADOPTERS' log.

### v1 (2026-10-01) -- first publish: the guide-reader app, rendering the setup-docean-studio guide with copy / copy-to-agent-chat buttons on every command, plus a run-the-whole-guide prompt block on the Overview page.

### v2 (2026-10-01) -- the guide now syncs itself from the source repo's main branch (a background refresh plus a manual "Sync now" button) instead of needing a manual re-copy of the markdown; the bundled copy is now only the offline/day-one fallback.

## Adaptation history

Each mind that adapts this template appends one dated entry below. Earlier
entries are never rewritten.
