"""Vertical reel (1080×1920) from a scenario file, in the cover style.

    REEL=reels/example.toml manimgx render reels/reel.py -o build/reels/example.mp4

The scenario lists frames in order; each has a `kind` and a duration in seconds.
Kinds: title, text, formula, image, person, outro (see reels/example.toml).
"""

import os
from pathlib import Path

import manimgx as m
import tomllib

m.config.pixel_width, m.config.pixel_height = 1080, 1920
m.config.frame_rate = 30

REPO = Path(__file__).resolve().parent.parent
FONTS = [str(REPO / "assets" / "fonts")]
FONT = "Open Sans"
W, H = 8.0, 14.222  # scene units of a 1080×1920 frame
MARGIN = 0.55


def _text(s: str, size: int, bold: bool, color) -> m.Text:
    return m.Text(
        s,
        font=FONT,
        font_paths=FONTS,
        font_size=size,
        weight=m.BOLD if bold else m.NORMAL,
        color=color,
    )


def wrap(s: str, size: int, bold: bool, width: float) -> str:
    """Break each paragraph into lines that fit `width`, measuring the rendered text."""
    out = []
    for paragraph in s.split("\n"):
        line = ""
        for word in paragraph.split():
            trial = f"{line} {word}".strip()
            if line and _text(trial, size, bold, m.WHITE).width > width:
                out.append(line)
                line = word
            else:
                line = trial
        out.append(line)
    return "\n".join(out)


def text(
    s: str, size: int, bold: bool = False, color=m.WHITE, width: float = W - 2 * MARGIN
) -> m.Mobject:
    """Left-aligned text, wrapped to the frame instead of shrunk."""
    mob = _text(wrap(s, size, bold, width), size, bold, color)
    return mob.align_to([-W / 2 + MARGIN, 0, 0], m.LEFT)


def centered(s: str, size: int, bold: bool, color) -> m.Mobject:
    """Wrapped text with each line centred on the frame."""
    lines = [
        _text(line, size, bold, color)
        for line in wrap(s, size, bold, W - 2 * MARGIN).split("\n")
    ]
    return m.VGroup(*lines).arrange(m.DOWN, buff=0.18).set_x(0)


