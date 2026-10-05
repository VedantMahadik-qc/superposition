"""Step 3+4: render the repaired MIDI, send strings + lead + impacts through retrocausal-echo-v1,
and mix: risers into each drop, impacts on the downbeats, kick-sidechained music, the quantum
echo taking over in the break, and a half-bar of dead silence before the final drop.

usage: python mix.py [variant] [--no-echo]   (default hype; 'source' renders the unblurred MIDI)
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import atlas  # noqa: E402
import instruments as ins  # noqa: E402
from compose import BAR, BREAK, BUILD2, DROP1, DROP2, END, GAP, tick2s  # noqa: E402

variant = sys.argv[1] if len(sys.argv) > 1 else "hype"
no_echo = "--no-echo" in sys.argv
STEMS, OUT = HERE / "stems", HERE / "output"
STEMS.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)
SR = ins.SR
midi = HERE / "midi" / (f"superposition_{variant}_fixed.mid" if variant != "source" else "superposition_source.mid")
T = lambda bar: tick2s(int(bar * BAR))  # noqa: E731

stems = ins.render(midi)
total = max(len(s) for s in stems.values()) + SR * 4
stems = {k: np.pad(v, ((0, total - len(v)), (0, 0))) for k, v in stems.items()}
for k, v in stems.items():
    ins.save(STEMS / f"{variant}_{k}.wav", v)
t = np.arange(total) / SR


def place(buf, x, at):
    i = int(at * SR)
    buf[i:i + len(x)] += x[: len(buf) - i]


# FX: risers into both drops, impacts on the drop downbeats and the end hit.
fx = np.zeros((total, 2))
place(fx, ins.riser(T(DROP1) - T(DROP1 - 4)), T(DROP1 - 4))
place(fx, ins.riser(tick2s(GAP[0]) - T(BUILD2)), T(BUILD2))
hits = np.zeros((total, 2))
for b in (DROP1, DROP2, END):
    place(hits, ins.impact(), T(b))

silence = ((t >= tick2s(GAP[0])) & (t < tick2s(GAP[1])))[:, None]

# Sidechain: duck the music after every kick in the drops.
kicks = np.zeros(total)
for s, d, p, v in ins.midi_notes(midi)["drums"]:
    if p == 36:
        kicks[min(int(s * SR), total - 1)] = v / 127
duck = 1 - 0.5 * np.clip(lfilter([1], [1, -np.exp(-1 / (0.13 * SR))], kicks), 0, 1)
duck = duck[:, None]

# Send: strings + lead from drop 1 onward, plus the impacts, mono, to the quantum delay.
music = stems["strings"] + stems["lead"]
send = (music * (t >= T(DROP1))[:, None] * ~silence).mean(1)
send = send / np.abs(send).max() * 0.7 + hits.mean(1) / np.abs(hits).max() * 0.4
send_path = STEMS / f"{variant}_echo_send.wav"
wavfile.write(send_path, SR, (send / np.abs(send).max() * 0.9 * 32767).astype(np.int16))

echo_params = {
    "bpm": 140, "division": 0.75, "depth": 14, "n_sites": 12,
    "theta_x": 1.2, "theta_zz": 0.9, "theta_z": 0.5,
    "negative_mode": "reverse", "grain_ms": 120,
    "feedback": 0.4, "feedback_source": "kick",
    "mix": 1.0, "stereo_width": 1.0, "decay": 0.9, "machine": "aer",
}
echo_wav = STEMS / f"{variant}_echo_return.wav"
if no_echo:
    echo = np.zeros((total, 2))
else:
    if not echo_wav.exists():
        jid, res, paths = atlas.run("retrocausal-echo-v1", echo_params, {"audio": send_path},
                                    out_dir=STEMS / "echo_job", prefix=f"{variant}_")
        Path(paths["result"]).replace(echo_wav)
    sr_e, echo = wavfile.read(echo_wav)
    assert sr_e == SR, sr_e
    echo = echo.astype(np.float32) / (np.iinfo(echo.dtype).max if echo.dtype.kind == "i" else 1)
    if echo.ndim == 1:
        echo = np.stack([echo, echo], 1)
    echo = np.pad(echo, ((0, max(0, total - len(echo))), (0, 0)))[:total]

# Echo level per section: a halo in drop 1, takes over in the break, back under for build 2.
pts = [(0, 0), (T(DROP1), 0.25), (T(BREAK) - 0.5, 0.3), (T(BREAK) + 0.5, 1.0), (T(BUILD2), 0.9),
       (T(BUILD2 + 2), 0.35), (T(DROP2), 0.55), (T(END), 0.6), (T(END) + 1, 1.0), (t[-1], 1.0)]
env = np.interp(t, *zip(*pts))[:, None]

tonal = (stems["strings"] * 1.0 + stems["lead"] * 0.9 + stems["brass"] * 0.8 + stems["bass"] * 0.9)
tonal = tonal / np.abs(tonal).max()
drums = stems["drums"] / np.abs(stems["drums"]).max()
wet = echo / (np.abs(echo).max() + 1e-9) * 0.55 * env
fx = fx / np.abs(fx).max() * 0.35
hits = hits / np.abs(hits).max() * 0.9

# Energy curve: builds start low and climb into each drop, so the drops land.
energy = np.interp(t, *zip(*[(0, 0.75), (T(4), 0.75), (T(4) + 0.01, 0.35), (T(DROP1) - 0.01, 0.8), (T(DROP1), 1.0),
                              (T(BREAK), 1.0), (T(BREAK) + 0.01, 0.6), (T(BUILD2), 0.6), (T(BUILD2) + 0.01, 0.35),
                              (T(DROP2) - 0.01, 0.85), (T(DROP2), 1.0), (t[-1], 1.0)]))[:, None]
mix = (ins.reverb(tonal * duck * energy * ~silence + fx * ~silence, seconds=2.5, wet=0.2)
       + drums * 0.85 * energy + hits + wet * duck)
mix *= ~silence   # the gap is true silence, reverb tails included
mix = np.tanh(mix * 1.5 / np.abs(mix).max()) / np.tanh(1.5) * 10 ** (-1 / 20)

level = np.convolve(np.abs(mix).max(1), np.ones(SR // 10) / (SR // 10), "same")
end = min(total, int(np.nonzero(level > 10 ** (-70 / 20))[0][-1]) + SR)
mix = mix[:end] * np.clip((end - np.arange(end)) / (3 * SR), 0, 1)[:, None]

wav = OUT / f"superposition_{variant}{'_dry' if no_echo else ''}.wav"
wavfile.write(wav, SR, (mix * 32767).astype(np.int16))
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "320k", str(wav.with_suffix(".mp3"))], check=True)
blur_jobs = HERE / "midi" / "blur_jobs.json"
(OUT / f"params_{variant}.json").write_text(json.dumps({
    "blur_midi": json.loads(blur_jobs.read_text()) if blur_jobs.exists() else None,
    "retrocausal_echo": echo_params}, indent=2))
print("wrote", wav, f"{len(mix) / SR:.1f}s  drops at {T(DROP1):.1f}s / {T(DROP2):.1f}s")
