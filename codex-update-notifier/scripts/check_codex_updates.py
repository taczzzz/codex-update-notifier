#!/usr/bin/env python3
"""Check official Codex changelog updates and compare them with local state."""

from __future__ import annotations

import argparse
import datetime as dt
from email.utils import parsedate_to_datetime
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.request
import xml.etree.ElementTree as ET


RSS_URL = "https://developers.openai.com/codex/changelog/rss.xml"
STATE_PATH = Path.home() / ".codex-update-notifier" / "state.json"
CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}encoded"
TEXT_WIDTH = 82


ZH_PHRASES = {
    "Codex CLI Release:": "Codex CLI 版本：",
    "Bug Fixes": "问题修复",
    "New Features": "新功能",
    "Chores": "维护更新",
    "Changelog": "变更记录",
    "Full Changelog": "完整变更记录",
    "No user-facing changes were identified for this release.": "本次未识别到面向用户的变化。",
    "Maintenance-only patch release with no user-facing changes since 0.142.2.": "维护性补丁版本，相比 0.142.2 没有面向用户的变化。",
    "Prevented full Responses WebSocket request payloads from being written to trace logs.": "修复 Responses WebSocket 完整请求载荷可能写入 trace 日志的问题。",
}


class MarkdownHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._in_li = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2", "h3"}:
            self.parts.append("\n\n")
        elif tag == "li":
            self._in_li = True
            self.parts.append("\n- ")
        elif tag in {"p", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "p", "li"}:
            self.parts.append("\n")
        if tag == "li":
            self._in_li = False

    def handle_data(self, data: str) -> None:
        cleaned = re.sub(r"\s+", " ", data).strip()
        if cleaned:
            self.parts.append(cleaned + " ")

    def markdown(self) -> str:
        text = "".join(self.parts)
        text = html.unescape(text)
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)


def fetch_rss(url: str, attempts: int = 3, retry_delay: float = 2.0) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "codex-update-notifier/1.0"},
    )
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(retry_delay)
    assert last_error is not None
    raise last_error


def html_to_text(raw: str) -> str:
    if "<" not in raw:
        return html.unescape(raw).strip()
    parser = MarkdownHTMLParser()
    parser.feed(raw)
    return parser.markdown()


def parse_items(rss_xml: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(rss_xml)
    items = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link or title).strip()
        description = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        content = item.findtext(CONTENT_NS) or description
        version = description if re.fullmatch(r"\d+(?:\.\d+)+(?:[-+\w.]+)?", description) else ""
        items.append(
            {
                "guid": guid,
                "title": title,
                "version": version,
                "published": pub_date,
                "link": link,
                "content": html_to_text(content),
            }
        )
    return items


