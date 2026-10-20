"""Reporting: figures + REPORT.md for one multi-storm run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _rolling(s, w=50):
    return pd.Series(s).rolling(w, min_periods=1).mean().values


def make_figures(run: Path):
    fig_dir = run / "figures"
    fig_dir.mkdir(exist_ok=True)
    train = pd.read_csv(run / "train_log.csv") if (run / "train_log.csv").exists() else None
    eval_df = pd.read_csv(run / "eval_log.csv") if (run / "eval_log.csv").exists() else None
    final = pd.read_csv(run / "final_eval.csv") if (run / "final_eval.csv").exists() else None

    # 1. training curves
    if train is not None and len(train):
        fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
        axes[0].plot(train.episode, _rolling(train.cso_reduction_pct), color="C0")
        axes[0].set_ylabel("CSO red % (roll50)")
        axes[0].axhline(0, color="gray", ls=":")
        axes[1].plot(train.episode, train.alpha, color="C1")
        axes[1].set_ylabel("alpha")
        axes[2].plot(train.episode, _rolling(train.score_adv), color="C2")
        axes[2].set_ylabel("score_adv (roll50)")
        axes[2].set_xlabel("episode")
        fig.suptitle("Training curves")
        fig.tight_layout()
        fig.savefig(fig_dir / "training_curves.png", dpi=140)
        plt.close(fig)

        # 8. per-storm learning
        ids = sorted(train.storm_id.unique())
        n = len(ids)
        cols = min(3, n)
        rows = int(np.ceil(n / cols))
        fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 2.5 * rows), squeeze=False)
        for i, sid in enumerate(ids):
            ax = axes[i // cols][i % cols]
            sub = train[train.storm_id == sid]
            ax.plot(sub.episode, _rolling(sub.cso_reduction_pct, 20))
            ax.set_title(sid, fontsize=8)
            ax.axhline(0, color="gray", ls=":")
        for j in range(i + 1, rows * cols):
            axes[j // cols][j % cols].axis("off")
        fig.suptitle("Per-storm learning")
        fig.tight_layout()
        fig.savefig(fig_dir / "per_storm_learning.png", dpi=140)
        plt.close(fig)

    # 2. val progress
    if eval_df is not None and len(eval_df):
        v = eval_df[eval_df.phase == "val"]
        if len(v):
            g = v.groupby("episode").agg(
                macro=("cso_reduction_pct", "mean"),
                worst=("cso_reduction_pct", "min"),
                flood=("flood_ratio", "mean"),
            ).reset_index()
            fig, ax = plt.subplots(figsize=(9, 4))
            ax.plot(g.episode, g.macro, label="val macro CSO red %")
            ax.plot(g.episode, g.worst, label="val worst")
            ax.plot(g.episode, g.flood, label="flood_ratio_mean")
            te = eval_df[eval_df.phase == "train_eval"]
            if len(te):
                tg = te.groupby("episode")["cso_reduction_pct"].mean()
                ax.plot(tg.index, tg.values, ls="--", label="train_eval macro")
            if (run / "checkpoints" / "best_val.pt").exists():
                # mark last peak of macro as proxy if we don't store episode
                best_ep = g.episode.iloc[g.macro.idxmax()] if len(g) else None
                if best_ep is not None:
                    ax.axvline(best_ep, color="green", ls=":", label=f"best~{best_ep}")
            ax.legend(fontsize=8)
            ax.set_xlabel("episode")
            ax.set_title("Validation progress")
            fig.tight_layout()
            fig.savefig(fig_dir / "val_progress.png", dpi=140)
            plt.close(fig)

    if final is not None and len(final):
        # 3. per_storm_final
        fig, ax = plt.subplots(figsize=(10, 4))
        colors = {"train": "C0", "val": "C1", "test": "C2"}
        for sp, sub in final.groupby("split"):
            ax.bar(sub.storm_id, sub.cso_reduction_pct, color=colors.get(sp, "gray"),
                   label=sp, alpha=0.85)
        ax.axhline(0, color="black", lw=0.8)
        ax.axhline(final.cso_reduction_pct.mean(), color="red", ls="--",
                   label=f"macro={final.cso_reduction_pct.mean():.1f}")
        ax.set_ylabel("CSO reduction %")
        ax.set_title("Final per-storm CSO reduction")
        ax.legend(fontsize=8)
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        fig.savefig(fig_dir / "per_storm_final.png", dpi=140)
        plt.close(fig)

        # 4. severity scatter
        fig, ax = plt.subplots(figsize=(7, 5))
        for sp, sub in final.groupby("split"):
            ax.scatter(sub.rain_total_mm, sub.cso_reduction_pct,
                       label=sp, color=colors.get(sp, "gray"), s=60)
        ax.axhline(0, color="gray", ls=":")
        ax.set_xlabel("rain_total_mm")
        ax.set_ylabel("cso_reduction_pct")
        ax.legend()
        ax.set_title("Severity vs CSO reduction")
        fig.tight_layout()
        fig.savefig(fig_dir / "severity_scatter.png", dpi=140)
        plt.close(fig)

        # 5. cso vs baselines
        fig, ax = plt.subplots(figsize=(10, 4))
        x = np.arange(len(final))
        w = 0.25
        ax.bar(x - w, final.static_cso, width=w, label="static")
        if "native_cso" in final.columns:
            ax.bar(x, final.native_cso.fillna(0), width=w, label="native")
            ax.bar(x + w, final.cso_total, width=w, label="agent")
        else:
            ax.bar(x + w / 2, final.cso_total, width=w, label="agent")
        ax.set_xticks(x)
        ax.set_xticklabels(final.storm_id, rotation=45, ha="right")
        ax.set_ylabel("CSO total")
        ax.legend()
        ax.set_title("CSO vs baselines")
        fig.tight_layout()
        fig.savefig(fig_dir / "cso_vs_baselines.png", dpi=140)
        plt.close(fig)

        # 6. gates heatmap
        gate_cols = [c for c in final.columns if c.startswith("gate") and c.endswith("_mean")]
        if gate_cols:
            mat = final[gate_cols].to_numpy()
            fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(final))))
            im = ax.imshow(mat, aspect="auto", vmin=0, vmax=1, cmap="viridis")
            ax.set_yticks(range(len(final)))
            ax.set_yticklabels(final.storm_id)
            ax.set_xticks(range(len(gate_cols)))
            ax.set_xticklabels(gate_cols, rotation=45, ha="right")
            fig.colorbar(im, ax=ax, fraction=0.03)
            ax.set_title("Mean gate actions (final)")
            fig.tight_layout()
            fig.savefig(fig_dir / "gates_by_storm.png", dpi=140)
            plt.close(fig)

        # 7. safety
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.bar(final.storm_id, final.flood_ratio, alpha=0.7, label="flood_ratio")
        ax.plot(final.storm_id, final.r6_frac, "o-", color="C3", label="r6_frac")
        ax.axhline(1.05, color="red", ls="--", label="flood cap 1.05")
        ax.axhline(0.01, color="orange", ls=":", label="r6 cap 0.01")
        plt.xticks(rotation=45, ha="right")
        ax.legend(fontsize=8)
        ax.set_title("Safety metrics")
        fig.tight_layout()
        fig.savefig(fig_dir / "safety.png", dpi=140)
        plt.close(fig)


def write_report(run: Path):
    final_agg = {}
    if (run / "final_agg.json").exists():
        final_agg = json.loads((run / "final_agg.json").read_text())
    manifest = {}
    if (run / "storm_manifest.json").exists():
        manifest = json.loads((run / "storm_manifest.json").read_text())
    final = pd.read_csv(run / "final_eval.csv") if (run / "final_eval.csv").exists() else None

    lines = ["# Multi-storm run report", "", f"Run: `{run}`", ""]
    si = manifest.get("split_info", {})
    lines.append(f"- selection_on_train: **{si.get('selection_on_train', final_agg.get('selection_on_train'))}**")
    lines.append(f"- split counts: `{si.get('counts')}`")
    lines.append("")
    lines.append("## Final aggregates by split")
    lines.append("")
    for sp in ("train", "val", "test"):
        if sp in final_agg and isinstance(final_agg[sp], dict):
            lines.append(f"### {sp}")
            for k, v in final_agg[sp].items():
                lines.append(f"- {k}: {v}")
            lines.append("")
    if final is not None:
        lines.append("## Per-storm final")
        lines.append("")
        cols = [c for c in ["storm_id", "split", "cso_total", "cso_reduction_pct",
                            "flood_ratio", "r6_frac", "score"] if c in final.columns]
        lines.append(final[cols].to_markdown(index=False))
        lines.append("")
    lines.append("## Figures")
    for p in sorted((run / "figures").glob("*.png")):
        lines.append(f"- `{p.name}`")
    (run / "REPORT.md").write_text("\n".join(lines))
    print(f"Wrote {run / 'REPORT.md'}")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, help="Path to runs/<name>")
    args = p.parse_args(argv)
    run = Path(args.run)
    make_figures(run)
    write_report(run)


if __name__ == "__main__":
    main()
