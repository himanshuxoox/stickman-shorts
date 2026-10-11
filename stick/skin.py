"""
Skinned fighters: the anime fight engine (stick/fight.py) drives a skeleton, and the AI-made
character art (assets/fighters/<name>) is drawn on top of it as cut-out sprites — the same
way 2D games animate characters (Spine-style cut-out animation).

    python -m stick.skin --seed 5000 --a blaze --b frost --arena pagoda --out /tmp/x

Assets come from tools/extract_fighter.py (parts + rig.json) and assets/arenas/*.jpg.
"""
import argparse, json, math, os, random, subprocess

import cairo
import numpy as np
from PIL import Image

from . import fight as F
from . import rig, fightaudio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FDIR = os.path.join(ROOT, "assets", "fighters")
ADIR = os.path.join(ROOT, "assets", "arenas")
W, H, FPS, S = F.W, F.H, F.FPS, F.S

FIGHTERS = {   # display name, UI colour
    "blaze": ("BLAZE", (1.0, 0.42, 0.12)),
    "frost": ("FROST", (0.45, 0.82, 1.0)),
    "shadow": ("SHADOW", (0.72, 0.4, 1.0)),
    "toxic": ("TOXIC", (0.45, 1.0, 0.3)),
    "void": ("VOID", (0.65, 0.3, 1.0)),
    "sun": ("SUN", (1.0, 0.82, 0.25)),
    "ninja": ("NINJA", (1.0, 0.25, 0.3)),
    "titan": ("TITAN", (0.85, 0.55, 0.35)),
    "spark": ("SPARK", (1.0, 0.92, 0.2)),
    "phantom": ("PHANTOM", (0.3, 1.0, 0.95)),
}
STRIKE_POSES = {"jab", "cross", "hook", "upper", "kick", "knee", "slam", "hammer", "airkick", "dash", "fire"}
ANGRY_POSES = {"wind", "charge", "powerup", "block"}
HURT_POSES = {"hurt", "launched", "shocked", "down"}


_KEEP = []


