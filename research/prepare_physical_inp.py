"""Build a 15-min Design_RG INP for physical rainfall injection.

The stock model uses:
  Design_RG  INTENSITY 1:00  TIMESERIES 9_12_08

Control steps are 15 min. With a 1-hour gage interval, sparse API rainfall
under-applies (peaks often never reach subcatchments). This script writes
`7MPF_CSO_08_physical.inp` with Design_RG at 0:15 and a zero TIMESERIES that
covers the full simulation window (dates on each midnight).

Legacy Trial 7 keeps using `7MPF_CSO_08.inp` unchanged.
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path


DEFAULT_SRC = "7MPF_CSO_08.inp"
DEFAULT_DST = "7MPF_CSO_08_physical.inp"
TS_NAME = "ZERO15"


def _parse_option_date(text: str, key: str) -> datetime | None:
    m = re.search(rf"^{key}\s+(\S+)", text, flags=re.M)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%m/%d/%Y")


def _parse_option_time(text: str, key: str) -> tuple[int, int, int]:
    m = re.search(rf"^{key}\s+(\d+):(\d+):(\d+)", text, flags=re.M)
    if not m:
        return 0, 0, 0
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def build_physical_inp(src: str | Path = DEFAULT_SRC,
                       dst: str | Path = DEFAULT_DST) -> Path:
    src, dst = Path(src), Path(dst)
    text = src.read_text(errors="ignore")

    start_d = _parse_option_date(text, "START_DATE") or datetime(2018, 6, 2)
    end_d = _parse_option_date(text, "END_DATE") or datetime(2018, 6, 5)
    sh, sm, ss = _parse_option_time(text, "START_TIME")
    eh, em, es = _parse_option_time(text, "END_TIME")
    start = start_d.replace(hour=sh, minute=sm, second=ss)
    end = end_d.replace(hour=eh, minute=em, second=es)
    # include a few steps past end for safety
    n_steps = int((end - start).total_seconds() / 900) + 8

    # Replace gage line (tolerate spacing variants)
    text2, n = re.subn(
        r"^Design_RG\s+INTENSITY\s+\S+\s+\S+\s+TIMESERIES\s+\S+.*$",
        f"Design_RG        INTENSITY 0:15     1.0      TIMESERIES {TS_NAME}",
        text,
        count=1,
        flags=re.M,
    )
    if n != 1:
        raise RuntimeError("Could not find Design_RG raingage line to patch")

    # Drop old 9_12_08 timeseries rows; inject ZERO15 with midnight dates
    lines = text2.splitlines(True)
    out: list[str] = []
    in_ts = False
    injected = False
    for line in lines:
        if line.startswith("[TIMESERIES]"):
            in_ts = True
            out.append(line)
            continue
        if in_ts and line.startswith("["):
            if not injected:
                out.extend(_zero15_lines(start, n_steps))
                injected = True
            in_ts = False
            out.append(line)
            continue
        if in_ts and line.startswith("9_12_08"):
            continue
        if in_ts and line.startswith(TS_NAME):
            continue
        out.append(line)
    if in_ts and not injected:
        out.extend(_zero15_lines(start, n_steps))

    dst.write_text("".join(out))
    return dst


def _zero15_lines(start: datetime, n_steps: int) -> list[str]:
    rows = []
    for i in range(n_steps):
        t = start + timedelta(minutes=15 * i)
        if i == 0 or (t.hour == 0 and t.minute == 0):
            rows.append(
                f"{TS_NAME}           {t.strftime('%m/%d/%Y %H:%M')}      0\n"
            )
        else:
            rows.append(
                f"{TS_NAME}                     {t.strftime('%H:%M')}      0\n"
            )
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--dst", default=DEFAULT_DST)
    a = ap.parse_args(argv)
    path = build_physical_inp(a.src, a.dst)
    print(f"Wrote {path}")
    # quick open smoke (separate process-safe if called alone)
    from pyswmm import Simulation, RainGages
    with Simulation(str(path)) as sim:
        sim.step_advance(900)
        rg = RainGages(sim)["Design_RG"]
        print("gage ok", rg.raingageid, "interval patch loaded")


if __name__ == "__main__":
    main()
