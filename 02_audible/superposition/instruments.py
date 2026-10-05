"""Numpy voices for 'Superposition' (reuses MIDI parsing + reverb from ../synth.py).

strings - spiccato: three detuned saws, short bowed envelope
brass   - braam: detuned saws, dark-to-bright as it swells, harder attack on loud notes
lead    - supersaw: seven detuned saws, band-limited
bass    - sub: sine + saturated octave
drums   - by pitch: 36 kick, 38 snare, 42 hat, 45 tom, 49 crash
riser(), impact() - audio-only FX added in mix.py
"""
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

sys.path.append(str(Path(__file__).resolve().parents[1]))
from synth import SR, hz, midi_notes, reverb, save  # noqa: E402,F401

RNG = np.random.default_rng(3)
NOISE = RNG.standard_normal(SR * 4)


def saw(f, t, ph=0.0):
    return 2 * ((f * t + ph) % 1) - 1


def lp(x, fc, order=2):
    return sosfilt(butter(order, min(fc, SR / 2 - 100), fs=SR, output="sos"), x, axis=0)


def hp(x, fc, order=2):
    return sosfilt(butter(order, fc, "highpass", fs=SR, output="sos"), x, axis=0)


def noise(n, seed):
    i = (seed * 7919) % (len(NOISE) - n) if n < len(NOISE) else 0
    return NOISE[i:i + n] if n < len(NOISE) else RNG.standard_normal(n)


def drum(p, vel):
    v = (vel / 127) ** 1.2
    if p == 36:   # kick: pitch-dropping sine + click
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        f = 48 + 110 * np.exp(-t * 28)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5.5)
        x += lp(noise(n, 1), 3000) * np.exp(-t * 200) * 0.4
        return np.tanh(2.2 * x) * v
    if p == 38:   # snare: tone + bright noise
        n = int(0.35 * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25) * 0.6
        x += hp(noise(n, 2), 1200) * np.exp(-t * 14) * 0.8
        return np.tanh(1.5 * x) * v * 0.8
    if p == 42:   # hat: short high noise tick
        n = int(0.06 * SR)
        t = np.arange(n) / SR
        return hp(noise(n, 3), 7000, 4) * np.exp(-t * 70) * v * 0.35
    if p == 45:   # tom: low ringing hit
        n = int(0.7 * SR)
        t = np.arange(n) / SR
        f = 85 + 60 * np.exp(-t * 18)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6)
        x += lp(noise(n, 4), 1200) * np.exp(-t * 40) * 0.5
        return np.tanh(1.8 * x) * v * 0.9
    if p == 49:   # crash: long washy noise
        n = int(2.5 * SR)
        t = np.arange(n) / SR
        return hp(noise(n, 5), 4000) * np.exp(-t * 1.6) * v * 0.3
    return np.zeros(1)


def voice(kind, f, dur, vel):
    v = (vel / 127) ** 1.4
    if kind == "strings":
        n = int((dur + 0.25) * SR)
        t = np.arange(n) / SR
        x = sum(saw(f * c, t, ph) for c, ph in [(1, 0), (1.004, .4), (0.996, .8)]) / 3
        x = lp(x, 2200 + 2 * f)
        env = np.minimum(t / 0.004, 1) * np.exp(-t * (12 if dur < 0.3 else 1.2))
        env *= np.where(t > dur, np.exp(-(t - dur) * 8), 1)
        return x * env * v * 0.42
    if kind == "brass":
        n = int((dur + 1.2) * SR)
        t = np.arange(n) / SR
        x = sum(saw(f * c, t, ph) for c, ph in [(1, 0), (1.003, .3), (0.997, .6), (2.002, .1)]) / 3.5
        attack = 0.04 if vel > 100 else 0.9
        env = np.minimum(t / attack, 1) ** 1.5 * np.where(t > dur, np.exp(-(t - dur) * 3), 1)
        bright = np.clip(env * v * np.exp(-t * 0.6), 0, 1)
        x = lp(x, 300) * (1 - bright) + lp(x, 300 + 3500 * v) * bright
        return np.tanh(1.6 * x) * env * v * 0.55
    if kind == "lead":
        n = int((dur + 0.4) * SR)
        t = np.arange(n) / SR
        x = sum(saw(f * (1 + d), t, k / 7) for k, d in enumerate([-.012, -.007, -.003, 0, .003, .007, .012])) / 5
        x = lp(x, 5000, 3)
        env = np.minimum(t / 0.01, 1) * (0.75 + 0.25 * np.exp(-t * 4)) * np.where(t > dur, np.exp(-(t - dur) * 12), 1)
        return x * env * v * 0.38
    if kind == "bass":
        n = int((dur + 0.15) * SR)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * f * t) + 0.35 * np.tanh(3 * np.sin(4 * np.pi * f * t))
        env = np.minimum(t / 0.005, 1) * np.where(t > dur, np.exp(-(t - dur) * 30), 1)
        return x * env * v * 0.6
    raise ValueError(kind)


PAN = {"brass": 0.0, "drums": 0.0, "strings": -0.25, "lead": 0.2, "bass": 0.0}


def render_track(kind, notes, total_s):
    buf = np.zeros(int((total_s + 4) * SR), np.float32)
    for s, d, p, vel in notes:
        w = drum(p, vel) if kind == "drums" else voice(kind, hz(p), max(d, 0.05), vel)
        i = int(s * SR)
        buf[i:i + len(w)] += w[: len(buf) - i]
    pan = PAN[kind]
    return np.stack([buf * np.sqrt((1 - pan) / 2), buf * np.sqrt((1 + pan) / 2)], 1)


def render(path, total_s=None):
    tracks = midi_notes(path)
    total_s = total_s or max(s + d for notes in tracks.values() for s, d, _, _ in notes)
    return {name: render_track(name, notes, total_s) for name, notes in tracks.items() if name in PAN}


def riser(seconds):
    """Noise sweep whose band climbs 200 Hz -> 8 kHz, plus a rising sine, getting louder."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    u = t / seconds
    x = np.zeros(n)
    blocks = 64
    src = RNG.standard_normal(n)
    for b in range(blocks):   # piecewise band-pass sweep
        a, z = b * n // blocks, (b + 1) * n // blocks
        fc = 200 * 40 ** (b / blocks)
        sos = butter(2, [fc * 0.7, min(fc * 1.4, SR / 2 - 100)], "bandpass", fs=SR, output="sos")
        x[a:z] = sosfilt(sos, src[max(0, a - 2000):z])[-(z - a):]
    tone = np.sin(2 * np.pi * np.cumsum(110 * 8 ** u) / SR) * 0.25
    y = (x / np.abs(x).max() + tone) * u ** 2
    return np.stack([y, np.roll(y, 300)], 1)


def impact(seconds=4.0, seed=11):
    """Downbeat hit: noise crack, sub drop 80 -> 30 Hz, short rumble."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    crack = lp(rng.standard_normal((n, 2)), 7000) * np.exp(-t * 20)[:, None] * 0.6
    sub = np.sin(2 * np.pi * np.cumsum(30 + 50 * np.exp(-t * 3)) / SR) * np.exp(-t * 0.9)
    rumble = lp(rng.standard_normal((n, 2)), 180, 4) * (np.exp(-t * 1.2) * 2.5)[:, None]
    return np.tanh((crack + sub[:, None] * 0.9 + rumble) * 1.3)
