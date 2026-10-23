"""Alumni bibliometrics and open-source history for the presentation charts.

Sources:
- alumni registry: machinelearning.ru page of department students (2004 on)
  and the theses table of intsystems.github.io (2022 on);
- publications: OpenAlex authors affiliated with MIPT, Skoltech, or FRC CSC RAS;
- open source: public repos of the two department GitHub organizations.

Run by hand before an event (OpenAlex key from the macOS Keychain):

    OPENALEX_API_KEY=$(security find-generic-password -s openalex -w) \
        uv run --python 3.11 scripts/research_stats.py

Writes data/research/{alumni.csv,stats.tex}. OpenAlex answers are cached in
data/research/openalex.json, so reruns cost nothing. data/research/overrides.csv
(alumnus key, OpenAlex author id or `none`) fixes wrong matches by hand.
"""

import argparse
import csv
import http.client
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "research"
CACHE = OUT / "openalex.json"
OVERRIDES = OUT / "overrides.csv"
WIKI_PAGE = "Интеллектуальные системы (кафедра МФТИ)/Студенты"
GITHUB_ORGS = ("Intelligent-Systems-Phystech", "intsystems")
# MIPT, Skoltech, FRC CSC RAS: where alumni published as students.
HOME_INSTITUTIONS = ("I153845743", "I125989756", "I4405258151")
NOW = 2026
# "Recent graduates" on the slides: the last five graduation years.
RECENT_YEARS = 5
# A student's first paper comes at most this many years before graduation.
FIRST_PAPER_LEAD = 7
CORE_FIELDS = ("Computer Science", "Mathematics", "Decision Sciences")
FAR_FIELDS = (
    "Physics and Astronomy",
    "Materials Science",
    "Chemistry",
    "Chemical Engineering",
)
AUTHOR_FIELDS = "id,display_name,works_count,cited_by_count,summary_stats,last_known_institutions,affiliations"
COHORTS = (("0–4", 0, 4), ("5–10", 5, 10), ("больше 10", 11, 99))
BIG_TECH = (
    "Google",
    "Meta",
    "Facebook",
    "Apple",
    "Amazon",
    "Microsoft",
    "Netflix",
    "NVIDIA",
    "DeepMind",
)
RU_TECH = (
    "Yandex",
    "Sber",
    "VK",
    "Mail.Ru",
    "Ozon",
    "Tinkoff",
    "T-Bank",
    "Avito",
    "Kaspersky",
    "MTS",
    "Huawei",
)
SECTORS = ("Российская наука", "Зарубежная наука", "Индустрия")

LATIN = "a b v g d e e zh z i y k l m n o p r s t u f kh ts ch sh shch _ y _ e yu ya"
TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", LATIN.split(), strict=True))
GIVEN_EN = {
    "Алексей": "Alexey",
    "Александр": "Alexander",
    "Александра": "Alexandra",
    "Дмитрий": "Dmitry",
    "Юрий": "Yury",
    "Андрей": "Andrey",
    "Сергей": "Sergey",
    "Максим": "Maxim",
    "Евгений": "Evgeny",
    "Мария": "Maria",
    "Наталия": "Natalia",
    "Наталья": "Natalia",
    "Анастасия": "Anastasia",
    "Василий": "Vasily",
    "Григорий": "Grigory",
    "Арсений": "Arseny",
    "Виталий": "Vitaly",
    "Валерий": "Valery",
    "Геннадий": "Gennady",
    "Анатолий": "Anatoly",
    "Ксения": "Ksenia",
}


def translit(text: str) -> str:
    out = "".join(TRANSLIT.get(ch.lower(), ch.lower()) for ch in text).replace("_", "")
    return out.capitalize()


def norm(text: str) -> str:
    """Lowercase Latin key: transliterate Cyrillic, drop everything but letters."""
    return re.sub(r"[^a-z]", "", translit(text).lower())


def loose(text: str) -> str:
    """Key that ignores romanization variants: Lyalin = Lialin, Frey = Frei."""
    key = norm(text)
    for old, new in (
        ("kh", "h"),
        ("ya", "ia"),
        ("yu", "iu"),
        ("yo", "e"),
        ("y", "i"),
        ("j", "i"),
    ):
        key = key.replace(old, new)
    return re.sub(r"i+", "i", key)


def alt_translit(text: str) -> str:
    """Second common romanization of the letters that have two: я ю й х."""
    alt = {"я": "ia", "ю": "iu", "й": "i", "х": "h"}
    out = "".join(
        alt.get(ch.lower(), TRANSLIT.get(ch.lower(), ch.lower())) for ch in text
    )
    return out.replace("_", "").capitalize()


