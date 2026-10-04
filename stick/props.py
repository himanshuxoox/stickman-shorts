"""Flat vector props and emotes, drawn with cairo. Every drawer: fn(ctx, x, y, size, accent)."""
import math

import cairo

INK = (0.07, 0.07, 0.09)
ACCENTS = {"red": (0.93, 0.22, 0.27), "blue": (0.16, 0.47, 0.96), "yellow": (1.0, 0.74, 0.1),
           "green": (0.13, 0.72, 0.38), "purple": (0.55, 0.32, 0.95), "orange": (1.0, 0.5, 0.12)}
GRAY = (0.62, 0.63, 0.67)


def _line(ctx, w):
    ctx.set_line_width(w)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)


def _rrect(ctx, x, y, w, h, r):
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


def _fill_stroke(ctx, fill, w):
    ctx.set_source_rgb(*fill)
    ctx.fill_preserve()
    ctx.set_source_rgb(*INK)
    _line(ctx, w)
    ctx.stroke()


def _text(ctx, s, x, y, size, rgb=INK):
    ctx.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(size)
    e = ctx.text_extents(s)
    ctx.move_to(x - e.width / 2 - e.x_bearing, y - e.height / 2 - e.y_bearing)
    ctx.set_source_rgb(*rgb)
    ctx.show_text(s)
    ctx.new_path()


# ------------------------------------------------------------------ props
def phone(ctx, x, y, s, a):
    _rrect(ctx, x - 0.32 * s, y - 0.55 * s, 0.64 * s, 1.1 * s, 0.1 * s)
    _fill_stroke(ctx, (0.15, 0.16, 0.2), 0.07 * s)
    _rrect(ctx, x - 0.24 * s, y - 0.45 * s, 0.48 * s, 0.86 * s, 0.05 * s)
    ctx.set_source_rgb(*a)
    ctx.fill()


def brain(ctx, x, y, s, a):
    pink = (1.0, 0.62, 0.72)
    for dx, dy, r in ((-0.22, -0.08, 0.3), (0.22, -0.08, 0.3), (-0.3, 0.16, 0.24), (0.3, 0.16, 0.24),
                      (0, -0.22, 0.28), (0, 0.18, 0.26)):
        ctx.arc(x + dx * s, y + dy * s, r * s, 0, 2 * math.pi)
        ctx.new_sub_path()
    ctx.set_source_rgb(*pink)
    ctx.fill()
    _line(ctx, 0.06 * s)
    ctx.set_source_rgb(*INK)
    ctx.move_to(x, y - 0.45 * s)
    ctx.line_to(x, y + 0.4 * s)
    ctx.stroke()
    for dx in (-0.28, 0.28):
        ctx.arc(x + dx * s, y, 0.14 * s, math.pi * 0.2, math.pi * 1.2)
        ctx.stroke()


def lightbulb(ctx, x, y, s, a):
    ctx.arc(x, y - 0.12 * s, 0.38 * s, 0, 2 * math.pi)
    _fill_stroke(ctx, ACCENTS["yellow"], 0.07 * s)
    ctx.rectangle(x - 0.16 * s, y + 0.24 * s, 0.32 * s, 0.22 * s)
    _fill_stroke(ctx, GRAY, 0.06 * s)
    _line(ctx, 0.05 * s)
    for k in range(7):
        ang = math.pi + k * math.pi / 6
        ctx.move_to(x + 0.5 * s * math.cos(ang), y - 0.12 * s + 0.5 * s * math.sin(ang))
        ctx.line_to(x + 0.66 * s * math.cos(ang), y - 0.12 * s + 0.66 * s * math.sin(ang))
    ctx.set_source_rgb(*ACCENTS["yellow"])
    ctx.stroke()


def money(ctx, x, y, s, a):
    ctx.arc(x, y, 0.45 * s, 0, 2 * math.pi)
    _fill_stroke(ctx, ACCENTS["green"], 0.07 * s)
    _text(ctx, "$", x, y, 0.62 * s, (1, 1, 1))


