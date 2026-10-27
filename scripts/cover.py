"""Render a header on request and send it to the editor as a PNG file; nothing is committed.

    python3 scripts/cover.py $'Принято на NeurIPS 2026\nСтатья о ландшафте функции потерь\nkiselev_ns\naward'

The argument is the text of the editor's /cover message without the command:
line 1 is the title, line 2 the subtitle ("-" or empty for none); any further line is
a person id from data/people.tex or a rubric from RUBRICS, in any order.
Runs in .github/workflows/cover.yml, dispatched by the bot.
"""

import argparse
import os
import sys

from render_post import RUBRICS, cover_tex, people, render, tex
from send_post import telegram

USAGE = (
    "/cover\n"
    "Title\n"
    "Subtitle or -\n"
    f"person id (optional), rubric (optional: {', '.join(RUBRICS)})"
)


def parse(text: str) -> dict[str, str]:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        sys.exit(f"Nothing to draw. Send:\n{USAGE}")
    meta = {"title": tex(lines[0]), "rubric": "news"}
    if len(lines) > 1 and lines[1] != "-":
        meta["subtitle"] = tex(lines[1])
    known = people()
    for extra in lines[2:]:
        if extra in RUBRICS:
            meta["rubric"] = extra
        elif extra in known:
            meta["person"] = extra
        else:
            sys.exit(
                f"`{extra}` is neither a rubric nor a person id from data/people.tex.\n{USAGE}"
            )
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("text")
    args = parser.parse_args()
    editor = os.environ["TELEGRAM_EDITOR_ID"]
    try:
        meta = parse(args.text)
    except SystemExit as error:
        telegram("sendMessage", {"chat_id": editor, "text": f"⚠️ {error}"})
        raise
    png = render("cover", cover_tex(meta))
    telegram(
        "sendDocument",
        {"chat_id": editor, "caption": "🖼 1920×1080"},
        png,
        field="document",
    )


if __name__ == "__main__":
    main()
