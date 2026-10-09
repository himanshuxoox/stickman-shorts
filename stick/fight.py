"""
Anime-style stickman fights, fully generated in code (~2 minutes each).

Each seed writes a different fight script from a library of beats: dash-in combos,
blocks + counters, teleport dodges, launcher juggles with ground slams, wall splats,
beam clashes, power-up comebacks, a K.O. — and sometimes an unexpected twist ending.
The look borrows anime tricks: impact frames (colour inversion), speed lines,
afterimages, screen shake, auras, shockwaves. Health bars + combo counters give it a
fighting-game feel, and "RED vs BLUE — who wins?" drives comments.

    python -m stick.fight --count 2            # -> out/<date>/NN_fight.mp4 + manifest
"""
import argparse, bisect, datetime as dt, json, math, os, random, subprocess, time
from zoneinfo import ZoneInfo

import cairo

from . import rig, fightaudio

W, H, FPS = 1080, 1920, 30
S = 0.62                                   # fighter scale (world px)
HIP_H = (rig.L_THIGH + rig.L_SHIN - 6) * S  # hip height above the feet
GROUND_Y = 1250                            # screen y of the ground when the camera is level
WALL = 860
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IST = ZoneInfo("Asia/Kolkata")

# ----------------------------------------------------------------------------- poses
P = rig.P
POSES = {
    "stance":   P(t=8, h=-4, la1=30, la2=125, ra1=55, ra2=105, ll1=-24, ll2=14, rl1=24, rl2=-8, y=14),
    "wind":     P(t=-4, h=-4, la1=30, la2=125, ra1=10, ra2=140, ll1=-26, ll2=14, rl1=22, rl2=-8, y=16),
    "jab":      P(t=14, h=-6, la1=30, la2=125, ra1=90, ra2=2, ll1=-30, ll2=10, rl1=28, rl2=-6, y=18),
    "cross":    P(t=22, h=-8, la1=92, la2=0, ra1=40, ra2=120, ll1=-34, ll2=16, rl1=30, rl2=-10, y=18),
    "hook":     P(t=18, h=-6, la1=30, la2=125, ra1=100, ra2=-70, ll1=-28, ll2=12, rl1=26, rl2=-8, y=16),
    "upper":    P(t=-6, h=-14, la1=30, la2=120, ra1=160, ra2=-10, ll1=-18, ll2=4, rl1=20, rl2=-4, y=-6),
    "kick":     P(t=-28, h=10, la1=-40, la2=70, ra1=20, ra2=110, ll1=-12, ll2=4, rl1=100, rl2=-4, y=0),
    "knee":     P(t=10, h=-6, la1=60, la2=60, ra1=70, ra2=50, ll1=-16, ll2=6, rl1=85, rl2=-125, y=-4),
    "slam":     P(t=26, h=8, la1=70, la2=10, ra1=75, ra2=8, ll1=-50, ll2=90, rl1=40, rl2=-80, y=0),
    "hammer":   P(t=-10, h=-10, la1=170, la2=5, ra1=175, ra2=-5, ll1=-30, ll2=60, rl1=30, rl2=-40, y=0),
    "block":    P(t=-6, h=8, la1=70, la2=100, ra1=78, ra2=96, ll1=-28, ll2=20, rl1=22, rl2=-6, y=24),
    "hurt":     P(t=-26, h=-24, la1=-70, la2=-40, ra1=-30, ra2=-30, ll1=-20, ll2=10, rl1=30, rl2=-30, y=10),
    "launched": P(t=-40, h=-20, la1=-140, la2=-30, ra1=-110, ra2=-40, ll1=-30, ll2=60, rl1=20, rl2=70, y=0),
    "down":     P(t=0, h=10, la1=-160, la2=-10, ra1=160, ra2=10, ll1=-6, ll2=0, rl1=6, rl2=0, y=0),
    "dash":     P(t=38, h=-10, la1=-120, la2=-10, ra1=-110, ra2=-10, ll1=-60, ll2=70, rl1=50, rl2=-40, y=10),
    "jump":     P(t=-6, h=-8, la1=40, la2=110, ra1=60, ra2=90, ll1=-40, ll2=100, rl1=30, rl2=-90, y=0),
    "airkick":  P(t=-20, h=0, la1=-50, la2=60, ra1=30, ra2=100, ll1=-30, ll2=110, rl1=95, rl2=0, y=0),
    "charge":   P(t=-8, h=-6, la1=-60, la2=-40, ra1=-50, ra2=-50, ll1=-36, ll2=24, rl1=34, rl2=-22, y=34),
    "fire":     P(t=14, h=-6, la1=88, la2=2, ra1=92, ra2=-2, ll1=-38, ll2=20, rl1=30, rl2=-12, y=26),
    "powerup":  P(t=0, h=-22, la1=-58, la2=-70, ra1=58, ra2=70, ll1=-30, ll2=20, rl1=30, rl2=-20, y=30),
    "victory":  P(t=0, h=-10, la1=-20, la2=-10, ra1=165, ra2=-10, ll1=-12, ll2=0, rl1=12, rl2=0, y=0),
    "shocked":  P(t=-10, h=-6, la1=-120, la2=-40, ra1=-100, ra2=-50, ll1=-20, ll2=6, rl1=20, rl2=-6, y=4),
    "walk1":    P(t=4, la1=20, la2=-20, ra1=-20, ra2=20, ll1=-20, ll2=10, rl1=20, rl2=0, y=0),
    "walk2":    P(t=4, la1=-20, la2=-20, ra1=20, ra2=20, ll1=20, ll2=10, rl1=-20, rl2=0, y=0),
}
STRIKES = {"jab": 5, "cross": 7, "hook": 7, "knee": 8, "kick": 9, "upper": 9}

THEMES = [
    dict(name="city", sky=((0.05, 0.03, 0.12), (0.22, 0.06, 0.25)), ground=(0.07, 0.05, 0.1)),
    dict(name="sunset", sky=((0.12, 0.04, 0.16), (0.75, 0.28, 0.12)), ground=(0.1, 0.05, 0.07)),
    dict(name="storm", sky=((0.02, 0.04, 0.08), (0.12, 0.22, 0.3)), ground=(0.04, 0.06, 0.08)),
    dict(name="void", sky=((0.0, 0.0, 0.0), (0.08, 0.02, 0.18)), ground=(0.03, 0.02, 0.06)),
]
RED = (1.0, 0.25, 0.32)
BLUE = (0.25, 0.62, 1.0)
GREEN = (0.35, 1.0, 0.45)
GOLD = (1.0, 0.85, 0.2)


def ease(k, kind):
    k = max(0.0, min(1.0, k))
    if kind == "snap":
        return 1 - (1 - k) ** 4
    if kind == "out":
        return 1 - (1 - k) ** 2
    if kind == "in":
        return k * k
    if kind == "smooth":
        return k * k * (3 - 2 * k)
    return k


