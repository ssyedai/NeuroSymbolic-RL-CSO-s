# Reproducing the current diagnostic release

This is a reproducible **blocked research checkpoint**, not a finished thesis release. No command here trains a controller or certifies the legacy results.

The 2026-10-20 integrated storage-volume experiment is documented in `docs/integral_storage_verification_20261020.md`. Its separate source is `runs/hydraulic_validation_20261020/integral_storage_source/`. Build it in a fresh CMake directory using the configuration/build commands below with that source path. This candidate inherits the earlier experimental orifice and conduit changes; it is not stock SWMM.

`research.tabular_balance_probe --dll <DLL> --out <fresh-directory>` compares the actual 7M storage curves with an independent integrated-volume solution for filling. Add `--inflow -65` for the bounded draining fixture; its 300-second duration preserves the fully submerged reference regime. `research.localize_stride_overflow --prior <saved-network-directory> --out <fresh-directory>` verifies cumulative-counter replays without changing scheduling. `research.report_stride_localization --root <replay-directory>` writes a diagnostic figure and interval attribution.

The control-change logger is verified. The first compiled version emitted only headers because a NaN sentinel was invalid under Release `/fp:fast`; the corrected finite sentinel reproduces final metrics and records native transitions. The predicate-level and frozen-control follow-ups are documented in `native_control_resolution_20261020.md`. Empty logs alone are still not evidence; the frozen-control probe requires exactly one initialization record per regulator/pump and rejects changed generated inputs on resume.

Use the Windows environment recorded in `requirements-windows-tested.txt` and the exact package inventory `runs/hydraulic_validation_20261017/environment_packages.json`. One SWMM simulation per process; the diagnostics below run serially. The installed engine is unchanged.

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q
.\.venv-win\Scripts\python.exe -m research.verify_noaa_table --directory runs/noaa_verification_20261017/detroit_city_airport
```

The NOAA command parses saved official data; it does not contact a server or rebuild historical scenarios. Use the verified airport-point CSV explicitly when the scenario rebuild is released. Preserve the old manifests for traceability.

To rebuild the current unvalidated surface-transition diagnostic DLL, use the saved complete source at `runs/hydraulic_validation_20261019/surface_transition_source/`:

```powershell
cmake -S runs/hydraulic_validation_20261019/surface_transition_source -B runs/hydraulic_validation_20261019/surface_transition_rebuild -G "Visual Studio 17 2022" -A x64 -DBUILD_TESTS=OFF -DBUILD_DOCS=OFF
cmake --build runs/hydraulic_validation_20261019/surface_transition_rebuild --config Release --parallel 2
```

That directory includes the pinned upstream-source lineage, successive diagnostic patches and the surface-transition patch/configuration. It is an alternative formulation, not a supported upstream engine release. Existing scripts `research.weir_reproduction`, `research.orifice_reproduction` and `research.continuous_orifice_probe` accept `--dll` for isolated verification. Use fresh output directories. `research.network_dll_probe --dll <DLL> --out <fresh-directory>` replays the fixed TRAIN storm at the default three resolutions with a 900-second total budget; add `--routing-seconds 0.125` for the separate third-refinement diagnostic. It is expected to report the documented failed native refinement. `research.prepare_predicate_trace` builds the bounded read-only 7M rule-predicate observer. `research.frozen_control_probe` compares already-generated TRAIN inputs with the complete control block removed; this is causal attribution only and never a native comparator.

`research.parent_statistics` accepts an explicitly supplied results file with matched method/seed/parent/storm IDs and all four outfall volumes. It checks accounting, aggregates children within parent/family/rung, and produces bootstrap intervals, paired tests and Holm corrections. It has only been verified with synthetic test fixtures; no final thesis statistics have been generated. Final planned comparisons must share one declared multiplicity family. Interpretation of statistics requires independently validated experiments.

For a full thesis release, retain raw rainfall licensing/provenance, scenario manifests, split definitions, reference and hindsight outputs, calibrated rule parameters, all seed checkpoints, evaluation outputs and a frozen versioned protocol. Those later-stage artifacts are not supplied by this diagnostic checkpoint. The review archive contains source and compact diagnostic evidence, not the entire rainfall archive or all SWMM binary outputs.

## Current read-only diagnostics

`research.prepare_window_trace` and `research.prepare_balance_bins` generate separate instrumented source trees from the rejected conduit-bypass source. Build them with the same CMake command pattern. `research.run_window_trace --prior runs/hydraulic_validation_20261019/network_balance_bypass --dll <instrumented-DLL> --out <fresh-directory>` verifies final recorded metrics against the saved uninstrumented TRAIN runs. Use `--balance-bins` with the balance-bins DLL. The executed sources and exact commands are recoverable from the dated source folders and run configurations. Instrumentation is not a solver repair. See `docs/internal_balance_diagnosis_20261019.md`.

The compiled surface-boundary checks and regulator suites are documented in `docs/conduit_surface_transition_20261019.md`. Rebuilds use fresh build/output folders. A successful software build or isolated test does not release the training block. `research.package_diagnostic_checkpoint --out <new-zip-path>` packages current code and selected evidence and verifies every archived entry against its SHA-256 manifest; it deliberately excludes full rainfall and binary simulation/checkpoint artifacts.
