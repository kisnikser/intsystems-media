# intsystems-media

YouTube covers for the Intelligent Systems channel, Telegram post headers, and the department presentation for junior students, in one visual style.
Overleaf project, XeLaTeX: `main.tex` builds covers, `presentation.tex` builds slides.

Old standalone covers live in `legacy/` and are not part of the build.
Leave them unchanged unless a path or compile fix is required.

## Build

Upload this repo to Overleaf.
Set Compiler to **XeLaTeX** and Main document to **`main.tex`**.
Open Sans is in TeX Live.
Overleaf runs XeLaTeX twice so TikZ overlay positions settle.

`\BuildCover` defaults to `all`.
Set it to a file name from `covers/` (no `.tex`) to build one playlist:

```tex
\newcommand{\BuildCover}{python}
```

`\coversemester{FALL 2026}` sets the term under the brand for every cover.
Override one playlist with `semester` in `\coversetup`.

Overleaf still downloads a PDF.
After Recompile, open Logs and output files, then Other logs and files, and take `covers-png.zip`.
Each page is 1920×1080.

## Add a cover

Copy `covers/template.tex` or a neighbour.
Add `\usecover{name}` in `main.tex`.
Register a person in `data/people.tex` if needed.

Lecture:

```tex
\coversetup{
  kind       = lecture,
  title      = {Course title},
  background = white-yellow,
  session    = {Лекция},
  semester   = {FALL 2026},
}
\covers{1,...,14}{vorontsov_kv}
```

Event:

```tex
\coversetup{
  kind       = event,
  title      = {Title},
  subtitle   = {Subtitle},
  background = design-2,
  badge      = {Интервью},
  lecturer   = panov_maxim,
}
\cover
```

Lecturer and seminarist on one cover:

```tex
\cover[session-number=1, lecturer=grabovoy_av, seminarist=kiselev_ns]
\covers[kiselev_ns]{1,...,14}{grabovoy_av}
```

## Keys

| Key | Meaning |
|---|---|
| `kind` | `lecture` or `event` |
| `semester` | `FALL 2026`, `SPRING 2026` |
| `title` | Course or event title |
| `subtitle` | Event subtitle |
| `subtitle-size` | `large` or `Huge` |
| `background` | File stem in `assets/backgrounds/` |
| `session` | `Лекция`, `Занятие`, `Семинар` |
| `session-number` | Session index |
| `session-y` | Shift the session line |
| `badge` | Event label at the bottom |
| `lecturer` | Id from `data/people.tex` |
| `seminarist` | Optional seminarist id |
| `alert` | Accent HEX if the palette is wrong |
| `text` | `black` or `white` if contrast is wrong |
| `photo-height`, `photo-x`, `photo-y` | Photo crop |

`white-*` backgrounds use dark text.
`black-*` backgrounds use light text.

## Add a person

```tex
\defineperson{kiselev_ns}{
  name  = {НИКИТА КИСЕЛЕВ},
  photo = {kiselev_ns.png},
}
```

Put the photo in `assets/people/`.
The id and the photo stem are the person's id on the department site (`lastname_ii`, as in `intsystems.github.io/_people/`), so one id names a person in covers, slides, and the site.
Optional `photo-height`, `photo-x`, `photo-y` adjust lecture framing.

## Presentation

`presentation.tex` is the department presentation for junior students, in the cover style (`sty/beamerthemeintsystems.sty`).
On Overleaf set Main document to **`presentation.tex`**; switch back to `main.tex` for covers.
Courses, instructors, theses, admission dates, and graduation photos come from `data/site/`; alumni and open-source charts from `data/research/`; scholarship holders are typed in `presentation.tex`.
Colors follow the site: accent `#c42929`, white slides, `#f5f5f5` cards.
Logos and portraits live in `assets/slides/`.
Team slides take `assets/slides/avatars/<id>.jpg` first (for people whose site avatar is missing or the placeholder), then the site avatar from `assets/site-people/`, then the cover portrait `assets/people/<id>.png`.

## Site data

