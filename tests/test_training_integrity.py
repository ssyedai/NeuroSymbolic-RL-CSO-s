from pathlib import Path
from types import SimpleNamespace

import pytest

from multistorm import train_multi
from multistorm import adapters
from research.readiness import assert_hydraulic_training_ready
from research.guard import assert_v8_scenario_manifest, APPROVED_ATLAS14_SHA256


def _cfg(variant):
    return SimpleNamespace(variant=variant, seed=3, theta_path=None,
                           inp="7MPF_CSO_08.inp")


@pytest.mark.parametrize(
    "variant,expected",
    [
        ("plain", dict(complete_overflow=True, native_pumps=True,
                       use_projection=False, lagrangian=False,
                       rain_features=False, w_store=0.0)),
        ("lag_only", dict(complete_overflow=True, native_pumps=True,
                          use_projection=False, lagrangian=True,
                          rain_features=False, w_store=0.0)),
        ("v8_notopo", dict(complete_overflow=True, native_pumps=True,
                           topology_aware=False)),
        ("v8_10d", dict(complete_overflow=True, native_pumps=True,
                        policy_dim=10)),
    ],
)
def test_v8_ablation_changes_only_named_factor(monkeypatch, variant, expected):
    calls = []
    monkeypatch.setattr(train_multi.A, "build_v8",
                        lambda seed, **kw: calls.append((seed, kw)) or kw)
    result = train_multi._build_stack(_cfg(variant))
    assert result is calls[0][1]
    assert calls[0][0] == 3
    for name, value in expected.items():
        assert calls[0][1][name] == value


def test_hydraulic_readiness_marker_is_strict(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(RuntimeError, match="blocked"):
        assert_hydraulic_training_ready(missing)
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"passed": true, "refinement_difference_pct": 1.1, '
                       '"refinement_limit_pct": 1.0}')
    with pytest.raises(RuntimeError, match="Invalid"):
        assert_hydraulic_training_ready(invalid)
    valid = tmp_path / "valid.json"
    valid.write_text(
        '{"passed": true, "true_native_control": true, '
        '"complete_four_outfall_objective": true, "zero_flood_preserved": true, '
        '"thresholds_unchanged": true, "refinement_difference_pct": 0.9, '
        '"refinement_limit_pct": 1.0}')
    assert assert_hydraulic_training_ready(valid)["passed"] is True


def test_static_baseline_cannot_leak_projection_state():
    class FakeEnv:
        use_projection = True
        physical_rain = True
        def reset(self, options):
            self.use_projection = options.get("use_projection", self.use_projection)
            self.options = options
            return __import__("torch").zeros(1), {}
        def step(self, action):
            return __import__("torch").zeros(1), 0.0, False, True, {}
        def get_episode_log(self):
            import numpy as np
            return dict(cso_flow=np.zeros(1), flooding=np.zeros(1),
                        storage_fill=np.zeros(1), actions_projected=np.zeros((1, 10)),
                        reward=np.zeros(1))
    env = FakeEnv()
    storm = SimpleNamespace()
    adapters.static_fn(env)(storm, 0.0)
    assert env.options["use_projection"] is False
    assert env.use_projection is True


def test_v8_manifest_rejects_stale_or_unapproved_extremes(tmp_path):
    import json
    path = tmp_path / "data_manifest.json"
    with pytest.raises(RuntimeError, match="manifest"):
        assert_v8_scenario_manifest(tmp_path)
    base = dict(
        schema_version=2, objective="complete_four_outfall_cumulative_m3",
        storms={"x": {"rung": "T1000"}},
        evidence=dict(onset_volume_units="m3",
                      onset_complete_four_outfall_objective=True,
                      atlas_sha256="wrong"),
    )
    path.write_text(json.dumps(base))
    with pytest.raises(RuntimeError, match="approved_atlas14"):
        assert_v8_scenario_manifest(tmp_path)
    base["evidence"]["atlas_sha256"] = APPROVED_ATLAS14_SHA256
    path.write_text(json.dumps(base))
    assert assert_v8_scenario_manifest(tmp_path)["schema_version"] == 2
