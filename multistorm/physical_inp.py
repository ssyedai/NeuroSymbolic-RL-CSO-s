"""Build a per-storm INP so physical 15-min rain is applied via TIMESERIES.

Stock `7MPF_CSO_08.inp` uses Design_RG INTENSITY 1:00 + API overrides. Sparse
15-min pulses then under-apply. For physical-rain research we write a temp INP
with Design_RG at 0:15 and the storm hyetograph as TIMESERIES STORM15 (in/hr).
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from .storms import rain_to_gage_value

DEFAULT_SRC = "7MPF_CSO_08.inp"
DEFAULT_DST_DIR = Path("runs/_physical_inp")
TS_NAME = "STORM15"


def _unique_dst() -> Path:
    """Per-process unique path so parallel SWMM workers do not clobber each other."""
    return DEFAULT_DST_DIR / f"storm_{os.getpid()}_{uuid.uuid4().hex[:8]}.inp"


def write_physical_storm_inp(
    depth_mm_per_15min,
    src: str | Path = DEFAULT_SRC,
    dst: str | Path | None = None,
    start: datetime | None = None,
) -> Path:
    """Write INP with 15-min Design_RG + STORM15 intensities (in/hr)."""
    src = Path(src)
    dst = Path(dst) if dst is not None else _unique_dst()
    dst.parent.mkdir(parents=True, exist_ok=True)
    depth = np.asarray(depth_mm_per_15min, dtype=float).reshape(-1)
    text = src.read_text(errors="ignore")

    if start is None:
        m = re.search(r"^START_DATE\s+(\S+)", text, flags=re.M)
        start_d = datetime.strptime(m.group(1), "%m/%d/%Y") if m else datetime(2018, 6, 2)
        mt = re.search(r"^START_TIME\s+(\d+):(\d+):(\d+)", text, flags=re.M)
        if mt:
            start = start_d.replace(
                hour=int(mt.group(1)), minute=int(mt.group(2)), second=int(mt.group(3)))
        else:
            start = start_d

    text, n = re.subn(
        r"^Design_RG\s+INTENSITY\s+\S+\s+\S+\s+TIMESERIES\s+\S+.*$",
        f"Design_RG        INTENSITY 0:15     1.0      TIMESERIES {TS_NAME}",
        text,
        count=1,
        flags=re.M,
    )
    if n != 1:
        raise RuntimeError("Design_RG raingage line not found in INP")

    # Extra dry steps past the series so the gage never runs off the end
    n_pad = max(16, 0)
    ts_lines = []
    n_total = len(depth) + n_pad
    for i in range(n_total):
        t = start + timedelta(minutes=15 * i)
        if i < len(depth):
            d = float(depth[i])
            val = float(rain_to_gage_value(d)) if d > 0 else 0.0
        else:
            val = 0.0
        if i == 0 or (t.hour == 0 and t.minute == 0):
            ts_lines.append(
                f"{TS_NAME}          {t.strftime('%m/%d/%Y %H:%M')}      {val:.8f}\n"
            )
        else:
            ts_lines.append(
                f"{TS_NAME}                    {t.strftime('%H:%M')}      {val:.8f}\n"
            )

    lines = text.splitlines(True)
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
                out.extend(ts_lines)
                injected = True
            in_ts = False
            out.append(line)
            continue
        if in_ts and (line.startswith("9_12_08") or line.startswith(TS_NAME)):
            continue
        out.append(line)
    if in_ts and not injected:
        out.extend(ts_lines)

    dst.write_text("".join(out))
    return dst
