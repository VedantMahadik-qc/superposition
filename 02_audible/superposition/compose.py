"""Compose 'Superposition': a hybrid trailer track, 36 bars + an end hit, 140 -> 150 BPM.

Sections (1-based bars): 1-4 intro, 5-12 build, 13-20 drop 1 (D minor), 21-24 break,
25-28 build 2 (accelerando, half-bar gap at the end), 29-36 final drop (up a tone, E minor),
37-40 end hit and tail.
Tracks: 0 tempo/meta, 1 brass, 2 drums, 3 strings, 4 lead, 5 bass.
Strings and lead play continuously with no rests (blur-midi-v1 drops rests);
quiet passages are written at low velocity and the gap is muted in the mix.
"""
from pathlib import Path

import mido

HERE = Path(__file__).resolve().parent
(HERE / "midi").mkdir(exist_ok=True)

TPB = 480
BAR = TPB * 4
S16 = TPB // 4
BARS = 40
DROP1, BREAK, BUILD2, DROP2, END = 12, 20, 24, 28, 36   # 0-based section starts
GAP = (DROP2 * BAR - BAR // 2, DROP2 * BAR)              # half-bar of silence before the final drop
BLUR = [(DROP1, BREAK), (DROP2, END)]                    # bars the quantum blur works on


def bpm_at(bar_f):
    if bar_f < BUILD2:
        return 140.0
    if bar_f < DROP2:
        return 140 + 10 * (bar_f - BUILD2) / (DROP2 - BUILD2)
    return 150.0 if bar_f < END else 120.0


def tempo_events():
    return [(b * TPB, mido.bpm2tempo(bpm_at(b / 4))) for b in range(BARS * 4)]


def tick2s(tick, events=None):
    events = events or tempo_events()
    s, last_t, last_tempo = 0.0, 0, events[0][1]
    for tt, tempo in events:
        if tt > tick:
            break
        s += mido.tick2second(tt - last_t, TPB, last_tempo)
        last_t, last_tempo = tt, tempo
    return s + mido.tick2second(tick - last_t, TPB, last_tempo)


# i - VI - III - VII in D minor: Dm, Bb, F, C. (bass root, chord tones low->high)
CHORDS = [(38, [62, 65, 69, 74]), (34, [62, 65, 70, 74]), (41, [60, 65, 69, 72]), (36, [60, 64, 67, 72])]
OSTINATO = [0, 3, 0, 2, 0, 3, 0, 1, 0, 3, 0, 2, 0, 3, 1, 2]   # pedal-tone 16ths
# Lead hook, one bar per chord: (pitch, beats); bars sum to 4 beats, no rests.
HOOK = [
    [(69, 1.5), (74, 1.5), (77, 1)],
    [(76, 1.5), (74, 1.5), (72, 1)],
    [(72, 1.5), (77, 1.5), (81, 1)],
    [(79, 2), (76, 1), (72, 1)],
    [(69, 1.5), (74, 1.5), (77, 1)],
    [(79, 1.5), (77, 1.5), (76, 1)],
    [(77, 1.5), (81, 1.5), (84, 1)],
    [(83, 1), (79, 1), (76, 1), (74, 1)],
]
K, SN, HH, TOM, CRASH = 36, 38, 42, 45, 49   # drum pitches


def section(bar):
    if bar < 4:
        return "intro"
    if bar < DROP1:
        return "build"
    if bar < BREAK:
        return "drop"
    if bar < BUILD2:
        return "break"
    if bar < DROP2:
        return "build2"
    if bar < END:
        return "drop2"
    return "end"


def build():
    brass, drums, strings, lead, bass = [], [], [], [], []
    for bar in range(END):
        sec = section(bar)
        root, tones = CHORDS[bar % 4]
        up = 2 if sec == "drop2" else 0                     # final drop: up a tone
        start = bar * BAR
        hot = sec in ("drop", "drop2")
        # Strings: 16th pedal ostinato all the way through, velocity follows the energy.
        sv = {"intro": 58, "build": 50 + 4 * (bar - 4), "drop": 100, "break": 55,
              "build2": 70 + 10 * (bar - BUILD2), "drop2": 112}[sec]
        for k in range(16):
            octave = 12 if hot and k % 2 else 0
            strings.append((start + k * S16, tones[OSTINATO[k]] + up + octave, S16, min(127, sv + (12 if k % 4 == 0 else 0))))
        # Lead: hook in the drops, quiet held roots elsewhere (keeps the track rest-free).
        if hot:
            t = start
            for p, beats in HOOK[bar % 8]:
                lead.append((t, p + up, int(beats * TPB), 105 if sec == "drop" else 118))
                t += int(beats * TPB)
        else:
            lead.append((start, root + 36, BAR, 22))
        # Bass: 8th pulse in drops, held in builds/break.
        if hot:
            bass += [(start + i * TPB // 2, root + up, TPB // 2, 110 if i % 2 == 0 else 85) for i in range(8)]
        elif sec != "intro":
            bass.append((start, root, BAR, 70))
        # Brass: braams on drop downbeats every 2 bars, swelling fifths in builds.
        if hot and bar % 2 == 0:
            brass += [(start, p + up, 2 * BAR, 115) for p in (root - 12, root - 5, root, tones[1] - 12)]
        elif sec in ("build", "build2") and bar % 2 == 0:
            brass += [(start, p, 2 * BAR, 60 + 4 * (bar % 8)) for p in (root - 12, root - 5)]
        # Drums.
        hats = 16 if sec in ("intro", "break", "drop2") else 8
        hv = 50 if sec in ("intro", "break") else 80
        drums += [(start + i * (BAR // hats), HH, S16 // 2, hv + (15 if i % (hats // 4) == 0 else 0)) for i in range(hats)]
        if sec == "intro":
            drums.append((start, K, S16, 70))
        elif sec in ("build", "build2"):
            drums += [(start + i * TPB // 2, TOM, S16, 70 + 3 * i) for i in (0, 3, 6)]
            drums.append((start, K, S16, 95))
            n_roll = {0: 0, 1: 0, 2: 0, 3: 0, 4: 4, 5: 8, 6: 16, 7: 32}[(bar - 4) % 8] if sec == "build" else [8, 16, 32, 32][bar - BUILD2]
            for i in range(n_roll):
                drums.append((start + i * BAR // n_roll, SN, max(S16 // 4, BAR // n_roll // 2), 60 + int(60 * i / n_roll)))
        elif hot:
            for i, beat in enumerate([0, 1.5, 2, 3.5] if sec == "drop2" else [0, 1.5, 2]):
                drums.append((start + int(beat * TPB), K, S16, 127 if i == 0 else 110))
            drums += [(start + b * TPB, SN, S16, 120) for b in (1, 3)]
            if bar % 4 == 3:
                drums += [(start + 3 * TPB + i * S16, TOM, S16, 100 + 6 * i) for i in range(4)]
            if bar in (DROP1, DROP2) or bar % 4 == 0:
                drums.append((start, CRASH, BAR, 120))
    # End hit (bar 37) and a ringing E minor chord over the tail.
    tail = END * BAR
    drums += [(tail, K, S16, 127), (tail, CRASH, 2 * BAR, 127)]
    brass += [(tail, p, 3 * BAR, 110) for p in (28, 35, 40, 43, 47)]
    strings += [(tail, p, 3 * BAR, 70) for p in (64, 67, 71, 76)]
    lead.append((tail, 76, 3 * BAR, 60))
    bass.append((tail, 28, 3 * BAR, 110))
    return brass, drums, strings, lead, bass


def main():
    mid = mido.MidiFile(type=1, ticks_per_beat=TPB)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    now = 0
    for tick, tempo in tempo_events():
        meta.append(mido.MetaMessage("set_tempo", tempo=tempo, time=tick - now))
        now = tick
    mid.tracks.append(meta)
    parts = build()
    names = [("brass", 61, 0), ("drums", 0, 9), ("strings", 48, 2), ("lead", 81, 3), ("bass", 38, 4)]
    for (name, prog, ch), notes in zip(names, parts):
        t = mido.MidiTrack()
        t.append(mido.MetaMessage("track_name", name=name, time=0))
        t.append(mido.Message("program_change", program=prog, channel=ch, time=0))
        add_notes(t, notes, ch)
        mid.tracks.append(t)
    out = HERE / "midi" / "superposition_source.mid"
    mid.save(out)
    print("wrote", out, f"{mid.length:.1f}s", {n[0]: len(p) for n, p in zip(names, parts)})


def add_notes(t, notes, channel):
    """notes: [(start_tick, pitch, dur_ticks, velocity)] -> delta-timed messages."""
    ev = []
    for s, p, d, v in notes:
        ev.append((s, 1, mido.Message("note_on", note=p, velocity=v, channel=channel)))
        ev.append((s + d, 0, mido.Message("note_off", note=p, velocity=0, channel=channel)))
    ev.sort(key=lambda e: (e[0], e[1]))
    now = 0
    for tick, _, msg in ev:
        msg.time = tick - now
        now = tick
        t.append(msg)


if __name__ == "__main__":
    main()
