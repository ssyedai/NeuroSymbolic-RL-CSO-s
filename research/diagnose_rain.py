"""Decisive rainfall-response diagnostic (physical units × scale factors).

Pick one extreme real storm and run it through the env path at several
multiples of its physical depth. Compare SWMM .rpt Total Precipitation at
k=1 with the storm depth in inches.

Usage:
  PYTHONPATH=. .venv/bin/python -m research.diagnose_rain \\
      --storm USC00200230_20000910 --rain-dir data/useful/rain_real_full
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

from multistorm import adapters as A
from multistorm.policies import ConstantPolicy
from multistorm.storms import Storm, load_storms, rain_to_gage_value
from multistorm.metrics_ext import CFS_TO_M3_PER_STEP


def _rpt_precip(inp: str = "7MPF_CSO_08.inp") -> tuple[float | None, str | None]:
    """Return (inches, raw line) from SWMM status Continuity block."""
    rpt = Path(inp).with_suffix(".rpt")
    if not rpt.exists():
        return None, None
    for line in rpt.read_text(errors="ignore").splitlines():
        if "Total Precipitation" in line:
            nums = re.findall(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)", line)
            inches = float(nums[-1]) if nums else None
            return inches, line.strip()
    return None, None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rain-dir", default="data/useful/rain_real_full")
    ap.add_argument("--storm", default="USC00200230_20000910")
    ap.add_argument("--inp", default="7MPF_CSO_08.inp")
    ap.add_argument("--out", default="runs/diagnose_rain.csv")
    a = ap.parse_args(argv)

    storms = {s.storm_id: s for s in load_storms(a.rain_dir, scaling="none")}
    if a.storm not in storms:
        raise SystemExit(f"storm {a.storm} not in {a.rain_dir}")
    base = storms[a.storm]
    expect_in = float(base.depth.sum()) / 25.4
    print(f"base {a.storm} total_mm={base.depth.sum():.2f} max15={base.depth.max():.2f} "
          f"expect_in={expect_in:.4f}")

    env, agent, kb = A.build(0)
    env.physical_rain = True
    pol = ConstantPolicy()
    rows = []
    for k in [0, 1, 2, 4, 6.35, 10, 25.4]:
        st = Storm(
            f"x{k}", base.source,
            base.intensity * k, base.depth * k,
            "test", dict(base.meta),
        )
        obs, _ = env.reset(options={
            "storm": st,
            "baseline_flooding": 0.0,
            "physical_rain": True,
        })
        done = False
        while not done:
            obs, r, term, trunc, info = env.step(pol.select_action(obs))
            done = bool(term or trunc)
        L = env.get_episode_log()
        gage_peak = float(np.max(rain_to_gage_value(st.depth))) if st.depth.max() > 0 else 0.0
        # intensity mm/h peak / 25.4 should equal gage in/hr if intensity = depth*4
        intensity_peak_in_hr = float(st.intensity.max()) / 25.4
        row = dict(
            k=k,
            total_mm=float(st.depth.sum()),
            max15_mm=float(st.depth.max()),
            gage_peak_in_hr=gage_peak,
            intensity_peak_over_25p4=intensity_peak_in_hr,
            gage_matches_intensity=abs(gage_peak - intensity_peak_in_hr) < 1e-9,
            cso_m3=float(np.sum(L["cso_flow"]) * CFS_TO_M3_PER_STEP),
            flood_total=float(np.sum(L["flooding"])),
            fill_max=float(np.max(L["storage_fill"])),
            fill_min=float(np.min(L["storage_fill"])),
        )
        if abs(k - 1.0) < 1e-12:
            # Physical path writes runs/_physical_active.rpt; flush via close.
            inp_used = getattr(env, "input_file", a.inp)
            try:
                env.sim.close()
            except Exception:
                pass
            inches, rpt_line = _rpt_precip(inp_used)
            if inches is None:
                inches, rpt_line = _rpt_precip(a.inp)
            row["rpt_total_precip_in"] = inches
            row["expect_precip_in"] = expect_in
            row["rpt_line"] = rpt_line
            row["inp_used"] = inp_used
            print(f"\nRPT k=1 ({inp_used}): {rpt_line}")
            print(f"expected depth inches (storm sum/25.4): {expect_in:.4f}")
            ratio = (inches / expect_in) if inches and expect_in else float("nan")
            print(f"rpt/expect ratio: {ratio:.4f}\n")
            # reopen so later k values can reset cleanly
            env._init_sim()
        rows.append(row)
        print(f"k={k:5g}  cso_m3={row['cso_m3']:.1f}  flood={row['flood_total']:.2f}  "
              f"fill_max={row['fill_max']:.4f}  gage_peak={gage_peak:.3f}")

    df = pd.DataFrame(rows)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print("\n" + df.drop(columns=[c for c in df.columns if c == "rpt_line"], errors="ignore")
          .to_string(index=False))
    print(f"\nWrote {out}")
    env.close()
    return df


if __name__ == "__main__":
    main()
