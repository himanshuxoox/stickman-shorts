"""Psychology & life-lessons scripts (Gemini), constrained to what the renderer can draw."""
import json, random

from . import llm
from .props import EMOTE_NAMES, PROP_NAMES, ACCENTS
from .rig import POSE_NAMES

AREAS = [
    "procrastination", "habits", "motivation", "dopamine and rewards", "focus and attention",
    "cognitive biases", "decision making", "social psychology", "confidence", "first impressions",
    "memory and learning", "money psychology", "happiness research", "stress", "sleep and the brain",
    "stoic life lessons", "friendship and loneliness", "persuasion (how to spot it)",
    "how to spot manipulation tactics (to protect yourself)", "self-discipline", "comparison and social media",
]

STYLE = f"""You write scripts for "stickman explainer" YouTube Shorts about psychology and life lessons.
A minimalist black stick figure acts out every line on a white background. Audience: adults and
teens worldwide. Tone: smart, punchy, a little witty, never preachy.

STRUCTURE — exactly 6 scenes following this retention arc:
  1. hook    — a counter-intuitive claim or question, under 12 words, written as a bold "you" statement.
               No "Did you know", no greetings, never start with "Research" or "Studies".
  2. disrupt — what most people believe, then break it in one line.
  3. secret  — the hidden mechanism (part 1).
  4. secret  — the hidden mechanism (part 2) or a relatable example.
  5. truth   — the "aha" payoff that explains everything.
  6. elevate — one practical, punchy takeaway the viewer can use today.
Then "outro": a debate-style question for the comments.
Total narration 110-140 words. Short sentences. Spoken English.

ACCURACY — psychology is full of myths. Only use well-replicated, mainstream findings. Do NOT use:
the "10% of the brain" myth, left-brain/right-brain personalities, "21 days to form a habit",
learning styles, the Stanford prison experiment as proof, power posing, ego depletion as settled
fact, or made-up statistics. No diagnoses, no therapy or medical advice. If in doubt, phrase it as
"research suggests" — but use that phrase at most ONCE per script. Manipulation topics must be framed as how to RECOGNISE and PROTECT yourself.

VISUALS — for every scene choose ONLY from these lists (exact spelling):
- "pose": {", ".join(p for p in POSE_NAMES if p not in ("walk", "run"))}
- "move": none, walk_in, walk_across, run_across, jump   (use sparingly, mostly "none")
- "props": 0-2 items, each {{"name": one of [{", ".join(PROP_NAMES)}],
           "at": one of [hand, above, left, right, center]}}  ("hand" = held in the right hand)
- "emote": one of [{", ".join(EMOTE_NAMES)}] or null — appears next to the head
- "other": null, or a second (gray) character standing on the RIGHT: {{"pose": "...", "label": "1-2 words like BOSS, FRIEND, YOUR BRAIN"}}.
  Poses are screen-relative: the other character points at the main one with "point_left";
  the main character points at the other with "point_right". Use "other" in at most 2 scenes.
- "keyword": 1-3 words shown big on screen (the key idea of the line, not a repeat of the caption)
- "accent": one of [{", ".join(ACCENTS)}] — vary it between scenes
Pick poses and props that literally act out the sentence. Make it visually busy: props in at
least 4 of the 6 scenes, the second character in 1-2 scenes, and a different pose in every scene."""

SCHEMA = """JSON shape:
{"title": "curiosity-driven YouTube title, max 70 chars, accurate, no hashtags",
 "scenes": [{"stage": "hook", "narration": "...", "pose": "...", "move": "none",
             "props": [{"name": "...", "at": "..."}], "emote": null, "other": null,
             "keyword": "...", "accent": "..."}],
 "outro": "question, max 12 words",
 "description": "2-3 sentence YouTube description",
 "tags": ["8-12 lowercase tags"]}"""


def pick_topic(history, rng):
    area = rng.choice(AREAS)
    recent = [v["topic"] for v in history[-120:]]
    q = (f"Suggest one specific, surprising, evidence-based psychology or life-lesson idea about "
         f"'{area}' for a 50-second stickman Short. It should make viewers think 'that's so me'. "
         f"Avoid these recent topics: {json.dumps(recent)}.\n"
         f"Reply as JSON: {{\"topic\": \"short topic name\", \"angle\": \"one-line hook idea\"}}")
    return llm.ask_json(q)


def sanitize(script):
    """Force every field into the renderer's vocabulary so nothing can crash or look broken."""
    poses = set(POSE_NAMES) - {"walk", "run"}
    scenes = []
    for sc in script.get("scenes", [])[:7]:
        if not sc.get("narration"):
            continue
        p = sc.get("pose") if sc.get("pose") in poses else "explain"
        props = [dict(name=x.get("name"), at=x.get("at") if x.get("at") in ("hand", "above", "left", "right", "center") else "right")
                 for x in (sc.get("props") or []) if isinstance(x, dict) and x.get("name") in PROP_NAMES][:2]
        other = sc.get("other")
        if isinstance(other, dict):
            other = dict(pose=other.get("pose") if other.get("pose") in poses else "stand",
                         label=str(other.get("label") or "")[:16])
        else:
            other = None
        scenes.append(dict(
            stage=sc.get("stage", ""), narration=sc["narration"].strip(), pose=p,
            move=sc.get("move") if sc.get("move") in ("none", "walk_in", "walk_across", "run_across", "jump") else "none",
            props=props, emote=sc.get("emote") if sc.get("emote") in EMOTE_NAMES else None,
            other=other, keyword=str(sc.get("keyword") or "")[:28],
            accent=sc.get("accent") if sc.get("accent") in ACCENTS else random.choice(list(ACCENTS))))
    if scenes and scenes[0]["move"] == "none":
        scenes[0]["move"] = "walk_in"
    script["scenes"] = scenes
    return script


def _words(s):
    return sum(len(sc.get("narration", "").split()) for sc in s.get("scenes", []))


def write(history, rng):
    idea = pick_topic(history, rng)
    script = llm.ask_json(f"{STYLE}\n\nTopic: {idea['topic']}. Angle: {idea.get('angle', '')}\n\n{SCHEMA}")
    if _words(script) < 100:
        try:
            longer = llm.ask_json(f"Expand this script to 115-135 words total with concrete, accurate "
                                  f"detail. Keep the same JSON shape, 6 scenes and visual vocabulary.\n\n"
                                  f"{json.dumps(script, ensure_ascii=False)}")
            if longer.get("scenes") and _words(longer) > _words(script):
                script = longer
        except Exception:
            pass
    script = fact_check(script)
    script = sanitize(script)
    script["topic"] = idea["topic"]
    return script


def fact_check(script):
    q = ("You are a strict fact-checker for psychology content. Check every claim in this script. "
         "Rewrite any line that is a myth, overstated, not replicated, or presented as more certain "
         "than the evidence. Remove made-up numbers. Hedge with 'research suggests' at most ONCE in the "
         "whole script and NEVER in the first scene — keep the hook bold (a true claim can be punchy). "
         "Keep total narration 110-140 words, the energy, and ALL visual fields unchanged. Return the SAME JSON plus "
         "\"confidence\": \"high\" | \"medium\" | \"low\".\n\n" + json.dumps(script, ensure_ascii=False))
    try:
        checked = llm.ask_json(q)
        if checked.get("scenes"):
            return checked
    except Exception:
        pass
    script["confidence"] = "medium"
    return script
