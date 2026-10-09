"""Synthesized fight audio: an original driving music track + hit / whoosh / beam / boom SFX.
Everything is generated with numpy, so there is nothing copyrighted in it."""
import wave

import numpy as np

SR = 32000


def _env(n, attack=0.002, decay=8.0):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t * decay)


def _noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def _lowpass(x, k):
    k = max(1, int(k))
    return np.convolve(x, np.ones(k) / k, mode="same")


def kick(vol=0.9):
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 120 * np.exp(-t * 18) + 42
    return vol * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)


def snare(vol=0.45, seed=1):
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return vol * (0.6 * _noise(n, seed) * np.exp(-t * 22) + 0.5 * body)


def hat(vol=0.12, seed=2):
    n = int(0.05 * SR)
    x = _noise(n, seed)
    x = x - _lowpass(x, 4)
    return vol * x * _env(n, 0.001, 60)


def tone(freq, dur, vol=0.2, wave_="saw", decay=3.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    ph = (freq * t) % 1.0
    if wave_ == "saw":
        w = 2 * ph - 1
    elif wave_ == "square":
        w = np.sign(np.sin(2 * np.pi * freq * t))
    else:
        w = np.sin(2 * np.pi * freq * t)
    return vol * w * _env(n, 0.004, decay)


def note(name):
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    pitch, octv = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((12 * (octv + 1) + names[pitch] - 69) / 12)


# --------------------------------------------------------------------- SFX
def sfx(kind, seed=0):
    if kind == "punch":
        n = int(0.18 * SR); t = np.arange(n) / SR
        thump = np.sin(2 * np.pi * (140 * np.exp(-t * 25) + 55) * t) * np.exp(-t * 18)
        return 0.9 * thump + 0.45 * _noise(n, seed) * np.exp(-t * 60)
    if kind == "heavy":
        n = int(0.45 * SR); t = np.arange(n) / SR
        thump = np.sin(2 * np.pi * np.cumsum(100 * np.exp(-t * 12) + 38) / SR) * np.exp(-t * 7)
        return 1.0 * thump + 0.55 * _lowpass(_noise(n, seed), 3) * np.exp(-t * 25)
    if kind == "whoosh":
        n = int(0.3 * SR); t = np.arange(n) / SR
        x = _noise(n, seed)
        x = _lowpass(x, 6) - _lowpass(x, 30)
        return 0.7 * x * np.sin(np.pi * t / (n / SR)) ** 2
    if kind == "block":
        n = int(0.3 * SR); t = np.arange(n) / SR
        ring = sum(np.sin(2 * np.pi * f * t) for f in (1450, 2210, 3170)) / 3
        return 0.45 * ring * np.exp(-t * 14) + 0.3 * _noise(n, seed) * np.exp(-t * 80)
    if kind == "charge":
        n = int(1.3 * SR); t = np.arange(n) / SR
        f = 70 + 260 * (t / t[-1]) ** 2
        w = 2 * ((np.cumsum(f) / SR) % 1) - 1
        return 0.25 * w * np.minimum(1, t * 3) + 0.08 * _noise(n, seed) * (t / t[-1])
    if kind == "beam":
        n = int(2.8 * SR); t = np.arange(n) / SR
        f = 95 * (1 + 0.03 * np.sin(2 * np.pi * 7 * t))
        w = 2 * ((np.cumsum(f) / SR) % 1) - 1
        w2 = 2 * ((np.cumsum(f * 1.5) / SR) % 1) - 1
        return (0.3 * w + 0.15 * w2) * np.minimum(1, t * 8) * np.minimum(1, (t[-1] - t) * 4) \
            + 0.12 * _lowpass(_noise(n, seed), 2)
    if kind == "boom":
        n = int(1.6 * SR); t = np.arange(n) / SR
        sub = np.sin(2 * np.pi * np.cumsum(70 * np.exp(-t * 3) + 28) / SR) * np.exp(-t * 2.5)
        return 1.0 * sub + 0.8 * _lowpass(_noise(n, seed), 8) * np.exp(-t * 3.5)
    if kind == "crack":
        n = int(0.4 * SR); t = np.arange(n) / SR
        return 0.8 * _noise(n, seed) * np.exp(-t * 18) * (1 + np.sign(np.sin(2 * np.pi * 30 * t))) / 2
    if kind == "teleport":
        n = int(0.25 * SR); t = np.arange(n) / SR
        f = 1800 * np.exp(-t * 9) + 300
        return 0.25 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    if kind == "ko":
        n = int(2.2 * SR); t = np.arange(n) / SR
        return 0.9 * np.sin(2 * np.pi * np.cumsum(55 * np.exp(-t * 0.8) + 20) / SR) * np.exp(-t * 1.6)
    if kind == "rise":
        n = int(1.5 * SR); t = np.arange(n) / SR
        f = 120 * 2 ** (3 * t / t[-1])
        w = 2 * ((np.cumsum(f) / SR) % 1) - 1
        return 0.3 * w * (t / t[-1]) ** 1.5
    return np.zeros(10)


# --------------------------------------------------------------------- music
PROGRESSIONS = [
    ["A2", "F2", "C3", "G2"], ["E2", "C3", "D3", "B2"], ["D2", "A#2", "F2", "C3"], ["C2", "G#2", "D#2", "A#2"],
]


def music(total, sections, seed=0, bpm=None):
    """sections: list of (t0, t1, intensity 0..3). 0 = silence/drone, 3 = full."""
    rng = np.random.default_rng(seed)
    bpm = bpm or int(rng.choice([132, 140, 150]))
    beat = 60.0 / bpm
    prog = PROGRESSIONS[int(rng.integers(0, len(PROGRESSIONS)))]
    out = np.zeros(int((total + 2) * SR))
    k_, s_, h_ = kick(), snare(seed=seed), hat(seed=seed)
    lead_pat = rng.integers(0, 5, 16)

    def inten(t):
        for a, b, v in sections:
            if a <= t < b:
                return v
        return 3

    def add(x, t):
        i = int(t * SR)
        if 0 <= i < len(out):
            out[i:i + len(x)] += x[: len(out) - i]

    nbeats = int(total / beat) + 1
    for b in range(nbeats):
        t = b * beat
        lvl = inten(t)
        root = note(prog[(b // 8) % len(prog)])
        if lvl >= 1:
            for e in range(2):                      # driving 8th-note bass
                add(tone(root, beat / 2 * 0.95, 0.22, "saw", 6), t + e * beat / 2)
        if lvl >= 2:
            add(k_, t)
            if b % 2 == 1:
                add(s_, t)
            for e in range(2):
                add(h_, t + e * beat / 2)
        if lvl >= 3:
            step = b % 16
            if lead_pat[step] in (0, 1, 2):
                semis = [0, 3, 7, 10, 12][int(lead_pat[step])]
                add(tone(root * 4 * 2 ** (semis / 12), beat * 0.9, 0.1, "square", 5), t)
        if lvl == 0 and b % 4 == 0:
            add(tone(root / 2, beat * 4, 0.12, "sine", 0.6), t)  # tension drone
    return out


def mix(total, events, sections, path, seed=0):
    """events: list of (t, kind). Writes a 16-bit mono wav."""
    m = music(total, sections, seed) * 0.55
    fx = np.zeros_like(m)
    for i, (t, kind) in enumerate(events):
        x = sfx(kind, seed + i)
        j = int(t * SR)
        if 0 <= j < len(fx):
            fx[j:j + len(x)] += x[: len(fx) - j]
    y = m + 0.8 * fx
    y = y[: int(total * SR)]
    y = np.tanh(y * 1.1)                       # soft limiter
    y = y / max(1e-9, np.abs(y).max()) * 0.9
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((y * 32767).astype(np.int16).tobytes())
