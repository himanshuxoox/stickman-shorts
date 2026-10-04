"""
Stickman explainer renderer: one or two stick figures acting out each scene, pop-in props
and emotes, a highlighted keyword, word-by-word captions, voice + SFX + music bed.
"""
import math, os, subprocess, wave

import cairo
import numpy as np

from . import props as PR
from . import rig

W, H, FPS = 1080, 1920, 30
SR = 24000
GAP = 0.15
OUTRO_MIN = 2.6
GROUND = 1410
SCALE = 1.12
BG = (0.985, 0.982, 0.972)
INK = PR.INK
OTHER_INK = (0.42, 0.43, 0.48)
FONT = os.environ.get("SHORTS_FONT", "Inter")


# ------------------------------------------------------------------ timeline
def build_timeline(scenes, audios, outro_len):
    t, out = 0.0, []
    for sc, a in zip(scenes, audios):
        speech = len(a) / SR
        words = sc["narration"].split()
        wts = np.array([len(w) + 2 for w in words], float)
        edges = np.concatenate([[0], np.cumsum(wts)]) / wts.sum() * speech
        out.append(dict(start=t, speech=speech, end=t + speech + GAP, sc=sc,
                        words=[(w, t + edges[i], t + edges[i + 1]) for i, w in enumerate(words)]))
        t += speech + GAP
    return out, t + outro_len


def caption_chunks(words, max_words=3, max_chars=18):
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or sum(len(x[0]) + 1 for x in cur) + len(w[0]) > max_chars):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if w[0][-1:] in ".?!,;:":
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def ease(x):
    return rig.ease(x)


def pop(x):
    """0..1 -> scale with a little overshoot."""
    if x <= 0:
        return 0.001                  # never 0: cairo can't invert a zero-scale matrix
    if x >= 1:
        return 1.0
    c1 = 1.70158                      # easeOutBack
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


# ------------------------------------------------------------------ text
def _font(ctx, size, bold=True):
    ctx.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)


def _wrap(ctx, text, size, max_w):
    _font(ctx, size)
    lines, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if ctx.text_extents(trial).x_advance > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def keyword(ctx, text, cy, accent, k):
    """Big bold keyword with a highlighter-marker swipe behind it."""
    size = 112
    lines = _wrap(ctx, text.upper(), size, W - 160)
    while len(lines) > 2 and size > 70:
        size -= 8
        lines = _wrap(ctx, text.upper(), size, W - 160)
    _font(ctx, size)
    lh = size * 1.12
    y = cy - (len(lines) - 1) * lh / 2
    sc = pop(k)
    ctx.save()
    ctx.translate(W / 2, cy)
    ctx.scale(sc, sc)
    ctx.translate(-W / 2, -cy)
    for ln in lines:
        e = ctx.text_extents(ln)
        w = e.x_advance
        swipe = ease(min(1, k * 1.6))
        ctx.rectangle(W / 2 - w / 2 - 22, y - size * 0.42, (w + 44) * swipe, size * 0.62)
        ctx.set_source_rgba(*accent, 0.85)
        ctx.fill()
        ctx.move_to(W / 2 - w / 2, y + size * 0.36)
        ctx.set_source_rgb(*INK)
        ctx.show_text(ln)
        ctx.new_path()
        y += lh
    ctx.restore()


def captions(ctx, chunks, t, accent):
    for ch in chunks:
        if ch[0][1] <= t < ch[-1][2] + 0.05:
            text = " ".join(w for w, _, _ in ch)
            size = 70
            _font(ctx, size)
            while ctx.text_extents(text).x_advance > W - 140 and size > 46:
                size -= 4
                _font(ctx, size)
            x = W / 2 - ctx.text_extents(text).x_advance / 2
            y = 1640
            for w, a, b in ch:
                ctx.move_to(x, y)
                ctx.set_source_rgb(*(accent if a <= t < b else INK))
                ctx.show_text(w)
                ctx.new_path()
                x += ctx.text_extents(w + " ").x_advance
            return