# ----------------------------------------------------------------------------- fighter tracks
class Fighter:
    def __init__(self, name, color, x, face, scale=1.0):
        self.name, self.color, self.scale = name, color, scale
        self.keys = [dict(t=0.0, pose=POSES["stance"], x=x, air=0.0, rot=0.0, face=face, ease="lin")]
        self.times = [0.0]
        self.hp = [(0.0, 100.0)]
        self.raw = []          # (t, raw damage) — rescaled into a story-shaped HP curve later

    @property
    def last(self):
        return self.keys[-1]

    def to(self, t, pose=None, x=None, air=None, rot=None, face=None, ease_="out"):
        k = dict(self.last)
        t = max(t, k["t"] + 1e-3)
        k.update(t=t, ease=ease_)
        if pose is not None:
            k["pose"] = POSES[pose] if isinstance(pose, str) else pose
        for name, v in (("x", x), ("air", air), ("rot", rot), ("face", face)):
            if v is not None:
                k[name] = v
        self.keys.append(k)
        self.times.append(t)

    def hold(self, t):
        if t > self.last["t"]:
            self.to(t, ease_="lin")

    def norm_rot(self):
        """After a full spin, snap the rotation back to the equivalent small angle."""
        r = self.last["rot"]
        n = round(r / 360.0) * 360.0
        if n:
            self.to(self.last["t"] + 1e-3, rot=r - n, ease_="lin")

    def sample(self, t):
        i = bisect.bisect_right(self.times, t)
        if i <= 0:
            return self.keys[0]
        if i >= len(self.keys):
            return self.keys[-1]
        a, b = self.keys[i - 1], self.keys[i]
        k = ease((t - a["t"]) / (b["t"] - a["t"]), b["ease"])
        pose = rig.lerp_pose(a["pose"], b["pose"], k)
        if b["pose"] is POSES["stance"] and a["pose"] is POSES["stance"]:     # idle bounce
            pose["y"] += 5 * math.sin(t * 2 * math.pi * 1.8)
        return dict(pose=pose, x=a["x"] + (b["x"] - a["x"]) * k, air=a["air"] + (b["air"] - a["air"]) * k,
                    rot=a["rot"] + (b["rot"] - a["rot"]) * k, face=b["face"] if k > 0.5 else a["face"])

    def damage(self, t, d, floor=8.0):
        self.raw.append((t, d))

    def hp_at(self, t):
        v = 100.0
        for (t0, val), nxt in zip(self.hp, self.hp[1:] + [(1e9, None)]):
            if t >= t0:
                prev = v
                v = val
                if t < t0 + 0.3:
                    v = prev + (val - prev) * (t - t0) / 0.3
        return v


