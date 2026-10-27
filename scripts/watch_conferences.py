"""Daily conference watch: decision-day reminders and new OpenReview acceptances by students.

    python3 scripts/watch_conferences.py --site ../intsystems.github.io [--seed]

Reminders: a conference in the site's _data/conferences.yml whose `notification` is today (Moscow).
Acceptances: papers on OpenReview with a student from _data/students.yml among the authors, at a conference
from conferences.yml; journals are left out. A main-track venue id (ICLR.cc/2026/Conference) means accepted; a
dblp.org/conf/<VENUE>/<year> id is a paper OpenReview imported from DBLP after publication.
Rejected, withdrawn, and workshop venue ids never match. Reported note ids are kept in
data/openreview/seen.txt; --seed records the current ones without messages.
Needs PyYAML. Env: OPENREVIEW_USERNAME, OPENREVIEW_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_EDITOR_ID.
"""

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import yaml
from render_post import REPO
from send_post import MOSCOW, telegram

API = "https://api2.openreview.net"
SEEN = REPO / "data" / "openreview" / "seen.txt"
# OpenReview and DBLP spell some venues differently from conferences.yml.
ALIASES = {
    "NIPS": "NeurIPS",
    "SIGKDD": "KDD",
    "PKDD": "ECML-PKDD",
    "ECMLPKDD": "ECML-PKDD",
}


def profile_ids(site: Path, person: str) -> list[str]:
    """`openreview` of _people/<person>.md front matter, or []."""
    path = site / "_people" / f"{person}.md"
    if not path.exists():
        return []
    head = path.read_text(encoding="utf-8").split("\n---\n", 1)[0].removeprefix("---\n")
    return yaml.safe_load(head).get("openreview") or []


def conferences(site: Path) -> list[dict]:
    return yaml.safe_load(
        (site / "_data" / "conferences.yml").read_text(encoding="utf-8")
    )["conferences"]


def students(site: Path) -> dict[str, str]:
    """OpenReview id -> name of every student; a profile's ids live in _people/<id>.md."""
    registry = yaml.safe_load(
        (site / "_data" / "students.yml").read_text(encoding="utf-8")
    )
    out = {}
    for st in registry["students"]:
        for i in profile_ids(site, st["id"]) or st.get("openreview") or []:
            out[i] = st["name"]["en"]
    return out


def venue_matcher(confs: list[dict]):
    names = {c["name"].upper().replace("-", ""): c["name"] for c in confs}
    names |= {k: v for k, v in ALIASES.items() if v.upper().replace("-", "") in names}
    ranks = {c["name"]: c.get("rank", "") for c in confs}

    def match(venueid: str) -> tuple[str, str, str] | None:
        """(venue, year, rank) of an accepted or published paper, or None."""
        m = re.match(
            r"^(?:[\w.-]+/)?([A-Za-z-]+?)(?:\.cc)?/(\d{4})/Conference$", venueid
        ) or re.match(r"^dblp\.org/conf/([A-Za-z-]+)/(\d{4})$", venueid)
        if not m or not (name := names.get(m.group(1).upper().replace("-", ""))):
            return None
        return name, m.group(2), ranks.get(name, "")

    return match


class OpenReview:
    def __init__(self) -> None:
        body = {
            "id": os.environ["OPENREVIEW_USERNAME"],
            "password": os.environ["OPENREVIEW_PASSWORD"],
        }
        self.token = self._call("/login", body)["token"]

    def _call(self, path: str, body: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if body is None:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            API + path,
            data=json.dumps(body).encode() if body else None,
            headers=headers,
        )
        for attempt in range(3):
            try:
                with urlopen(request, timeout=60) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code == 429 and attempt < 2:
                    time.sleep(10)
                    continue
                sys.exit(
                    f"OpenReview {path}: {error.code} {error.read().decode()[:300]}"
                )
        raise AssertionError

    def aliases(self, profile_ids: list[str]) -> dict[str, list[str]]:
        """All ids of each profile: papers keep whichever one the author used when submitting.

        One request for all profiles; the API allows 100 requests an hour per account.
        """
        query = ",".join(urllib.parse.quote(i) for i in profile_ids)
        out = {}
        for profile in self._call(f"/profiles?ids={query}")["profiles"]:
            names = [
                n["username"]
                for n in profile["content"].get("names", [])
                if n.get("username")
            ]
            for i in [profile["id"], *names]:
                if i in profile_ids:
                    out[i] = list(dict.fromkeys([i, profile["id"], *names]))
        return out

    def notes_by(self, author: str) -> list[dict]:
        notes, offset = [], 0
        while True:
            page = self._call(
                f"/notes?content.authorids={urllib.parse.quote(author)}&limit=1000&offset={offset}"
            )["notes"]
            notes += page
            if len(page) < 1000:
                return notes
            offset += 1000


