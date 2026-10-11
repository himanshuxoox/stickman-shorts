"""
Cut a fighter's AI-generated art into rig-ready sprites.

    python tools/extract_fighter.py <fighter folder> assets/fighters/<name>

The folder holds (any file names; recognised by keywords):
  * parts sheet  (".. parts .." / ".. armor sprite sheet ..")  green background, every body part separate
  * faces sheet  (".. expression ..")                            3x2 grid of heads on green
  * weapon       (".. spear / sword / gauntlet .. on green")    optional
  * effect       (".. fireball / explosion ..")                 black background, optional

Writes PNGs (transparent) + rig.json with the joint anchors of every part:
  head, torso, scarf, ua0/ua1 (upper arms), fa0/fa1 (forearms), fist0/fist1, th0/th1, sn0/sn1, foot0/foot1,
  face_<calm|angry|shout|hurt|ko|win>, weapon, effect.
"""
import json, os, sys

import cv2
import numpy as np

FACE_NAMES = ["calm", "angry", "shout", "hurt", "ko", "win"]
# expected centroids on a 1536x1024 parts sheet (both sheets we got use this layout)
TEMPLATE = {
    "ua0": (440, 330), "ua1": (905, 330), "fa0": (255, 470), "fa1": (1115, 470),
    "fist0": (215, 665), "fist1": (1140, 665), "th0": (530, 560), "th1": (855, 560),
    "sn0": (490, 760), "sn1": (880, 760), "foot0": (375, 935), "foot1": (985, 935),
}


def key_green(img):
    """BGR image on a green screen -> BGRA with soft alpha and green spill removed."""
    b, g, r = [img[..., i].astype(np.float32) for i in range(3)]
    k = g - np.maximum(r, b)
    a = np.clip(1.0 - (k - 40.0) / 70.0, 0, 1)
    g2 = np.where(k > 0, np.minimum(g, np.maximum(r, b) + 8), g)
    out = np.dstack([b, g2, r, a * 255]).astype(np.uint8)
    return out


def key_black(img):
    """Glowing effect on black -> premultiplied-ready BGRA (alpha = brightness)."""
    f = img.astype(np.float32)
    a = np.clip(f.max(axis=2) * 1.15, 0, 255)
    rgb = np.where(a[..., None] > 0, f * 255.0 / np.maximum(a[..., None], 1), 0)
    return np.dstack([np.clip(rgb, 0, 255), a]).astype(np.uint8)


def components(rgba, min_area=1500):
    m = (rgba[..., 3] > 128).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area >= min_area:
            out.append(dict(i=i, box=(x, y, w, h), area=int(area), c=tuple(cent[i]), lab=lab))
    return out


def crop(rgba, comp, pad=6):
    x, y, w, h = comp["box"]
    H, W = rgba.shape[:2]
    x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
    sub = rgba[y0:y1, x0:x1].copy()
    mask = (comp["lab"][y0:y1, x0:x1] == comp["i"])
    mask = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    sub[~mask] = 0
    return sub


def limb_anchors(sub, inset=0.07):
    """Long axis of the part; proximal = upper end. Returns (p0, p1) in crop pixels."""
    ys, xs = np.nonzero(sub[..., 3] > 128)
    pts = np.stack([xs, ys], 1).astype(np.float32)
    c = pts.mean(0)
    u = np.linalg.svd(pts - c, full_matrices=False)[2][0]
    if u[1] < 0:
        u = -u                                     # point downwards
    proj = (pts - c) @ u
    lo, hi = proj.min(), proj.max()
    L = hi - lo
    p0 = c + u * (lo + inset * L)
    p1 = c + u * (hi - inset * L)
    return p0.tolist(), p1.tolist()


def skull(sub):
    """Centre + radius of the dark round head inside a head sprite."""
    a = sub[..., 3] > 128
    lum = sub[..., :3].astype(np.float32).mean(2)
    dark = (a & (lum < 45)).astype(np.uint8)
    n, lab, st, cent = cv2.connectedComponentsWithStats(dark, 8)
    i = 1 + int(np.argmax(st[1:, 4]))
    r = float(np.sqrt(st[i, 4] / np.pi))
    return [float(cent[i][0]), float(cent[i][1])], r


def save(out, name, sub):
    cv2.imwrite(os.path.join(out, name + ".png"), sub)


def find(folder, *words, exclude=()):
    for f in sorted(os.listdir(folder)):
        lf = f.lower()
        if any(w in lf for w in words) and not any(x in lf for x in exclude):
            return os.path.join(folder, f)
    return None


