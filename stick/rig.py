"""
Stick-figure rig: forward kinematics, a pose library and smooth transitions.

Angle convention (degrees, screen space, y grows down):
  0 = limb points straight down, 90 = right, -90 = left, 180 = up.
Arms: a1 = upper-arm absolute angle, a2 = forearm angle RELATIVE to the upper arm.
Legs: same with thigh / shin. Torso "t" leans the body (0 = upright), "h" tilts the head.
"""
import math

import cairo

L_TORSO, L_NECK, R_HEAD = 230, 18, 54
L_UPPER, L_FORE, L_THIGH, L_SHIN = 120, 112, 145, 140
KEYS = ["t", "h", "la1", "la2", "ra1", "ra2", "ll1", "ll2", "rl1", "rl2", "y"]

BASE = dict(t=0, h=0, la1=-10, la2=-4, ra1=10, ra2=4, ll1=-7, ll2=0, rl1=7, rl2=0, y=0)


def P(**kw):
    p = dict(BASE)
    p.update(kw)
    return p


# static poses (+ optional gentle oscillations: key -> (amplitude_deg, hz))
POSES = {
    "stand":        (P(), {"h": (2, 0.4)}),
    "explain":      (P(la1=-40, la2=-75, ra1=40, ra2=75), {"ra2": (12, 1.4), "la2": (-12, 1.4)}),
    "point_right":  (P(ra1=95, ra2=-4, h=6), {"ra1": (3, 1.0)}),
    "point_left":   (P(la1=-95, la2=4, h=-6), {"la1": (-3, 1.0)}),
    "point_up":     (P(ra1=148, ra2=8, h=-8), {"ra1": (4, 1.2)}),
    "think":        (P(ra1=25, ra2=172, la1=-30, la2=88, h=9), {"h": (3, 0.5)}),
    "shrug":        (P(la1=-55, la2=-105, ra1=55, ra2=105, h=10), {"y": (-6, 1.2)}),
    "celebrate":    (P(la1=-138, la2=-12, ra1=138, ra2=12, ll1=-16, rl1=16), {"y": (-28, 2.2), "ra2": (15, 2.2)}),
    "sad":          (P(la1=-3, la2=0, ra1=3, ra2=0, h=24, t=4, y=12), {"h": (2, 0.3)}),
    "shocked":      (P(la1=-125, la2=-35, ra1=125, ra2=35, ll1=-18, rl1=18, y=-8), {"la1": (-6, 3), "ra1": (6, 3)}),
    "stressed":     (P(la1=-115, la2=-142, ra1=115, ra2=142, h=0), {"t": (3, 1.8)}),
    "facepalm":     (P(ra1=115, ra2=142, la1=-12, la2=-4, h=14), {"h": (2, 0.6)}),
    "wave":         (P(ra1=140, ra2=25), {"ra2": (28, 2.6)}),
    "confident":    (P(la1=-55, la2=85, ra1=55, ra2=-85, ll1=-12, rl1=12), {"h": (3, 0.4)}),
    "arms_crossed": (P(la1=-16, la2=112, ra1=16, ra2=-112), {"h": (2, 0.4)}),
    "phone":        (P(ra1=45, ra2=165, la1=-10, la2=-4, h=-10), {"h": (2, 0.5)}),
    "tired":        (P(la1=-2, la2=0, ra1=2, ra2=0, t=8, h=22, y=16), {"t": (2, 0.3)}),
    "walk":         (P(), {}),   # procedural
    "run":          (P(), {}),   # procedural
}
POSE_NAMES = list(POSES)


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp_pose(a, b, k):
    return {key: a[key] + (b[key] - a[key]) * k for key in KEYS}


