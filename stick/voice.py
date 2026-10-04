"""Narration: Kokoro (free, open-source, runs on CPU) with Gemini TTS as fallback."""
import os

import numpy as np

SR = 24000
ENGINE = os.environ.get("TTS_ENGINE", "kokoro")          # kokoro | gemini | mock
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "am_michael")
SPEED = float(os.environ.get("TTS_SPEED", "1.08"))

_pipe = None


def _kokoro(text):
    global _pipe
    if _pipe is None:
        from kokoro import KPipeline
        _pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    parts = []
    for _gs, _ps, audio in _pipe(text, voice=KOKORO_VOICE, speed=SPEED):
        a = audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio)
        parts.append(a.astype(np.float32))
    return np.concatenate(parts) if parts else np.zeros(SR // 2, np.float32)


def _mock(text):
    """Offline stand-in: a soft 'babble' whose length matches real speech pace."""
    dur = max(1.0, len(text.split()) / 2.7)
    t = np.arange(int(SR * dur)) / SR
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 3.2 * t) ** 2
    return (0.08 * env * np.sin(2 * np.pi * 180 * t)).astype(np.float32)


def speak(text):
    """Returns float32 mono audio at 24 kHz, trimmed of long silences at the ends."""
    order = {"kokoro": ["kokoro", "gemini"], "gemini": ["gemini", "kokoro"], "mock": ["mock"]}[ENGINE]
    last = None
    for eng in order:
        try:
            if eng == "kokoro":
                a = _kokoro(text)
            elif eng == "gemini":
                from . import llm
                a = llm.tts(text, SR)
            else:
                a = _mock(text)
            return _trim(a)
        except Exception as e:
            last = e
            print(f"   TTS engine {eng} failed: {e}")
    raise RuntimeError(f"All TTS engines failed: {last}")


def _trim(a, thr=0.01):
    idx = np.where(np.abs(a) > thr)[0]
    if len(idx) == 0:
        return a
    s, e = max(0, idx[0] - int(0.03 * SR)), min(len(a), idx[-1] + int(0.08 * SR))
    return a[s:e]