def coin_stack(ctx, x, y, s, a):
    for k in range(5):
        cy = y + 0.35 * s - k * 0.16 * s
        ctx.save()
        ctx.translate(x, cy)
        ctx.scale(1, 0.35)
        ctx.arc(0, 0, 0.4 * s, 0, 2 * math.pi)
        ctx.restore()
        _fill_stroke(ctx, ACCENTS["yellow"], 0.05 * s)


def clock(ctx, x, y, s, a):
    ctx.arc(x, y, 0.45 * s, 0, 2 * math.pi)
    _fill_stroke(ctx, (1, 1, 1), 0.08 * s)
    _line(ctx, 0.07 * s)
    ctx.set_source_rgb(*a)
    ctx.move_to(x, y)
    ctx.line_to(x, y - 0.3 * s)
    ctx.move_to(x, y)
    ctx.line_to(x + 0.22 * s, y + 0.08 * s)
    ctx.stroke()


def hourglass(ctx, x, y, s, a):
    ctx.move_to(x - 0.3 * s, y - 0.5 * s)
    ctx.line_to(x + 0.3 * s, y - 0.5 * s)
    ctx.line_to(x, y)
    ctx.line_to(x + 0.3 * s, y + 0.5 * s)
    ctx.line_to(x - 0.3 * s, y + 0.5 * s)
    ctx.line_to(x, y)
    ctx.close_path()
    _fill_stroke(ctx, (1, 1, 1), 0.07 * s)
    ctx.move_to(x - 0.2 * s, y + 0.44 * s)
    ctx.line_to(x + 0.2 * s, y + 0.44 * s)
    ctx.line_to(x, y + 0.2 * s)
    ctx.close_path()
    ctx.set_source_rgb(*a)
    ctx.fill()


def heart(ctx, x, y, s, a, color=None):
    c = color or ACCENTS["red"]
    ctx.move_to(x, y + 0.4 * s)
    ctx.curve_to(x - 0.7 * s, y - 0.1 * s, x - 0.35 * s, y - 0.6 * s, x, y - 0.2 * s)
    ctx.curve_to(x + 0.35 * s, y - 0.6 * s, x + 0.7 * s, y - 0.1 * s, x, y + 0.4 * s)
    ctx.close_path()
    _fill_stroke(ctx, c, 0.06 * s)


def broken_heart(ctx, x, y, s, a):
    heart(ctx, x, y, s, a)
    _line(ctx, 0.08 * s)
    ctx.set_source_rgb(1, 1, 1)
    ctx.move_to(x, y - 0.2 * s)
    ctx.line_to(x - 0.08 * s, y)
    ctx.line_to(x + 0.08 * s, y + 0.12 * s)
    ctx.line_to(x, y + 0.36 * s)
    ctx.stroke()


def _chart(ctx, x, y, s, up):
    _line(ctx, 0.07 * s)
    ctx.set_source_rgb(*INK)
    ctx.move_to(x - 0.5 * s, y - 0.5 * s)
    ctx.line_to(x - 0.5 * s, y + 0.5 * s)
    ctx.line_to(x + 0.55 * s, y + 0.5 * s)
    ctx.stroke()
    pts = [(-0.4, 0.3), (-0.15, 0.05), (0.08, 0.18), (0.42, -0.35)] if up else \
          [(-0.4, -0.35), (-0.15, -0.05), (0.08, -0.18), (0.42, 0.3)]
    ctx.set_source_rgb(*(ACCENTS["green"] if up else ACCENTS["red"]))
    _line(ctx, 0.1 * s)
    ctx.move_to(x + pts[0][0] * s, y + pts[0][1] * s)
    for px, py in pts[1:]:
        ctx.line_to(x + px * s, y + py * s)
    ctx.stroke()


def chart_up(ctx, x, y, s, a):
    _chart(ctx, x, y, s, True)


def chart_down(ctx, x, y, s, a):
    _chart(ctx, x, y, s, False)


