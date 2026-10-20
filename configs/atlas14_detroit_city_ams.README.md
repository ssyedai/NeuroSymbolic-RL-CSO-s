# Official Atlas 14 frequency point: Detroit City Airport

Selected under the user's authorization to use the Detroit airport area or an appropriate surrounding weather station. NOAA's GHCN inventory identifies **USW00014822, DETROIT CITY AP**, at **42.4072, −83.0089**. This preserves the station basis of the previous fitted table. It is distinct from Detroit Metropolitan Airport and is a representative rainfall-frequency point, not a surveyed sewer-network centroid.

Source: NOAA Atlas 14 **Volume 8, Version 2**, annual maxima series (AMS), precipitation depth in millimetres. Point estimates and lower/upper **90% confidence bounds** are saved in the three `atlas14_detroit_city_ams_*mm.csv` files. `atlas14_detroit_city_ams_provenance.json` records the source URL, coordinate choice and hashes. Raw response, official interface labels and station inventory rows are retained under `runs/noaa_verification_20261017/detroit_city_airport/`.

The response was parsed as literal values, never executed as code. Duration ordering and AMS frequency columns were checked against the official interface; positive, monotone depths and enclosing confidence bounds were checked. Durations include 60, **180**, 360 and 1440 minutes. Columns cover AEPs 1/2 through 1/1000. There is no 1-year AMS column; none has been invented. AMS AEP columns must not be silently relabelled as PDS return intervals.

Use `atlas14_detroit_city_ams_mm.csv` explicitly for the next scenario build. Existing `atlas14_mm.csv`, legacy fitted tables and previously generated scenarios are preserved for audit, not retrospectively certified. Rebuild and hash amplified scenarios and record the frequency-source change before research evaluation. These point rainfall estimates do not establish a catchment-wide flood return period or validate extreme-storm hydraulic extrapolation.

Official documentation: https://www.weather.gov/owp/hdsc_faqs (sections 2.5 and 3.1). Station inventory: https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt.
