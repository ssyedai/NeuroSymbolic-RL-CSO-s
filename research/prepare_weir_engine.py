"""Create an explicitly experimental source copy with stronger damping.

This prepares a separate build; never installs or replaces any engine.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    target = args.source / "src/solver/dynwave.c"
    before = target.read_text()
    needle = "static const double OMEGA               = 0.5;"
    if before.count(needle) != 1:
        raise ValueError("Unexpected source; refuse unverified patch")
    after = before.replace(needle, "static const double OMEGA               = 0.1;")
    shutil.copytree(args.source, args.out)  # fails if destination already exists
    (args.out / "src/solver/dynwave.c").write_text(after)
    (args.out / "diagnostic.patch").write_text("".join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile="baseline/src/solver/dynwave.c",
        tofile="experimental/src/solver/dynwave.c")))
    hashes = {str(p.relative_to(args.source)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in args.source.rglob("*") if p.is_file()}
    (args.out / "diagnostic_config.json").write_text(json.dumps(dict(
        purpose="Isolated experimental damping comparison; no production adoption",
        upstream_commit="27dc6990cda8bce21f6c16ddae631b37e7510ffc",
        original_source_hashes=hashes, changed_file="src/solver/dynwave.c",
        before_omega=.5, after_omega=.1,
        changed_sha256=hashlib.sha256((args.out / "src/solver/dynwave.c").read_bytes()).hexdigest()), indent=2))


if __name__ == "__main__":
    main()
