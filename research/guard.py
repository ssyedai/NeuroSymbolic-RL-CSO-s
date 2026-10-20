"""Provenance guard: refuse to train/evaluate on anything that is not documented real or amplified-real rain."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

DEFAULT_ALLOWED = {"train": {"observed", "scaled_real"}, "val": {"observed", "scaled_real"},
                   "test": {"observed", "scaled_real"}}
V8_SCENARIO_SCHEMA = 2
APPROVED_ATLAS14_SHA256 = "f6c180e2cb547f0b47f495e66798d0fb2e1c0c63313d7b1f986cb85e2298fb76"


def file_sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assert_provenance(storms, rain_dir, manifest_path=None, allowed=None):
    """storms: objects with .storm_id, .split, .meta. Raises RuntimeError listing every violation.

    Use allowed={'test': {'observed'}} for the PRIMARY (unamplified) test run."""
    allowed = {**DEFAULT_ALLOWED, **(allowed or {})}
    rain_dir = Path(rain_dir)
    man = json.loads(Path(manifest_path or rain_dir / "data_manifest.json").read_text())["storms"]
    bad = []
    for s in storms:
        m = man.get(s.storm_id)
        if m is None:
            bad.append((s.storm_id, "not in manifest")); continue
        if m.get("provenance") not in allowed.get(s.split, set()):
            bad.append((s.storm_id, f"provenance {m.get('provenance')!r} not allowed for split {s.split}"))
        if getattr(s, "meta", {}).get("scaling", "none") != "none":
            bad.append((s.storm_id, "rescaled on the fly (use pre-built amplified files)"))
        if "aug_scale" in getattr(s, "meta", {}):
            bad.append((s.storm_id, "on-the-fly augmentation"))
        f = rain_dir / f"{s.storm_id}.csv"
        if not f.exists() or file_sha256(f) != m.get("file_sha256"):
            bad.append((s.storm_id, "file missing or changed since manifest"))
    if bad:
        raise RuntimeError(f"Provenance guard failed: {bad}")


def assert_real_only(storms, rain_dir="data/useful/rain_real",
                     manifest="data/useful/rain_real/data_manifest.json"):
    """Legacy v7 helper: observed provenance only (no scaled_real)."""
    assert_provenance(
        storms, rain_dir, manifest_path=manifest,
        allowed={"train": {"observed"}, "val": {"observed"}, "test": {"observed"}},
    )


def assert_v8_scenario_manifest(rain_dir, manifest_path=None) -> dict:
    """Reject stale two-outfall/onset or unverified extreme-rain catalogs."""
    path = Path(manifest_path or Path(rain_dir) / "data_manifest.json")
    if not path.is_file():
        raise RuntimeError(f"V8 scenario manifest is missing: {path}")
    blob = json.loads(path.read_text())
    failures = []
    if blob.get("schema_version") != V8_SCENARIO_SCHEMA:
        failures.append("schema_version")
    if blob.get("objective") != "complete_four_outfall_cumulative_m3":
        failures.append("objective")
    evidence = blob.get("evidence") or {}
    if evidence.get("onset_volume_units") != "m3":
        failures.append("onset_volume_units")
    if evidence.get("onset_complete_four_outfall_objective") is not True:
        failures.append("onset_complete_four_outfall_objective")
    storms = blob.get("storms") or {}
    has_extremes = any(str(m.get("rung", "")).startswith(("T200", "T500", "T1000"))
                       for m in storms.values())
    if has_extremes and evidence.get("atlas_sha256") != APPROVED_ATLAS14_SHA256:
        failures.append("approved_atlas14")
    if failures:
        raise RuntimeError(
            f"V8 scenario manifest is stale or incomplete ({failures}); rebuild it "
            "after G1 with configs/atlas14_detroit_city_ams_mm.csv")
    return blob
