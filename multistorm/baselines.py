# multistorm/baselines.py
from __future__ import annotations
import hashlib, json
from pathlib import Path


def file_sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


# Bump when rain-unit convention or INP hydrology assumptions change.
# Keeps physical-unit results from colliding with Trial-7 legacy-unit cache rows.
# P9: bump so stale v7-unit / pre-nativefix records are never reused.
DEFAULT_BASELINE_TAG = "v3|physrain|nativefix|kb8"


class BaselineStore:
    def __init__(self, cache_path, inp_path, calibrate_fn, static_fn, native_fn=None,
                 tag=DEFAULT_BASELINE_TAG):
        self.path = Path(cache_path)
        self.inp_sha, self.tag = file_sha(inp_path), tag
        self.calibrate_fn, self.static_fn, self.native_fn = calibrate_fn, static_fn, native_fn
        self._d = json.loads(self.path.read_text()) if self.path.exists() else {}

    def _key(self, storm) -> str:
        return f"{self.tag}|{self.inp_sha}|{storm.sha}"

    def get(self, storm) -> dict:
        k = self._key(storm)
        if k not in self._d:
            fb = float(self.calibrate_fn(storm))
            rec = {"storm_id": storm.storm_id, "baseline_flooding": fb,
                   "static": self.static_fn(storm, fb),
                   "native": self.native_fn(storm) if self.native_fn else None}
            self._d[k] = rec
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._d, indent=1, default=float))
        return self._d[k]