class Reel(m.Scene):
    def construct(self) -> None:
        scenario = tomllib.loads(Path(os.environ["REEL"]).read_text(encoding="utf-8"))
        accent = m.ManimColor(scenario.get("accent", "#FFFFFF"))
        frames = scenario["frame"]
        total = sum(f.get("duration", 3) for f in frames)

        # Background: a 16:9 cover background, cropped to the vertical frame and drifting slowly.
        bg = m.ImageMobject(
            str(
                REPO
                / "assets"
                / "backgrounds"
                / f"{scenario.get('background', 'black-design-2')}.png"
            )
        )
        bg.scale_to_fit_height(H).shift(2.5 * m.RIGHT)
        self.add(bg)
        bg.add_updater(lambda mob, dt: mob.shift(0.12 * dt * m.LEFT))

        # Brand line and a progress bar that fills over the whole reel.
        brand = text("INTELLIGENT SYSTEMS", 34, color=accent).to_edge(m.UP, buff=0.9)
        bar_back = m.Line(
            [-W / 2 + MARGIN, -H / 2 + 0.7, 0],
            [W / 2 - MARGIN, -H / 2 + 0.7, 0],
            stroke_width=4,
            color=m.WHITE,
            stroke_opacity=0.25,
        )
        bar = m.Line(
            bar_back.get_start(),
            bar_back.get_start() + [0.001, 0, 0],
            stroke_width=4,
            color=accent,
        )
        start, length = bar_back.get_start(), bar_back.get_length()
        elapsed = {"t": 0.0}

        def grow(mob: m.Mobject, dt: float) -> None:
            elapsed["t"] = min(elapsed["t"] + dt, total)
            mob.put_start_and_end_on(
                start, start + [max(length * elapsed["t"] / total, 0.001), 0, 0]
            )

        bar.add_updater(grow)
        self.add(bar_back, bar, brand)

        for frame in frames:
            group = getattr(self, f"frame_{frame['kind']}")(frame, accent)
            hold = frame.get("duration", 3)
            self.play(
                m.LaggedStart(
                    *(m.FadeIn(part, shift=0.3 * m.UP) for part in group),
                    lag_ratio=0.15,
                ),
                run_time=0.8,
            )
            self.wait(max(hold - 1.4, 0.2))
            self.play(m.FadeOut(m.Group(*group), shift=0.3 * m.UP), run_time=0.6)

    # --- frame kinds; each returns its parts in the order they appear ---------------

    def frame_title(self, f: dict, accent) -> list[m.Mobject]:
        parts = []
        if badge := f.get("badge"):
            parts.append(text(badge.upper(), 30, bold=True, color=accent))
        parts.append(text(f["title"], 64, bold=True))
        if sub := f.get("subtitle"):
            parts.append(text(sub, 40))
        return [
            m.Group(*parts)
            .arrange(m.DOWN, aligned_edge=m.LEFT, buff=0.45)
            .move_to([0, 0.6, 0])
            .align_to([-W / 2 + MARGIN, 0, 0], m.LEFT)
        ][0].submobjects

    def frame_text(self, f: dict, accent) -> list[m.Mobject]:
        parts = [
            text(
                " ".join(f["lines"]) if isinstance(f["lines"], list) else f["lines"], 44
            )
        ]
        if head := f.get("heading"):
            parts.insert(0, text(head, 34, bold=True, color=accent))
        return (
            m.VGroup(*parts)
            .arrange(m.DOWN, aligned_edge=m.LEFT, buff=0.45)
            .move_to([0, 0.4, 0])
            .align_to([-W / 2 + MARGIN, 0, 0], m.LEFT)
            .submobjects
        )

    def frame_formula(self, f: dict, accent) -> list[m.Mobject]:
        formula = m.MathTex(f["tex"], color=m.WHITE)
        formula.scale_to_fit_width(W - 2 * MARGIN)  # formulas are short; fill the width
        if formula.height > 2.5:
            formula.scale_to_fit_height(2.5)
        parts = [formula.move_to([0, 0.8, 0])]
        if cap := f.get("caption"):
            parts.append(
                text(cap, 34)
                .next_to(formula, m.DOWN, buff=0.7)
                .align_to([-W / 2 + MARGIN, 0, 0], m.LEFT)
            )
        return parts

    def frame_image(self, f: dict, accent) -> list[m.Mobject]:
        image = m.ImageMobject(str(REPO / f["image"])).scale_to_fit_width(
            W - 2 * MARGIN
        )
        if image.height > H * 0.55:
            image.scale_to_fit_height(H * 0.55)
        frame = m.SurroundingRectangle(image, buff=0, color=accent, stroke_width=3)
        parts = [m.Group(image, frame).move_to([0, 1.0, 0])]
        if cap := f.get("caption"):
            parts.append(
                text(cap, 34)
                .next_to(parts[0], m.DOWN, buff=0.5)
                .align_to([-W / 2 + MARGIN, 0, 0], m.LEFT)
            )
        return parts

    def frame_person(self, f: dict, accent) -> list[m.Mobject]:
        photo = m.ImageMobject(
            str(REPO / "assets" / "people" / f"{f['person']}.png")
        ).scale_to_fit_height(H * 0.45)
        photo.move_to([W / 2 - photo.width / 2, -H / 2 + 0.9 + photo.height / 2, 0])
        name = (
            text(f["name"], 48, bold=True)
            .move_to([0, 4.2, 0])
            .align_to([-W / 2 + MARGIN, 0, 0], m.LEFT)
        )
        parts = [photo, name]
        if role := f.get("role"):
            parts.append(
                text(role, 32, color=accent)
                .next_to(name, m.DOWN, buff=0.3)
                .align_to(name, m.LEFT)
            )
        return parts

    def frame_outro(self, f: dict, accent) -> list[m.Mobject]:
        logo = (
            m.ImageMobject(str(REPO / "assets" / "logo" / "square.png"))
            .scale_to_fit_height(2.6)
            .move_to([0, 1.6, 0])
        )
        parts = [
            logo,
            centered(
                f.get("title", "Кафедра интеллектуальных систем"), 44, True, m.WHITE
            ).next_to(logo, m.DOWN, buff=0.6),
        ]
        if cta := f.get("cta"):
            parts.append(
                centered(cta, 34, False, accent).next_to(parts[-1], m.DOWN, buff=0.35)
            )
        return parts