def load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def save_state(path: Path, latest: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_seen_guid": latest["guid"],
        "last_seen_title": latest["title"],
        "last_seen_version": latest.get("version", ""),
        "last_seen_published": latest["published"],
        "last_checked_at": now_local(),
        "source": RSS_URL,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def detect_local_codex_version() -> str:
    executable = shutil.which("codex")
    if not executable:
        return "未检测到"
    try:
        result = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except subprocess.TimeoutExpired:
        return "检测超时"
    except Exception as exc:
        return f"检测失败：{exc.__class__.__name__}"
    output = (result.stdout or result.stderr).strip()
    return output or f"检测失败：退出码 {result.returncode}"


def now_local() -> str:
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def parse_published(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone()


def format_published(value: str) -> str:
    published = parse_published(value)
    if published is None:
        return value or "未知时间"
    return published.strftime("%Y-%m-%d %H:%M %Z")


def relative_time(value: str) -> str:
    published = parse_published(value)
    if published is None:
        return value or "未知时间"
    delta = dt.datetime.now().astimezone() - published
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 3600:
        minutes = max(1, seconds // 60)
        return f"{minutes}分钟前"
    if seconds < 86400:
        return f"{seconds // 3600}小时前"
    days = seconds // 86400
    if days < 7:
        return f"{days}天前"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks}周前"
    months = days // 30
    if months < 12:
        return f"{months}个月前"
    return f"{days // 365}年前"


def select_updates(items: list[dict[str, str]], state: dict[str, str], initial_latest: int) -> list[dict[str, str]]:
    last_seen = state.get("last_seen_guid")
    if not last_seen:
        return items[:initial_latest]

    updates = []
    for item in items:
        if item["guid"] == last_seen:
            break
        updates.append(item)
    return updates


def wrap_content(content: str, width: int = 96) -> str:
    lines = []
    for line in content.splitlines():
        if not line:
            continue
        prefix = "- " if line.startswith("- ") else ""
        body = line[2:] if prefix else line
        wrapped = textwrap.wrap(body, width=width, subsequent_indent="  ")
        if not wrapped:
            continue
        lines.append(prefix + wrapped[0])
        lines.extend(("  " + part) for part in wrapped[1:])
    return "\n".join(lines)


def wrap_plain(text: str, width: int = TEXT_WIDTH, indent: str = "") -> list[str]:
    wrapped = textwrap.wrap(text, width=width) or [text]
    return [indent + line for line in wrapped]


def localize_text(text: str) -> str:
    translated = text
    for source, replacement in ZH_PHRASES.items():
        translated = translated.replace(source, replacement)
    translated = re.sub(r"Full 变更记录:", "完整变更记录：", translated)
    translated = translated.replace("Full Changelog:", "完整变更记录：")
    translated = re.sub(r"\s*\(\s*#\d+\s*\)", "", translated)
    translated = re.sub(r"\s+@[\w-]+", "", translated)
    translated = re.sub(r"：\s+", "：", translated)
    return translated


def display_version(item: dict[str, str]) -> str:
    return item.get("version") or item["title"].replace("Codex CLI Release: ", "")


def strip_noise(line: str) -> str:
    line = re.sub(r"^\s*[-*]\s*", "", line).strip()
    line = re.sub(r"\s*\([^)]*#\d+[^)]*\)", "", line)
    line = re.sub(r"\s*@[\w-]+", "", line)
    return re.sub(r"\s+", " ", line).strip()


def is_developer_noise(line: str) -> bool:
    stripped = strip_noise(line)
    lowered = stripped.lower()
    if not stripped:
        return True
    if lowered in {"changelog", "full changelog", "变更记录", "完整变更记录"}:
        return True
    if lowered.startswith("full changelog:") or lowered.startswith("完整变更记录："):
        return True
    if re.match(r"^#\d+\b", stripped):
        return True
    if "github.com/openai/codex/compare" in lowered:
        return True
    if re.search(r"\brust-v\d+\.\d+\.\d+", stripped):
        return True
    return False


def compact_summary(item: dict[str, str], max_points: int = 2) -> list[str]:
    points = []
    for raw_line in item["content"].splitlines():
        line = strip_noise(raw_line)
        if is_developer_noise(line):
            continue
        if re.fullmatch(r"(new features|bug fixes|chores|improvements|fixes)", line, re.I):
            continue
        points.append(localize_text(line))
        if len(points) >= max_points:
            break
    return points or [localize_text(item["title"])]


def localized_full_content(content: str) -> str:
    lines = []
    for raw_line in content.splitlines():
        if is_developer_noise(raw_line):
            continue
        localized = localize_text(raw_line)
        if localized.startswith("- "):
            body = localized[2:].strip()
            lines.extend(wrap_plain(body, indent="  · "))
        elif localized:
            lines.extend(wrap_plain(localized, indent="  "))
    return "\n".join(lines) or "  本次没有可提炼的用户可见变更。"


def render_feed_entry(item: dict[str, str]) -> list[str]:
    version = display_version(item)
    points = compact_summary(item)
    lines = [
        f"{version}  {relative_time(item['published'])}",
        "Codex 更新",
    ]
    for index, point in enumerate(points, start=1):
        lines.extend(wrap_plain(f"{index}. {point}", indent="  "))
    lines.extend(
        [
            "",
            "更多",
            f"  标题：{localize_text(item['title'])}",
            f"  发布时间：{format_published(item['published'])}",
            f"  版本号：{item.get('version') or 'n/a'}",
            f"  链接：{item['link']}",
            "",
            "完整内容",
            localized_full_content(item["content"]),
            "",
        ]
    )
    return lines


def render_feed(
    updates: list[dict[str, str]],
    state: dict[str, str],
    local_version: str,
    state_path: Path,
    quiet_no_updates: bool,
) -> str:
    if quiet_no_updates and not updates:
        return ""

    lines = [
        "版本历史记录",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"检查时间：{now_local()}",
        f"本机版本：{local_version}",
    ]

    if not updates:
        last = state.get("last_seen_title") or "unknown"
        published = state.get("last_seen_published") or "unknown date"
        lines.extend(["", f"没有发现新的 Codex 更新。上次记录：{localize_text(last)}（{published}）"])
        return "\n".join(lines)

    if not state.get("last_seen_guid"):
        lines.extend(["", f"首次记录，显示最近 {len(updates)} 次更新。"])
    else:
        lines.extend(["", f"发现 {len(updates)} 次新增更新。"])

    for item in updates:
        lines.extend(["", "────────────────────────────────────────", ""])
        lines.extend(render_feed_entry(item))
    lines.extend(["", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", f"来源：{RSS_URL}", f"状态文件：{state_path}"])
    return "\n".join(lines).strip()


def render_full(
    updates: list[dict[str, str]],
    state: dict[str, str],
    local_version: str,
    state_path: Path,
    quiet_no_updates: bool,
) -> str:
    if quiet_no_updates and not updates:
        return ""

    lines = [
        "# Codex 更新检查",
        "",
        f"- 检查时间: {now_local()}",
        f"- 本机 Codex CLI: {local_version}",
        f"- 来源: {RSS_URL}",
        f"- 状态文件: {state_path}",
    ]

    if not updates:
        last = state.get("last_seen_title") or "unknown"
        published = state.get("last_seen_published") or "unknown date"
        lines.extend(["", f"没有发现新的 Codex 更新。上次记录: {last} ({published})"])
        return "\n".join(lines)

    lines.extend(["", f"发现 {len(updates)} 条 Codex 更新:", ""])
    for item in updates:
        title = item["title"]
        version = item.get("version") or "n/a"
        lines.extend(
            [
                f"## {title}",
                "",
                f"- 发布时间: {item['published']}",
                f"- 版本号: {version}",
                f"- 链接: {item['link']}",
                "",
                wrap_content(item["content"]),
                "",
            ]
        )
    return "\n".join(lines).strip()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check official Codex changelog updates.")
    parser.add_argument("--latest", type=int, default=3, help="Entries to show on first run before state exists.")
    parser.add_argument("--state", type=Path, default=STATE_PATH, help="State file path.")
    parser.add_argument("--no-save", action="store_true", help="Do not update the state file.")
    parser.add_argument(
        "--quiet-no-updates",
        action="store_true",
        help="Print nothing when no new updates are found. Useful for chat automations.",
    )
    parser.add_argument(
        "--style",
        choices=("feed", "full"),
        default="feed",
        help="Output style. feed is Chinese plain text; full is the original verbose Markdown format.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    parser.add_argument("--url", default=RSS_URL, help="RSS feed URL.")
    parser.add_argument("--retries", type=int, default=3, help="RSS fetch retry attempts.")
    parser.add_argument("--retry-delay", type=float, default=2.0, help="Seconds to wait between retries.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        items = parse_items(fetch_rss(args.url, args.retries, args.retry_delay))
    except Exception as exc:
        print(f"Codex update check failed: {exc}", file=sys.stderr)
        print("Open the official changelog manually: https://developers.openai.com/codex/changelog", file=sys.stderr)
        return 1

    if not items:
        print("Codex update check failed: RSS feed contained no items.", file=sys.stderr)
        return 1

    state = load_state(args.state)
    updates = select_updates(items, state, max(args.latest, 1))
    local_version = detect_local_codex_version()

    if not args.no_save:
        save_state(args.state, items[0])

    if args.json:
        print(
            json.dumps(
                {
                    "checked_at": now_local(),
                    "source": args.url,
                    "state_file": os.fspath(args.state),
                    "local_codex_cli": local_version,
                    "updates": updates,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        renderer = render_feed if args.style == "feed" else render_full
        output = renderer(updates, state, local_version, args.state, args.quiet_no_updates)
        if output:
            print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
