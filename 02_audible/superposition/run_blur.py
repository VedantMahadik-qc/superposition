"""Step 2: quantum-blur the strings + lead in both drops with blur-midi-v1 (Blur Jazz)."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import atlas  # noqa: E402
from compose import BAR, BLUR, tick2s  # noqa: E402

SRC = HERE / "midi" / "superposition_source.mid"


mid_id = atlas.upload(SRC, "audio/midi")
# Track indexes follow the SMF: 0 meta, 1 brass, 2 drums, 3 strings, 4 lead, 5 bass.
mask = [[tr, tick2s(a * BAR), tick2s(b * BAR)] for a, b in BLUR for tr in (3, 4)]
variants = {
    "hype": {"strength": 0.55, "reach": 0.3, "margin": 0.2, "threshold": 0.1, "mask": mask},
    "collapse": {"strength": 0.75, "reach": 0.6, "margin": 0.25, "threshold": 0.08, "mask": mask},
}
jobs = {n: atlas.submit("blur-midi-v1", p, {"midi": f"asset:{mid_id}"})[0] for n, p in variants.items()}
print(jobs, flush=True)
(HERE / "midi" / "blur_jobs.json").write_text(json.dumps({"midi_asset": mid_id, "jobs": jobs, "params": variants}, indent=2))


def fetch(name):
    atlas.wait(jobs[name], timeout=3600, interval=5, verbose=False)
    res = atlas.result(jobs[name])
    atlas.download_asset(res["outputs"][0]["output_asset_id"], HERE / "midi" / f"superposition_{name}.mid")
    print("done", name, flush=True)


with ThreadPoolExecutor(2) as ex:
    list(ex.map(fetch, jobs))