# ----------------------------------------------------------------------------- director
class Director:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.seed = seed
        self.t = 0.0
        self.fx = []        # visual effects
        self.au = []        # (t, sfx kind)
        self.music = []     # (t0, t1, intensity)
        names = self.rng.choice([("RED", "BLUE"), ("BLUE", "RED")])
        cols = {"RED": RED, "BLUE": BLUE}
        self.A = Fighter(names[0], cols[names[0]], -330, 1)
        self.B = Fighter(names[1], cols[names[1]], 330, -1)
        self.extra = []     # twist characters
        self.combo_n = 0
        self.marks = {}

    # ---- helpers
    def fighters(self):
        return [self.A, self.B] + self.extra

    def sync(self, t=None):
        t = self.t if t is None else t
        for f in (self.A, self.B):
            f.hold(t)
        self.t = max(self.t, t)

    def e(self, kind, t0, t1=None, **kw):
        if kind == "text":                    # never stack two captions on top of each other
            for old in self.fx:
                if old["kind"] == "text" and old["t0"] <= t0 < old["t1"]:
                    old["t1"] = t0
        if kind == "wallcrack":               # keep at most two cracks per wall
            same = [o for o in self.fx if o["kind"] == "wallcrack" and o["x"] == kw["x"] and o["t1"] > t0]
            for o in same[:-1]:
                o["t1"] = t0
        self.fx.append(dict(kind=kind, t0=t0, t1=t0 + 0.4 if t1 is None else t1, **kw))

    def recenter(self):
        """Both fighters dash back toward the middle so the fight doesn't stay glued to a wall."""
        t0 = self.t
        left, right = sorted((self.A, self.B), key=lambda f: f.last["x"])
        tl, tr = -self.rng.uniform(220, 300), self.rng.uniform(220, 300)
        if abs(left.last["x"] - tl) < 120 and abs(right.last["x"] - tr) < 120:
            return
        for f, tx, face in ((left, tl, 1), (right, tr, -1)):
            if abs(f.last["x"] - tx) > 60:
                f.to(t0 + 0.06, "dash", face=1 if tx > f.last["x"] else -1)
                f.to(t0 + 0.36, x=tx, ease_="out")
                self.e("afterimage", t0, t0 + 0.36, who=f)
            f.to(t0 + 0.45, "stance", face=face)
        self.sfx(t0, "whoosh")
        self.sync(t0 + 0.45)

    def sfx(self, t, kind):
        self.au.append((t, kind))

    def other(self, f):
        return self.B if f is self.A else self.A

    def body(self, f, part="sh"):
        k = f.last
        J = rig.joints(k["pose"] if k["face"] > 0 else rig.mirror(k["pose"]), k["x"], -k["air"], S)
        return J[part]

    def face_each_other(self, t):
        a, b = self.A, self.B
        da = 1 if b.last["x"] > a.last["x"] else -1
        a.to(t, face=da, ease_="lin")
        b.to(t, face=-da, ease_="lin")

    # ---- beats
    def approach(self, A, B, gap=235):
        t0 = self.t
        d = 1 if B.last["x"] > A.last["x"] else -1
        target = B.last["x"] - d * gap
        if abs(target - A.last["x"]) < 40:
            return
        A.to(t0 + 0.07, "dash", face=d)
        A.to(t0 + 0.3, x=target, ease_="out")
        A.to(t0 + 0.38, "stance")
        self.e("afterimage", t0, t0 + 0.32, who=A)
        self.e("speedlines", t0, t0 + 0.28)
        self.sfx(t0 + 0.02, "whoosh")
        self.sync(t0 + 0.38)

    def hit(self, A, B, move, dmg_mult=1.0, last=False, color=None):
        t0 = self.t
        d = A.last["face"]
        A.to(t0 + 0.07, "wind")
        A.to(t0 + 0.12, move, ease_="snap")
        ti = t0 + 0.12
        part = "head" if move in ("jab", "cross", "hook", "upper") else "sh"
        px, py = self.body(B, part)
        self.e("spark", ti, ti + 0.25, x=px, y=py, color=color or GOLD, size=60 + 20 * last)
        self.e("shake", ti, ti + 0.15, amp=10)
        self.sfx(ti, "punch")
        B.to(ti + 0.02, "hurt", x=B.last["x"] + d * 22, face=-d, ease_="snap")
        B.to(ti + 0.3, "stance", ease_="out")
        A.to(t0 + 0.32, "stance", x=A.last["x"] + d * 10)
        B.damage(ti, STRIKES.get(move, 6) * dmg_mult * self.rng.uniform(0.8, 1.2))
        self.combo_n += 1
        self.t = t0 + 0.24

    def launch_away(self, A, B, power=420, move="kick", dmg=12, color=None):
        """Big finisher: impact frame, B flies back spinning, maybe splats on the wall."""
        t0 = self.t
        d = A.last["face"]
        A.to(t0 + 0.12, "wind")
        A.to(t0 + 0.2, move, ease_="snap")
        ti = t0 + 0.2
        px, py = self.body(B, "sh")
        self.e("impact", ti, ti + 2.5 / FPS)
        self.e("spark", ti, ti + 0.4, x=px, y=py, color=color or GOLD, size=150)
        self.e("shockwave", ti, ti + 0.5, x=px, y=py, color=(1, 1, 1))
        self.e("shake", ti, ti + 0.35, amp=26)
        self.e("zoom", ti, ti + 0.45, amount=0.18)
        self.sfx(ti, "heavy")
        x0 = B.last["x"]
        x1 = x0 + d * power
        wall = abs(x1) > WALL
        if wall:
            x1 = math.copysign(WALL - 40, x1)
        B.to(ti + 0.03, "launched", air=40, face=-d, ease_="snap")
        B.to(ti + 0.42, x=x1, air=150, rot=-d * 300, ease_="out")
        B.damage(ti, dmg)
        A.to(ti + 0.45, "stance")
        if wall:
            wx = math.copysign(WALL, x1)
            self.e("wallcrack", ti + 0.42, 999, x=wx, y=-150 - HIP_H, seed=self.rng.random())
            self.e("dust", ti + 0.42, ti + 1.0, x=wx, y=-180)
            self.sfx(ti + 0.42, "crack")
            self.e("shake", ti + 0.42, ti + 0.6, amp=18)
            B.to(ti + 0.72, air=40, rot=-d * 360, ease_="in")
        B.to(ti + 0.88, "down", air=-HIP_H + 12, rot=-d * 270, ease_="in")
        self.e("dust", ti + 0.88, ti + 1.5, x=B.last["x"], y=-10)
        self.sfx(ti + 0.88, "punch")
        B.to(ti + 1.55, "down")
        B.to(ti + 1.95, "stance", air=0, rot=-d * 360, ease_="out")
        B.norm_rot()
        self.sync(ti + 1.95)
        self.recenter()
        self.face_each_other(self.t + 0.01)

    def combo(self, A, B, n=None, finisher=True, color=None, mult=1.0):
        self.approach(A, B)
        self.combo_n = 0
        n = n or self.rng.randint(2, 5)
        moves = self.rng.choices(["jab", "cross", "hook", "knee", "jab", "cross"], k=n)
        for m in moves:
            self.hit(A, B, m, mult, color=color)
        if finisher:
            self.combo_n += 1
            self.e("text", self.t + 0.2, self.t + 1.4, text=f"{self.combo_n} HIT COMBO!", color=A.color)
            self.launch_away(A, B, power=self.rng.choice([360, 460, 600]), dmg=10 * mult, color=color)
        else:
            self.sync(self.t + 0.3)

    def block_counter(self, A, B):
        """A attacks, B blocks, then B punishes."""
        self.approach(A, B)
        t0 = self.t
        d = A.last["face"]
        A.to(t0 + 0.08, "wind")
        A.to(t0 + 0.14, "cross", ease_="snap")
        B.to(t0 + 0.1, "block", face=-d, ease_="snap")
        ti = t0 + 0.14
        hx, hy = self.body(B, "sh")
        self.e("spark", ti, ti + 0.3, x=hx + d * -10, y=hy, color=(0.8, 0.95, 1), size=110)
        self.e("text", ti, ti + 0.8, text="BLOCKED!", color=(0.85, 0.95, 1))
        self.e("shake", ti, ti + 0.15, amp=8)
        self.sfx(ti, "block")
        A.to(ti + 0.25, "hurt", x=A.last["x"] - d * 70)
        B.to(ti + 0.25, "stance")
        A.to(ti + 0.4, "stance")
        self.sync(ti + 0.42)
        self.e("text", self.t, self.t + 0.8, text="COUNTER!", color=B.color)
        self.combo(B, A, n=self.rng.randint(2, 3))

    def dodge_counter(self, A, B):
        """A swings, B teleports behind A and kicks A into the wall."""
        self.approach(A, B)
        t0 = self.t
        d = A.last["face"]
        A.to(t0 + 0.08, "wind")
        A.to(t0 + 0.14, "hook", ease_="snap")
        oldx = B.last["x"]
        self.e("ghost", t0 + 0.1, t0 + 0.6, who=B, x=oldx)
        self.sfx(t0 + 0.1, "teleport")
        B.to(t0 + 0.11, x=A.last["x"] - d * 160, face=d, ease_="snap")
        self.e("spark", t0 + 0.11, t0 + 0.3, x=A.last["x"] - d * 160, y=-HIP_H - 60, color=B.color, size=70)
        A.to(t0 + 0.3, "shocked")
        A.to(t0 + 0.42, face=-d, ease_="lin")
        self.e("text", t0 + 0.12, t0 + 0.9, text="TOO SLOW!", color=B.color)
        self.sync(t0 + 0.42)
        self.combo_n = 1
        self.launch_away(B, A, power=self.rng.choice([500, 700]), dmg=13)

    def juggle(self, A, B):
        """Uppercut launch, air combo, ground slam with crater."""
        self.approach(A, B, gap=190)
        t0 = self.t
        d = A.last["face"]
        A.to(t0 + 0.08, "wind")
        A.to(t0 + 0.14, "upper", ease_="snap")
        ti = t0 + 0.14
        px, py = self.body(B, "head")
        self.e("spark", ti, ti + 0.3, x=px, y=py, color=GOLD, size=110)
        self.e("shake", ti, ti + 0.2, amp=14)
        self.sfx(ti, "heavy")
        B.damage(ti, 8)
        bx = B.last["x"] + d * 60
        B.to(ti + 0.03, "launched", ease_="snap")
        B.to(ti + 0.5, x=bx, air=420, rot=-d * 360, ease_="out")
        A.to(ti + 0.22, "jump", air=60)
        A.to(ti + 0.5, x=bx - d * 120, air=400, ease_="out")
        self.e("speedlines", ti + 0.2, ti + 0.5)
        self.sfx(ti + 0.2, "whoosh")
        t = ti + 0.5
        self.combo_n = 1
        for m in ("airkick", "jab", "cross"):
            A.to(t + 0.05, "wind")
            A.to(t + 0.1, m, ease_="snap")
            px, py = self.body(B, "sh")
            self.e("spark", t + 0.1, t + 0.3, x=px, y=py, color=GOLD, size=70)
            self.sfx(t + 0.1, "punch")
            B.to(t + 0.12, "hurt", air=B.last["air"] + 25, rot=B.last["rot"] - d * 20, ease_="snap")
            B.damage(t + 0.1, 5)
            self.combo_n += 1
            t += 0.22
        # slam
        A.to(t + 0.1, "hammer", air=470)
        A.to(t + 0.2, "slam", ease_="snap")
        ti = t + 0.2
        px, py = self.body(B, "sh")
        self.e("impact", ti, ti + 2.5 / FPS)
        self.e("spark", ti, ti + 0.3, x=px, y=py, color=GOLD, size=140)
        self.sfx(ti, "heavy")
        B.to(ti + 0.2, "down", air=-HIP_H + 12, rot=-d * 630, ease_="in")
        tl = ti + 0.2
        self.combo_n += 1
        self.e("crater", tl, 999, x=bx, seed=self.rng.random())
        self.e("dust", tl, tl + 0.9, x=bx, y=-10, big=True)
        self.e("shockwave", tl, tl + 0.6, x=bx, y=-10, color=(1, 0.9, 0.7))
        self.e("shake", tl, tl + 0.5, amp=30)
        self.e("zoom", tl, tl + 0.5, amount=0.2)
        self.e("text", tl, tl + 1.3, text=f"{self.combo_n} HIT COMBO!", color=A.color)
        self.sfx(tl, "boom")
        B.damage(tl, 12)
        A.to(tl + 0.35, "stance", air=0, x=bx - d * 260, ease_="in")
        B.to(tl + 1.1, "down")
        B.to(tl + 1.5, "stance", air=0, rot=-d * 720, ease_="out")
        B.norm_rot()
        self.sync(tl + 1.5)
        self.recenter()
        self.face_each_other(self.t + 0.01)

    def beam_clash(self, A, B, winner):
        t0 = self.t
        loser = self.other(winner)
        A.to(t0 + 0.5, "jump", x=-470, air=120, rot=-360, face=1, ease_="out")
        B.to(t0 + 0.5, "jump", x=470, air=120, rot=360, face=-1, ease_="out")
        A.to(t0 + 0.75, "charge", air=0, ease_="in")
        B.to(t0 + 0.75, "charge", air=0, ease_="in")
        A.norm_rot(); B.norm_rot()
        self.sfx(t0, "whoosh")
        tc = t0 + 0.75
        self.music.append((tc, tc + 1.5, 0))
        for f in (A, B):
            self.e("aura", tc, tc + 4.6, who=f, power=1.0)
        self.sfx(tc, "charge")
        self.e("shake", tc, tc + 1.5, amp=5)
        self.e("text", tc + 0.2, tc + 1.4, text="...", color=(1, 1, 1))
        tf = tc + 1.5
        A.to(tf, "charge"); B.to(tf, "charge")
        A.to(tf + 0.08, "fire", ease_="snap"); B.to(tf + 0.08, "fire", ease_="snap")
        dur = 2.6
        self.e("beam", tf + 0.08, tf + 0.08 + dur + 0.3, a=A, b=B, winner=winner,
               push=tf + 0.08 + dur - 0.6, seed=self.rng.random())
        self.e("shake", tf + 0.08, tf + dur, amp=9)
        self.e("speedlines", tf + 0.08, tf + 0.6)
        self.sfx(tf + 0.08, "beam")
        te = tf + 0.08 + dur
        self.e("impact", te, te + 3 / FPS)
        self.e("explosion", te, te + 1.2, x=loser.last["x"], y=-HIP_H - 40)
        self.e("shake", te, te + 0.7, amp=34)
        self.sfx(te, "boom")
        A.hold(te); B.hold(te)
        d = 1 if loser.last["x"] > 0 else -1
        loser.to(te + 0.05, "launched", air=80, ease_="snap")
        loser.to(te + 0.5, x=d * (WALL - 60), air=200, rot=-d * 300, ease_="out")
        loser.to(te + 0.85, "down", air=-HIP_H + 12, rot=-d * 270, ease_="in")
        loser.damage(te, 22)
        winner.to(te + 0.6, "stance")
        loser.to(te + 1.8, "down")
        loser.to(te + 2.2, "stance", air=0, rot=-d * 360)
        loser.norm_rot()
        self.sync(te + 2.2)
        self.recenter()
        self.face_each_other(self.t + 0.01)

    def powerup(self, f):
        t0 = self.t
        f.to(t0 + 0.3, "down", air=-HIP_H + 12, rot=-90 * f.last["face"])
        f.norm_rot()
        self.e("text", t0 + 0.3, t0 + 1.6, text="IT'S NOT OVER...", color=(1, 1, 1))
        self.music.append((t0, t0 + 1.8, 0))
        f.to(t0 + 1.4, "stance", air=0, rot=0, ease_="smooth")
        f.to(t0 + 1.8, "powerup")
        ti = t0 + 1.8
        self.e("aura", ti, 999, who=f, power=1.6, gold=True)
        self.e("impact", ti, ti + 3 / FPS)
        self.e("shockwave", ti, ti + 0.8, x=f.last["x"], y=-HIP_H, color=GOLD)
        self.e("shake", ti, ti + 1.0, amp=22)
        self.e("text", ti, ti + 1.5, text="POWER UP!", color=GOLD)
        self.e("rocks", ti, ti + 2.5, x=f.last["x"], seed=self.rng.random())
        self.sfx(t0 + 0.4, "rise")
        self.sfx(ti, "boom")
        self.marks["power"] = (t0, ti + 1.5)
        f.to(ti + 1.2, "powerup")
        f.to(ti + 1.5, "stance")
        self.sync(ti + 1.5)

    def knockout(self, A, B):
        """A finishes B."""
        self.approach(A, B)
        self.combo_n = 0
        for m in ("jab", "cross", "knee"):
            self.hit(A, B, m)
        t0 = self.t
        d = A.last["face"]
        A.to(t0 + 0.15, "wind")
        A.to(t0 + 0.26, "upper", ease_="snap")
        ti = t0 + 0.26
        px, py = self.body(B, "head")
        self.e("impact", ti, ti + 4 / FPS)
        self.e("spark", ti, ti + 0.5, x=px, y=py, color=(1, 1, 1), size=200)
        self.e("shockwave", ti, ti + 0.8, x=px, y=py, color=(1, 1, 1))
        self.e("shake", ti, ti + 0.6, amp=36)
        self.e("zoom", ti, ti + 1.6, amount=0.3)
        self.sfx(ti, "heavy")
        self.sfx(ti + 0.05, "ko")
        self.marks["ko"] = ti
        B.to(ti + 0.05, "launched", ease_="snap")
        B.to(ti + 0.9, x=B.last["x"] + d * 160, air=520, rot=-d * 540, ease_="out")
        B.to(ti + 1.5, "down", air=-HIP_H + 12, rot=-d * 630, ease_="in")
        self.e("dust", ti + 1.5, ti + 2.2, x=B.last["x"], y=-10, big=True)
        self.e("shake", ti + 1.5, ti + 1.8, amp=16)
        self.sfx(ti + 1.5, "heavy")
        self.e("ko", ti + 0.2, ti + 3.6)
        A.to(ti + 0.8, "stance")
        A.to(ti + 1.8, "victory", face=d)
        self.music.append((ti, ti + 2.4, 1))
        self.sync(ti + 3.6)
        return ti

    def twist_tiny(self, winner):
        """A tiny green stickman walks in and flicks the champion off the screen."""
        t0 = self.t
        d = winner.last["face"]
        side = -d                                   # comes from behind the winner
        tiny = Fighter("???", GREEN, winner.last["x"] + side * 900, -side, scale=0.38)
        tiny.keys[0]["t"] = t0
        tiny.times[0] = t0
        self.extra.append(tiny)
        self.music.append((t0, t0 + 4.0, 0))
        for i in range(10):
            tiny.to(t0 + 0.25 * (i + 1), "walk1" if i % 2 else "walk2",
                    x=winner.last["x"] + side * (900 - 82 * (i + 1)), ease_="lin")
        tw = t0 + 2.6
        tiny.to(tw, "stance")
        winner.to(tw, "victory")
        winner.to(tw + 0.3, "shocked", face=side)
        self.e("text", tw + 0.2, tw + 1.4, text="...WAIT WHAT?", color=GREEN)
        tiny.to(tw + 1.3, "wind")
        tiny.to(tw + 1.4, "jab", ease_="snap")
        ti = tw + 1.4
        self.e("impact", ti, ti + 3 / FPS)
        self.e("spark", ti, ti + 0.4, x=winner.last["x"], y=-HIP_H, color=GREEN, size=120)
        self.e("shake", ti, ti + 0.4, amp=30)
        self.sfx(ti, "heavy")
        self.marks["flick"] = ti
        winner.to(ti + 0.04, "launched", ease_="snap")
        winner.to(ti + 1.0, x=winner.last["x"] - side * 2200, air=1500, rot=side * 900, ease_="out")
        self.e("twinkle", ti + 0.95, ti + 1.6)
        self.sfx(ti + 0.95, "teleport")
        tiny.to(ti + 0.6, "stance")
        tiny.to(ti + 1.2, "victory")
        self.music.append((ti, ti + 3, 2))
        self.sync(ti + 3.0)
        tiny.hold(self.t)
        return tiny

    def finalize_hp(self):
        """Turn raw hit damage into HP curves that follow the story: the eventual loser leads early,
        the hero is nearly beaten, powers up, and wins. Within each act the hits keep their order
        and relative size; only the totals are scaled."""
        p0, p1 = self.marks["power"]
        ko = self.marks["ko"]
        bounds = [0.0, self.marks["act1"], self.marks["act2"], p0, p1, ko]
        targets = {id(self.hero): [100, 62, 36, 14, 56, 44], id(self.other_): [100, 93, 74, 68, 68, 14]}
        for f in (self.hero, self.other_):
            tg = targets[id(f)]
            hp = [(0.0, 100.0)]
            for i in range(5):
                a, b = bounds[i], bounds[i + 1]
                start, end = tg[i], tg[i + 1]
                if end > start:                                   # the power-up heal
                    hp.append((b - 0.3, float(end)))
                    continue
                ev = [(t, d) for t, d in f.raw if a <= t < b]
                tot = sum(d for _, d in ev)
                cur = float(start)
                for t, d in ev:
                    cur -= (start - end) * d / tot
                    hp.append((t, cur))
            if f is self.other_:
                hp.append((ko, 0.0))
            f.hp = hp
        if "flick" in self.marks:
            self.hero.hp.append((self.marks["flick"], 0.0))

    # ---- the whole fight
    def write(self, length=118.0):
        r = self.rng
        A, B = self.A, self.B
        # cold open: both dash in, fists collide
        A.to(0.05, "dash"); B.to(0.05, "dash")
        A.to(0.32, "cross", x=-62, ease_="out"); B.to(0.32, "cross", x=62, ease_="out")
        self.e("speedlines", 0.0, 0.32)
        self.e("impact", 0.32, 0.32 + 3 / FPS)
        self.e("shockwave", 0.32, 1.0, x=0, y=-HIP_H - 130, color=(1, 1, 1))
        self.e("spark", 0.32, 0.8, x=0, y=-HIP_H - 130, color=(1, 1, 1), size=180)
        self.e("shake", 0.32, 0.8, amp=30)
        self.sfx(0.0, "whoosh"); self.sfx(0.32, "boom")
        A.to(0.75, "stance", x=-260); B.to(0.75, "stance", x=260)
        self.e("vs", 0.0, 3.2)
        self.sync(1.0)
        hero, other = (A, B) if r.random() < 0.5 else (B, A)     # hero = eventual winner
        # act 1: the eventual LOSER dominates
        beats1 = [self.combo, self.juggle, self.dodge_counter, self.combo]
        while self.t < length * 0.33:
            r.choice(beats1)(other, hero)
            self.sync(self.t + r.uniform(0.15, 0.4))
            if r.random() < 0.3:
                self.block_counter(hero, other)
        self.marks["act1"] = self.t
        # act 2: back and forth, beam clash
        while self.t < length * 0.55:
            att = r.choice([hero, other])
            r.choice([self.combo, self.juggle, self.block_counter])(att, self.other(att))
            self.sync(self.t + r.uniform(0.15, 0.35))
        self.beam_clash(A, B, winner=other)
        self.marks["act2"] = self.t
        # act 3: hero is beaten down... and powers up
        while self.t < length * 0.72:
            r.choice([self.combo, self.juggle])(other, hero)
            self.sync(self.t + 0.2)
        self.powerup(hero)
        while self.t < length * 0.88:
            r.choice([self.combo, self.juggle, self.dodge_counter])(hero, other)
            self.sync(self.t + r.uniform(0.1, 0.25))
            if r.random() < 0.25:
                self.block_counter(other, hero)       # the loser still fights back
        self.knockout(hero, other)
        twist = r.random() < 0.3
        if twist:
            tiny = self.twist_tiny(hero)
            self.winner = tiny
        else:
            self.winner = hero
            self.sync(self.t + 1.0)
        self.loser = other
        self.twist = twist
        self.hero, self.other_ = hero, other
        self.finalize_hp()
        self.length = self.t + 0.5
        for f in self.fighters():
            f.hold(self.length)
        return self


