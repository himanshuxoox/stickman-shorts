"""Thin wrappers around the Gemini API (free tier): text + text-to-speech."""
import base64, io, json, os, re, time, wave

import numpy as np

TEXT_MODELS = [m for m in os.environ.get(
    "GEMINI_MODEL", "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.8-flash").split(",") if m]
TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-lite-tts")
TTS_VOICE = os.environ.get("GEMINI_TTS_VOICE", "Charon")

_client = None


def client():
    global _client
    if _client is None:
        from google import genai
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=key)
    return _client


def _call_text(model, prompt):
    c = client()
    try:  # current Interactions API
        it = c.interactions.create(model=model, input=prompt)
        return it.output_text
    except AttributeError:
        pass
    r = c.models.generate_content(model=model, contents=prompt)  # older SDKs
    return r.text


def ask(prompt, retries=3):
    """Ask the first text model that works. Retries on rate limits."""
    last = None
    for model in TEXT_MODELS:
        for attempt in range(retries):
            try:
                out = _call_text(model, prompt)
                if out and out.strip():
                    return out
            except Exception as e:  # 429s, model-not-found, etc.
                last = e
                msg = str(e)
                if "404" in msg or "not found" in msg.lower():
                    break  # try next model
                time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"Gemini text failed on all models: {last}")


def ask_json(prompt):
    """Ask and parse a JSON object out of the reply."""
    for _ in range(2):
        txt = ask(prompt + "\n\nReturn ONLY valid JSON. No markdown, no commentary.")
        m = re.search(r"\{.*\}", txt, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise RuntimeError("Gemini did not return valid JSON")


def tts(text, sr_out=24000):
    """Gemini TTS -> float32 mono numpy array at 24 kHz."""
    c = client()
    it = c.interactions.create(
        model=TTS_MODEL,
        input=[{"type": "user_input", "content": [{"type": "text", "text": text}]}],
        response_format={"type": "audio"},
        generation_config={"speech_config": [{"voice": TTS_VOICE}]},
    )
    a = it.output_audio
    raw = a.data if isinstance(a.data, (bytes, bytearray)) else base64.b64decode(a.data)
    if raw[:4] == b"RIFF":
        with wave.open(io.BytesIO(raw)) as w:
            sr = w.getframerate()
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    else:  # headerless L16
        sr = a.sample_rate or 24000
        pcm = np.frombuffer(raw, dtype=np.int16)
    x = pcm.astype(np.float32) / 32768.0
    if sr != sr_out:
        idx = np.linspace(0, len(x) - 1, int(len(x) * sr_out / sr))
        x = np.interp(idx, np.arange(len(x)), x).astype(np.float32)
    return x
