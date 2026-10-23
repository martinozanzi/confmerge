"""Screenshot di ogni schermata a 100/150/200%, a dimensione minima, in tema chiaro e con testo ingrandito;
fallisce se trova widget sovrapposti o tagliati. Gli screenshot vanno in docs/screenshots/."""
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg assente")

SCENARIOS = [
    ("100", {"QT_SCALE_FACTOR": "1"}, []),
    ("150", {"QT_SCALE_FACTOR": "1.5"}, []),
    ("200", {"QT_SCALE_FACTOR": "2"}, []),
    ("min", {"QT_SCALE_FACTOR": "1"}, ["--min"]),
    ("light-100", {"QT_SCALE_FACTOR": "1"}, ["--theme", "light"]),
    ("min-testo125", {"QT_SCALE_FACTOR": "1"}, ["--min", "--font-scale", "1.25"]),
]


@pytest.mark.parametrize("name,env,extra", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_screens_have_no_overlap_or_clipping(name, env, extra):
    out = ROOT / "docs" / "screenshots" / name
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "screenshots.py"), str(out), *extra],
                       capture_output=True, text=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen", **env},
                       timeout=600)
    line = next((l for l in r.stdout.splitlines() if l.startswith("{")), None)
    assert line, r.stdout[-500:] + r.stderr[-500:]
    data = json.loads(line)
    assert len(data["shots"]) >= 10
    assert not data["problems"], json.dumps(data["problems"][:5], ensure_ascii=False, indent=1)
    for s in data["shots"]:
        assert (out / f"{s}.png").stat().st_size > 5000