def trophy(ctx, x, y, s, a):
    gold = ACCENTS["yellow"]
    ctx.move_to(x - 0.35 * s, y - 0.45 * s)
    ctx.line_to(x + 0.35 * s, y - 0.45 * s)
    ctx.curve_to(x + 0.35 * s, y + 0.05 * s, x + 0.1 * s, y + 0.12 * s, x, y + 0.12 * s)
    ctx.curve_to(x - 0.1 * s, y + 0.12 * s, x - 0.35 * s, y + 0.05 * s, x - 0.35 * s, y - 0.45 * s)
    ctx.close_path()
    _fill_stroke(ctx, gold, 0.06 * s)
    ctx.rectangle(x - 0.06 * s, y + 0.12 * s, 0.12 * s, 0.2 * s)
    _fill_stroke(ctx, gold, 0.05 * s)
    ctx.rectangle(x - 0.25 * s, y + 0.32 * s, 0.5 * s, 0.13 * s)
    _fill_stroke(ctx, gold, 0.05 * s)


def book(ctx, x, y, s, a):
    _rrect(ctx, x - 0.42 * s, y - 0.3 * s, 0.84 * s, 0.6 * s, 0.05 * s)
    _fill_stroke(ctx, a, 0.07 * s)
    ctx.set_source_rgb(*INK)
    ctx.move_to(x, y - 0.3 * s)
    ctx.line_to(x, y + 0.3 * s)
    ctx.stroke()


def dumbbell(ctx, x, y, s, a):
    _line(ctx, 0.1 * s)
    ctx.set_source_rgb(*INK)
    ctx.move_to(x - 0.4 * s, y)
    ctx.line_to(x + 0.4 * s, y)
    ctx.stroke()
    for dx in (-0.45, 0.45):
        _rrect(ctx, x + dx * s - 0.1 * s, y - 0.25 * s, 0.2 * s, 0.5 * s, 0.05 * s)
        _fill_stroke(ctx, a, 0.05 * s)


def target(ctx, x, y, s, a):
    for r, c in ((0.48, ACCENTS["red"]), (0.32, (1, 1, 1)), (0.16, ACCENTS["red"])):
        ctx.arc(x, y, r * s, 0, 2 * math.pi)
        _fill_stroke(ctx, c, 0.05 * s)


def scale(ctx, x, y, s, a):
    _line(ctx, 0.07 * s)
    ctx.set_source_rgb(*INK)
    ctx.move_to(x, y - 0.45 * s)
    ctx.line_to(x, y + 0.45 * s)
    ctx.move_to(x - 0.25 * s, y + 0.45 * s)
    ctx.line_to(x + 0.25 * s, y + 0.45 * s)
    ctx.move_to(x - 0.5 * s, y - 0.3 * s)
    ctx.line_to(x + 0.5 * s, y - 0.3 * s)
    ctx.stroke()
    for dx in (-0.5, 0.5):
        ctx.arc(x + dx * s, y - 0.05 * s, 0.18 * s, 0, math.pi)
        _fill_stroke(ctx, a, 0.05 * s)


def calendar(ctx, x, y, s, a):
    _rrect(ctx, x - 0.42 * s, y - 0.38 * s, 0.84 * s, 0.8 * s, 0.07 * s)
    _fill_stroke(ctx, (1, 1, 1), 0.07 * s)
    ctx.rectangle(x - 0.42 * s, y - 0.38 * s, 0.84 * s, 0.22 * s)
    ctx.set_source_rgb(*a)
    ctx.fill()
    for r in range(2):
        for c in range(3):
            ctx.rectangle(x + (-0.28 + c * 0.2) * s, y + (-0.06 + r * 0.2) * s, 0.12 * s, 0.12 * s)
    ctx.set_source_rgb(*GRAY)
    ctx.fill()


