"""Draft a post from the editor's facts with an LLM, commit it, and send the preview.

    python3 scripts/draft_post.py "Kiselev and Grabovoy: paper accepted at ICLR 2027, https://arxiv.org/abs/..."

Runs in .github/workflows/draft-post.yml, dispatched by the bot for any message that is not a reply.
Env: GITHUB_TOKEN with `models: read` and `contents: write`; Telegram variables as in send_post.py.
The model writes only from the facts and the arXiv abstract; links and numbers it adds anyway are flagged on the card.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from render_post import REPO, RUBRICS, parse_post
from send_post import MOSCOW, preview

MODEL = "openai/gpt-4.1"
EXAMPLES = 3  # latest published posts shown to the model as the house style
ATOM = "{http://www.w3.org/2005/Atom}"

SYSTEM = """You write posts for the Telegram channel of the Intelligent Systems Department at MIPT (Moscow).
Readers are students and alumni. Write in Russian, in a calm, factual, friendly tone, as the examples show.

Rules:
- Use only the facts and the paper abstract given. Do not add venues, ranks, numbers, dates, links, or claims that are not there.
- No clichés: no "рады сообщить", "с гордостью", "невероятный", "уникальный".
- Caption in Telegram HTML: <b>, <i>, <a href="...">; no other tags; 300-700 characters; first line is a bold headline.
- For a paper, explain the result in one or two plain sentences a second-year student understands.
- End with the links from the facts.
- Header: title of at most 60 characters, subtitle of at most 90 characters, plain text, no markup.
- rubric is one of: {rubrics}.
- person is the id of the one department member the news is about, from the list, or "" if none fits or several do.
- slug: 2-5 lowercase English words joined by "-".

People (id: name):
{people}

Answer with one JSON object: {{"rubric", "slug", "title", "subtitle", "person", "caption"}}."""


def people() -> dict[str, str]:
    text = (REPO / "data" / "people.tex").read_text(encoding="utf-8")
    return dict(re.findall(r"\\defineperson\{(\w+)\}\{\s*name\s*=\s*\{([^}]*)\}", text))


def arxiv(facts: str) -> str:
    """Title, authors, and abstract of the first arXiv link in the facts, or ""."""
    match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", facts)
    if not match:
        return ""
    with urlopen(
        f"https://export.arxiv.org/api/query?id_list={match.group(1)}", timeout=60
    ) as response:
        entry = ET.parse(response).getroot().find(f"{ATOM}entry")
    authors = ", ".join(
        a.findtext(f"{ATOM}name") for a in entry.findall(f"{ATOM}author")
    )
    title = " ".join(entry.findtext(f"{ATOM}title").split())
    abstract = " ".join(entry.findtext(f"{ATOM}summary").split())
    return f"Paper: {title}\nAuthors: {authors}\nAbstract: {abstract}"


def examples() -> str:
    published = []
    for path in sorted((REPO / "posts").glob("*.md"), reverse=True):
        meta, caption = parse_post(path)
        if meta.get("status") == "published":
            published.append(
                f"rubric: {meta['rubric']}\ntitle: {meta['title']}\ncaption:\n{caption}"
            )
        if len(published) == EXAMPLES:
            break
    return "\n\n---\n\n".join(published)


def ask_model(facts: str, paper: str) -> dict[str, str]:
    staff = "\n".join(f"{key}: {name.title()}" for key, name in people().items())
    user = f"Facts from the editor:\n{facts}"
    if paper:
        user += f"\n\n{paper}"
    if shots := examples():
        user += f"\n\nPublished posts, for style only:\n\n{shots}"
    body = {
        "model": MODEL,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": SYSTEM.format(rubrics=", ".join(RUBRICS), people=staff),
            },
            {"role": "user", "content": user},
        ],
    }
    request = Request(
        "https://models.github.ai/inference/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=120) as response:
            answer = json.load(response)
    except HTTPError as error:
        sys.exit(f"GitHub Models: {error.code} {error.read().decode()}")
    return json.loads(answer["choices"][0]["message"]["content"])


def unsupported(draft: dict[str, str], source: str) -> list[str]:
    """Links and numbers in the draft that appear nowhere in the facts or the abstract."""
    text = " ".join([draft["title"], draft["subtitle"], draft["caption"]])
    links = [
        link
        for link in re.findall(r'https?://[^\s"<>]+', text)
        if link.rstrip("/.") not in source
    ]
    numbers = [n for n in set(re.findall(r"\d+(?:[.,]\d+)?", text)) if n not in source]
    return [f"link {link}" for link in links] + [f"number {n}" for n in sorted(numbers)]


def tex(line: str) -> str:
    """Header fields are TeX; escape what the model writes as plain text."""
    return re.sub(r"(?<!\\)([%&#$_])", r"\\\1", line.strip())


def write(draft: dict[str, str]) -> Path:
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
    lines += ["---", draft["caption"].strip(), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("facts")
    args = parser.parse_args()
    paper = arxiv(args.facts)
    draft = ask_model(args.facts, paper)
    path = write(draft)
    relative = path.relative_to(REPO)
    for cmd in (
        ["git", "add", str(relative)],
        ["git", "commit", "-q", "-m", f"feat: draft {relative}"],
        ["git", "push", "-q"],
    ):
        subprocess.run(cmd, cwd=REPO, check=True)
    flags = unsupported(draft, f"{args.facts}\n{paper}")
    note = (
        ("⚠️ Not in the facts: " + ", ".join(flags))
        if flags
        else "Facts check: no unsupported links or numbers."
    )
    preview(path, note)


if __name__ == "__main__":
    main()
