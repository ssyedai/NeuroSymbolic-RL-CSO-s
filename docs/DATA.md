# Research rainfall unit convention (Stage 12)

## INP facts
- `[OPTIONS] FLOW_UNITS = CFS` → US customary units
- `[RAINGAGES] Design_RG INTENSITY 1:00 1.0 TIMESERIES ...`
- Control step in the env is **15 minutes** (API-driven), even though the INP gage interval field is 1:00

## PySWMM
`RainGage.total_precip` is documented as a **precipitation rate** (in/hr or mm/hr), not a depth.

## Decision
**Write inches per hour to `total_precip`.**

```text
rain_to_gage_value(depth_mm_per_15min) = depth_mm / 6.35
# = (depth_mm / 25.4) / 0.25
```

Implemented in `multistorm/storms.py` and `app.py`. Enabled with `--physical-rain` / `--real-only`.

## Trial 7 caveat
Trial 7 passed **mm-per-interval depths** directly into `total_precip`. If SWMM interpreted those as in/hr, storms were physically inflated (~25×). That likely explains baseline flooding ≈ 7183 and R6 = 9500. Research runs use the corrected physical convention; golden tests keep the legacy path (`physical_rain=False`) so Trial 7 regression stays intact.

## Data sources (observed only)
- Primary: NCEI HPD 15-min `USC00200230` (Ann Arbor U of Mich) — closest high-coverage COOP gauge (~69 km W of Detroit catchment; **not** on-site)
- Secondary: `USC00209218` (Ypsilanti)
- `data/unused/rain/raindata.csv` and `data/unused/rain/randomrainfall.xlsx` have
  **unknown provenance** and are excluded from reported runs (`--real-only`)
- Active catalogs live under `data/useful/`; NCEI downloads under `data/raw/`
  (see `data/README.md`)

## Baseline cache
Keys are `tag|inp_sha|storm_sha`. Current tag: **`v3-phys-timeseries`**. Older caches mixed
legacy (mm-as-in/hr) and physical rows — delete and rebuild after any unit change.

## Physical-rain injection (fixed)
Stock `Design_RG` is `INTENSITY 1:00` with API overrides. Sparse 15-min pulses
under-reported depth (e.g. 101.6 mm → `.rpt` 1.867 in vs 4.000 expected).

**Research path (`physical_rain=True` / `--real-only`):** each reset writes
`runs/_physical_active.inp` with `Design_RG INTENSITY 0:15` and TIMESERIES
`STORM15` (in/hr from `rain_to_gage_value`). No per-step API rain write.
Legacy Trial 7 (`physical_rain=False`) unchanged on `7MPF_CSO_08.inp`.

Baseline cache tag: `v3-phys-timeseries`.

## Storage fill vs rain
Under static gates, `fill_max` is invariant to rainfall scale (including k=0). Storage
nodes appear driven by baked-in `[INFLOWS]`, not the rain gage. Confirm under
non-static actions before interpreting R1/R2 / `r_close` as storm-responsive.