# ------------------------------------------------------------------ actors
def scene_layout(sc):
    duo = bool(sc.get("other"))
    return (330, 750) if duo else (540, None)


def actor_state(tl, i, t):
    """(main_x, main_pose, other_x, other_pose, other_alpha) at time t inside scene i."""
    s = tl[i]
    sc = s["sc"]
    lt = t - s["start"]
    mx, ox = scene_layout(sc)
    k = ease(lt / 0.35)
    # blend from where the previous scene left off
    if i > 0:
        ps = tl[i - 1]
        pmx, pox = scene_layout(ps["sc"])
        prev_pose = rig.pose_at(ps["sc"]["pose"], s["start"] - ps["start"])
    else:
        pmx, pox, prev_pose = mx, ox, rig.pose_at(sc["pose"], 0)
    pose = rig.lerp_pose(prev_pose, rig.pose_at(sc["pose"], lt), k)
    x = pmx + (mx - pmx) * k

    move = sc.get("move", "none")
    dur = s["end"] - s["start"]
    if move == "walk_in" and lt < 1.3:
        x = -160 + (mx + 160) * ease(lt / 1.3)
        pose = rig.pose_at("walk", lt)
    elif move in ("walk_across", "run_across"):
        span = min(dur, 3.2)
        if lt < span:
            x = 140 + (W - 280) * (lt / span)
            pose = rig.pose_at("walk" if move == "walk_across" else "run", lt)
        else:
            x = W - 140 + (mx - (W - 140)) * ease((lt - span) / 0.5)
    elif move == "jump" and lt < 0.7:
        pose = dict(pose)
        pose["y"] -= 160 * math.sin(math.pi * lt / 0.7)

    other_pose, oa = None, 0.0
    if ox is not None:
        # poses are screen-relative: the other character stands on the RIGHT, so it points
        # at the main character with "point_left"
        other_pose = rig.pose_at(sc["other"].get("pose", "stand"), lt + 0.4)
        oa = ease(lt / 0.3) if (i == 0 or not tl[i - 1]["sc"].get("other")) else 1.0
    return x, pose, ox, other_pose, oa


