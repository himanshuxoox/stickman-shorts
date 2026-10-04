"""
Daily batch of stickman psychology Shorts.

    GEMINI_API_KEY=... python -m stick.batch --count 4
    python -m stick.batch --count 1 --mock        # offline test (canned script, fake voice)

Output: out/<date>/NN_stickman.mp4 + .json + _cover.png, manifest.json, UPLOAD_SHEET.txt
"""
import argparse, copy, datetime as dt, json, os, random, time, traceback
from zoneinfo import ZoneInfo

from . import render, voice

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state", "history.json")
IST = ZoneInfo("Asia/Kolkata")
HASHTAGS = "#shorts #psychology #lifelessons #stickman #mindset"


def load_state():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {"videos": []}


def save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(st, f, indent=1, ensure_ascii=False)


def make_meta(script):
    title = script["title"].strip().rstrip(".")[:88] + " #shorts"
    desc = "\n".join([
        script.get("description", "").strip(), "",
        f"💬 {script['outro']}", "",
        "General education only — not medical, psychological or financial advice.",
        "Animated with code. Narration is an AI voice.",
        "New psychology shorts every day — subscribe! 🔔", "",
        HASHTAGS])
    tags = [t.lower() for t in script.get("tags", [])][:12] + ["psychology", "stickman", "shorts", "life lessons"]
    return dict(title=title, description=desc, tags=list(dict.fromkeys(tags)), categoryId="27",
                containsSyntheticMedia=False)


def make_one(idx, out_dir, history, rng, mock):
    t0 = time.time()
    if mock:
        from .mock import MOCK_SCRIPT
        from .writer import sanitize
        script = sanitize(copy.deepcopy(MOCK_SCRIPT))
        script["topic"] = "mock"
    else:
        from . import writer
        script = writer.write(history, rng)
    if script.get("confidence") == "low":
        raise RuntimeError("fact-check confidence low — skipped")
    if len(script["scenes"]) < 4:
        raise RuntimeError("script too short")
    base = os.path.join(out_dir, f"{idx:02d}_stickman")
    audios = [voice.speak(sc["narration"]) for sc in script["scenes"]]
    outro = voice.speak(script["outro"])
    dur = render.render(script, audios, outro, base + ".mp4", rng.randint(1, 10 ** 6))
    item = dict(file=os.path.basename(base + ".mp4"), cover=os.path.basename(base + "_cover.png"),
                duration=dur, topic=script["topic"], script=script, **make_meta(script))
    with open(base + ".json", "w") as f:
        json.dump(item, f, indent=1, ensure_ascii=False)
    print(f"[{idx}] {script['title']}  ({dur}s, {time.time() - t0:.0f}s)", flush=True)
    return item


def upload_sheet(items, path):
    L = []
    for v in items:
        L += ["=" * 60, v["file"], "=" * 60, "TITLE:", v["title"], "", "DESCRIPTION:", v["description"],
              "", "TAGS:", ", ".join(v["tags"]), "",
              "Made for kids: NO  |  Category: Education  |  Altered/synthetic content: NO", "", ""]
    with open(path, "w") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--date", default=dt.datetime.now(IST).strftime("%Y-%m-%d"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    if a.mock:
        voice.ENGINE = "mock"

    st = load_state()
    rng = random.Random(f"{a.date}-{len(st['videos'])}")
    out_dir = os.path.join(a.out, a.date)
    os.makedirs(out_dir, exist_ok=True)
    items = []
    for i in range(1, a.count + 1):
        try:
            items.append(make_one(i, out_dir, st["videos"], rng, a.mock))
        except Exception:
            print(f"[{i}] FAILED:\n{traceback.format_exc()}", flush=True)
            continue
        if not a.mock:
            st["videos"].append(dict(date=a.date, topic=items[-1]["topic"], title=items[-1]["title"]))
            save_state(st)

    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(dict(date=a.date, videos=items), f, indent=1, ensure_ascii=False)
    upload_sheet(items, os.path.join(out_dir, "UPLOAD_SHEET.txt"))
    print(f"done: {len(items)}/{a.count} videos in {out_dir}")
    if not items:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