def main(src, out):
    os.makedirs(out, exist_ok=True)
    rig = {}
    # ---------------- parts sheet
    p = find(src, "parts", "armor sprite", "rig")
    img = cv2.imread(p)
    sx, sy = img.shape[1] / 1536.0, img.shape[0] / 1024.0
    rgba = key_green(img)
    comps = components(rgba)
    comps.sort(key=lambda c: -c["area"])
    used = set()

    def take(pred):
        for c in comps:
            if id(c) not in used and pred(c):
                used.add(id(c))
                return c
        raise RuntimeError("part not found")

    head = take(lambda c: c["c"][0] < 560 * sx and c["c"][1] < 360 * sy)
    torso = take(lambda c: abs(c["c"][0] - 768 * sx) < 220 * sx and c["c"][1] < 470 * sy)
    scarf = take(lambda c: c["c"][0] > 820 * sx and c["c"][1] < 480 * sy)
    rest = [c for c in comps if id(c) not in used]
    # greedy nearest assignment to the template
    pairs = sorted(((np.hypot(c["c"][0] - tx * sx, c["c"][1] - ty * sy), name, k)
                    for name, (tx, ty) in TEMPLATE.items() for k, c in enumerate(rest)))
    got, taken = {}, set()
    for d, name, k in pairs:
        if name not in got and k not in taken:
            got[name], _ = rest[k], taken.add(k)
    missing = [n for n in TEMPLATE if n not in got]
    if missing:
        raise RuntimeError(f"missing parts: {missing}")

    s = crop(rgba, head); save(out, "head", s)
    (cx, cy), r = skull(s)
    ys, xs = np.nonzero(s[..., 3] > 128)
    rig["head"] = dict(skull=[cx, cy], r=r)

    s = crop(rgba, torso); save(out, "torso", s)
    ys, xs = np.nonzero(s[..., 3] > 128)
    top, bot = ys.min(), ys.max()
    hgt = bot - top

    def row_center(fy):
        y = int(top + fy * hgt)
        row = np.nonzero(s[y, :, 3] > 128)[0]
        return [float(row.mean()), float(y)]
    # hips sit just below the waist (narrowest row between 25 % and 70 % of the torso height)
    widths = [(np.count_nonzero(s[int(top + f * hgt), :, 3] > 128), f) for f in np.linspace(0.25, 0.7, 40)]
    waist = min(widths)[1]
    rig["torso"] = dict(sh=row_center(0.14), hip=row_center(min(0.72, waist + 0.1)), waist=waist)

    s = crop(rgba, scarf)
    s = s[:, ::-1].copy()                          # trail behind a right-facing fighter
    save(out, "scarf", s)
    ys, xs = np.nonzero(s[..., 3] > 128)
    right = xs.max()
    sel = xs > right - 25
    rig["scarf"] = dict(anchor=[float(right - 8), float(ys[sel].mean())])

    for name in TEMPLATE:
        s = crop(rgba, got[name])
        if name.startswith("foot"):
            ys, xs = np.nonzero(s[..., 3] > 128)
            ank_y = ys.min() + 6
            top_row = np.nonzero(s[ys.min() + 10, :, 3] > 128)[0]
            ank_x = float(top_row.mean())
            if (xs < ank_x).sum() > (xs > ank_x).sum():        # toe must point forward (right)
                s = s[:, ::-1].copy()
                ank_x = s.shape[1] - 1 - ank_x
            save(out, name, s)
            ys, xs = np.nonzero(s[..., 3] > 128)
            heel_y = float(ys.max())
            rig[name] = dict(p0=[ank_x, float(ank_y)], p1=[ank_x, heel_y])
            continue
        save(out, name, s)
        p0, p1 = limb_anchors(s, inset=0.0 if name.startswith("fist") else 0.08)
        rig[name] = dict(p0=p0, p1=p1)

    # ---------------- faces sheet (3 x 2)
    p = find(src, "expression", "face")
    if p:
        img = cv2.imread(p)
        rgba = key_green(img)
        fc = components(rgba, min_area=4000)
        fc.sort(key=lambda c: -c["area"])
        fc = fc[:6]
        fc.sort(key=lambda c: (round(c["c"][1] / (img.shape[0] / 2)), c["c"][0]))
        for nm, c in zip(FACE_NAMES, fc):
            s = crop(rgba, c)
            save(out, "face_" + nm, s)
            (cx, cy), r = skull(s)
            rig["face_" + nm] = dict(skull=[cx, cy], r=r)

    # ---------------- weapon (on green)
    p = find(src, "spear", "sword", "katana", "axe", "hammer", "scythe", "staff", "weapon", "gauntlet",
             exclude=("parts", "sprite", "expression"))
    if p:
        img = cv2.imread(p)
        rgba = key_green(img)
        c = max(components(rgba), key=lambda c: c["area"])
        s = crop(rgba, c)
        save(out, "weapon", s)
        ys, xs = np.nonzero(s[..., 3] > 128)
        rig["weapon"] = dict(grip=[float(xs.min() + 0.36 * (xs.max() - xs.min())), float(ys.mean())],
                             tip=[float(xs.max()), float(ys.mean())], file=os.path.basename(p))

    # ---------------- effect (on black)
    p = find(src, "fireball", "explosion", "effect", "burst", "blast", "shard")
    if p:
        img = cv2.imread(p)
        s = key_black(img)
        ys, xs = np.nonzero(s[..., 3] > 20)
        s = s[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        save(out, "effect", s)
        rig["effect"] = dict(size=[int(s.shape[1]), int(s.shape[0])], file=os.path.basename(p))

    with open(os.path.join(out, "rig.json"), "w") as f:
        json.dump(rig, f, indent=1)
    print(f"{out}: {len(rig)} parts")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
