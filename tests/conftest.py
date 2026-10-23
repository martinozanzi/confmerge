import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

FS = 8000


def make_world(seconds: float, seed: int = 0, fs: int = FS) -> np.ndarray:
    """Segnale tipo 'parlato': rumore a banda larga con inviluppo variabile."""
    rng = np.random.default_rng(seed)
    n = int(seconds * fs)
    noise = rng.standard_normal(n).astype(np.float32)
    env_pts = rng.uniform(0.2, 1.0, int(seconds) + 2).astype(np.float32)
    env = np.interp(np.arange(n) / fs, np.arange(len(env_pts)), env_pts).astype(np.float32)
    return (noise * env * 0.1).astype(np.float32)


@pytest.fixture
def world():
    return make_world(300, seed=1)
