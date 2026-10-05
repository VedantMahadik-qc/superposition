"""Tiny numpy synth: render each MIDI track to its own stereo stem.

pad    - three detuned saws through a low-pass, slow swell
bass   - sine + soft saturation, plucked envelope
arp    - FM pluck (bright, short)
melody - FM bell / celesta (ratio 3.5, long decay)
"""
from pathlib import Path

import mido
import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100


def midi_notes(path):
    """Return {track_name: [(start_s, dur_s, pitch, velocity)]} using the file's tempo map."""
    mid = mido.MidiFile(path)
    tempo_map = []  # (tick, tempo)
    for tr in mid.tracks:
        t = 0
        for m in tr:
            t += m.time
            if m.type == "set_tempo":
                tempo_map.append((t, m.tempo))
    tempo_map = sorted(tempo_map) or [(0, 500000)]

    def tick2s(tick):
        s, last_t, last_tempo = 0.0, 0, tempo_map[0][1]
        for tt, tempo in tempo_map:
            if tt > tick:
                break
            s += mido.tick2second(tt - last_t, mid.ticks_per_beat, last_tempo)
            last_t, last_tempo = tt, tempo
        return s + mido.tick2second(tick - last_t, mid.ticks_per_beat, last_tempo)

    out = {}
    for i, tr in enumerate(mid.tracks):
        name = next((m.name for m in tr if m.type == "track_name"), f"track{i}")
        t, on, notes = 0, {}, []
        for m in tr:
            t += m.time
            if m.type == "note_on" and m.velocity > 0:
                on.setdefault((m.channel, m.note), []).append((t, m.velocity))
            elif m.type in ("note_off", "note_on"):
                stack = on.get((m.channel, m.note))
                if stack:
                    st, vel = stack.pop(0)
                    s0 = tick2s(st)
                    notes.append((s0, tick2s(t) - s0, m.note, vel))
        if notes:
            out[name] = notes
    return out


def hz(p):
    return 440.0 * 2 ** ((p - 69) / 12)


def adsr(n, a, d, s, r, sustain_n):
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    env = np.zeros(n, np.float32)
    k = np.arange(n)
    env = np.where(k < a, k / max(a, 1), env)
    env = np.where((k >= a) & (k < a + d), 1 - (1 - s) * (k - a) / max(d, 1), env)
    env = np.where((k >= a + d) & (k < sustain_n), s, env)
    rel_start_level = s if sustain_n >= a + d else np.interp(sustain_n, [0, a, a + d], [0, 1, s])
    env = np.where(k >= sustain_n, rel_start_level * np.exp(-(k - sustain_n) / max(r / 4, 1)), env)
    return env


def voice(kind, f, dur, vel):
    v = (vel / 127) ** 1.3
    if kind == "pad":
        n = int((dur + 1.6) * SR)
        t = np.arange(n) / SR
        x = sum(2 * ((f * d * t + ph) % 1) - 1 for d, ph in [(1, 0), (1.004, .3), (0.996, .7)]) / 3
        x = sosfilt(butter(2, min(900 + f * 2, 8000), fs=SR, output="sos"), x)
        return x * adsr(n, 0.7, 0.5, 0.8, 1.6, int(dur * SR)) * v * 0.5
    if kind == "bass":
        n = int((dur + 0.4) * SR)
        t = np.arange(n) / SR
        x = np.tanh(1.6 * np.sin(2 * np.pi * f * t)) + 0.3 * np.sin(4 * np.pi * f * t)
        return x * adsr(n, 0.01, 0.3, 0.6, 0.3, int(dur * SR)) * v * 0.55
    if kind == "arp":
        n = int((dur + 0.6) * SR)
        t = np.arange(n) / SR
        idx = 2.5 * np.exp(-t * 14)
        x = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * 2 * f * t))
        return x * np.exp(-t * 5.5) * np.minimum(t / 0.003, 1) * v * 0.32
    if kind == "melody":
        n = int((dur + 2.2) * SR)
        t = np.arange(n) / SR
        idx = 1.8 * np.exp(-t * 3)
        x = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * 3.5 * f * t))
        x += 0.25 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 4)
        env = np.exp(-t * 1.4) * np.minimum(t / 0.004, 1)
        env *= np.where(t > dur, np.exp(-(t - dur) * 3), 1)
        return x * env * v * 0.42
    raise ValueError(kind)


PAN = {"pad": 0.0, "bass": 0.0, "arp": -0.35, "melody": 0.2}


def render_track(kind, notes, total_s):
    buf = np.zeros(int((total_s + 4) * SR), np.float32)
    for s, d, p, vel in notes:
        w = voice(kind, hz(p), max(d, 0.05), vel)
        i = int(s * SR)
        buf[i:i + len(w)] += w[: len(buf) - i]
    pan = PAN[kind]
    return np.stack([buf * np.sqrt((1 - pan) / 2), buf * np.sqrt((1 + pan) / 2)], 1)


def render(path, total_s=None):
    tracks = midi_notes(path)
    total_s = total_s or max(s + d for notes in tracks.values() for s, d, _, _ in notes)
    return {name: render_track(name, notes, total_s) for name, notes in tracks.items() if name in PAN}


def reverb(x, seconds=2.8, wet=0.25, seed=1):
    """Classical convolution reverb (exponentially decaying noise IR) for glue only."""
    from scipy.signal import fftconvolve
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal((n, 2)) * np.exp(-t * 6.9 / seconds)[:, None]
    ir = sosfilt(butter(1, 5000, fs=SR, output="sos"), ir, axis=0)
    ir /= np.sqrt((ir ** 2).sum(0))
    y = np.stack([fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], 1)
    return x * (1 - wet) + y * wet



def save(path, x):
    from scipy.io import wavfile
    peak = np.abs(x).max() or 1
    wavfile.write(str(path), SR, (np.clip(x / peak * 0.89, -1, 1) * 32767).astype(np.int16))
    return Path(path)