# ------------------------------------------------------------------ frame
def draw_frame(ctx, t, T, script, tl, chunks, outro_start):
    i = max(k for k, s in enumerate(tl) if s["start"] <= t)
    s = tl[i]
    sc = s["sc"]
    lt = t - s["start"]
    accent = PR.ACCENTS.get(sc.get("accent", "yellow"), PR.ACCENTS["yellow"])

    ctx.set_source_rgb(*BG)
    ctx.paint()

    # camera: punch-in on each cut + slow push
    z = 1.0 + 0.05 * (1 - ease(lt / 0.3)) + 0.025 * min(1, lt / max(0.1, s["end"] - s["start"]))
    ctx.save()
    ctx.translate(W / 2, 1000)
    ctx.scale(z, z)
    ctx.translate(-W / 2, -1000)

    # floor line
    ctx.set_source_rgba(0, 0, 0, 0.08)
    ctx.set_line_width(4)
    ctx.move_to(120, GROUND + 10)
    ctx.line_to(W - 120, GROUND + 10)
    ctx.stroke()

    mx, mpose, ox, opose, oa = actor_state(tl, i, t)
    if opose is not None and oa > 0:
        ctx.push_group()
        rig.draw(ctx, opose, ox, GROUND, SCALE * 0.94, OTHER_INK)
        lab = (sc.get("other") or {}).get("label")
        if lab:
            J = rig.joints(opose, ox, GROUND, SCALE * 0.94)
            _font(ctx, 38)
            e = ctx.text_extents(lab.upper())
            ctx.move_to(ox - e.x_advance / 2, J["head"][1] - 80)
            ctx.set_source_rgb(*OTHER_INK)
            ctx.show_text(lab.upper())
            ctx.new_path()
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(oa)
    J = rig.draw(ctx, mpose, mx, GROUND, SCALE, INK)

    in_outro = t >= outro_start
    # props (cleared on the outro card so they don't cover the CTA text)
    for n, p in enumerate([] if in_outro else sc.get("props", [])[:2]):
        f = PR.PROPS.get(p.get("name"))
        if not f:
            continue
        k = (lt - 0.25 - 0.3 * n) / 0.35
        if k <= 0:
            continue
        at = p.get("at", "right")
        bob = 8 * math.sin(2 * math.pi * 0.8 * lt + n)
        if at == "hand":
            hx, hy = J["r_hand"]
            px, py, size = hx + 10, hy - 30, 110
            bob = 0
        elif at == "above":
            px, py, size = mx, max(560, J["head"][1] - 215), 150
        elif at == "left":
            px, py, size = (mx - 310 if ox is None else 140), 860, 200
        elif at == "center":
            if ox:
                px, py, size = (mx + ox) / 2, 580, 190
            else:  # solo: beside the figure, never on top of the head
                px, py, size = mx + 300, 760, 210
        else:  # right
            px, py, size = (mx + 310 if ox is None else 940), 860, 200
        sc_ = pop(k)
        ctx.save()
        ctx.translate(px, py + bob)
        ctx.scale(sc_, sc_)
        f(ctx, 0, 0, size, accent)
        ctx.restore()

    # emote
    em = None if in_outro else PR.EMOTES.get(sc.get("emote") or "")
    if em:
        k = (lt - 0.4) / 0.3
        if k > 0:
            hx, hy = J["head"]
            ctx.save()
            ctx.translate(hx + 95, hy - 95 + 6 * math.sin(2 * math.pi * 1.2 * lt))
            ctx.scale(pop(k), pop(k))
            em(ctx, 0, 0, 92, accent)
            ctx.restore()
    ctx.restore()  # camera

    # UI layer (not zoomed)
    ctx.rectangle(0, 0, W * min(1, t / T), 12)
    ctx.set_source_rgb(*accent)
    ctx.fill()

    if t < outro_start:
        kw = sc.get("keyword") or ""
        if kw:
            keyword(ctx, kw, 380, accent, (lt - 0.05) / 0.35)
        captions(ctx, chunks, t, accent)
    else:
        k = (t - outro_start) / 0.35
        lines = _wrap(ctx, script["outro"], 76, W - 180)
        _font(ctx, 76)
        y = 380 - (len(lines) - 1) * 44
        ctx.save()
        ctx.translate(W / 2, 420)
        ctx.scale(pop(k), pop(k))
        ctx.translate(-W / 2, -420)
        for ln in lines:
            e = ctx.text_extents(ln)
            ctx.move_to(W / 2 - e.x_advance / 2, y)
            ctx.set_source_rgb(*INK)
            ctx.show_text(ln)
            ctx.new_path()
            y += 88
        _font(ctx, 44)
        msg = "Comment below  •  Follow for more"
        e = ctx.text_extents(msg)
        ctx.move_to(W / 2 - e.x_advance / 2, y + 30)
        ctx.set_source_rgb(*accent)
        ctx.show_text(msg)
        ctx.new_path()
        ctx.restore()


# ------------------------------------------------------------------ audio
def _sfx_pop(n=int(0.12 * SR)):
    t = np.arange(n) / SR
    f = 900 * np.exp(-t * 18) + 300
    return 0.35 * np.exp(-t * 30) * np.sin(2 * np.pi * np.cumsum(f) / SR)


def _sfx_whoosh(n=int(0.35 * SR), seed=0):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    k = np.linspace(0, 1, n)
    env = np.sin(np.pi * k) ** 2
    y = np.convolve(x, np.ones(24) / 24, "same")   # soft low-pass
    return 0.22 * env * y / (np.abs(y).max() + 1e-9)


