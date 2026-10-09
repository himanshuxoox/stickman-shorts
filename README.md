# Stickman Shorts: anime-style stickman fights (default) + psychology explainers

## Fights (default mode)

`python -m stick.fight --count 2` makes ~2-minute "RED vs BLUE" stickman battles, fully in code:

- **Every seed is a different fight script** built from beats: dash-in combos, block + counter,
  teleport dodge ("TOO SLOW!"), uppercut launch + air combo + ground slam (crater), wall splats,
  a beam clash, a power-up comeback, and a K.O. About 1 in 3 fights ends with a twist.
- **Anime look**: impact frames (colour inversion), speed lines, afterimages, screen shake,
  shockwaves, auras, camera zoom punches, 4 background themes.
- **Game feel**: health bars that follow the story, "N HIT COMBO!", "BLOCKED!", "K.O.!".
- **Engagement**: "RED vs BLUE — WHO WINS?" on screen and "Comment RED or BLUE!" at the bottom.
- **Audio**: an original synthesized fight track + punch / whoosh / beam / boom effects.
- Each video ends with a short cross-fade back to its first frame, so Shorts replays loop.
- No API keys needed. `FIGHT_LENGTH` (env) changes the length (default 118 s).

The workflow makes 2 fights a day and (with `AUTO_UPLOAD = true`) schedules them at 12:00 and 20:00 IST.
Set the repo variable `STICK_MODE = explainer` to switch back to the psychology explainers below.

---

# Stickman Shorts: daily psychology explainers, animated in code

This repo makes 4 YouTube Shorts a day and costs nothing to run. In each one, a minimalist black
stick figure on a white background acts out a ~50-second psychology or life-lesson script.

```
Gemini (free tier)  →  6-scene script in a 5-stage retention arc
                       (hook → disrupt → secret → secret → truth → elevate → comment question)
                    →  a fact-check pass that removes psychology myths
Kokoro (free, CPU)  →  narration
stick/render.py     →  stick-figure acting, props, emotes, keyword highlight,
                       word-by-word captions, sound effects and a generated music bed
GitHub Actions      →  daily run, videos kept as a downloadable artifact (+ optional YouTube upload)
```

- **Fully code-animated.** It needs no image or video API, so the character stays identical in every video.
- **Renderer vocabulary:** 19 poses, 32 props, 9 emotes, walk/run/jump moves, and an optional second character.
  The script writer can only choose from this list, and `sanitize()` fixes anything outside it.
- **Accuracy guard:** well-known myths are banned (10% brain, 21-day habits, learning styles, power posing…).
  A second pass softens anything that isn't well replicated.

## Setup

1. Push this folder to a new GitHub repo.
2. Go to Settings → Secrets → Actions and add `GEMINI_API_KEY`. The same free key as the other channels works.
3. Go to **Actions → Daily Stickman → Run workflow**. The first run takes about 15 minutes because the voice model downloads; after that, a run takes about 5–8 minutes.
4. Download the `stickman-N` artifact. Each video comes with a `.json` file, and there is one `UPLOAD_SHEET.txt` with titles, descriptions and tags.

Later, for automatic uploads, add `YT_CLIENT_ID`, `YT_CLIENT_SECRET` and `YT_REFRESH_TOKEN` for this channel,
then set the variable `AUTO_UPLOAD = true`. API uploads stay private until the YouTube API audit is approved.

## Local test

```bash
pip install -r requirements.txt
python -m stick.batch --count 1 --mock     # canned script + placeholder voice, no API needed
```

## Tuning

| What | Where |
|---|---|
| Topic areas | `AREAS` in `stick/writer.py` |
| Poses | `POSES` in `stick/rig.py` (angles are screen-relative, 0° = down) |
| Props / emotes | `stick/props.py`. Add a drawer function and it is automatically available to the script writer |
| Look (background, scale, layout) | constants at the top of `stick/render.py` |
| Voice | env `KOKORO_VOICE` (default `am_michael`) |
