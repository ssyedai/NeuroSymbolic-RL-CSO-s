"""Create a local, allowlisted reproduction archive; never uploads or sends it."""
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    root = Path("runs/hydraulic_validation_20261012")
    out = root / "weir_comparison/reproduction_package.zip"
    files = {
        "README.md": Path("docs/isolated_weir_verification_20261016.md"),
        **{f"research/{name}": Path("research")/name for name in (
            "weir_reproduction.py", "isolated_swmm_dll.py", "prepare_weir_engine.py",
            "report_weir_reproduction.py")},
        "tests/test_weir_reproduction.py": Path("tests/test_weir_reproduction.py"),
        "comparison/summary.json": root/"weir_comparison/summary.json",
        "comparison/comparison.csv": root/"weir_comparison/comparison.csv",
        "comparison/flow_verification.png": root/"weir_comparison/flow_verification.png",
        "experimental/diagnostic.patch": root/"engine_damped_source/diagnostic.patch",
        "experimental/diagnostic_config.json": root/"engine_damped_source/diagnostic_config.json",
    }
    for folder in ("weir_isolated", "weir_source_baseline", "weir_source_damped"):
        for name in ("run_config.json", "results.csv", "runner_source.py", "summary.json"):
            files[f"evidence/{folder}/{name}"] = root/folder/name
    # Original baseline INPs/reports are sufficient; rebuilt baseline inputs are identical.
    for path in (root/"weir_isolated").iterdir():
        if path.suffix in {".inp", ".rpt"}:
            files[f"models/{path.name}"] = path
    for folder in ("weir_isolated", "weir_source_damped"):
        for profile in ("tight", "extra_tight"):
            name = f"submerged_EXTRAN_{profile}_0.5.csv.gz"
            files[f"traces/{folder}/{name}"] = root/folder/name
    manifest = {name: dict(bytes=path.stat().st_size,
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                for name, path in sorted(files.items())}
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(files.items()):
            archive.write(path, name)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("RUNME.md", """# Reproduce the installed-engine experiment

Extract this archive into an empty folder. From that folder, with Python and
the dependencies listed in evidence/weir_isolated/run_config.json available:

    python -m research.weir_reproduction --out fresh-results

This runs 24 short synthetic simulations and saves inputs, reports, traces,
results.csv and a configuration. Do not reuse an existing output directory.
Compare results with evidence/weir_isolated/results.csv. The standalone INPs
in models/ can also be opened in SWMM; each filename identifies its conditions.
Their reports are supplied, but routing-step CSVs are needed to see oscillations
that a one-second report interval can miss.

The optional source-build experiment requires compiling the pinned OWA source
revision described in README.md. Its original archive URL is:
https://codeload.github.com/pyswmm/Stormwater-Management-Model/zip/27dc6990cda8bce21f6c16ddae631b37e7510ffc
Pass the separately built DLL explicitly with --dll; never replace the installed
engine. The experimental one-line patch is supplied for inspection and was NOT
accepted as a fix. Source-build result files are included under evidence/.

The report-generation command in README.md refers to the original repository's
directory layout. This compact archive instead supplies the completed report,
comparison files, selected plot traces and source scripts for inspection.
No full Detroit model, rainfall, checkpoints or compiled binaries are included.
The archive has not been sent or uploaded to anyone.
""")
    with zipfile.ZipFile(out) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive integrity failed")
        for name, record in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != record["sha256"]:
                raise ValueError(f"Archive content mismatch: {name}")
    result = dict(path=str(out), members=len(files)+2, bytes=out.stat().st_size,
                  sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
                  sent_or_uploaded=False, contents="Synthetic verification only; no full network, rainfall, checkpoints or DLLs")
    (out.parent/"package_manifest.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