The department presentation takes courses, people, and stats from a local clone of [intsystems.github.io](https://github.com/intsystems/intsystems.github.io).
Before an event, pull that repo, then run:

```sh
uv run --python 3.11 scripts/sync_site.py   # --site ../intsystems.github.io by default
```

It rewrites `data/site/{people,courses,stats,theses,admission}.tex`, `assets/site-people/` (avatars of course instructors and of the ids in `data/supervisors.tex`), and `assets/site-life/` (graduation photos of the latest year).
Commit the result: Overleaf builds offline.
`data/supervisors.tex` is edited by hand.

## Research data

The charts on alumni and open source come from `scripts/research_stats.py`:

| Data | Source |
|---|---|
| Alumni registry | machinelearning.ru page «Интеллектуальные системы (кафедра МФТИ)/Студенты» (2007 on) and the site's `thesis.md` (2022 on) |
| Publications, citations, h-index, current affiliation | OpenAlex authors affiliated with MIPT, Skoltech, or FRC CSC RAS |
| Open-source projects per year | GitHub API, own public repos of `Intelligent-Systems-Phystech` and `intsystems` |

```sh
OPENALEX_API_KEY=$(security find-generic-password -s openalex -w) \
  uv run --python 3.11 scripts/research_stats.py
```

It writes `data/research/stats.tex` and `data/research/alumni.csv`, one row per alumnus with the matched OpenAlex author.
Check the CSV after a run; fix a wrong match by adding `key,openalex` rows (`openalex` is an author id or `none`) to `data/research/overrides.csv` and rerun.
OpenAlex answers are cached in `data/research/openalex.json`, so a rerun only pays for new queries.

## Telegram posts

One file per channel post: `posts/YYYY-MM-DD-slug.md`, copied from `posts/template.md`.
Front matter is flat `key: value`; the body is the caption in Telegram HTML (`<b>`, `<i>`, `<a href>`, `<blockquote>`).

| Key | Meaning |
|---|---|
| `date` | Publication time, `YYYY-MM-DD HH:MM` |
| `rubric` | `paper`, `accepted`, `award`, `event`, `seminar`, `deadlines`, `news`; sets the default background and badge |
| `status` | `draft`, `approved`, `published`, `rejected` |
| `title`, `subtitle` | Header text, TeX as in `covers/` |
| `person` | Optional id from `data/people.tex`, drawn on the header |
| `background`, `badge` | Override the rubric defaults |
| `message_id` | Channel message id once published |

```sh
uv run --python 3.11 scripts/render_post.py posts/2026-10-27-mipt-conference.md
```

It writes `build/posts/<stem>.png` (1920×1080, the `event` cover layout) and `build/posts/<stem>.html` (the caption).
It refuses a post with an unknown rubric or status, a tag Telegram rejects, or a caption over 1024 characters.
Rubric defaults live in `RUBRICS` in `scripts/render_post.py`.
`build/` is not committed.

A push to `main` that adds or changes a post with `status: draft` runs `.github/workflows/preview-posts.yml`: it renders the post and sends the header, caption, and metadata to the editor through [@intsystems_media_bot](https://t.me/intsystems_media_bot).
Resend one post with Actions → Preview posts → Run workflow.
The workflow needs the repository secret `TELEGRAM_BOT_TOKEN` and the variable `TELEGRAM_EDITOR_ID` (the editor's numeric Telegram id).
The editor must have sent `/start` to the bot once; a bot cannot open a chat.
The repository is public, so a pushed draft is public before it is posted: push news under embargo only once it is announced.

## Gotchas

- **Titles grow upward from a fixed line; subtitles and the session line stay put.** Break long titles with a plain `\\`; adding `\vspace` or `session-y` to compensate shifts the layout.
- **Text inside a TikZ node needs `\par` before the node ends.** Without it the paragraph ends outside the font group: lines use the normal-size baselineskip and `\hyphenpenalty` is lost.
- **Packages in `sty/` are found only through `latexmkrc`, which adds `./sty//` to `TEXINPUTS`.** Plain `xelatex main.tex` fails with `intsystems-cover.sty not found`; build with `latexmk`.
- **The PNG export in `latexmkrc` skips the root file `presentation`.** Rename `presentation.tex` and Overleaf will zip the slides as covers.
- **OpenAlex matching misses alumni whose profiles have no MIPT, Skoltech, or FRC CSC affiliation, and those spelled unlike the transliteration (`Фрей` is `Frei`).** Charts say how many alumni were matched; add misses to `data/research/overrides.csv`.
- **A search costs $0.001 of OpenAlex budget; without a key the whole network shares $0.10 a day.** A full run without the cache needs about $0.6, so use the free key (Keychain service `openalex`).
- **Only `design-*` and `black-design-*` backgrounds carry the logo that the `event` badge sits next to.** On other backgrounds the badge floats right of an empty spot; keep post backgrounds to these six.
- **Open Sans is loaded by file name (`OpenSans-Regular.ttf`), not by family name.** Family lookup works on Overleaf but fails on a local TeX Live whose fonts fontconfig cannot see.

## Layout

```
main.tex                       Overleaf entry: covers
presentation.tex               Overleaf entry: department slides
latexmkrc                      XeLaTeX, sty/ on TEXINPUTS, PNG zip
sty/intsystems-base.sty        Font, palette, people registry
sty/intsystems-cover.sty       Cover layout and commands
sty/beamerthemeintsystems.sty  Slide theme
scripts/sync_site.py           Site data for the presentation
data/site/                     Generated from the site, do not edit
scripts/research_stats.py      Alumni and GitHub data for the charts
scripts/render_post.py         Telegram post header and caption check
.github/workflows/             Post previews to the editor
posts/                         One file per Telegram post
data/research/                 Generated research data and OpenAlex cache
data/supervisors.tex           Supervisors for team slides
data/people.tex                People registry
covers/                        One file per playlist
assets/backgrounds/            16:9 backgrounds
assets/people/                 Portraits
assets/site-people/            Site avatars, generated
assets/site-life/              Site graduation photos, generated
assets/logo/                   Department logos
assets/slides/                 Logos and portraits for slides
legacy/                        Previous standalone covers
```
