# Codex Update Notifier

Codex skill for checking official Codex release notes and reporting newly detected updates in the current conversation.

Install:

If this repository root is the skill folder:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
git clone <this-repo-url> "${CODEX_HOME:-$HOME/.codex}/skills/codex-update-notifier"
```

If this repository contains `codex-update-notifier/` as a subfolder:

```bash
tmpdir="$(mktemp -d)"
git clone <this-repo-url> "$tmpdir"
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R "$tmpdir/codex-update-notifier" "${CODEX_HOME:-$HOME/.codex}/skills/"
```

Use in a Codex conversation:

```text
Use $codex-update-notifier to check what changed in the latest Codex update.
```

The skill reads the official RSS feed:

```text
https://developers.openai.com/codex/changelog/rss.xml
```

It stores local state at:

```text
~/.codex-update-notifier/state.json
```

Behavior:

- First run: shows the latest 3 updates and records the newest one as the baseline.
- Later runs: shows every update newer than the saved baseline, including several consecutive releases.
- Default display: Chinese plain-text version-history feed with version, relative time, concise summary, and user-facing `更多` details.
- Internal PR lines, compare links, and author mentions are hidden by default to keep automatic conversation updates readable.

Note: a skill does not run in the background by itself. To notify after every update automatically, pair the bundled script with a Codex automation, `launchd`, cron, or an update wrapper.

For automatic messages in one Codex conversation, create a heartbeat automation attached to that conversation and have it run:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/codex-update-notifier/scripts/check_codex_updates.py" --quiet-no-updates
```

With `--quiet-no-updates`, the automation only posts when new update content exists.

Use the old verbose output when needed:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/codex-update-notifier/scripts/check_codex_updates.py" --style full
```