def battery(ctx, x, y, s, a, level=0.2):
    _rrect(ctx, x - 0.45 * s, y - 0.22 * s, 0.85 * s, 0.44 * s, 0.06 * s)
    _fill_stroke(ctx, (1, 1, 1), 0.07 * s)
    ctx.rectangle(x + 0.42 * s, y - 0.1 * s, 0.08 * s, 0.2 * s)
    ctx.set_source_rgb(*INK)
    ctx.fill()
    ctx.rectangle(x - 0.38 * s, y - 0.15 * s, 0.71 * s * level, 0.3 * s)
    ctx.set_source_rgb(*(ACCENTS["red"] if level < 0.4 else ACCENTS["green"]))
    ctx.fill()


def battery_low(ctx, x, y, s, a):
    battery(ctx, x, y, s, a, 0.18)


def battery_full(ctx, x, y, s, a):
    battery(ctx, x, y, s, a, 1.0)


def lock(ctx, x, y, s, a):
    _line(ctx, 0.09 * s)
    ctx.set_source_rgb(*INK)
    ctx.arc(x, y - 0.12 * s, 0.22 * s, math.pi, 2 * math.pi)
    ctx.stroke()
    _rrect(ctx, x - 0.35 * s, y - 0.12 * s, 0.7 * s, 0.55 * s, 0.07 * s)
    _fill_stroke(ctx, a, 0.06 * s)


def gift(ctx, x, y, s, a):
    ctx.rectangle(x - 0.4 * s, y - 0.2 * s, 0.8 * s, 0.6 * s)
    _fill_stroke(ctx, a, 0.06 * s)
    ctx.rectangle(x - 0.07 * s, y - 0.2 * s, 0.14 * s, 0.6 * s)
    ctx.set_source_rgb(*ACCENTS["yellow"])
    ctx.fill()
    _line(ctx, 0.06 * s)
    ctx.set_source_rgb(*ACCENTS["yellow"])
    for d in (-1, 1):
        ctx.move_to(x, y - 0.2 * s)
        ctx.curve_to(x + d * 0.3 * s, y - 0.55 * s, x + d * 0.4 * s, y - 0.2 * s, x, y - 0.2 * s)
    ctx.stroke()


def bell(ctx, x, y, s, a):
    ctx.move_to(x - 0.35 * s, y + 0.25 * s)
    ctx.curve_to(x - 0.3 * s, y - 0.5 * s, x + 0.3 * s, y - 0.5 * s, x + 0.35 * s, y + 0.25 * s)
    ctx.close_path()
    _fill_stroke(ctx, ACCENTS["yellow"], 0.06 * s)
    ctx.arc(x, y + 0.32 * s, 0.08 * s, 0, 2 * math.pi)
    ctx.set_source_rgb(*INK)
    ctx.fill()
    ctx.arc(x + 0.32 * s, y - 0.32 * s, 0.14 * s, 0, 2 * math.pi)
    ctx.set_source_rgb(*ACCENTS["red"])
    ctx.fill()


def coffee(ctx, x, y, s, a):
    ctx.move_to(x - 0.3 * s, y - 0.25 * s)
    ctx.line_to(x + 0.3 * s, y - 0.25 * s)
    ctx.line_to(x + 0.24 * s, y + 0.38 * s)
    ctx.line_to(x - 0.24 * s, y + 0.38 * s)
    ctx.close_path()
    _fill_stroke(ctx, (0.55, 0.35, 0.22), 0.06 * s)
    _line(ctx, 0.06 * s)
    ctx.set_source_rgb(*INK)
    ctx.arc(x + 0.32 * s, y, 0.13 * s, -math.pi / 2, math.pi / 2)
    ctx.stroke()
    ctx.set_source_rgb(*GRAY)
    for dx in (-0.1, 0.1):
        ctx.move_to(x + dx * s, y - 0.35 * s)
        ctx.curve_to(x + (dx - 0.08) * s, y - 0.45 * s, x + (dx + 0.08) * s, y - 0.55 * s, x + dx * s, y - 0.65 * s)
    ctx.stroke()


def crowd(ctx, x, y, s, a):
    from . import rig
    for k, dx in enumerate((-0.7, -0.35, 0, 0.35, 0.7)):
        rig.draw(ctx, rig.pose_at("stand", k * 0.3), x + dx * s, y + 0.5 * s, s * 0.0016,
                 color=GRAY, width=18, shadow=False)


