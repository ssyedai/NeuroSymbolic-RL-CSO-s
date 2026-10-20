# Research data card — working diagnostic release

Historical storm shapes come from the repository's NCEI 15-minute rainfall archive, primarily Ann Arbor station USC00200230. This is spatially displaced from the sewer model. Do not describe those records as on-site Detroit airport gauge observations. Family R is unscaled observed rainfall; T/C/F are prebuilt amplified children and must be labelled accordingly.

Parents and all their children share a year-based split. Retain VAL 2021–2022 and TEST 2023–2026 as the user requested. Prior project work examined TEST results; disclose that exposure. No new test-set tuning is permitted, and the retained test set must not be described as wholly untouched. A year listed in the split definition is not evidence that every month or event in that year has been observed.

The user authorized an appropriate Detroit airport-area weather station for frequency estimates. Official Atlas 14 AMS depths and 90% confidence bounds have been retrieved at Detroit City Airport, 42.4072, −83.0089, NOAA station USW00014822. This is the representative frequency point, separate from the historical hyetograph gauge. See `configs/atlas14_detroit_city_ams.README.md`. The old fitted frequency table is not an official NOAA point table. Existing amplified manifests must be rebuilt before claiming agreement with the newly verified frequencies.

Preserve raw rainfall and scenario hashes. Research loading must enforce provenance, physical units and no on-the-fly scaling. Return-period labels are duration-specific rainfall estimates, not flood probabilities. The hydraulic calibration range does not establish model accuracy at 200–1000-year rainfall. Official confidence bounds describe uncertainty in rainfall-frequency estimates; they do not encompass all hydraulic or controller uncertainty.

The optional September 2018/August 2019 local anchor-event gauge records remain unverified/unavailable in the current evidence package. Do not substitute unrelated events while retaining those names. Missing results and failed hydraulic checks must remain visible in final reporting.