# ----------------------------------------------------------------------------- camera
def camera_track(D, n):
    cams = []
    cx, cy, z = 0.0, -260.0, 1.0
    for i in range(n):
        t = i / FPS
        xs, top = [], 0.0
        for f in D.fighters():
            if f.keys[0]["t"] > t:
                continue
            k = f.sample(t)
            if abs(k["x"]) < 1400 and k["air"] < 900:
                xs.append(k["x"])
                top = max(top, min(k["air"], 600))
        xs = xs or [0.0]
        tx = (min(xs) + max(xs)) / 2
        span = max(xs) - min(xs)
        tz = max(0.8, min(1.75, 1300 / (span + 560)))
        ty = -HIP_H - 120 - top * 0.6
        for e in D.fx:
            if e["kind"] == "zoom" and e["t0"] <= t < e["t1"]:
                k = (t - e["t0"]) / (e["t1"] - e["t0"])
                tz *= 1 + e["amount"] * math.sin(math.pi * k)
        a = 0.18 if i else 1.0
        cx += (tx - cx) * a
        cy += (ty - cy) * a
        z += (tz - z) * a
        sx = sy = 0.0
        for e in D.fx:
            if e["kind"] == "shake" and e["t0"] <= t < e["t1"]:
                k = 1 - (t - e["t0"]) / (e["t1"] - e["t0"])
                sx += e["amp"] * k * math.sin(t * 91.0 + e["t0"])
                sy += e["amp"] * k * math.cos(t * 77.0 + e["t0"] * 3)
        cams.append((cx, cy, z, sx, sy))
    return cams


