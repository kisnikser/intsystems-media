"""Send posts to Telegram: previews with buttons to the editor, approved posts to the channel.

    python3 scripts/send_post.py preview posts/2026-10-27-mipt-conference.md
    python3 scripts/send_post.py due        # approved posts whose date has passed
    python3 scripts/send_post.py publish posts/2026-10-27-mipt-conference.md

Env: TELEGRAM_BOT_TOKEN; TELEGRAM_EDITOR_ID for preview; TELEGRAM_CHANNEL_ID (`@name` or `-100<id>`) for publish.
Dates in posts are Moscow time. Buttons are handled by worker/index.js.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from render_post import REPO, build, parse_post

MOSCOW = timezone(timedelta(hours=3))  # no DST since 2014
GITHUB_URL = "https://github.com/kisnikser/intsystems-media/blob/main"


def telegram(
    method: str,
    fields: dict[str, object],
    photo: Path | None = None,
    field: str = "photo",
) -> dict:
    """Call the Bot API with multipart form data; exit with Telegram's error text."""
    boundary = uuid4().hex
    parts = []
    for key, value in fields.items():
        text = value if isinstance(value, str) else json.dumps(value)
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{text}\r\n'.encode()
        )
    if photo:
        head = f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{photo.name}"\r\nContent-Type: image/png\r\n\r\n'
        parts.append(head.encode() + photo.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    request = Request(
        f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.load(response)["result"]
    except HTTPError as error:
        sys.exit(f"{method}: {error.read().decode()}")


def set_meta(path: Path, key: str, value: str) -> None:
    """Replace or add a front matter line; the worker does the same in JS."""
    text = path.read_text(encoding="utf-8")
    head, body = text.split("\n---\n", 1)
    line = f"{key}: {value}"
    if re.search(rf"^{key}:", head, re.MULTILINE):
        head = re.sub(rf"^{key}:.*$", line, head, flags=re.MULTILINE)
    else:
        head += f"\n{line}"
    path.write_text(f"{head}\n---\n{body}", encoding="utf-8")


def preview(path: Path, note: str = "") -> None:
    meta, caption, png, _ = build(path)
    editor = os.environ["TELEGRAM_EDITOR_ID"]
    photo = telegram(
        "sendPhoto", {"chat_id": editor, "caption": caption, "parse_mode": "HTML"}, png
    )
    stem = path.stem
    buttons = [
        [
            {"text": "✅ Publish now", "callback_data": f"p:{stem}"},
            {"text": f"🕒 At {meta['date']}", "callback_data": f"s:{stem}"},
        ],
        [
            {"text": "✏️ Text", "callback_data": f"t:{stem}"},
            {"text": "🖼 Header", "callback_data": f"h:{stem}"},
            {"text": "📅 Date", "callback_data": f"d:{stem}"},
        ],
        [
            {"text": "❌ Reject", "callback_data": f"r:{stem}"},
            {"text": "GitHub", "url": f"{GITHUB_URL}/posts/{path.name}"},
        ],
    ]
    telegram(
        "sendMessage",
        {
            "chat_id": editor,
            "text": f"Draft posts/{path.name} · {meta['rubric']} · {meta['date']}\n{note}".strip(),
            "reply_parameters": {"message_id": photo["message_id"]},
            "reply_markup": {"inline_keyboard": buttons},
        },
    )


def due() -> list[Path]:
    now = datetime.now(MOSCOW)
    posts = []
    for path in sorted((REPO / "posts").glob("*.md")):
        meta, _ = parse_post(path)
        if (
            meta.get("status") == "approved"
            and datetime.strptime(meta["date"], "%Y-%m-%d %H:%M").replace(tzinfo=MOSCOW)
            <= now
        ):
            posts.append(path)
    return posts


def publish(path: Path) -> None:
    channel = os.environ["TELEGRAM_CHANNEL_ID"]
    _, caption, png, _ = build(path)
    message = telegram(
        "sendPhoto", {"chat_id": channel, "caption": caption, "parse_mode": "HTML"}, png
    )
    set_meta(path, "status", "published")
    set_meta(path, "message_id", str(message["message_id"]))
    # Public channels are `@name`; private ones are `-100<id>` and link through /c/.
    handle = (
        channel.removeprefix("@")
        if channel.startswith("@")
        else f"c/{channel.removeprefix('-100')}"
    )
    link = f"https://t.me/{handle}/{message['message_id']}"
    telegram(
        "sendMessage",
        {
            "chat_id": os.environ["TELEGRAM_EDITOR_ID"],
            "text": f"Published posts/{path.name}: {link}",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["preview", "due", "publish"])
    parser.add_argument("posts", nargs="*", type=Path)
    args = parser.parse_args()
    if args.command == "due":
        print(" ".join(str(path.relative_to(REPO)) for path in due()))
    for path in args.posts:
        {"preview": preview, "publish": publish}[args.command](path)


if __name__ == "__main__":
    main()