def music_bed(n, seed=0):
    """Light, original ukulele-ish pluck loop + soft pad (generated, no copyright)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    prog = rng.choice([[60, 55, 57, 53], [62, 57, 59, 55], [57, 53, 60, 55]])
    f = lambda m: 440 * 2 ** ((m - 69) / 12)
    bar, out = 2.4, np.zeros(n, np.float32)
    for b in range(int(n / SR / bar) + 1):
        root = prog[b % 4]
        for k, iv in enumerate((0, 7, 12, 16, 12, 7, 4, 7)):
            ps = int((b * bar + k * bar / 8) * SR)
            pe = min(n, ps + int(0.5 * SR))
            if ps >= n:
                break
            tp = t[ps:pe] - (b * bar + k * bar / 8)
            out[ps:pe] += 0.035 * np.exp(-tp * 7) * (np.sin(2 * np.pi * f(root + iv) * tp)
                                                     + 0.3 * np.sin(4 * np.pi * f(root + iv) * tp))
        s, e = int(b * bar * SR), min(n, int((b + 1) * bar * SR))
        if s < n:
            tt = t[s:e] - b * bar
            out[s:e] += 0.018 * np.sin(2 * np.pi * f(root - 12) * tt) * np.minimum(1, tt / 0.3)
    return out


def mix_audio(tl, audios, outro_audio, T, path, seed):
    n = int(T * SR) + SR
    voice = np.zeros(n, np.float32)
    sfx = np.zeros(n, np.float32)
    for k, (s, a) in enumerate(zip(tl, audios)):
        i = int(s["start"] * SR)
        voice[i:i + len(a)] += a[: n - i]
        if k > 0:
            w = _sfx_whoosh(seed=seed + k)
            j = max(0, i - int(0.12 * SR))
            sfx[j:j + len(w)] += w[: n - j]
        sc = s["sc"]
        cues = [0.25 + 0.3 * m for m in range(min(2, len(sc.get("props", []))))]
        if sc.get("emote"):
            cues.append(0.4)
        for c in cues:
            j = int((s["start"] + c) * SR)
            p = _sfx_pop()
            sfx[j:j + len(p)] += p[: n - j]
    if outro_audio is not None:
        i = int(tl[-1]["end"] * SR)
        voice[i:i + len(outro_audio)] += outro_audio[: n - i]
    voice /= max(1e-6, np.abs(voice).max()) / 0.9
    env = np.convolve(np.abs(voice), np.ones(SR // 10) / (SR // 10), "same")
    duck = 1 - 0.5 * np.clip(env / (env.max() + 1e-9) * 4, 0, 1)
    mus = music_bed(n, seed) * duck
    fade = np.ones(n)
    fade[-SR:] = np.linspace(1, 0, SR)
    mixd = np.clip(voice + 0.55 * sfx + mus * fade, -1, 1)[: int(T * SR)]
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mixd * 32767).astype(np.int16).tobytes())


# ------------------------------------------------------------------ main
def render(script, audios, outro_audio, out_path, seed=0):
    outro_len = max(OUTRO_MIN, len(outro_audio) / SR + 0.9) if outro_audio is not None else OUTRO_MIN
    tl, T = build_timeline(script["scenes"], audios, outro_len)
    chunks = caption_chunks([w for s in tl for w in s["words"]])
    outro_start = tl[-1]["end"]
    wav = out_path + ".wav"
    mix_audio(tl, audios, outro_audio, T, wav, seed)

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    tmp = out_path + ".video.mp4"
    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for f in range(int(T * FPS)):
        draw_frame(ctx, f / FPS, T, script, tl, chunks, outro_start)
        surf.flush()
        ff.stdin.write(bytes(surf.get_data()))
        if f == int(1.0 * FPS):
            surf.write_to_png(out_path.replace(".mp4", "_cover.png"))
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-i", wav, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "160k", "-shortest", "-movflags", "+faststart", out_path], check=True)
    os.remove(tmp)
    os.remove(wav)
    return round(T, 2)