def speech_bubble(ctx, x, y, s, a):
    _rrect(ctx, x - 0.55 * s, y - 0.35 * s, 1.1 * s, 0.6 * s, 0.2 * s)
    _fill_stroke(ctx, (1, 1, 1), 0.06 * s)
    for dx in (-0.22, 0, 0.22):
        ctx.arc(x + dx * s, y - 0.05 * s, 0.06 * s, 0, 2 * math.pi)
        ctx.set_source_rgb(*a)
        ctx.fill()


def check(ctx, x, y, s, a):
    ctx.arc(x, y, 0.42 * s, 0, 2 * math.pi)
    ctx.set_source_rgb(*ACCENTS["green"])
    ctx.fill()
    _line(ctx, 0.12 * s)
    ctx.set_source_rgb(1, 1, 1)
    ctx.move_to(x - 0.2 * s, y)
    ctx.line_to(x - 0.04 * s, y + 0.16 * s)
    ctx.line_to(x + 0.22 * s, y - 0.16 * s)
    ctx.stroke()


def cross(ctx, x, y, s, a):
    ctx.arc(x, y, 0.42 * s, 0, 2 * math.pi)
    ctx.set_source_rgb(*ACCENTS["red"])
    ctx.fill()
    _line(ctx, 0.12 * s)
    ctx.set_source_rgb(1, 1, 1)
    for d in (1, -1):
        ctx.move_to(x - 0.17 * s, y - d * 0.17 * s)
        ctx.line_to(x + 0.17 * s, y + d * 0.17 * s)
    ctx.stroke()


def arrow_right(ctx, x, y, s, a):
    _line(ctx, 0.14 * s)
    ctx.set_source_rgb(*a)
    ctx.move_to(x - 0.5 * s, y)
    ctx.line_to(x + 0.4 * s, y)
    ctx.move_to(x + 0.15 * s, y - 0.25 * s)
    ctx.line_to(x + 0.45 * s, y)
    ctx.line_to(x + 0.15 * s, y + 0.25 * s)
    ctx.stroke()


def flame(ctx, x, y, s, a):
    for k, (sc, col) in enumerate(((1.0, ACCENTS["orange"]), (0.55, ACCENTS["yellow"]))):
        ctx.move_to(x, y - 0.55 * s * sc)
        ctx.curve_to(x + 0.45 * s * sc, y - 0.1 * s * sc, x + 0.38 * s * sc, y + 0.42 * s * sc, x, y + 0.42 * s * sc)
        ctx.curve_to(x - 0.38 * s * sc, y + 0.42 * s * sc, x - 0.45 * s * sc, y - 0.1 * s * sc, x, y - 0.55 * s * sc)
        ctx.close_path()
        ctx.set_source_rgb(*col)
        ctx.fill()


def ladder(ctx, x, y, s, a):
    _line(ctx, 0.07 * s)
    ctx.set_source_rgb(*INK)
    for dx in (-0.25, 0.25):
        ctx.move_to(x + dx * s, y - 0.6 * s)
        ctx.line_to(x + dx * s, y + 0.6 * s)
    for k in range(5):
        yy = y - 0.45 * s + k * 0.24 * s
        ctx.move_to(x - 0.25 * s, yy)
        ctx.line_to(x + 0.25 * s, yy)
    ctx.stroke()


def thought_cloud(ctx, x, y, s, a):
    for dx, dy, r in ((-0.3, 0, 0.28), (0, -0.12, 0.34), (0.32, 0, 0.28), (0, 0.12, 0.3)):
        ctx.arc(x + dx * s, y + dy * s, r * s, 0, 2 * math.pi)
        ctx.new_sub_path()
    ctx.set_source_rgb(*INK)
    _line(ctx, 0.1 * s)
    ctx.stroke_preserve()
    ctx.set_source_rgb(1, 1, 1)
    ctx.fill()
    for k, (dx, dy, r) in enumerate(((-0.45, 0.45, 0.08), (-0.6, 0.62, 0.05))):
        ctx.arc(x + dx * s, y + dy * s, r * s, 0, 2 * math.pi)
        _fill_stroke(ctx, (1, 1, 1), 0.04 * s)


