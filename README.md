# intsystems-cover

YouTube covers for the Intelligent Systems channel.
Overleaf project, XeLaTeX, `main.tex`.

Old standalone files live in `legacy/` and are not part of the build.

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

## Presentation

`presentation.tex` is the department presentation for junior students, in the cover style (`sty/beamerthemeintsystems.sty`).
On Overleaf set Main document to **`presentation.tex`**; switch back to `main.tex` for covers.
Courses, instructors, and the GitHub repo count come from `data/site/`; scholarship holders, alumni, and charts are typed in `presentation.tex`.
Logos and portraits live in `assets/slides/`.

## Site data

The department presentation takes courses, people, and stats from a local clone of [intsystems.github.io](https://github.com/intsystems/intsystems.github.io).
Before an event, pull that repo, then run:

```sh
uv run --python 3.11 scripts/sync_site.py   # --site ../intsystems.github.io by default
```

It rewrites `data/site/{people,courses,stats}.tex` and `assets/site-people/` (avatars of course instructors and of the ids in `data/supervisors.tex`).
Commit the result: Overleaf builds offline.
`data/supervisors.tex` is edited by hand.

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
The id and the photo stem are the person's id on the department site (`lastname_ii`, as in `intsystems.github.io/_people/`), so slides can join cover data with site data.
Optional `photo-height`, `photo-x`, `photo-y` adjust lecture framing.

## Gotchas

- **Titles grow upward from a fixed line; subtitles and the session line stay put.** Break long titles with a plain `\\`; adding `\vspace` or `session-y` to compensate shifts the layout.
- **Text inside a TikZ node needs `\par` before the node ends.** Without it the paragraph ends outside the font group: lines use the normal-size baselineskip and `\hyphenpenalty` is lost.
- **Packages in `sty/` are found only through `latexmkrc`, which adds `./sty//` to `TEXINPUTS`.** Plain `xelatex main.tex` fails with `intsystems-cover.sty not found`; build with `latexmk`.
- **The PNG export in `latexmkrc` skips the root file `presentation`.** Rename `presentation.tex` and Overleaf will zip the slides as covers.
- **Open Sans is loaded by file name (`OpenSans-Regular.ttf`), not by family name.** Family lookup works on Overleaf but fails on a local TeX Live whose fonts fontconfig cannot see.

## Layout

```
main.tex                 Overleaf entry: covers
presentation.tex         Overleaf entry: department slides
latexmkrc                XeLaTeX, sty/ on TEXINPUTS, PNG zip
sty/intsystems-base.sty  Font, palette, people registry
sty/intsystems-cover.sty Cover layout and commands
sty/beamerthemeintsystems.sty  Slide theme
scripts/sync_site.py     Site data for the presentation
data/site/               Generated from the site, do not edit
data/supervisors.tex     Supervisors for team slides
data/people.tex          People registry
covers/                  One file per playlist
assets/backgrounds/      16:9 backgrounds
assets/people/           Portraits
assets/site-people/      Site avatars, generated
assets/logo/             Department logos
assets/slides/           Logos and portraits for slides
legacy/                  Previous standalone covers
```