# ----------------------------------------------------------------------------- drawing
def _text(ctx, s, x, y, size, rgb, a=1.0, bold=True, outline=0):
    ctx.select_font_face("Inter", cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    e = ctx.text_extents(s)
    ctx.move_to(x - e.width / 2 - e.x_bearing, y)
    ctx.text_path(s)
    if outline:
        ctx.set_source_rgba(0, 0, 0, a)
        ctx.set_line_width(outline)
        ctx.stroke_preserve()
    ctx.set_source_rgba(*rgb, a)
    ctx.fill()


def draw_background(ctx, D, theme, cam):
    cx, cy, z, sx, sy = cam
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgb(0, *theme["sky"][0])
    g.add_color_stop_rgb(1, *theme["sky"][1])
    ctx.set_source(g)
    ctx.paint()
    rng = random.Random(D.seed)
    # parallax skyline / mountains (moves at 30 % of camera speed)
    par = 0.3
    base = GROUND_Y + (0 - cy) * z * 0.55
    if theme["name"] in ("city", "storm"):
        ctx.set_source_rgba(0, 0, 0, 0.55)
        x = -1600
        while x < 1600:
            w = rng.uniform(70, 160); hh = rng.uniform(160, 520)
            ctx.rectangle(540 + (x - cx * par) * 0.7, base - hh, w, hh + 400)
            x += w + rng.uniform(4, 30)
        ctx.fill()
        ctx.set_source_rgba(1.0, 0.85, 0.5, 0.25)
        rng2 = random.Random(D.seed + 1)
        for _ in range(160):
            wx = rng2.uniform(-1600, 1600); wy = rng2.uniform(80, 480)
            ctx.rectangle(540 + (wx - cx * par) * 0.7, base - wy, 6, 9)
        ctx.fill()
    else:
        ctx.set_source_rgba(0, 0, 0, 0.5)
        ctx.move_to(-200, base + 300)
        x = -1800
        while x < 1800:
            ctx.line_to(540 + (x - cx * par) * 0.7, base - rng.uniform(80, 420))
            x += rng.uniform(140, 300)
        ctx.line_to(1300, base + 300)
        ctx.close_path()
        ctx.fill()


def draw_fighter(ctx, f, k, alpha=1.0, color=None, glow=False):
    pose = k["pose"] if k["face"] > 0 else rig.mirror(k["pose"])
    feet = -k["air"]
    col = color or f.color
    s = S * f.scale
    J = rig.joints(pose, k["x"], feet, s)
    ctx.save()
    if k["rot"]:
        hx, hy = J["hip"]
        ctx.translate(hx, hy)
        ctx.rotate(math.radians(k["rot"]))
        ctx.translate(-hx, -hy)
    if alpha < 1:
        ctx.push_group()
    if glow:
        ctx.set_source_rgba(*col, 0.25)
        _sticks(ctx, J, 40 * s)
    ctx.set_source_rgb(*col)
    _sticks(ctx, J, 17 * s)
    nx, ny = J["head"]
    ctx.new_path()
    ctx.arc(nx, ny, rig.R_HEAD * s, 0, 2 * math.pi)
    ctx.set_source_rgb(*col)
    ctx.fill()
    # anime eye: a white slash looking forward
    fd = 1 if k["face"] > 0 else -1
    ctx.set_source_rgb(1, 1, 1)
    ctx.set_line_width(7 * s)
    ctx.move_to(nx + fd * 14 * s, ny - 8 * s)
    ctx.line_to(nx + fd * 38 * s, ny - 2 * s)
    ctx.stroke()
    if alpha < 1:
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(alpha)
    ctx.restore()
    return J


def _sticks(ctx, J, width):
    ctx.set_line_width(width)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    for chain in (("hip", "l_knee", "l_foot"), ("hip", "r_knee", "r_foot"),
                  ("hip", "sh"), ("sh", "l_elbow", "l_hand"), ("sh", "r_elbow", "r_hand"), ("sh", "head")):
        ctx.move_to(*J[chain[0]])
        for c in chain[1:]:
            ctx.line_to(*J[c])
        ctx.stroke()


def draw_aura(ctx, f, k, t, power, gold):
    col = GOLD if gold else f.color
    pose = k["pose"] if k["face"] > 0 else rig.mirror(k["pose"])
    J = rig.joints(pose, k["x"], -k["air"], S * f.scale)
    pts = [J[p] for p in ("head", "sh", "hip", "l_hand", "r_hand", "l_foot", "r_foot", "l_knee", "r_knee")]
    for layer, (rad, a) in enumerate(((95, 0.10), (65, 0.16), (40, 0.24))):
        for i, (x, y) in enumerate(pts):
            fl = 1 + 0.25 * math.sin(t * 23 + i * 1.7 + layer)
            rr = rad * power * fl * S * 1.6
            g = cairo.RadialGradient(x, y - 10, 0, x, y - 10, rr)
            g.add_color_stop_rgba(0, *col, a)
            g.add_color_stop_rgba(1, *col, 0)
            ctx.set_source(g)
            ctx.arc(x, y - 10, rr, 0, 2 * math.pi)
            ctx.fill()
    # rising sparks
    rng = random.Random(int(t * 30) + int(k["x"]))
    ctx.set_source_rgba(*col, 0.8)
    for _ in range(int(10 * power)):
        x = k["x"] + rng.uniform(-90, 90)
        y = -k["air"] - rng.uniform(0, 380)
        ctx.rectangle(x, y, 4, rng.uniform(14, 34))
    ctx.fill()


def draw_effect(ctx, e, t, D):
    k = (t - e["t0"]) / max(1e-6, e["t1"] - e["t0"])
    kind = e["kind"]
    if kind == "spark":
        x, y, size, col = e["x"], e["y"], e["size"], e["color"]
        rng = random.Random(int(e["t0"] * 1000))
        ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        r0 = size * 0.2 + size * 0.9 * ease(k, "out")
        for i in range(12):
            a = rng.uniform(0, 2 * math.pi)
            ln = size * rng.uniform(0.4, 1.0) * (1 - k)
            ctx.set_source_rgba(*col, 1 - k)
            ctx.set_line_width(max(1.5, 9 * (1 - k)))
            ctx.move_to(x + math.cos(a) * r0 * 0.5, y + math.sin(a) * r0 * 0.5)
            ctx.line_to(x + math.cos(a) * (r0 * 0.5 + ln), y + math.sin(a) * (r0 * 0.5 + ln))
            ctx.stroke()
        if k < 0.35:
            ctx.set_source_rgba(1, 1, 1, 1 - k / 0.35)
            ctx.arc(x, y, size * 0.45 * (1 - k), 0, 2 * math.pi)
            ctx.fill()
    elif kind == "shockwave":
        ctx.set_source_rgba(*e["color"], 0.8 * (1 - k))
        ctx.set_line_width(14 * (1 - k) + 2)
        ctx.new_path()
        ctx.save()
        ctx.translate(e["x"], e["y"])
        ctx.scale(1, 0.45 if e["y"] > -60 else 1)
        ctx.arc(0, 0, 40 + 520 * ease(k, "out"), 0, 2 * math.pi)
        ctx.restore()
        ctx.stroke()
    elif kind == "dust":
        rng = random.Random(int(e["t0"] * 977))
        n = 14 if e.get("big") else 8
        for _ in range(n):
            dx = rng.uniform(-1, 1)
            r = rng.uniform(20, 55) * (1.6 if e.get("big") else 1) * (0.5 + k)
            ctx.set_source_rgba(0.75, 0.7, 0.65, 0.45 * (1 - k))
            ctx.arc(e["x"] + dx * 220 * ease(k, "out"), e["y"] - r * 0.4 - 60 * k, r, 0, 2 * math.pi)
            ctx.fill()
    elif kind == "crater":
        rng = random.Random(e["seed"])
        ctx.set_source_rgba(0, 0, 0, 0.55)
        ctx.save(); ctx.translate(e["x"], 6); ctx.scale(1, 0.18)
        ctx.arc(0, 0, 200, 0, 2 * math.pi); ctx.restore(); ctx.fill()
        ctx.set_source_rgba(1, 1, 1, 0.35)
        ctx.set_line_width(3)
        for _ in range(7):
            a = rng.uniform(-0.4, 0.4)
            x = e["x"]
            ctx.move_to(x, 4)
            for j in range(4):
                x += math.copysign(rng.uniform(30, 70), rng.uniform(-1, 1))
                ctx.line_to(x, 4 + rng.uniform(-6, 18))
            ctx.stroke()
    elif kind == "wallcrack":
        rng = random.Random(e["seed"])
        ctx.set_source_rgba(1, 1, 1, 0.3)
        ctx.set_line_width(3)
        for _ in range(7):
            a = rng.uniform(0, 2 * math.pi)
            x, y = e["x"], e["y"]
            ctx.move_to(x, y)
            for j in range(4):
                x += math.cos(a) * rng.uniform(20, 50) * 0.4
                y += math.sin(a) * rng.uniform(25, 60)
                a += rng.uniform(-0.6, 0.6)
                ctx.line_to(x, y)
            ctx.stroke()
    elif kind == "explosion":
        x, y = e["x"], e["y"]
        r = 60 + 420 * ease(k, "out")
        g = cairo.RadialGradient(x, y, 0, x, y, r)
        g.add_color_stop_rgba(0, 1, 1, 0.9, 1 - k)
        g.add_color_stop_rgba(0.4, 1, 0.6, 0.2, 0.8 * (1 - k))
        g.add_color_stop_rgba(1, 0.6, 0.1, 0.1, 0)
        ctx.set_source(g)
        ctx.arc(x, y, r, 0, 2 * math.pi)
        ctx.fill()
    elif kind == "beam":
        a, b = e["a"], e["b"]
        ka, kb = a.sample(t), b.sample(t)
        ya = rig.joints(ka["pose"] if ka["face"] > 0 else rig.mirror(ka["pose"]), ka["x"], -ka["air"], S)["r_hand"]
        yb = rig.joints(kb["pose"] if kb["face"] > 0 else rig.mirror(kb["pose"]), kb["x"], -kb["air"], S)["r_hand"]
        rng = random.Random(e["seed"])
        ph = rng.uniform(0, 6)
        mid = (ya[0] + yb[0]) / 2 + 90 * math.sin((t - e["t0"]) * 3.3 + ph) * math.sin((t - e["t0"]) * 1.1)
        if t > e["push"]:
            loser = b if e["winner"] is a else a
            lx = loser.sample(t)["x"]
            mid = mid + (lx - mid) * ease((t - e["push"]) / 0.6, "in")
        grow = min(1.0, (t - e["t0"]) / 0.15)
        for (hx, hy), f, end in ((ya, a, mid), (yb, b, mid)):
            col = f.color
            x0, x1 = hx, hx + (end - hx) * grow
            yy = (ya[1] + yb[1]) / 2
            for wdt, al, c in ((90, 0.18, col), (52, 0.45, col), (20, 1.0, (1, 1, 1))):
                wob = wdt * (1 + 0.15 * math.sin(t * 40 + wdt))
                ctx.set_source_rgba(*c, al)
                ctx.set_line_width(wob)
                ctx.set_line_cap(cairo.LINE_CAP_ROUND)
                ctx.move_to(x0, hy)
                ctx.line_to(x1, yy)
                ctx.stroke()
        if grow >= 1:
            yy = (ya[1] + yb[1]) / 2
            rr = 110 + 25 * math.sin(t * 30)
            g = cairo.RadialGradient(mid, yy, 0, mid, yy, rr)
            g.add_color_stop_rgba(0, 1, 1, 1, 1)
            g.add_color_stop_rgba(0.5, 1, 0.9, 0.6, 0.7)
            g.add_color_stop_rgba(1, 1, 0.5, 0.8, 0)
            ctx.set_source(g)
            ctx.arc(mid, yy, rr, 0, 2 * math.pi)
            ctx.fill()
    elif kind == "rocks":
        rng = random.Random(e["seed"])
        for _ in range(16):
            x = e["x"] + rng.uniform(-260, 260)
            y = -rng.uniform(0, 60) - 260 * ease(k, "out") * rng.uniform(0.5, 1.2)
            s = rng.uniform(8, 22)
            ctx.set_source_rgba(0.55, 0.5, 0.45, 1 - k * 0.7)
            ctx.rectangle(x - s / 2, y - s / 2, s, s * 0.8)
            ctx.fill()


def draw_ghosts(ctx, D, t):
    for e in D.fx:
        if e["kind"] == "afterimage" and e["t0"] <= t < e["t1"] + 0.15:
            f = e["who"]
            for j in range(1, 5):
                tt = t - 0.035 * j
                if tt < e["t0"]:
                    break
                draw_fighter(ctx, f, f.sample(tt), alpha=0.35 - 0.07 * j)
        if e["kind"] == "ghost" and e["t0"] <= t < e["t1"]:
            k = (t - e["t0"]) / (e["t1"] - e["t0"])
            f = e["who"]
            ks = dict(f.sample(e["t0"] - 0.01))
            ks["x"] = e["x"]
            draw_fighter(ctx, f, ks, alpha=0.5 * (1 - k), color=(1, 1, 1))


def draw_ui(ctx, D, t):
    # health bars
    for f, side in ((D.A, -1), (D.B, 1)):
        hp = max(0.0, f.hp_at(t)) / 100
        x0 = 60 if side < 0 else 560
        ctx.set_source_rgba(0, 0, 0, 0.55)
        ctx.rectangle(x0 - 4, 156, 468, 44)
        ctx.fill()
        ctx.set_source_rgb(*f.color)
        wv = 460 * hp
        ctx.rectangle(x0 + (460 - wv if side < 0 else 0), 160, wv, 36)
        ctx.fill()
        ctx.set_source_rgba(1, 1, 1, 0.9)
        ctx.set_line_width(3)
        ctx.rectangle(x0 - 4, 156, 468, 44)
        ctx.stroke()
        _text(ctx, f.name, x0 + 60 if side < 0 else x0 + 400, 240, 40, f.color, 1, outline=0)
    _text(ctx, "VS", 540, 194, 44, (1, 1, 1), 1)
    for e in D.fx:
        if not (e["t0"] <= t < e["t1"]):
            continue
        k = (t - e["t0"]) / (e["t1"] - e["t0"])
        if e["kind"] == "text":
            s = 1.0 + 0.4 * max(0.0, 1 - k / 0.12)
            a = 1.0 if k < 0.75 else (1 - k) / 0.25
            ctx.save(); ctx.translate(540, 560); ctx.scale(s, s)
            _text(ctx, e["text"], 0, 0, 74, e["color"], a, outline=8)
            ctx.restore()
        elif e["kind"] == "vs":
            a = 1.0 if k < 0.8 else (1 - k) / 0.2
            _text(ctx, f"{D.A.name} vs {D.B.name}", 540, 360, 96, (1, 1, 1), a, outline=10)
            _text(ctx, "WHO WINS?", 540, 450, 70, GOLD, a, outline=8)
        elif e["kind"] == "ko":
            s = 1.0 + 1.5 * max(0.0, 1 - k / 0.08)
            ctx.save(); ctx.translate(540, 620); ctx.scale(s, s)
            _text(ctx, "K.O.!", 0, 0, 220, (1, 0.2, 0.2), min(1.0, (1 - k) * 4), outline=14)
            ctx.restore()
        elif e["kind"] == "twinkle":
            x, y = 870, 330
            r = 40 * math.sin(math.pi * k)
            ctx.set_source_rgba(1, 1, 1, 1)
            for a in range(4):
                ang = a * math.pi / 2
                ctx.move_to(x, y)
                ctx.line_to(x + math.cos(ang) * r, y + math.sin(ang) * r)
            ctx.set_line_width(6)
            ctx.stroke()


def draw_speedlines(ctx, t, e):
    rng = random.Random(int(t * FPS))
    k = (t - e["t0"]) / (e["t1"] - e["t0"])
    ctx.set_source_rgba(1, 1, 1, 0.35 * (1 - k * 0.5))
    for _ in range(46):
        a = rng.uniform(0, 2 * math.pi)
        r0 = rng.uniform(430, 600)
        ctx.set_line_width(rng.uniform(2, 7))
        ctx.move_to(540 + math.cos(a) * r0, 960 + math.sin(a) * r0)
        ctx.line_to(540 + math.cos(a) * 1400, 960 + math.sin(a) * 1400)
        ctx.stroke()


def draw_frame(ctx, D, theme, cams, i):
    t = i / FPS
    cam = cams[min(i, len(cams) - 1)]
    draw_background(ctx, D, theme, cam)
    ctx.save()
    cx, cy, z, sx, sy = cam
    ctx.translate(540 + sx, 930 + sy)
    ctx.scale(z, z)
    ctx.translate(-cx, -cy)
    # ground
    ctx.set_source_rgb(*theme["ground"])
    ctx.rectangle(cx - 3000, 0, 6000, 3000)
    ctx.fill()
    ctx.set_source_rgba(1, 1, 1, 0.5)
    ctx.set_line_width(3)
    ctx.move_to(cx - 3000, 0); ctx.line_to(cx + 3000, 0)
    ctx.stroke()
    ctx.set_source_rgba(1, 1, 1, 0.08)            # arena walls
    ctx.rectangle(-WALL - 40, -900, 40, 900)
    ctx.rectangle(WALL, -900, 40, 900)
    ctx.fill()
    active = [e for e in D.fx if e["t0"] <= t < e["t1"]]
    for e in active:
        if e["kind"] in ("crater", "wallcrack", "dust", "rocks"):
            draw_effect(ctx, e, t, D)
    for e in active:
        if e["kind"] == "aura":
            f = e["who"]
            draw_aura(ctx, f, f.sample(t), t, e["power"] * min(1.0, (t - e["t0"]) / 0.4 + 0.2), e.get("gold"))
    draw_ghosts(ctx, D, t)
    for e in active:
        if e["kind"] == "beam":
            draw_effect(ctx, e, t, D)
    for f in D.fighters():
        if f.keys[0]["t"] <= t:
            gold = any(e["kind"] == "aura" and e["who"] is f and e.get("gold") for e in active)
            col = tuple(min(1.0, c * 0.6 + 0.45) for c in f.color) if gold else None   # brighter, same colour
            draw_fighter(ctx, f, f.sample(t), color=col, glow=gold)
    for e in active:
        if e["kind"] in ("spark", "shockwave", "explosion"):
            draw_effect(ctx, e, t, D)
    ctx.restore()
    for e in active:
        if e["kind"] == "speedlines":
            draw_speedlines(ctx, t, e)
    draw_ui(ctx, D, t)
    _text(ctx, "Comment RED or BLUE!", 540, 1575, 42, (1, 1, 1), 0.85, outline=0)
    if any(e["kind"] == "impact" for e in active):          # anime impact frame
        ctx.set_operator(cairo.OPERATOR_DIFFERENCE)
        ctx.set_source_rgb(1, 1, 1)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)