def rain_cloud(ctx, x, y, s, a):
    for dx, dy, r in ((-0.3, 0, 0.26), (0, -0.12, 0.32), (0.3, 0, 0.26)):
        ctx.arc(x + dx * s, y + dy * s, r * s, 0, 2 * math.pi)
        ctx.new_sub_path()
    ctx.set_source_rgb(0.55, 0.57, 0.62)
    ctx.fill()
    _line(ctx, 0.06 * s)
    ctx.set_source_rgb(*ACCENTS["blue"])
    for dx in (-0.25, 0, 0.25):
        ctx.move_to(x + dx * s, y + 0.32 * s)
        ctx.line_to(x + (dx - 0.06) * s, y + 0.5 * s)
    ctx.stroke()


def _clean(f):
    """Start every drawer with an empty path (show_text leaves a current point behind)."""
    def g(ctx, x, y, s, a):
        ctx.new_path()
        ctx.save()
        f(ctx, x, y, s, a)
        ctx.restore()
        ctx.new_path()
    g.__name__ = f.__name__
    return g


PROPS = {f.__name__: _clean(f) for f in (
    phone, brain, lightbulb, money, coin_stack, clock, hourglass, heart, broken_heart, chart_up,
    chart_down, trophy, book, dumbbell, target, scale, calendar, battery_low, battery_full, lock,
    gift, bell, coffee, crowd, speech_bubble, check, cross, arrow_right, flame, ladder,
    thought_cloud, rain_cloud)}
PROP_NAMES = list(PROPS)


# ------------------------------------------------------------------ emotes (small, above the head)
def _mark(ch, color):
    def f(ctx, x, y, s, a):
        _text(ctx, ch, x, y, s, color)
    return f


def sweat(ctx, x, y, s, a):
    ctx.move_to(x, y - 0.4 * s)
    ctx.curve_to(x + 0.3 * s, y, x + 0.25 * s, y + 0.35 * s, x, y + 0.35 * s)
    ctx.curve_to(x - 0.25 * s, y + 0.35 * s, x - 0.3 * s, y, x, y - 0.4 * s)
    ctx.set_source_rgb(0.45, 0.75, 1.0)
    ctx.fill()


def anger(ctx, x, y, s, a):
    _line(ctx, 0.12 * s)
    ctx.set_source_rgb(*ACCENTS["red"])
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        ctx.move_to(x + dx * 0.12 * s, y + dy * 0.12 * s)
        ctx.curve_to(x + dx * 0.15 * s, y + dy * 0.35 * s, x + dx * 0.15 * s, y + dy * 0.35 * s,
                     x + dx * 0.35 * s, y + dy * 0.15 * s)
    ctx.stroke()


def sparkle(ctx, x, y, s, a):
    ctx.set_source_rgb(*ACCENTS["yellow"])
    for dx, dy, r in ((0, 0, 0.4), (0.45, -0.3, 0.18)):
        cx, cy, rr = x + dx * s, y + dy * s, r * s
        ctx.move_to(cx, cy - rr)
        ctx.curve_to(cx, cy, cx, cy, cx + rr, cy)
        ctx.curve_to(cx, cy, cx, cy, cx, cy + rr)
        ctx.curve_to(cx, cy, cx, cy, cx - rr, cy)
        ctx.curve_to(cx, cy, cx, cy, cx, cy - rr)
        ctx.fill()


EMOTES = {k: _clean(v) for k, v in {
    "question": _mark("?", ACCENTS["blue"]),
    "exclaim": _mark("!", ACCENTS["red"]),
    "zzz": _mark("Zzz", ACCENTS["purple"]),
    "sweat": sweat, "anger": anger, "sparkle": sparkle,
    "heart": heart, "idea": lightbulb, "rain": rain_cloud,
}.items()}
EMOTE_NAMES = list(EMOTES)
