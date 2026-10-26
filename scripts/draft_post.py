"""Make a draft from the editor's own post text: an LLM proposes only the header.

    python3 scripts/draft_post.py '<b>Статья принята на ICLR 2027</b> ...'

Runs in .github/workflows/draft-post.yml, dispatched by the bot for any message that is not a reply.
The caption is the editor's text as Telegram HTML, kept verbatim; the model picks rubric, title, subtitle, and person.
Env: CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN (Workers AI); Telegram variables as in send_post.py.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from render_post import REPO, RUBRICS
from send_post import MOSCOW, preview

# Workers AI free plan: 10,000 neurons a day. DeepSeek, Kimi, and GLM need the paid plan.
MODEL = "@cf/openai/gpt-oss-120b"

SYSTEM = """You make the header image text for a post in the Telegram channel of the Intelligent Systems Department at MIPT.
The editor wrote the post; read it and answer with one JSON object {{"rubric", "slug", "title", "subtitle", "person"}}:
- title: the news in Russian, at most 60 characters, plain text; use only what the post says.
- subtitle: who or where, at most 90 characters, or "".
- rubric: one of {rubrics}.
- person: the id of the one department member the post is about, from the list, or "" if none fits or several do.
- slug: 2-5 lowercase English words joined by "-".

People (id: name):
{people}"""


def people() -> dict[str, str]:
    text = (REPO / "data" / "people.tex").read_text(encoding="utf-8")
    return dict(re.findall(r"\\defineperson\{(\w+)\}\{\s*name\s*=\s*\{([^}]*)\}", text))


def ask_model(caption: str) -> dict[str, str]:
    staff = "\n".join(f"{key}: {name.title()}" for key, name in people().items())
    body = {
        "model": MODEL,
        "temperature": 0.4,
        # gpt-oss reasons before it answers; the default limit ends it mid-thought.
        "max_tokens": 4000,
        "reasoning_effort": "low",
        "messages": [
            {
                "role": "system",
                "content": SYSTEM.format(rubrics=", ".join(RUBRICS), people=staff),
            },
            {"role": "user", "content": caption},
        ],
    }
    request = Request(
        f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CLOUDFLARE_ACCOUNT_ID']}/ai/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=120) as response:
            answer = json.load(response)
    except HTTPError as error:
        sys.exit(f"Workers AI: {error.code} {error.read().decode()}")
    content = answer["choices"][0]["message"]["content"] or ""
    # Not every model honors a JSON mode: take the outermost object from the text.
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        sys.exit(f"Workers AI: no JSON in the answer: {content[:500]}")
    return json.loads(match.group(0))


def tex(line: str) -> str:
    """Header fields are TeX; escape what the model writes as plain text."""
    return re.sub(r"(?<!\\)([%&#$_])", r"\\\1", line.strip())


def write(draft: dict[str, str], caption: str) -> Path:
    date = (datetime.now(MOSCOW) + timedelta(days=1)).strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", draft["slug"].lower()).strip("-")[:40] or "post"
    path = REPO / "posts" / f"{date}-{slug}.md"
    for n in range(2, 100):
        if not path.exists():
            break
        path = REPO / "posts" / f"{date}-{slug}-{n}.md"
    rubric = draft["rubric"] if draft["rubric"] in RUBRICS else "news"
    lines = [
        "---",
        f"date: {date} 10:00",
        f"rubric: {rubric}",
        "status: draft",
        f"title: {tex(draft['title'])}",
    ]
    if draft.get("subtitle"):
        lines.append(f"subtitle: {tex(draft['subtitle'])}")
    if draft.get("person") in people():
        lines.append(f"person: {draft['person']}")
    lines += ["---", caption.strip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("caption", help="post text in Telegram HTML")
    args = parser.parse_args()
    path = write(ask_model(args.caption), args.caption)
    relative = path.relative_to(REPO)
    subprocess.run(["git", "add", str(relative)], cwd=REPO, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", f"feat: draft {relative}"], cwd=REPO, check=True
    )
    # The bot commits to main at any time; rebase onto it until the push lands.
    for _ in range(3):
        subprocess.run(["git", "pull", "-q", "--rebase"], cwd=REPO, check=True)
        if subprocess.run(["git", "push", "-q"], cwd=REPO, check=False).returncode == 0:
            break
    else:
        sys.exit("git push kept failing")
    preview(path)


if __name__ == "__main__":
    main()
