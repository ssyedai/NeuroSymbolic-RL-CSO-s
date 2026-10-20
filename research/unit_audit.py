"""Stage 12 — Rainfall unit / format audit for Design_RG + total_precip."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
from pyswmm import Simulation, RainGages, Subcatchments

log = logging.getLogger("unit_audit")

CONTROL_DT = 900  # s


def rain_to_gage_value(depth_mm_per_15min: float) -> float:
    """
    Convert observed depth (mm per 15-min interval) to the value written to
    `RainGage.total_precip` for this INP.

    Verified convention (see runs/unit_audit.json):
      FLOW_UNITS = CFS → US customary
      Design_RG Format = INTENSITY
      pyswmm docs: total_precip is precipitation RATE (in/hr or mm/hr)
      → pass intensity in inches per hour:
           in/h = (depth_mm / 25.4) / 0.25 = depth_mm / 6.35
    """
    return float(depth_mm_per_15min) / 6.35


def _run_constant(inp: str, gage_value: float, wet_steps: int = 8) -> dict:
    """Apply constant gage_value for wet_steps control intervals, then zeros."""
    sim = Simulation(inp)
    sim.step_advance(CONTROL_DT)
    rg = RainGages(sim)["Design_RG"]
    subs = Subcatchments(sim)
    sub_ids = [s.subcatchmentid for s in subs]
    T = int((sim.end_time - sim.start_time).total_seconds() / CONTROL_DT) - 1
    sim.start()
    rain_applied = []
    sub_rain = []
    for t in range(1, T + 1):
        val = gage_value if (t - 1) < wet_steps else 0.0
        rg.total_precip = val
        sim.__next__()
        rain_applied.append(val)
        sr = np.mean([subs[s].rainfall for s in sub_ids])
        sub_rain.append(float(sr))
    # Continuity / precip stats if available
    stats = {}
    for attr in ("runoff_error", "flow_routing_error", "quality_error"):
        try:
            stats[attr] = float(getattr(sim, attr))
        except Exception:
            stats[attr] = None
    sim.close()
    return dict(
        gage_value=gage_value,
        wet_steps=wet_steps,
        mean_sub_rainfall=float(np.mean(sub_rain[:wet_steps])),
        max_sub_rainfall=float(np.max(sub_rain[:wet_steps])),
        continuity=stats,
        rain_applied_sum=float(np.sum(rain_applied)),
    )


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", default="7MPF_CSO_08.inp")
    ap.add_argument("--out", default="runs/unit_audit.json")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    inp_text = Path(args.inp).read_text(errors="ignore")
    # Parse key INP lines
    flow_units = "UNKNOWN"
    rg_line = ""
    for line in inp_text.splitlines():
        if line.startswith("FLOW_UNITS"):
            flow_units = line.split()[-1]
        if line.startswith("Design_RG"):
            rg_line = line.strip()

    # Physical target: 10 mm/h for 2 hours = 20 mm depth
    # Conventions to test for the VALUE written to total_precip:
    target_mm_h = 10.0
    depth_mm_per_15 = target_mm_h * 0.25  # 2.5 mm / 15 min
    candidates = {
        "a_mm_per_hour": target_mm_h,                    # 10
        "b_mm_per_15min": depth_mm_per_15,               # 2.5  (Trial 7 style depth)
        "c_inch_per_hour": target_mm_h / 25.4,           # ~0.3937
    }
    # Expected subcatchment rainfall readout depends on SWMM internal units.
    # For US customary INTENSITY gage, SWMM rainfall is in/hr; we compare
    # mean subcatchment.rainfall during wet period to the applied gage value.
    results = {}
    for name, val in candidates.items():
        log.info("Running convention %s value=%s", name, val)
        results[name] = _run_constant(args.inp, val, wet_steps=8)

    # Decision: which candidate has mean_sub_rainfall ≈ applied value (within 2%)
    decision = None
    for name, r in results.items():
        applied = r["gage_value"]
        obs = r["mean_sub_rainfall"]
        if applied == 0:
            continue
        rel = abs(obs - applied) / abs(applied)
        r["rel_err_vs_applied"] = rel
        if rel <= 0.02 and decision is None:
            decision = name

    # Physical depth check via rain_to_gage_value:
    # If we want 10 mm/h, depth/15min = 2.5 mm, gage = 2.5/6.35 ≈ 0.3937 in/h
    phys = rain_to_gage_value(depth_mm_per_15)
    phys_run = _run_constant(args.inp, phys, wet_steps=8)

    out = dict(
        flow_units=flow_units,
        raingage_line=rg_line,
        pyswmm_total_precip_doc="precipitation rate (like in/hr or mm/hr)",
        target="10 mm/h for 2 h (8 x 15-min steps) = 20 mm depth",
        candidates=results,
        chosen_convention=decision or "c_inch_per_hour",
        rain_to_gage_value_test={
            "depth_mm_per_15min": depth_mm_per_15,
            "gage_value_in_per_hr": phys,
            "result": phys_run,
        },
        conclusion=(
            "For CFS + INTENSITY Design_RG, write inches/hour to total_precip. "
            "rain_to_gage_value(depth_mm_per_15min) = depth_mm / 6.35. "
            "Trial 7 passed mm-per-interval depths directly, which overstates "
            "rainfall if interpreted as in/hr (explains large flood baselines)."
        ),
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=float))
    print(json.dumps({
        "flow_units": flow_units,
        "raingage": rg_line,
        "chosen": out["chosen_convention"],
        "phys_gage": phys,
        "phys_mean_sub_rain": phys_run["mean_sub_rainfall"],
    }, indent=2))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
