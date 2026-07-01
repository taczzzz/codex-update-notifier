---
name: codex-update-notifier
description: Track OpenAI Codex release notes from the official Codex changelog RSS feed, compare them with a local state file, and report newly published updates in the current conversation. Use when the user asks what changed after a Codex update, wants Codex version release notes, wants a repeatable update log workflow, or asks to check/update a Codex changelog notification.
---

# Codex Update Notifier

## Overview

Use this skill to check official Codex changelog entries and summarize newly detected updates back into the active conversation. On first run, show the latest 3 updates and create the local baseline; on later runs, show every update after the last seen entry, including multiple consecutive releases. The default output is a polished Chinese plain-text version-history feed with version, relative time, short summary, and a `更多` section containing localized user-facing details. Internal PR lines, compare links, and author mentions are hidden by default; use `--style full` when the user wants the raw upstream changelog. The skill cannot subscribe to a native Codex update event, so the closest practical behavior is a one-minute Codex heartbeat automation attached to the target conversation.

## Quick Start

Run the bundled script from the skill directory:

```bash
python3 scripts/check_codex_updates.py
```

Then paste the script output in the conversation. It already includes:

- Chinese plain-text version-history entries
- Relative publish time
- Short first-screen summary
- Localized user-facing details under `更多`
- Official source link

## Workflow

1. If the user asks for the latest Codex changes, run `scripts/check_codex_updates.py`.
2. If the output says no new updates, report that clearly with the last-seen update.
3. If there are new entries, paste the script output directly so the Chinese plain-text summary and `更多` details stay intact.
4. If the user wants all recent entries regardless of state, run:

```bash
python3 scripts/check_codex_updates.py --latest 10 --no-save
```

5. If the user asks for automatic notification after updates, read `references/install-and-automation.md` and create or suggest a one-minute Codex heartbeat automation attached to the target conversation. The heartbeat should run the script with `--quiet-no-updates` and reply only when the script prints update content.

## Near-Real-Time Mode

Use this mode when the user wants behavior as close as possible to "Codex update event -> immediately show update content".

Create a heartbeat automation on the current conversation with:

- Frequency: every 1 minute
- Prompt: run `python3 "${CODEX_HOME:-$HOME/.codex}/skills/codex-update-notifier/scripts/check_codex_updates.py" --quiet-no-updates`; if output is empty, send no user-facing message; if output is non-empty, paste it exactly into the conversation.

This is polling, not true server-side push. State that the worst-case delay is approximately the heartbeat interval plus network/runtime time.

## Script Behavior

`scripts/check_codex_updates.py` reads the official Codex changelog RSS feed at `https://developers.openai.com/codex/changelog/rss.xml`.

By default, it stores state in:

```text
~/.codex-update-notifier/state.json
```

Use `--state <path>` when the user wants project-local state or multiple independent trackers.

Default behavior:

- First run with no state file: display the latest 3 updates and save the newest entry as the baseline.
- Later runs: display all entries newer than the saved baseline, without truncating consecutive releases.

Useful options:

- `--latest N`: Change the number of entries shown only on first run before state exists.
- `--no-save`: Do not update the state file.
- `--quiet-no-updates`: Print nothing when there are no new updates; use this for conversation automations.
- `--style feed`: Default Chinese plain-text version-history format, optimized for automatic conversation updates.
- `--style full`: Original verbose Markdown output with raw upstream changelog details.
- `--state PATH`: Use a custom state file.
- `--json`: Emit machine-readable JSON.

When the RSS feed is unavailable, report the network or parsing error and link the user to `https://developers.openai.com/codex/changelog`.
