"""Poster art + demo video for 'Superposition', drawn from the real MIDI and audio.

  python make_media.py poster   -> poster_4x3.png (1600x1200)
  python make_media.py video    -> superposition_demo.mp4 (1920x1080, 30 fps, ~2 min)

The piano roll is the repaired MIDI that was rendered: source notes in cool colours,
notes chosen by Blur Jazz (blur-midi-v1) in hot pink with opacity = velocity, and the
Retrocausal Echo return drawn as a teal band under the roll.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy.io import wavfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent))
from compose import BAR, BREAK, BUILD2, DROP1, DROP2, END, GAP, tick2s  # noqa: E402
from synth import midi_notes  # noqa: E402

FONTS = Path("C:/Windows/Fonts")
F = lambda name, size: ImageFont.truetype(str(FONTS / name), size)  # noqa: E731
BOLD, REG, LIGHT, MONO = "segoeuib.ttf", "segoeui.ttf", "segoeuil.ttf", "consola.ttf"

BG = (9, 9, 18)
INK = (236, 236, 244)
DIM = (140, 140, 165)
COL = {"strings": (90, 169, 230), "lead": (235, 235, 255), "brass": (127, 90, 240),
       "bass": (44, 182, 125), "drums": (110, 110, 130)}
QUANTUM = (255, 64, 129)
ECHO = (0, 210, 200)
T = lambda bar: tick2s(int(bar * BAR))  # noqa: E731
USE = [(T(DROP1 + 4), T(BREAK)), (T(DROP2), T(END))]
MIDI = ROOT / "midi" / "superposition_hype_fixed.mid"
MIX = ROOT / "submission" / "superposition.wav"
DRY = ROOT / "output" / "superposition_source_dry.wav"
ECHO_WAV = ROOT / "stems" / "hype_echo_return.wav"


def quantum(kind, s):
    return kind in ("strings", "lead") and any(a <= s < b for a, b in USE)


def roll(width, height, pps, t0=0.0, lo=26, hi=96, glow=True):
    """Piano roll of the whole track as an RGB image; x = (t - t0) * pps."""
    img = Image.new("RGB", (width, height), BG)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lane = height / (hi - lo)
    notes = midi_notes(MIDI)
    for kind in ("bass", "brass", "strings", "lead"):
        for s, dur, p, v in notes.get(kind, []):
            x0, x1 = (s - t0) * pps, (s - t0 + max(dur, 0.06)) * pps
            if x1 < 0 or x0 > width:
                continue
            y = height - (p - lo) * lane
            q = quantum(kind, s)
            c = QUANTUM if q else COL[kind]
            a = int(60 + 195 * (v / 127)) if q else int((70 + 160 * v / 127) if kind in ("lead", "strings") else 150)
            d.rectangle([x0, y - lane * 0.85, max(x0 + 1, x1 - 1), y], fill=c + (a,))
    for s, dur, p, v in notes.get("drums", []):
        x = (s - t0) * pps
        if 0 <= x <= width and p in (36, 38):
            h = height * (0.06 if p == 36 else 0.035) * v / 127
            d.rectangle([x, height - h, x + 2, height], fill=COL["drums"] + (180,))
    if glow:
        img.paste(layer.filter(ImageFilter.GaussianBlur(6)), (0, 0), layer.filter(ImageFilter.GaussianBlur(6)))
    img.paste(layer, (0, 0), layer)
    return img


def echo_envelope(fps):
    """Per-frame level of the echo return as it sits in the mix (same automation as mix.py)."""
    sr, e = wavfile.read(ECHO_WAV)
    e = np.abs(e.astype(np.float32)).mean(1) if e.ndim == 2 else np.abs(e.astype(np.float32))
    hop = sr // fps
    lvl = np.array([e[i:i + hop].mean() for i in range(0, len(e) - hop, hop)])
    t = np.arange(len(lvl)) / fps
    pts = [(0, 0), (T(DROP1), 0.25), (T(BREAK) - 0.5, 0.3), (T(BREAK) + 0.5, 1.0), (T(BUILD2), 0.9),
           (T(BUILD2 + 2), 0.35), (T(DROP2), 0.55), (T(END), 0.6), (T(END) + 1, 1.0), (1e9, 1.0)]
    lvl = lvl * np.interp(t, *zip(*pts))
    gap = (t >= tick2s(GAP[0])) & (t < tick2s(GAP[1]))
    lvl[gap] = 0
    return lvl / (lvl.max() + 1e-9)


def text(d, xy, s, font, fill=INK, anchor="la"):
    d.text(xy, s, font=font, fill=fill, anchor=anchor)


# ---------------------------------------------------------------- poster
def poster():
    W, H = 1600, 1200
    total = 66.0
    img = roll(W, 760, W / total, t0=0, glow=True)
    canvas = Image.new("RGB", (W, H), BG)
    canvas.paste(img, (0, 300))
    d = ImageDraw.Draw(canvas)
    for name, b in [("DROP 1", DROP1), ("BREAK", BREAK), ("FINAL DROP", DROP2)]:
        x = T(b) * W / total
        d.line([x, 300, x, 1060], fill=(60, 60, 85), width=1)
        text(d, (x + 8, 312), name, F(MONO, 22), DIM)
    text(d, (70, 70), "SUPERPOSITION", F(BOLD, 128))
    text(d, (76, 222), "a hype track whose drops are quantum", F(LIGHT, 44), DIM)
    text(d, (70, 1095), "Blur Jazz  ·  Retrocausal Echo  ·  Moth Atlas", F(REG, 36))
    text(d, (W - 70, 1100), "Moth_Hack 2026 · Challenge 02", F(MONO, 26), DIM, anchor="ra")
    lx = W - 70 - 470
    for lab, c in [("source", COL["strings"]), ("quantum (Blur Jazz)", QUANTUM)]:
        d.rectangle([lx, 247, lx + 24, 265], fill=c)
        text(d, (lx + 36, 238), lab, F(REG, 30), DIM)
        lx += 36 + int(d.textlength(lab, font=F(REG, 30))) + 40
    out = HERE / "poster_4x3.png"
    canvas.save(out)
    print("wrote", out)


# ---------------------------------------------------------------- video
W, H, FPS = 1920, 1080, 30


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def fade(frame, a):
    return Image.blend(Image.new("RGB", frame.size, BG), frame, max(0.0, min(1.0, a)))


def card_title(t, dur):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    a = ease(t / 1.2) * ease((dur - t) / 0.8)
    c = tuple(int(BG[i] + (INK[i] - BG[i]) * a) for i in range(3))
    cd = tuple(int(BG[i] + (DIM[i] - BG[i]) * a) for i in range(3))
    text(d, (W // 2, 400), "SUPERPOSITION", F(BOLD, 150), c, "mm")
    text(d, (W // 2, 530), "a hype track whose drops are quantum", F(LIGHT, 52), cd, "mm")
    if t > 2.5:
        b = ease((t - 2.5) / 1.0) * ease((dur - t) / 0.8)
        cb = tuple(int(BG[i] + (DIM[i] - BG[i]) * b) for i in range(3))
        text(d, (W // 2, 700), "Moth_Hack 2026  ·  Challenge 02: Make it audible", F(MONO, 34), cb, "mm")
    return im


STEPS = [
    ("1", "Compose", "Original 40-bar trailer track written as MIDI in Python.\nStrings, brass, supersaw lead, sub bass, drums."),
    ("2", "Blur Jazz", "blur-midi-v1 on Moth Atlas scrambles the strings + hook\nin both drops: 306 notes in, 2,830 quantum notes out."),
    ("3", "Arrange", "Snap to the 16th grid; rescale each step so the strongest\nquantum note gets the original velocity. Pitches untouched."),
    ("4", "Retrocausal Echo", "retrocausal-echo-v1: a delay whose taps are measured\nfrom a 12-site spin chain. Negative taps play reversed."),
    ("5", "Synth + mix", "numpy synthesis, sidechain, risers, impacts, and a\nhalf-bar of true silence before the final drop."),
]


def card_steps(t, dur):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    text(d, (140, 110), "How it was made", F(BOLD, 64))
    for i, (n, head, body) in enumerate(STEPS):
        a = ease((t - 0.6 - i * 1.6) / 0.6)
        if a <= 0:
            continue
        y = 230 + i * 158
        col = QUANTUM if head in ("Blur Jazz", "Retrocausal Echo") else COL["strings"]
        c = tuple(int(BG[k] + (col[k] - BG[k]) * a) for k in range(3))
        ci = tuple(int(BG[k] + (INK[k] - BG[k]) * a) for k in range(3))
        cd = tuple(int(BG[k] + (DIM[k] - BG[k]) * a) for k in range(3))
        d.ellipse([140, y + 6, 196, y + 62], outline=c, width=3)
        text(d, (168, y + 34), n, F(BOLD, 32), c, "mm")
        text(d, (230, y), head, F(BOLD, 40), ci)
        text(d, (720, y + 4), body, F(REG, 30), cd)
    return fade(im, ease((dur - t) / 0.6))


def card_before_after(t, dur, rolls):
    """Same 4 bars (17-20): left = written hook, right = after Blur Jazz. Audio follows the highlight."""
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    text(d, (W // 2, 90), "Bars 17–20: before and after Blur Jazz", F(BOLD, 56), INK, "mm")
    half = dur / 2
    for i, (lab, r) in enumerate(zip(("written hook  (you hear: no quantum)", "after Blur Jazz  (you hear: quantum)"), rolls)):
        x = 80 + i * 900
        on = (t < half) == (i == 0)
        im.paste(r if on else Image.blend(Image.new("RGB", r.size, BG), r, 0.35), (x, 200))
        d.rectangle([x - 2, 198, x + r.width + 2, 200 + r.height + 2], outline=QUANTUM if on and i else (COL["strings"] if on else (50, 50, 70)), width=3)
        text(d, (x, 200 + r.height + 30), lab, F(REG, 34), INK if on else DIM)
        if on:
            seg = (t % half) / half
            px = x + seg * r.width
            d.line([px, 200, px, 200 + r.height], fill=INK, width=3)
    text(d, (W // 2, 1000), "Pink = notes chosen by the quantum blur, opacity = velocity", F(REG, 30), DIM, "mm")
    return fade(im, ease(t / 0.4) * ease((dur - t) / 0.4))


SECTIONS = [(0, "INTRO", "ticking hats · string ostinato"), (T(4), "BUILD", "toms · snare roll · riser"),
            (T(DROP1), "DROP 1", "the hook, played clean"), (T(DROP1 + 4), "QUANTUM", "Blur Jazz collapses the hook"),
            (T(BREAK), "BREAK", "Retrocausal Echo takes over"), (T(BUILD2), "BUILD 2", "140 → 150 BPM"),
            (tick2s(GAP[0]), "", ""), (T(DROP2), "FINAL DROP", "up a tone · quantum all the way"),
            (T(END), "END", "the echo carries it out")]


def playback_frames(big, pps, echo, n):
    rh = big.height
    arr = np.asarray(big)
    px = 560
    for f in range(n):
        ts = f / FPS
        x0 = int(ts * pps) - px + 2000
        crop = Image.fromarray(arr[:, max(0, x0):x0 + W]) if x0 >= 0 else None
        im = Image.new("RGB", (W, H), BG)
        if crop is not None:
            im.paste(crop, (0, 150))
        d = ImageDraw.Draw(im)
        # played region dims slightly, playhead
        d.line([px, 150, px, 150 + rh], fill=INK, width=2)
        # echo band
        y0, y1 = 150 + rh + 24, 150 + rh + 124
        mid = (y0 + y1) / 2
        for xi in range(0, W, 4):
            k = f + int((xi - px) / pps * FPS)
            if 0 <= k < len(echo):
                h = echo[k] * (y1 - y0) / 2
                a = 1.0 if xi <= px else 0.45
                c = tuple(int(BG[i] + (ECHO[i] - BG[i]) * a) for i in range(3))
                d.rectangle([xi, mid - h, xi + 2, mid + h], fill=c)
        text(d, (40, y0 - 4), "Retrocausal Echo return", F(MONO, 22), ECHO)
        # section caption
        cur = max((s for s in SECTIONS if s[0] <= ts), key=lambda s: s[0])
        if cur[1]:
            age = ts - cur[0]
            a = ease(age / 0.4)
            hot = cur[1] in ("QUANTUM", "FINAL DROP")
            col = QUANTUM if hot else (ECHO if cur[1] == "BREAK" else INK)
            c = tuple(int(BG[i] + (col[i] - BG[i]) * a) for i in range(3))
            cd = tuple(int(BG[i] + (DIM[i] - BG[i]) * a) for i in range(3))
            text(d, (60, 58), cur[1], F(BOLD, 56), c)
            text(d, (60 + d.textlength(cur[1], font=F(BOLD, 56)) + 30, 76), cur[2], F(LIGHT, 38), cd)
        text(d, (W - 60, 70), f"{int(ts // 60)}:{ts % 60:04.1f}", F(MONO, 34), DIM, "ra")
        text(d, (W - 60, 1040), "SUPERPOSITION · Moth_Hack 2026", F(MONO, 24), (70, 70, 95), "ra")
        lx = 60
        for lab, c in (("source", COL["strings"]), ("quantum (Blur Jazz)", QUANTUM)):
            d.rectangle([lx, 1030, lx + 18, 1046], fill=c)
            text(d, (lx + 28, 1024), lab, F(REG, 24), DIM)
            lx += 60 + int(d.textlength(lab, font=F(REG, 24)))
        if f < 12:
            im = fade(im, f / 12)
        yield im


def card_outro(t, dur):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    a = ease(t / 0.8) * ease((dur - t) / 1.2)
    col = lambda c: tuple(int(BG[i] + (c[i] - BG[i]) * a) for i in range(3))  # noqa: E731
    text(d, (W // 2, 360), "SUPERPOSITION", F(BOLD, 120), col(INK), "mm")
    text(d, (W // 2, 500), "Blur Jazz (blur-midi-v1)  ·  Retrocausal Echo (retrocausal-echo-v1)", F(REG, 40), col(QUANTUM), "mm")
    text(d, (W // 2, 570), "Moth Atlas · emulation", F(REG, 36), col(DIM), "mm")
    text(d, (W // 2, 700), REPO, F(MONO, 36), col(INK), "mm")
    text(d, (W // 2, 780), "Moth_Hack 2026 · Challenge 02: Make it audible", F(MONO, 30), col(DIM), "mm")
    return im


REPO = "github.com/VedantMahadik-qc/superposition"


def video():
    sr, mix = wavfile.read(MIX)
    _, dry = wavfile.read(DRY)
    mix = mix.astype(np.float32) / 32768
    dry = dry.astype(np.float32) / 32768
    track_len = len(mix) / sr

    D_TITLE, D_STEPS, D_BA, D_OUT = 6.0, 10.5, 14.0, 7.0
    t_play = D_TITLE + D_STEPS + D_BA
    total = t_play + track_len + D_OUT

    # Audio: quiet intro bed under the cards, the A/B demo, the full track, silence for the outro.
    out = np.zeros((int(total * sr) + sr, 2), np.float32)
    bed = mix[: int((D_TITLE + D_STEPS) * sr)] * 0.35
    bed *= np.clip((len(bed) - np.arange(len(bed))) / (1.0 * sr), 0, 1)[:, None]
    out[: len(bed)] += bed
    a, b = T(DROP1 + 4), T(BREAK)
    seg = int(D_BA / 2 * sr)
    for i, src in enumerate((dry, mix)):
        clip = src[int(a * sr): int(a * sr) + seg].copy()
        r = int(0.05 * sr)
        clip[:r] *= np.linspace(0, 1, r)[:, None]
        clip[-r:] *= np.linspace(1, 0, r)[:, None]
        start = int((D_TITLE + D_STEPS) * sr) + i * seg
        out[start:start + len(clip)] += clip * (0.8 if i == 0 else 1.0)
    out[int(t_play * sr): int(t_play * sr) + len(mix)] += mix
    wav = HERE / "demo_audio.wav"
    wavfile.write(wav, sr, (np.clip(out, -1, 1) * 32767).astype(np.int16))

    # Before/after panels: bars 17-20, source vs blurred.
    pps_ba = 820 / (b - a)
    rolls = []
    for m in (ROOT / "midi" / "superposition_source.mid", MIDI):
        r = roll_file(m, 820, 640, pps_ba, a, quantum_on=(m == MIDI))
        rolls.append(r)

    pps = 220
    big_w = int(track_len * pps) + 4000
    big = roll(big_w, 700, pps, t0=-2000 / pps, glow=True)
    echo = echo_envelope(FPS)

    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(wav),
                           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-strict", "-2", "-b:a", "256k", "-shortest", str(HERE / "superposition_demo.mp4")],
                          stdin=subprocess.PIPE)

    def emit(im):
        ff.stdin.write(im.tobytes())

    for f in range(int(D_TITLE * FPS)):
        emit(card_title(f / FPS, D_TITLE))
    for f in range(int(D_STEPS * FPS)):
        emit(card_steps(f / FPS, D_STEPS))
    for f in range(int(D_BA * FPS)):
        emit(card_before_after(f / FPS, D_BA, rolls))
    for im in playback_frames(big, pps, echo, int(track_len * FPS)):
        emit(im)
    for f in range(int(D_OUT * FPS)):
        emit(card_outro(f / FPS, D_OUT))
    ff.stdin.close()
    ff.wait()
    print("wrote", HERE / "superposition_demo.mp4", f"{total:.1f}s")


def roll_file(path, width, height, pps, t0, quantum_on):
    """Small roll for the before/after panels (strings + lead only)."""
    img = Image.new("RGB", (width, height), (14, 14, 26))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lo, hi = 56, 92
    lane = height / (hi - lo)
    notes = midi_notes(path)
    for kind in ("strings", "lead"):
        for s, dur, p, v in notes.get(kind, []):
            x0, x1 = (s - t0) * pps, (s - t0 + max(dur, 0.06)) * pps
            if x1 < 0 or x0 > width:
                continue
            y = height - (p - lo) * lane
            q = quantum_on and quantum(kind, s)
            c = QUANTUM if q else COL[kind]
            al = int(60 + 195 * v / 127) if q else 220
            d.rectangle([x0, y - lane * 0.8, max(x0 + 1, x1 - 1), y], fill=c + (al,))
    img.paste(layer.filter(ImageFilter.GaussianBlur(4)), (0, 0), layer.filter(ImageFilter.GaussianBlur(4)))
    img.paste(layer, (0, 0), layer)
    return img


if __name__ == "__main__":
    {"poster": poster, "video": video}[sys.argv[1]]()