def pose_at(name, t):
    """Pose for `name` at local time t (seconds since this pose began)."""
    if name == "walk":
        s = math.sin(t * 2 * math.pi * 1.6)
        c = abs(math.cos(t * 2 * math.pi * 1.6))
        return P(ll1=-24 * s, ll2=12 * max(0, s), rl1=24 * s, rl2=12 * max(0, -s),
                 la1=20 * s, la2=-12, ra1=-20 * s, ra2=12, y=-8 * c, h=2)
    if name == "run":
        s = math.sin(t * 2 * math.pi * 2.6)
        c = abs(math.cos(t * 2 * math.pi * 2.6))
        return P(t=10, ll1=-42 * s, ll2=40 * max(0, s), rl1=42 * s, rl2=40 * max(0, -s),
                 la1=38 * s, la2=-75, ra1=-38 * s, ra2=75, y=-22 * c, h=4)
    base, osc = POSES.get(name, POSES["stand"])
    p = dict(base)
    for key, (amp, hz) in osc.items():
        p[key] += amp * math.sin(t * 2 * math.pi * hz)
    return p


def mirror(p):
    """Mirror a pose left<->right (used for the second character facing the main one)."""
    return dict(t=-p["t"], h=-p["h"], la1=-p["ra1"], la2=-p["ra2"], ra1=-p["la1"], ra2=-p["la2"],
                ll1=-p["rl1"], ll2=-p["rl2"], rl1=-p["ll1"], rl2=-p["ll2"], y=p["y"])


def _v(a, length, up=False):
    r = math.radians(a)
    return (length * math.sin(r), (-1 if up else 1) * length * math.cos(r))


def joints(p, x, ground, s=1.0):
    """Returns dict of joint positions for pose p with feet near `ground`."""
    hip = (x, ground - (L_THIGH + L_SHIN - 6) * s + p["y"] * s)
    dx, dy = _v(p["t"], L_TORSO * s, up=True)
    sh = (hip[0] + dx, hip[1] + dy)
    hx, hy = _v(p["t"] + p["h"], (L_NECK + R_HEAD) * s, up=True)
    head = (sh[0] + hx, sh[1] + hy)
    J = dict(hip=hip, sh=sh, head=head)
    for side in ("l", "r"):
        a1, a2 = p[f"{side}a1"], p[f"{side}a2"]
        ex, ey = _v(a1, L_UPPER * s)
        el = (sh[0] + ex, sh[1] + ey)
        fx, fy = _v(a1 + a2, L_FORE * s)
        J[f"{side}_elbow"], J[f"{side}_hand"] = el, (el[0] + fx, el[1] + fy)
        b1, b2 = p[f"{side}l1"], p[f"{side}l2"]
        kx, ky = _v(b1, L_THIGH * s)
        kn = (hip[0] + kx, hip[1] + ky)
        fx2, fy2 = _v(b1 + b2, L_SHIN * s)
        J[f"{side}_knee"], J[f"{side}_foot"] = kn, (kn[0] + fx2, kn[1] + fy2)
    return J


def draw(ctx, p, x, ground, s=1.0, color=(0.07, 0.07, 0.09), width=16, shadow=True):
    J = joints(p, x, ground, s)
    if shadow:
        ctx.save()
        ctx.translate(x, ground + 8 * s)
        ctx.scale(1, 0.18)
        ctx.arc(0, 0, 120 * s, 0, 2 * math.pi)
        ctx.restore()
        ctx.set_source_rgba(0, 0, 0, 0.07)
        ctx.fill()
    ctx.set_source_rgb(*color)
    ctx.set_line_width(width * s)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    for chain in (("hip", "l_knee", "l_foot"), ("hip", "r_knee", "r_foot"),
                  ("hip", "sh"), ("sh", "l_elbow", "l_hand"), ("sh", "r_elbow", "r_hand")):
        ctx.move_to(*J[chain[0]])
        for k in chain[1:]:
            ctx.line_to(*J[k])
        ctx.stroke()
    # neck + head (white face, faceless classic style)
    nx, ny = J["head"]
    ctx.move_to(*J["sh"])
    ctx.line_to(nx + (J["sh"][0] - nx) * (R_HEAD / (L_NECK + R_HEAD)),
                ny + (J["sh"][1] - ny) * (R_HEAD / (L_NECK + R_HEAD)))
    ctx.stroke()
    ctx.arc(nx, ny, R_HEAD * s, 0, 2 * math.pi)
    ctx.set_source_rgb(1, 1, 1)
    ctx.fill_preserve()
    ctx.set_source_rgb(*color)
    ctx.stroke()
    return J
