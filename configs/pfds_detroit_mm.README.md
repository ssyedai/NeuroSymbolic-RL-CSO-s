# Atlas 14-derived PFDS table for Detroit catchment (mm)

Source: NOAA Atlas 14 Volume 8 AMS (https://hdsc.nws.noaa.gov/pub/hdsc/data/mw/dur*_ams_na14v8.txt).

Method:
- Fit GEV to AMS at **Detroit City AP** (60-min, 6-h, 24-h).
- Convert AMS→PDS ARI with Langbein; depths in→mm.
- **15-min** not published for Detroit City AP in Vol8 AMS; scaled from 60-min using median Ann Arbor 15/60 quantile ratio (0.937), then clipped so depths increase with duration.

Target point: catchment_approx_latlon in configs/data.json (7 Mile / Hubbell–Southfield, Detroit).