@dataclass
class Alumnus:
    surname: str
    given: str
    year: int
    degrees: set[str] = field(default_factory=set)
    advisor: str = ""
    name_en: str = ""

    @property
    def key(self) -> str:
        return f"{norm(self.surname)}-{norm(self.given)[:3]}"

    @property
    def query(self) -> str:
        if self.name_en:
            return self.name_en
        return (
            f"{GIVEN_EN.get(self.given, translit(self.given))} {translit(self.surname)}"
        )


def http_json(url: str, headers: dict[str, str] | None = None) -> dict | list:
    """GET JSON; retries twice, since long GitHub pages sometimes arrive cut."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "intsystems-cover", **(headers or {})}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except (http.client.IncompleteRead, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(2)
    raise AssertionError("unreachable")


# --- alumni registry ----------------------------------------------------------


def wiki_alumni() -> list[Alumnus]:
    title = urllib.parse.quote(WIKI_PAGE.replace(" ", "_"))
    url = f"http://www.machinelearning.ru/wiki/index.php?title={title}&action=raw"
    with urllib.request.urlopen(url, timeout=60) as response:
        text = response.read().decode("utf-8")
    people, end_year = [], None
    for line in text.splitlines():
        if group := re.match(r"==\s*Группа.*?\((\d{4})\s*[—–-]\s*(\d{4})\)", line):
            end_year = int(group[2])
        elif line.startswith("*") and end_year:
            name = re.sub(
                r"\[\[[^|\]]*\|([^\]]*)\]\]", r"\1", line.lstrip("* ")
            ).strip()
            parts = name.split()
            if len(parts) >= 2:
                people.append(Alumnus(parts[0], parts[1], end_year))
        elif line.startswith(":") and people:
            degree = re.match(r":\s*(Бакалаврская|Магист\w*|Кандидатская)", line)
            if degree:
                people[-1].degrees.add(
                    {"Б": "bachelor", "М": "master", "К": "phd"}[degree[1][0]]
                )
            advisor = re.search(
                r"научный руководитель:\s*(?:\[\[[^|\]]*\||\[\S+\s)?([^\],\]]+)", line
            )
            if advisor and not people[-1].advisor:
                people[-1].advisor = advisor[1].strip(" ']")
    return people


def site_alumni(site: Path) -> list[Alumnus]:
    people, year, kind = [], None, None
    for line in (
        (site / "_i18n" / "en" / "thesis.md").read_text(encoding="utf-8").splitlines()
    ):
        if heading := re.match(r"### (\d{4})", line):
            year = int(heading[1])
        elif heading := re.match(r"#### (\w+)", line):
            kind = {"Bachelor": "bachelor", "Master": "master", "PhD": "phd"}.get(
                heading[1].split("'")[0]
            )
        elif (
            line.startswith("|")
            and year
            and not re.match(r"\|\s*:?-", line)
            and "Student" not in line
        ):
            cells = [c.strip() for c in line.strip("|").split("|")]
            name = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cells[0]).strip()
            parts = name.split()
            if len(parts) >= 2:
                alumnus = Alumnus(
                    parts[-1], parts[0], year, {kind} if kind else set(), name_en=name
                )
                alumnus.advisor = re.sub(
                    r"\[([^\]]+)\]\([^)]*\)", r"\1", cells[2]
                ).strip()
                people.append(alumnus)
    return people


def merge(people: list[Alumnus]) -> list[Alumnus]:
    """One record per person; the site name order is ambiguous, so match both orders."""
    merged: dict[str, Alumnus] = {}
    for person in people:
        swapped = f"{norm(person.given)}-{norm(person.surname)[:3]}"
        key = person.key if person.key in merged or swapped not in merged else swapped
        if key in merged:
            known = merged[key]
            known.year = max(known.year, person.year)
            known.degrees |= person.degrees
            known.name_en = known.name_en or person.name_en
        else:
            merged[key] = person
    return list(merged.values())


# --- OpenAlex -----------------------------------------------------------------


class OpenAlex:
    def __init__(self, key: str | None) -> None:
        self.key = key
        self.cache: dict[str, object] = (
            json.loads(CACHE.read_text()) if CACHE.exists() else {}
        )
        self.spent = 0.0

    def get(self, path: str, params: dict[str, str]) -> dict:
        cache_key = f"{path}?{urllib.parse.urlencode(sorted(params.items()))}"
        if cache_key not in self.cache:
            query = dict(params, **({"api_key": self.key} if self.key else {}))
            data = http_json(
                f"https://api.openalex.org/{path}?{urllib.parse.urlencode(query)}"
            )
            self.spent += (
                data.get("meta", {}).get("cost_usd", 0) if isinstance(data, dict) else 0
            )
            data.pop("meta", None)
            self.cache[cache_key] = data
            time.sleep(0.12)
        return self.cache[cache_key]

    def save(self) -> None:
        CACHE.write_text(
            json.dumps(self.cache, ensure_ascii=False, indent=0, sort_keys=True)
        )

    def match(self, person: Alumnus) -> dict | None:
        """Author with a home affiliation and the same surname; most works wins.

        The surname must equal a name token up to romanization; site names come in
        either order, so both their tokens are tried as the surname.
        """
        home = "affiliations.institution.id:" + "|".join(HOME_INSTITUTIONS)
        surnames = {loose(person.surname)} | (
            {loose(person.given)} if person.name_en else set()
        )
        queries = [person.query]
        if re.search("[яюйх]", (person.surname + person.given).lower()):
            queries.append(
                f"{alt_translit(person.given)} {alt_translit(person.surname)}"
            )
        queries.append(f"{person.given} {person.surname}")
        best = None
        for number, query in enumerate(queries):
            found = self.get(
                "authors",
                {
                    "search": query,
                    "filter": home,
                    "select": AUTHOR_FIELDS,
                    "per-page": "5",
                },
            )
            for author in found["results"]:
                tokens = {loose(t) for t in author["display_name"].split()}
                if surnames & tokens and (
                    not best or author["works_count"] > best["works_count"]
                ):
                    best = author
            # Romanized queries are all tried; the Cyrillic one only as a fallback.
            if best and number >= len(queries) - 2:
                break
        return best

    def relevant(self, author: dict, graduated: int) -> bool:
        """Reject namesakes: MIPT physicists (no CS or math topic) and senior
        researchers whose first paper predates the student's studies."""
        author_id = author["id"].split("/")[-1]
        found = self.get(f"authors/{author_id}", {"select": "id,topics"})
        fields = [t["field"]["display_name"] for t in found.get("topics") or []][:5]
        if (
            sum(f in CORE_FIELDS for f in fields) < 1
            or sum(f in FAR_FIELDS for f in fields) >= 3
        ):
            return False
        first = self.get(
            "works",
            {
                "filter": f"author.id:{author_id}",
                "sort": "publication_year:asc",
                "per-page": "1",
                "select": "publication_year",
            },
        )["results"]
        year = (first[0]["publication_year"] if first else None) or graduated
        return year >= graduated - FIRST_PAPER_LEAD

    def author(self, author_id: str) -> dict:
        return self.get(f"authors/{author_id}", {"select": AUTHOR_FIELDS})

    def top_work(self, author_id: str) -> dict | None:
        found = self.get(
            "works",
            {
                "filter": f"author.id:{author_id}",
                "sort": "cited_by_count:desc",
                "per-page": "1",
                "select": "title,cited_by_count,publication_year",
            },
        )
        return found["results"][0] if found["results"] else None