# ----------------------------------------------------------------------------- render one
def render(seed, out_base, length=118.0):
    D = Director(seed).write(length)
    theme = random.Random(seed * 7).choice(THEMES)
    n = int(D.length * FPS)
    cams = camera_track(D, n)
    music_sections = D.music + [(0, 1.0, 3), (D.length - 3, D.length + 2, 1)]
    wav = out_base + ".wav"
    fightaudio.mix(D.length + 0.6, D.au, sorted(music_sections), wav, seed)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    tmp = out_base + ".v.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                           "-crf", "20", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    first = None
    for i in range(n):
        draw_frame(ctx, D, theme, cams, i)
        surf.flush()
        if i == 0:
            first = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
            c2 = cairo.Context(first); c2.set_source_surface(surf); c2.paint()
        ff.stdin.write(bytes(surf.get_data()))
    # loop: cross-fade back to the first frame
    last = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c3 = cairo.Context(last); c3.set_source_surface(surf); c3.paint()
    nl = int(0.5 * FPS)
    for j in range(1, nl + 1):
        ctx.set_source_surface(last); ctx.paint()
        ctx.set_source_surface(first); ctx.paint_with_alpha(j / nl)
        surf.flush()
        ff.stdin.write(bytes(surf.get_data()))
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-i", wav, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "160k", "-shortest", "-movflags", "+faststart", out_base + ".mp4"], check=True)
    os.remove(tmp); os.remove(wav)
    # cover: the middle of the beam clash if there is one
    beam = next((e for e in D.fx if e["kind"] == "beam"), None)
    ci = int(((beam["t0"] + beam["push"]) / 2 if beam else D.length * 0.4) * FPS)
    draw_frame(ctx, D, theme, cams, min(ci, n - 1))
    surf.write_to_png(out_base + "_cover.png")
    return D, round(n / FPS + 0.5, 2)


