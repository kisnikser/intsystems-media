"""Render the header PNG of a Telegram post and check its caption.

    uv run --python 3.11 scripts/render_post.py posts/2026-10-27-mipt-conference.md

Writes build/posts/<stem>.png (1920x1080) and build/posts/<stem>.html (the caption).
"""

import argparse
import html
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "build" / "posts"
CAPTION_LIMIT = 1024  # Telegram counts UTF-16 code units of the visible text

# rubric: (background, badge). Only design-* backgrounds carry the logo the badge sits next to.
RUBRICS = {
    "paper": ("design-3", "Статья"),
    "accepted": ("design-2", "Принято"),
    "award": ("black-design-1", "Награда"),
    "event": ("black-design-2", "Событие"),
    "seminar": ("black-design-3", "Семинар"),
    "deadlines": ("design-3", "Дедлайны"),
    "news": ("design-1", "Новости"),
}
STEM_LIMIT = 60  # Telegram callback data is at most 64 bytes, 2 go to the action prefix
STATUSES = ("draft", "approved", "published", "rejected")
REQUIRED = ("date", "rubric", "status", "title")
TELEGRAM_TAGS = {
    "b",
    "strong",
    "i",
    "em",
    "u",
    "ins",
    "s",
    "strike",
    "del",
    "a",
    "code",
    "pre",
    "blockquote",
    "tg-spoiler",
}


def people() -> dict[str, str]:
    """Ids and names of data/people.tex: the people a header can show."""
    text = (REPO / "data" / "people.tex").read_text(encoding="utf-8")
    return dict(re.findall(r"\\defineperson\{(\w+)\}\{\s*name\s*=\s*\{([^}]*)\}", text))


def tex(line: str) -> str:
    """Header fields are TeX; escape specials typed as plain text."""
    return re.sub(r"(?<!\\)([%&#$_])", r"\\\1", line.strip())


def parse_post(path: Path) -> tuple[dict[str, str], str]:
    """Flat `key: value` front matter between `---` lines, then the caption."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.DOTALL)
    if not match:
        sys.exit(f"{path}: no front matter")
    meta = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            sys.exit(f"{path}: bad front matter line {line!r}")
        meta[key.strip()] = value.strip()
    return meta, match.group(2).strip()


def check(path: Path, meta: dict[str, str], caption: str) -> int:
    """Return the caption length; exit on errors that would break posting."""
    errors = [f"missing `{key}`" for key in REQUIRED if not meta.get(key)]
    if len(path.stem.encode()) > STEM_LIMIT:
        errors.append(
            f"file name is over {STEM_LIMIT} bytes; bot buttons cannot carry it"
        )
    if meta.get("rubric") and meta["rubric"] not in RUBRICS:
        errors.append(f"rubric `{meta['rubric']}` not in {', '.join(RUBRICS)}")
    if meta.get("status") and meta["status"] not in STATUSES:
        errors.append(f"status `{meta['status']}` not in {', '.join(STATUSES)}")
    bad_tags = set(re.findall(r"</?([a-zA-Z-]+)", caption)) - TELEGRAM_TAGS
    if bad_tags:
        errors.append(f"tags Telegram does not support: {', '.join(sorted(bad_tags))}")
    visible = html.unescape(re.sub(r"<[^>]+>", "", caption))
    length = len(visible.encode("utf-16-le")) // 2
    if length > CAPTION_LIMIT:
        errors.append(
            f"caption is {length} characters, {length - CAPTION_LIMIT} over the limit"
        )
    if errors:
        sys.exit(f"{path}:\n  " + "\n  ".join(errors))
    return length


def cover_tex(meta: dict[str, str]) -> str:
    """Header fields are TeX, as in covers/: `\\\\` breaks a title line."""
    background, badge = RUBRICS[meta["rubric"]]
    keys = {
        "kind": "event",
        "title": f"{{{meta['title']}}}",
        "subtitle": f"{{{meta.get('subtitle', '')}}}",
        "background": meta.get("background") or background,
        "badge": f"{{{meta.get('badge') or badge}}}",
        "lecturer": meta.get("person", ""),
    }
    setup = ",\n  ".join(f"{key} = {value}" for key, value in keys.items())
    return (
        "\\documentclass[aspectratio=169]{beamer}\n"
        "\\usepackage{intsystems-cover}\n"
        "\\begin{document}\n"
        f"\\coversetup{{\n  {setup},\n}}\n"
        "\\cover\n"
        "\\end{document}\n"
    )


def render(stem: str, tex: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{stem}.tex").write_text(tex, encoding="utf-8")
    # Two runs let TikZ overlay positions settle; sty/ is on TEXINPUTS as in latexmkrc.
    cmd = [
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={OUT}",
        str(OUT / f"{stem}.tex"),
    ]
    env = {**os.environ, "TEXINPUTS": f"{REPO / 'sty'}//:"}
    for _ in range(2):
        result = subprocess.run(
            cmd, cwd=REPO, env=env, capture_output=True, text=True, check=False
        )
        if result.returncode:
            sys.exit(f"xelatex failed, see {OUT / f'{stem}.log'}")
    png = OUT / f"{stem}.png"
    subprocess.run(
        [
            "pdftoppm",
            "-png",
            "-singlefile",
            "-scale-to-x",
            "1920",
            "-scale-to-y",
            "1080",
            str(OUT / f"{stem}.pdf"),
            str(png.with_suffix("")),
        ],
        check=True,
    )
    return png


def build(path: Path) -> tuple[dict[str, str], str, Path, int]:
    """Check a post, render its header, and write its caption next to the PNG."""
    meta, caption = parse_post(path)
    length = check(path, meta, caption)
    png = render(path.stem, cover_tex(meta))
    (OUT / f"{path.stem}.html").write_text(caption + "\n", encoding="utf-8")
    return meta, caption, png, length


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("posts", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.posts:
        _, _, png, length = build(path)
        print(f"{png.relative_to(REPO)}  caption {length}/{CAPTION_LIMIT}")


if __name__ == "__main__":
    main()