def _surface(path, dark=1.0):
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(np.float32)
    al = a[..., 3:4] / 255.0
    rgb = a[..., :3] * dark
    bgra = np.concatenate([rgb[..., 2:3] * al, rgb[..., 1:2] * al, rgb[..., 0:1] * al, a[..., 3:4]], 2)
    h, w = bgra.shape[:2]
    stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32, w)
    buf = np.zeros((h, stride // 4, 4), np.uint8)
    buf[:, :w] = np.clip(bgra + 0.5, 0, 255).astype(np.uint8)
    surf = cairo.ImageSurface.create_for_data(memoryview(buf), cairo.FORMAT_ARGB32, w, h, stride)
    _KEEP.append(buf)                 # cairo does not own the pixel buffer
    return surf


class Skin:
    def __init__(self, key):
        d = os.path.join(FDIR, key)
        self.key = key
        self.name, self.color = FIGHTERS.get(key, (key.upper(), (1, 1, 1)))
        self.rig = json.load(open(os.path.join(d, "rig.json")))
        self.img, self.dark = {}, {}
        for part in self.rig:
            p = os.path.join(d, part + ".png")
            if os.path.exists(p):
                self.img[part] = _surface(p)
                if part[-1] == "1" or part == "scarf":
                    self.dark[part] = _surface(p, 0.72)
        # global sprite scale: match the upper arm + forearm sprites to the rig bone lengths
        def ln(part):
            a, b = self.rig[part]["p0"], self.rig[part]["p1"]
            return math.hypot(b[0] - a[0], b[1] - a[1])
        def tln():
            t = self.rig["torso"]
            return math.hypot(t["hip"][0] - t["sh"][0], t["hip"][1] - t["sh"][1])
        foot_px = (self.rig["foot0"]["p1"][1] - self.rig["foot0"]["p0"][1]) * 0.85
        # one uniform scale for the whole character (the art keeps its own proportions);
        # every fighter is normalised to the same total height as the classic stickman (~425 px)
        tall = ln("th0") + ln("sn0") + foot_px + tln() + 2.0 * self.rig["head"]["r"]
        self.gs = 425.0 / tall
        self.foot_h = foot_px * self.gs
        self.arm_k = 0.8                 # arms a bit slimmer so big gauntlets don't hide the face
        self.L = dict(torso=tln() * self.gs, ua=ln("ua0") * self.gs * 0.85, fa=ln("fa0") * self.gs * 0.85,
                      th=ln("th0") * self.gs, sn=ln("sn0") * self.gs,
                      head=self.rig["head"]["r"] * self.gs * 1.05)
        w = self.rig.get("weapon")
        self.weapon = w
        if w:
            self.wscale = 470.0 / max(1.0, (w["tip"][0] - w["grip"][0]) / 0.64)   # whole spear ~ 470 px
        self.effect = self.img.get("effect")

    def joints(self, p, x, ground):
        """Same angle convention as rig.joints, but with this character's own bone lengths."""
        L = self.L
        v = rig._v
        hip = (x, ground - (L["th"] + L["sn"] + self.foot_h - 4) + p["y"] * S)
        dx, dy = v(p["t"], L["torso"], up=True)
        sh = (hip[0] + dx, hip[1] + dy)
        hx, hy = v(p["t"] + p["h"], L["head"], up=True)
        J = dict(hip=hip, sh=sh, head=(sh[0] + hx, sh[1] + hy))
        for side in ("l", "r"):
            ex, ey = v(p[f"{side}a1"], L["ua"])
            el = (sh[0] + ex, sh[1] + ey)
            fx, fy = v(p[f"{side}a1"] + p[f"{side}a2"], L["fa"])
            J[f"{side}_elbow"], J[f"{side}_hand"] = el, (el[0] + fx, el[1] + fy)
            kx, ky = v(p[f"{side}l1"], L["th"])
            kn = (hip[0] + kx, hip[1] + ky)
            fx2, fy2 = v(p[f"{side}l1"] + p[f"{side}l2"], L["sn"] + self.foot_h)
            J[f"{side}_knee"], J[f"{side}_foot"] = kn, (kn[0] + fx2, kn[1] + fy2)
        return J

    # draw a sprite so its anchor p0 sits on A and its p0->p1 axis points at B
    def bone(self, ctx, part, A, B, back=False, width=None):
        if width is None and part[:2] in ("ua", "fa", "fi"):
            width = self.gs * self.arm_k
        surf = (self.dark if back else self.img).get(part) or self.img.get(part)
        if surf is None:
            return
        r = self.rig[part]
        p0, p1 = (r["p0"], r["p1"]) if "p0" in r else (r["sh"], r["hip"])
        li = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) or 1
        lw = math.hypot(B[0] - A[0], B[1] - A[1]) or 1
        ai = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        aw = math.atan2(B[1] - A[1], B[0] - A[0])
        k = self.arm_k if part[:2] in ("ua", "fa", "fi") else 1.0
        axial = max(0.75 * self.gs * k, min(1.35 * self.gs, lw / li))
        ctx.save()
        ctx.translate(*A)
        ctx.rotate(aw)
        ctx.scale(axial, width or self.gs)
        ctx.rotate(-ai)
        ctx.translate(-p0[0], -p0[1])
        ctx.set_source_surface(surf, 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
        ctx.paint()
        ctx.restore()

    def head(self, ctx, J, face):
        part = "face_" + face if ("face_" + face) in self.img else "head"
        sk = self.rig[part]["skull"]
        r = self.rig[part]["r"]
        base_r = self.rig["head"]["r"]
        scale = self.gs
        hx, hy = J["head"]
        sx, sy = J["sh"]
        tilt = math.atan2(hx - sx, -(hy - sy))
        ctx.save()
        ctx.translate(hx, hy)
        ctx.rotate(tilt)
        ctx.scale(scale * base_r / r, scale * base_r / r)
        ctx.translate(-sk[0], -sk[1])
        ctx.set_source_surface(self.img[part], 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
        ctx.paint()
        ctx.restore()

    def scarf(self, ctx, J, t, speed):
        surf = self.dark.get("scarf")
        if surf is None:
            return
        an = self.rig["scarf"]["anchor"]
        sx, sy = J["sh"]
        ang = 0.25 * math.sin(t * 7.0) + 0.1 * math.sin(t * 13.0) - min(0.6, abs(speed) * 0.0006)
        ctx.save()
        ctx.translate(sx - 6, sy - 10)
        ctx.rotate(ang)
        ctx.scale(self.gs * 0.9, self.gs * 0.9)
        ctx.translate(-an[0], -an[1])
        ctx.set_source_surface(surf, 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
        ctx.paint()
        ctx.restore()

    def spear(self, ctx, elbow, hand):
        w = self.weapon
        a = math.atan2(hand[1] - elbow[1], hand[0] - elbow[0])
        ctx.save()
        ctx.translate(*hand)
        ctx.rotate(a)
        ctx.scale(self.wscale, self.wscale)
        ctx.translate(-w["grip"][0], -w["grip"][1])
        ctx.set_source_surface(self.img["weapon"], 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
        ctx.paint()
        ctx.restore()

    # ------------------------------------------------------------------ whole fighter
    def draw(self, ctx, k, t, face, alpha=1.0, tint=None, speed=0.0):
        """Draw at sample k (from Fighter.sample). Pose is always built facing right and mirrored."""
        pose = k["pose"]
        feet = -k["air"]
        J = self.joints(pose, k["x"], feet)
        hx, hy = J["hip"]
        ctx.save()
        if k["rot"]:
            ctx.translate(hx, hy); ctx.rotate(math.radians(k["rot"])); ctx.translate(-hx, -hy)
        if k["face"] < 0:
            ctx.translate(k["x"], 0); ctx.scale(-1, 1); ctx.translate(-k["x"], 0)
        group = alpha < 1 or tint is not None
        if group:
            ctx.push_group()
        fh = self.foot_h

        def leg(side, part_i, back):
            hip, kn, ft = J["hip"], J[f"{side}_knee"], J[f"{side}_foot"]
            dx, dy = ft[0] - kn[0], ft[1] - kn[1]
            L = math.hypot(dx, dy) or 1
            ank = (ft[0] - dx / L * fh, ft[1] - dy / L * fh)
            self.bone(ctx, f"th{part_i}", hip, kn, back)
            self.bone(ctx, f"sn{part_i}", kn, ank, back)
            self.bone(ctx, f"foot{part_i}", ank, (ank[0] + dx / L * fh, ank[1] + dy / L * fh), back)

        def arm(side, part_i, back, weapon=False):
            sh, el, hd = J["sh"], J[f"{side}_elbow"], J[f"{side}_hand"]
            self.bone(ctx, f"ua{part_i}", (sh[0], sh[1] + 6), el, back)
            self.bone(ctx, f"fa{part_i}", el, hd, back)
            dx, dy = hd[0] - el[0], hd[1] - el[1]
            L = math.hypot(dx, dy) or 1
            fl = 0.75 * self.arm_k * math.hypot(self.rig[f"fist{part_i}"]["p1"][0] - self.rig[f"fist{part_i}"]["p0"][0],
                                   self.rig[f"fist{part_i}"]["p1"][1] - self.rig[f"fist{part_i}"]["p0"][1]) * self.gs
            back_off = 0.18 * fl
            st = (hd[0] - dx / L * back_off, hd[1] - dy / L * back_off)
            if weapon and self.weapon:
                self.spear(ctx, el, hd)
            self.bone(ctx, f"fist{part_i}", st, (st[0] + dx / L * fl, st[1] + dy / L * fl), back)

        arm("l", 1, True)
        leg("l", 1, True)
        self.scarf(ctx, J, t, speed)
        leg("r", 0, False)
        # torso: shoulder line -> hips
        self.bone(ctx, "torso", J["sh"], J["hip"], width=self.gs * 1.0)
        self.head(ctx, J, face)
        arm("r", 0, False, weapon=True)
        if group:
            pat = ctx.pop_group()
            if tint == "white":
                ctx.set_source_rgba(1, 1, 1, alpha)
                ctx.mask(pat)
            else:
                ctx.set_source(pat)
                ctx.paint_with_alpha(alpha)
                if tint:                       # power-up: a light additive golden glow
                    ctx.set_operator(cairo.OPERATOR_ADD)
                    ctx.set_source_rgba(*tint, 0.12 + 0.05 * math.sin(t * 20))
                    ctx.mask(pat)
                    ctx.set_operator(cairo.OPERATOR_OVER)
        ctx.restore()
        return J


# ====================================================================== arena
class Arena:
    SCALE = 1.25          # world px per image px
    FLOOR = 0.805         # image height fraction where the fighters stand

    def __init__(self, key):
        im = Image.open(os.path.join(ADIR, key + ".jpg")).convert("RGB")
        w, h = im.size
        pano = Image.new("RGB", (w * 3, h))
        flip = im.transpose(Image.FLIP_LEFT_RIGHT)
        pano.paste(flip, (0, 0)); pano.paste(im, (w, 0)); pano.paste(flip, (2 * w, 0))
        arr = np.asarray(pano).astype(np.float32)
        self.top_col = tuple(arr[:12].reshape(-1, 3).mean(0) / 255)
        self.bot_col = tuple(arr[-12:].reshape(-1, 3).mean(0) / 255 * 0.7)
        pano.putalpha(255)
        tmp = os.path.join("/tmp", f"_pano_{key}.png")
        pano.save(tmp)
        self.surf = _surface(tmp)
        self.w, self.h = w, h

    def draw(self, ctx):
        sc = self.SCALE
        x0 = -1.5 * self.w * sc
        y0 = -self.FLOOR * self.h * sc
        ctx.set_source_rgb(*self.top_col)
        ctx.rectangle(-6000, -6000, 12000, 6000 + y0 + 4); ctx.fill()
        ctx.set_source_rgb(*self.bot_col)
        ctx.rectangle(-6000, y0 + self.h * sc - 4, 12000, 6000); ctx.fill()
        ctx.save()
        ctx.translate(x0, y0)
        ctx.scale(sc, sc)
        ctx.set_source_surface(self.surf, 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
        ctx.paint()
        ctx.restore()


# ====================================================================== frame
def face_for(D, f, k, t):
    pn = k.get("pname") or "stance"
    ko_t = D.marks.get("ko", 1e9)
    if f is D.winner and pn == "victory":
        return "win"
    if t >= ko_t and f is not D.winner and pn in ("down", "launched", "hurt"):
        return "ko"
    if pn in HURT_POSES:
        return "hurt"
    if pn in STRIKE_POSES:
        return "shout"
    if pn in ANGRY_POSES:
        return "angry"
    if pn == "victory":
        return "win"
    return "calm" if f.hp_at(t) > 55 else "angry"


def draw_effect_sprite(ctx, skin, x, y, size, rot=0.0, alpha=1.0):
    s = skin.effect
    if s is None:
        return
    w, h = s.get_width(), s.get_height()
    sc = size / max(w, h)
    ctx.save()
    ctx.translate(x, y); ctx.rotate(rot); ctx.scale(sc, sc); ctx.translate(-w / 2, -h / 2)
    ctx.set_operator(cairo.OPERATOR_ADD)
    ctx.set_source_surface(s, 0, 0)
    ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
    ctx.paint_with_alpha(alpha)
    ctx.set_operator(cairo.OPERATOR_OVER)
    ctx.restore()


def draw_frame(ctx, D, arena, skins, cams, i):
    t = i / FPS
    cam = cams[min(i, len(cams) - 1)]
    ctx.set_source_rgb(0, 0, 0); ctx.paint()
    ctx.save()
    cx, cy, z, sx, sy = cam
    ctx.translate(540 + sx, 930 + sy)
    ctx.scale(z, z)
    ctx.translate(-cx, -cy)
    arena.draw(ctx)
    active = [e for e in D.fx if e["t0"] <= t < e["t1"]]
    for e in active:
        if e["kind"] in ("crater", "wallcrack", "dust", "rocks"):
            F.draw_effect(ctx, e, t, D)
    # shadows
    for f in (D.A, D.B):
        k = f.sample(t)
        r = 120 * (1 - min(0.7, k["air"] / 600))
        ctx.save(); ctx.translate(k["x"], 4); ctx.scale(1, 0.16)
        ctx.arc(0, 0, r, 0, 2 * math.pi); ctx.restore()
        ctx.set_source_rgba(0, 0, 0, 0.45); ctx.fill()
    for e in active:
        if e["kind"] == "aura":
            f = e["who"]
            F.draw_aura(ctx, f, f.sample(t), t, e["power"] * min(1.0, (t - e["t0"]) / 0.4 + 0.2), e.get("gold"))
    # afterimages / ghosts
    for e in D.fx:
        if e["kind"] == "afterimage" and e["t0"] <= t < e["t1"] + 0.15 and e["who"] in skins:
            f = e["who"]
            for j in range(1, 5):
                tt = t - 0.035 * j
                if tt < e["t0"]:
                    break
                k = f.sample(tt)
                skins[f].draw(ctx, k, tt, face_for(D, f, k, tt), alpha=0.35 - 0.07 * j)
        if e["kind"] == "ghost" and e["t0"] <= t < e["t1"] and e["who"] in skins:
            kk = (t - e["t0"]) / (e["t1"] - e["t0"])
            f = e["who"]
            ks = dict(f.sample(e["t0"] - 0.01)); ks["x"] = e["x"]
            skins[f].draw(ctx, ks, t, "calm", alpha=0.55 * (1 - kk), tint="white")
    for e in active:
        if e["kind"] == "beam":
            F.draw_effect(ctx, e, t, D)
            _beam_sprites(ctx, e, t, D, skins)
    for f in D.fighters():
        if f.keys[0]["t"] > t:
            continue
        k = f.sample(t)
        if f in skins:
            gold = any(e["kind"] == "aura" and e["who"] is f and e.get("gold") for e in active)
            k2 = f.sample(t - 1 / FPS)
            skins[f].draw(ctx, k, t, face_for(D, f, k, t), tint=(1, 0.85, 0.3) if gold else None,
                          speed=(k["x"] - k2["x"]) * FPS)
        else:
            F.draw_fighter(ctx, f, k)          # twist characters stay classic stickmen
    for e in active:
        if e["kind"] in ("spark", "shockwave", "explosion"):
            F.draw_effect(ctx, e, t, D)
            if e["kind"] == "spark" and e["size"] > 60:
                att = next((f for f in skins if f.color == e["color"]), None)
                if att is not None:
                    kk = (t - e["t0"]) / max(1e-6, e["t1"] - e["t0"])
                    draw_effect_sprite(ctx, skins[att], e["x"], e["y"], e["size"] * (2.2 + 1.5 * kk),
                                       rot=e["t0"] * 7, alpha=max(0.0, 1 - kk) * 0.9)
            if e["kind"] == "explosion":
                kk = (t - e["t0"]) / max(1e-6, e["t1"] - e["t0"])
                for j, sk in enumerate(skins.values()):
                    draw_effect_sprite(ctx, sk, e["x"] + (j - 0.5) * 120, e["y"], 300 + 700 * kk,
                                       rot=j * 1.3, alpha=max(0.0, 1 - kk))
    ctx.restore()
    for e in active:
        if e["kind"] == "speedlines":
            F.draw_speedlines(ctx, t, e)
    F.draw_ui(ctx, D, t)
    F._text(ctx, f"Comment {D.A.name} or {D.B.name}!", 540, 1575, 42, (1, 1, 1), 0.9, outline=6)
    if any(e["kind"] == "impact" for e in active):
        ctx.set_operator(cairo.OPERATOR_DIFFERENCE)
        ctx.set_source_rgb(1, 1, 1)
        ctx.paint()
        ctx.set_operator(cairo.OPERATOR_OVER)


def _beam_sprites(ctx, e, t, D, skins):
    """Fireball / ice burst riding on the front of each fighter's beam."""
    a, b = e["a"], e["b"]
    ka, kb = a.sample(t), b.sample(t)
    ha = rig.joints(ka["pose"] if ka["face"] > 0 else rig.mirror(ka["pose"]), ka["x"], -ka["air"], S)["r_hand"]
    hb = rig.joints(kb["pose"] if kb["face"] > 0 else rig.mirror(kb["pose"]), kb["x"], -kb["air"], S)["r_hand"]
    rng = random.Random(e["seed"])
    ph = rng.uniform(0, 6)
    mid = (ha[0] + hb[0]) / 2 + 90 * math.sin((t - e["t0"]) * 3.3 + ph) * math.sin((t - e["t0"]) * 1.1)
    if t > e["push"]:
        loser = b if e["winner"] is a else a
        mid = mid + (loser.sample(t)["x"] - mid) * F.ease((t - e["push"]) / 0.6, "in")
    yy = (ha[1] + hb[1]) / 2
    for f, h in ((a, ha), (b, hb)):
        if f not in skins:
            continue
        d = 1 if mid > h[0] else -1
        x = mid - d * 70
        draw_effect_sprite(ctx, skins[f], x, yy, 330 + 30 * math.sin(t * 25), rot=0 if d > 0 else math.pi,
                           alpha=0.95)


# ====================================================================== render
def render(seed, out_base, a="blaze", b="frost", arena="pagoda", length=118.0):
    sa, sb = Skin(a), Skin(b)
    D = F.Director(seed, roster=[(sa.name, sa.color), (sb.name, sb.color)]).write(length)
    skins = {}
    for f in (D.A, D.B):
        skins[f] = sa if f.name == sa.name else sb
    ar = Arena(arena)
    n = int(D.length * FPS)
    cams = F.camera_track(D, n)
    music_sections = D.music + [(0, 1.0, 3), (D.length - 3, D.length + 2, 1)]
    wav = out_base + ".wav"
    fightaudio.mix(D.length + 0.6, D.au, sorted(music_sections), wav, seed)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    tmp = out_base + ".v.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                           "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for i in range(n):
        draw_frame(ctx, D, ar, skins, cams, i)
        surf.flush()
        ff.stdin.write(bytes(surf.get_data()))
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-i", wav, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "160k", "-shortest", "-movflags", "+faststart", out_base + ".mp4"], check=True)
    os.remove(tmp); os.remove(wav)
    beam = next((e for e in D.fx if e["kind"] == "beam"), None)
    ci = int(((beam["t0"] + beam["push"]) / 2 if beam else D.length * 0.4) * FPS)
    draw_frame(ctx, D, ar, skins, cams, min(ci, n - 1))
    surf.write_to_png(out_base + "_cover.png")
    return D, round(n / FPS, 2)


def available():
    fighters = sorted(d for d in os.listdir(FDIR) if os.path.exists(os.path.join(FDIR, d, "rig.json")))
    arenas = sorted(os.path.splitext(f)[0] for f in os.listdir(ADIR) if f.endswith(".jpg"))
    return fighters, arenas


def pick(seed):
    """Matchup + arena for a seed: every pair of available fighters comes up in turn."""
    fighters, arenas = available()
    pairs = [(a, b) for i, a in enumerate(fighters) for b in fighters[i + 1:]]
    rng = random.Random(seed * 17 + 3)
    a, b = pairs[seed % len(pairs)]
    if rng.random() < 0.5:
        a, b = b, a
    return a, b, arenas[(seed // len(pairs)) % len(arenas)]


TITLES = [
    "{a} vs {b} — who wins? 🔥",
    "{a} vs {b}: wait for the beam clash 💥",
    "Pick a side: {a} or {b}? ⚔️",
    "{a} vs {b} — the comeback nobody expected 😳",
    "Stickman battle: {a} vs {b} 🔥 Who did you pick?",
]


def make_meta(D, seed):
    rng = random.Random(seed * 13 + 1)
    a, b = D.A.name.title(), D.B.name.title()
    title = rng.choice(TITLES).format(a=a, b=b)
    desc = "\n".join([
        f"{a} vs {b} — a full stickman battle: combos, beam clash, power-up and K.O.",
        f"Who did you pick? Comment {D.A.name} or {D.B.name} 👇",
        "",
        "New fights every day — subscribe! 🔔",
        "Characters designed for this channel; animated with code. Music and sound effects are original.",
        "",
        "#shorts #stickman #stickfight #animation #anime #fight",
    ])
    tags = ["stickman", "stick fight", "stickman fight", "animation", "anime fight", a.lower(), b.lower(),
            "fight animation", "shorts", "battle", "beam clash", "power up", "2d fight"]
    return dict(title=f"{title} #shorts"[:100], description=desc, tags=tags, categoryId="1",
                containsSyntheticMedia=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=5000)
    ap.add_argument("--a", default="blaze")
    ap.add_argument("--b", default="frost")
    ap.add_argument("--arena", default="pagoda")
    ap.add_argument("--length", type=float, default=118.0)
    ap.add_argument("--out", default=".")
    x = ap.parse_args()
    os.makedirs(x.out, exist_ok=True)
    D, d = render(x.seed, os.path.join(x.out, f"skin_{x.a}_vs_{x.b}_{x.seed}"), x.a, x.b, x.arena, x.length)
    print("done", d, "winner", D.winner.name)
