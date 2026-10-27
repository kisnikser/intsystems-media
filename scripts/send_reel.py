"""Send a rendered reel to the editor with buttons to post it to the channel or discard it.

    python3 scripts/send_reel.py build/reels/request.toml build/reels/request.mp4

The scenario's optional `caption` (Telegram HTML) becomes the video's caption. The buttons are
handled by worker/index.js, which copies this very message to the channel: nothing is stored.
Env: TELEGRAM_BOT_TOKEN, TELEGRAM_EDITOR_ID.
"""

import argparse
import os
from pathlib import Path

import tomllib
from send_post import telegram


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario", type=Path)
    parser.add_argument("video", type=Path)
    args = parser.parse_args()
    caption = tomllib.loads(args.scenario.read_text(encoding="utf-8")).get(
        "caption", ""
    )
    editor = os.environ["TELEGRAM_EDITOR_ID"]
    fields = {
        "chat_id": editor,
        "width": "1080",
        "height": "1920",
        "supports_streaming": "true",
    }
    if caption:
        fields |= {"caption": caption, "parse_mode": "HTML"}
    video = telegram("sendVideo", fields, args.video, field="video")
    telegram(
        "sendMessage",
        {
            "chat_id": editor,
            "text": "🎬 Reel ready",
            "reply_parameters": {"message_id": video["message_id"]},
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "📤 Post to channel", "callback_data": "v:"},
                        {"text": "❌ Discard", "callback_data": "x:"},
                    ]
                ]
            },
        },
    )


if __name__ == "__main__":
    main()
