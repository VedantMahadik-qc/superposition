"""Step 2b: repair the blur-midi-v1 output before rendering.

blur-midi-v1 can leak notes outside its mask, drifts off the grid, and spreads each note's
energy over a cloud of quiet notes. Repair:
  - drop 1 plays the clean hook for 4 bars, then the blurred version (bars 17-20);
    the final drop is blurred throughout; everything else comes from the source,
  - blurred notes are snapped to a 16th grid,
  - per 16th step, velocities are rescaled so the loudest quantum note gets the source
    note's velocity (relative quantum weights kept); notes under 20% of that are dropped.

usage: python fix_midi.py <variant>   -> midi/superposition_<variant>_fixed.mid
"""
import sys
from pathlib import Path

import mido

from compose import BAR, BLUR, S16, TPB, add_notes

HERE = Path(__file__).resolve().parent
variant = sys.argv[1] if len(sys.argv) > 1 else "hype"
RANGES = [(a * BAR, b * BAR) for a, b in BLUR]
USE = [((BLUR[0][0] + 4) * BAR, BLUR[0][1] * BAR), (BLUR[1][0] * BAR, BLUR[1][1] * BAR)]
KEEP = 0.2


def inside(tick):
    return any(lo <= tick < hi for lo, hi in RANGES)


def notes(tr):
    """-> [(start_tick, pitch, dur_ticks, velocity)] from a delta-timed track."""
    now, open_, out = 0, {}, []
    for m in tr:
        now += m.time
        if m.type == "note_on" and m.velocity > 0:
            open_[m.note] = (now, m.velocity)
        elif m.type in ("note_off", "note_on") and m.note in open_:
            s, v = open_.pop(m.note)
            out.append((s, m.note, now - s, v))
    return out


def main():
    src = mido.MidiFile(HERE / "midi" / "superposition_source.mid")
    blur = mido.MidiFile(HERE / "midi" / f"superposition_{variant}.mid")
    out = mido.MidiFile(type=1, ticks_per_beat=TPB)
    for i, tr in enumerate(src.tracks):
        if i not in (3, 4):
            out.tracks.append(tr)
            continue
        head = [m for m in tr if m.is_meta or m.type == "program_change"][:2]
        ch = next(m.channel for m in tr if m.type == "note_on")
        used = lambda tick: any(lo <= tick < hi for lo, hi in USE)  # noqa: E731
        src_notes = notes(tr)
        clean = [n for n in src_notes if not used(n[0])]
        target = {}
        for s, p, d, v in src_notes:
            target[s // S16] = max(target.get(s // S16, 0), v)
        steps = {}
        for s, p, d, v in notes(blur.tracks[i]):
            q = round(s / S16) * S16
            if used(q):
                cur = steps.setdefault(q, {})
                if v > cur.get(p, (0, 0))[0]:
                    cur[p] = v, max(S16, round(d / S16) * S16)
        blurred = []
        for q, cur in steps.items():
            top = max(v for v, _ in cur.values())
            # sustained source notes (the lead) set the level of every step they cover
            tv = target.get(q // S16) or max((v for (s, p, d, v) in src_notes if s <= q < s + d), default=100)
            for p, (v, d) in cur.items():
                if v >= KEEP * top:
                    blurred.append((q, p, d, max(1, min(127, round(v / top * tv)))))
        t = mido.MidiTrack()
        for m in head:
            t.append(m.copy(time=0))
        add_notes(t, clean + blurred, ch)
        out.tracks.append(t)
        print(f"{head[0].name}: {len(clean)} source + {len(blurred)} blurred notes")
    dst = HERE / "midi" / f"superposition_{variant}_fixed.mid"
    out.save(dst)
    print("wrote", dst, f"{out.length:.1f}s")


if __name__ == "__main__":
    main()
