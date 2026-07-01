# Install and Automation Notes

## Install from GitHub

Users can install the skill by cloning or downloading this folder into their Codex skills directory:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
git clone <repo-url> "${CODEX_HOME:-$HOME/.codex}/skills/codex-update-notifier"
```

If the repository contains this skill as a subfolder, copy only `codex-update-notifier/` into the skills directory.

## Manual Trigger

After installation, users can open a Codex conversation and ask:

```text
Use $codex-update-notifier to check what changed in the latest Codex update.
```

Codex should run:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/codex-update-notifier/scripts/check_codex_updates.py"
```

On the first run, the script displays the latest 3 updates and records the newest one as the baseline. On later runs, it displays every changelog entry newer than the saved baseline, so consecutive releases are not missed.

## Automatic Conversation Updates

A skill only provides instructions and bundled resources after it is invoked. It cannot independently notice that Codex was updated or push a message into a conversation without another trigger.

To make update content appear automatically in a Codex conversation, use a heartbeat automation attached to that conversation. The automation prompt should tell Codex to run:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/codex-update-notifier/scripts/check_codex_updates.py" --quiet-no-updates
```

Expected behavior:

- First automated run: the conversation receives the latest 3 updates in a Chinese plain-text version-history feed.
- Later runs with no updates: the conversation stays quiet.
- Later runs after one or more releases: the conversation receives every new changelog entry after the saved baseline.
- Each entry shows a short first-screen summary plus a `更多` section containing localized user-facing update content.
- Internal PR lines, compare links, and author mentions are hidden in the default feed. Use `--style full` if raw upstream changelog detail is required.

If heartbeat automation is unavailable, use one of these fallback triggers:

- Codex automation that runs the script on a schedule.
- macOS `launchd` job that runs the script and writes a Markdown log.
- Shell update wrapper that runs the script after upgrading Codex CLI.

Keep credentials out of the skill. This workflow only reads the public OpenAI Developers RSS feed.