# ----------------------------------------------------------------------------- metadata + batch
TITLES = [
    "{a} vs {b} — who wins? 🔴🔵",
    "Stickman fight: {a} vs {b} 🔥 Who did you pick?",
    "He wasn't supposed to get back up… 😳",
    "Wait for the beam clash 💥 {a} vs {b}",
    "The ending is crazy 😱 Stickman battle",
    "{a} vs {b}: the comeback nobody expected 🔥",
]
TWIST_TITLES = ["Nobody expected the ending 😳 Stickman fight", "Wait for the ending… 😂 {a} vs {b}"]


def make_meta(D, seed):
    rng = random.Random(seed * 13)
    pool = TWIST_TITLES if D.twist else TITLES
    title = rng.choice(pool).format(a=D.A.name.title(), b=D.B.name.title())
    desc = "\n".join([
        f"{D.A.name.title()} vs {D.B.name.title()} — a full stickman battle: combos, beam clash, power-up and K.O.",
        "Who did you pick? Comment RED or BLUE 👇",
        "",
        "New stickman fights every day — subscribe! 🔔",
        "Animated entirely with code. Music and sound effects are original and synthesized.",
        "",
        "#shorts #stickman #stickfight #animation #anime #fight",
    ])
    tags = ["stickman", "stick fight", "stickman fight", "animation", "anime fight", "red vs blue",
            "fight animation", "shorts", "stick figure", "battle", "beam clash", "power up"]
    return dict(title=f"{title} #shorts"[:100], description=desc, tags=tags, categoryId="1",
                containsSyntheticMedia=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=2)
    ap.add_argument("--date", default=dt.datetime.now(IST).strftime("%Y-%m-%d"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--length", type=float, default=float(os.environ.get("FIGHT_LENGTH", "118")))
    a = ap.parse_args()
    state_p = os.path.join(ROOT, "state", "history.json")
    st = json.load(open(state_p)) if os.path.exists(state_p) else {"videos": []}
    seed0 = st.get("fight_seed", 5000)
    out_dir = os.path.join(a.out, a.date)
    os.makedirs(out_dir, exist_ok=True)
    items = []
    for i in range(a.count):
        seed = seed0 + i
        t0 = time.time()
        base = os.path.join(out_dir, f"{i + 1:02d}_fight_{seed}")
        D, dur = render(seed, base, a.length)
        item = dict(file=os.path.basename(base + ".mp4"), cover=os.path.basename(base + "_cover.png"),
                    duration=dur, seed=seed, winner=D.winner.name, twist=D.twist, **make_meta(D, seed))
        with open(base + ".json", "w") as f:
            json.dump(item, f, indent=1, ensure_ascii=False)
        items.append(item)
        print(f"[{i + 1}] fight seed={seed} {dur}s winner={D.winner.name} twist={D.twist} "
              f"({time.time() - t0:.0f}s)  {item['title']}", flush=True)
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(dict(date=a.date, videos=items), f, indent=1, ensure_ascii=False)
    with open(os.path.join(out_dir, "UPLOAD_SHEET.txt"), "w") as f:
        for v in items:
            f.write("\n".join(["=" * 60, v["file"], "=" * 60, "TITLE:", v["title"], "", "DESCRIPTION:",
                               v["description"], "", "TAGS:", ", ".join(v["tags"]), "",
                               "Made for kids: NO  |  Category: Film & Animation", "", ""]))
    st["fight_seed"] = seed0 + a.count
    st["videos"] = st.get("videos", []) + [dict(date=a.date, topic="fight", title=v["title"]) for v in items]
    os.makedirs(os.path.dirname(state_p), exist_ok=True)
    json.dump(st, open(state_p, "w"), indent=1, ensure_ascii=False)
    print(f"done: {len(items)} fights in {out_dir}")


if __name__ == "__main__":
    main()
