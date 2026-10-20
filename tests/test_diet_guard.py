"""T08 acceptance: diet filters and provenance guard."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from multistorm.diet import eligible_for_training, filter_train_pool
from multistorm.storms import Storm
from research.guard import assert_provenance


def _storm(sid, split="train", family="T", rung="T10", T=10.0, test_only=False, k=1.0):
    d = np.ones(288)
    return Storm(sid, "x", d * 4, d, split, dict(
        family=family, rung=rung, T_anchor=T, test_only=test_only, k=k,
        scaling="none", parent="P", provenance="scaled_real" if family != "R" else "observed",
    ))


def test_d2_excludes_t200_and_non_train():
    storms = [
        _storm("a", "train", "T", "T10", 10),
        _storm("b", "train", "T", "T200", 200, test_only=True),
        _storm("c", "val", "T", "T10", 10),
        _storm("d", "train", "F", "F2", 2),
        _storm("e", "train", "R", "R", float("nan")),
    ]
    pool = filter_train_pool(storms, "D2_ladder100", train_max_T=100,
                             allow_test_only_rungs=False)
    ids = {s.storm_id for s in pool}
    # An unknown research-scenario severity cannot demonstrate ceiling compliance.
    assert ids == {"a"}
    assert not eligible_for_training(storms[1], "D2_ladder100", 100, False)


def test_tampered_file_raises(tmp_path: Path):
    rain = tmp_path / "rain"
    rain.mkdir()
    sid = "s1"
    f = rain / f"{sid}.csv"
    f.write_text("1\n" * 288)
    man = {
        "storms": {
            sid: dict(provenance="observed", family="R", rung="R", k=1.0,
                      parent=sid, test_only=False,
                      T_by_dur={"360": 1.0}, file_sha256="deadbeef"),
        }
    }
    (rain / "data_manifest.json").write_text(json.dumps(man))
    s = Storm(sid, str(f), np.ones(288) * 4, np.ones(288), "train",
              dict(scaling="none"))
    with pytest.raises(RuntimeError, match="changed|missing"):
        assert_provenance([s], rain)