def current_institution(author: dict) -> dict | None:
    """Last known institution, else the affiliation with the latest year."""
    if author.get("last_known_institutions"):
        return author["last_known_institutions"][0]
    dated = [
        (max(a.get("years") or [0]), a["institution"])
        for a in author.get("affiliations") or []
    ]
    return max(dated, key=lambda d: d[0])[1] if dated else None


def is_company(inst: dict) -> bool:
    name = inst.get("display_name", "").lower()
    return inst.get("type") == "company" or any(
        b.lower() in name for b in BIG_TECH + RU_TECH
    )


def sector(author: dict) -> str | None:
    inst = current_institution(author)
    if not inst:
        return None
    if is_company(inst):
        return SECTORS[2]
    return SECTORS[0] if inst.get("country_code") == "RU" else SECTORS[1]


# --- GitHub -------------------------------------------------------------------


def github_years() -> dict[int, int]:
    """Own (non-fork) public repos per creation year over both organizations."""
    headers = (
        {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"}
        if "GITHUB_TOKEN" in os.environ
        else {}
    )
    years: dict[int, int] = {}
    for org in GITHUB_ORGS:
        page = 1
        while repos := http_json(
            f"https://api.github.com/orgs/{org}/repos?per_page=100&type=public&page={page}",
            headers,
        ):
            for repo in repos:
                if not repo["fork"]:
                    year = int(repo["created_at"][:4])
                    years[year] = years.get(year, 0) + 1
            page += 1
    return dict(sorted(years.items()))


# --- output -------------------------------------------------------------------


def tex(text: str) -> str:
    return re.sub(r"([%#&_$])", r"\\\1", text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--site", type=Path, default=REPO.parent / "intsystems.github.io"
    )
    parser.add_argument(
        "--no-openalex", action="store_true", help="registry and GitHub only"
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    people = merge(wiki_alumni() + site_alumni(args.site.resolve()))
    people.sort(key=lambda p: (p.year, p.surname))
    print(f"alumni: {len(people)} ({people[0].year}--{people[-1].year})")

    overrides = {}
    if OVERRIDES.exists():
        with OVERRIDES.open(encoding="utf-8") as f:
            overrides = {row["key"]: row["openalex"] for row in csv.DictReader(f)}

    openalex = (
        None if args.no_openalex else OpenAlex(os.environ.get("OPENALEX_API_KEY"))
    )
    if openalex and not openalex.key:
        print("warning: no OPENALEX_API_KEY; using the shared keyless budget")
    rows, matched = [], []
    for person in people:
        author = None
        if openalex:
            override = overrides.get(person.key)
            if override == "none":
                author = None
            elif override:
                author = openalex.author(override)
            else:
                author = openalex.match(person)
                if author and not openalex.relevant(author, person.year):
                    author = None
        rows.append((person, author))
        if author:
            matched.append((person, author))
    if openalex:
        openalex.save()
        print(f"openalex: {len(matched)} matched, ${openalex.spent:.3f} spent this run")

    with (OUT / "alumni.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "key",
                "surname",
                "given",
                "year",
                "degrees",
                "advisor",
                "query",
                "openalex",
                "openalex_name",
                "works",
                "citations",
                "h_index",
                "institution",
                "sector",
            ]
        )
        for person, author in rows:
            inst = (
                (current_institution(author) or {}).get("display_name", "")
                if author
                else ""
            )
            writer.writerow(
                [
                    person.key,
                    person.surname,
                    person.given,
                    person.year,
                    ",".join(sorted(person.degrees)),
                    person.advisor,
                    person.query,
                    (author or {}).get("id", "").split("/")[-1],
                    (author or {}).get("display_name", ""),
                    (author or {}).get("works_count", ""),
                    (author or {}).get("cited_by_count", ""),
                    ((author or {}).get("summary_stats") or {}).get("h_index", ""),
                    inst,
                    sector(author) if author else "",
                ]
            )

    lines = [
        "% Generated by scripts/research_stats.py. Do not edit.",
        f"\\researchstat{{alumni}}{{{len(people)}}}",
        f"\\researchstat{{alumni-from}}{{{people[0].year}}}",
        f"\\researchstat{{alumni-phd}}{{{sum('phd' in p.degrees for p in people)}}}",
    ]
    for year, count in github_years().items():
        lines.append(f"\\githubyear{{{year}}}{{{count}}}")
    if openalex:
        lines.append(f"\\researchstat{{alumni-matched}}{{{len(matched)}}}")
        for label, low, high in COHORTS:
            cohort = [a for p, a in matched if low <= NOW - p.year <= high]
            if cohort:
                works = statistics.median(a["works_count"] for a in cohort)
                cites = statistics.median(a["cited_by_count"] for a in cohort)
                h = statistics.median(a["summary_stats"]["h_index"] for a in cohort)
                lines.append(
                    f"\\alumnicohort{{{label}}}{{{len(cohort)}}}{{{works:g}}}{{{cites:g}}}{{{h:g}}}"
                )
        sectors = [sector(a) for _, a in matched]
        lines.append(
            f"\\researchstat{{alumni-placed}}{{{sum(s is not None for s in sectors)}}}"
        )
        lines.append(
            f"\\researchstat{{sector-max}}{{{max(sectors.count(n) for n in SECTORS)}}}"
        )
        for name in SECTORS:
            lines.append(f"\\alumnisector{{{tex(name)}}}{{{sectors.count(name)}}}")
        abroad = Counter(
            inst["display_name"]
            for _, a in matched
            if (inst := current_institution(a)) and inst.get("country_code") != "RU"
        )
        names = [re.sub(r"\s*\(.*\)$", "", n) for n, _ in abroad.most_common()]
        lines.append(f"\\researchstat{{abroad}}{{{tex(', '.join(names))}}}")
        recent = [(p, a) for p, a in matched if p.year >= NOW - RECENT_YEARS]
        for macro, group in (("alumnitop", matched), ("alumnitoprecent", recent)):
            for person, author in sorted(
                group, key=lambda pa: -pa[1]["cited_by_count"]
            )[:5]:
                work = openalex.top_work(author["id"].split("/")[-1]) or {}
                cyrillic = re.search("[а-яё]", person.surname.lower())
                name = (
                    f"{person.given} {person.surname}" if cyrillic else person.name_en
                )
                lines.append(
                    f"\\{macro}{{{tex(name)}}}{{{person.year}}}"
                    f"{{{author['cited_by_count']}}}{{{author['summary_stats']['h_index']}}}"
                    f"{{{tex(work.get('title') or '')}}}{{{work.get('cited_by_count', 0)}}}"
                )
        openalex.save()
    (OUT / "stats.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {(OUT / 'stats.tex').relative_to(REPO)}: {len(lines) - 1} entries")


if __name__ == "__main__":
    main()