def title_key(note: dict) -> str:
    return re.sub(r"\W+", "", note["content"]["title"]["value"].lower())


def remind(confs: list[dict], editor: str) -> None:
    today = datetime.now(MOSCOW).strftime("%Y-%m-%d")
    for c in confs:
        if str(c.get("notification", "")) == today:
            text = (
                f"📬 Today {c['name']} ({c.get('rank', '')}) decisions are expected.\n"
                "Papers on OpenReview are picked up automatically; for the rest, send links of accepted papers."
            )
            telegram("sendMessage", {"chat_id": editor, "text": text})


def scan(site: Path, confs: list[dict], editor: str, seed: bool) -> None:
    match = venue_matcher(confs)
    ours = students(site)
    # One line per reported paper: note id and normalized title. The title catches the same paper
    # coming back as a DBLP import after its OpenReview acceptance was reported.
    lines = SEEN.read_text(encoding="utf-8").splitlines() if SEEN.exists() else []
    seen_ids = {line.split("\t")[0] for line in lines}
    seen_titles = {line.split("\t")[1] for line in lines if "\t" in line}
    client = OpenReview()
    recorded = sorted(ours)
    for i, ids in client.aliases(recorded).items():
        ours |= dict.fromkeys(ids, ours[i])
    found: dict[str, tuple[dict, tuple[str, str, str]]] = {}
    for author in recorded:  # one query per recorded id; the API resolves its aliases
        for note in client.notes_by(author):
            hit = match(note["content"].get("venueid", {}).get("value", ""))
            key = title_key(note)
            if (
                hit
                and note["id"] not in seen_ids
                and key not in seen_titles
                and key not in {title_key(n) for n, _ in found.values()}
            ):
                found[note["id"]] = (note, hit)
        time.sleep(0.3)
    for note_id, (note, (venue, year, rank)) in found.items():
        if not seed:
            content = note["content"]
            names = content.get("authors", {}).get("value", [])
            ids = content.get("authorids", {}).get("value", [])
            authors = ", ".join(
                f"<b>{html.escape(n)}</b>" if i in ours else html.escape(n)
                for n, i in zip(names, ids)
            )
            kind = (
                "published (DBLP)"
                if content["venueid"]["value"].startswith("dblp")
                else "accepted"
            )
            text = (
                f"🎉 {html.escape(venue)} {year} ({rank}), {kind}\n"
                f"<b>{html.escape(content['title']['value'])}</b>\n{authors}\n"
                f"https://openreview.net/forum?id={note.get('forum', note_id)}"
            )
            telegram(
                "sendMessage",
                {
                    "chat_id": editor,
                    "text": text,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
            )
        lines.append(f"{note_id}\t{title_key(note)}")
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(
        "".join(f"{line}\n" for line in sorted(set(lines))), encoding="utf-8"
    )
    print(
        f"{len(ours)} student ids, {len(found)} new {'(seeded)' if seed else 'reported'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument(
        "--seed",
        action="store_true",
        help="record current acceptances without messages",
    )
    args = parser.parse_args()
    confs = conferences(args.site)
    editor = os.environ.get("TELEGRAM_EDITOR_ID", "")
    if not args.seed:
        remind(confs, editor)
    scan(args.site, confs, editor, args.seed)


if __name__ == "__main__":
    main()
