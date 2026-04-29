"""
统计分析脚本 — 实验结果后处理

用法:
    cd experiment/analysis
    python stats.py [--results-dir ../results]

依赖:
    pip install pandas numpy scipy scikit-posthocs
"""
import os
import sys
import json
import argparse
import pandas as pd
import numpy as np
from scipy.stats import friedmanchisquare

# ── Bonferroni-corrected significance level ──
# 5 methods → C(5,2) = 10 pairwise comparisons
# α_corrected = 0.05 / 10 = 0.005
ALPHA = 0.005


def load_results(results_dir: str) -> pd.DataFrame:
    """Load all result.json files into a DataFrame."""
    data = []
    failed_runs = 0

    for run_dir in sorted(os.listdir(results_dir)):
        result_path = os.path.join(results_dir, run_dir, 'result.json')
        if not os.path.exists(result_path):
            continue
        try:
            with open(result_path, 'r') as f:
                res = json.load(f)
            metrics = res.get('metrics', {})
            config = res.get('config', {})

            # Gracefully handle missing fields
            static_input = metrics.get('staticInputTokens', 0)
            total_tokens = metrics.get('totalTokens', 0)
            main_total = metrics.get('mainAgentTokens', {}).get('total', 0)
            sub_total = metrics.get('subAgentTokens', {}).get('total', 0)
            dynamic_total = total_tokens - static_input

            data.append({
                'method': config.get('method', 'unknown'),
                'task': config.get('task', 'unknown'),
                'run': config.get('run', 0),
                'passed': 1 if res.get('testsPassed') else 0,
                'totalTokens': total_tokens,
                'totalCostCny': metrics.get('totalCostCny', 0),
                'totalCostUsd': metrics.get('totalCostUsd', 0),
                'durationSec': res.get('durationMs', 0) / 1000,
                # MOR_AO: sub-agent tokens as fraction of dynamic (non-static) tokens
                'mor_ao': (sub_total / dynamic_total) if dynamic_total > 0 else 0,
                'mainTokens': main_total,
                'subTokens': sub_total,
                # Per-model usage (for cost attribution)
                'modelUsage': metrics.get('modelUsage', {}),
            })
        except Exception as e:
            print(f"  [warn] Failed to parse {result_path}: {e}", file=sys.stderr)
            failed_runs += 1

    df = pd.DataFrame(data)
    print(f"Loaded {len(df)} valid runs ({failed_runs} corrupted/skipped)")
    return df


def check_matrix(df: pd.DataFrame) -> None:
    """Print sample matrix to verify completeness."""
    counts = df.groupby(['method', 'task']).size().unstack(fill_value=0)
    print("\n── Sample Matrix (runs per method × task) ──")
    print(counts.to_string())
    print()


def descriptive_stats(df: pd.DataFrame) -> None:
    """Print per-method summary statistics for primary metrics."""
    primary = ['passed', 'totalTokens', 'totalCostCny', 'durationSec', 'mor_ao']
    print("── Descriptive Statistics (mean ± std) ──")
    summary = df.groupby('method')[primary].agg(['mean', 'std'])
    # Flatten column names
    summary.columns = [f"{col}_{stat}" for col, stat in summary.columns]
    print(summary.to_string())
    print()


def friedman_test(df: pd.DataFrame, metric: str) -> None:
    """Run Friedman test on a metric across methods (per-task blocks)."""
    # Pivot: rows = (task, run) blocks, columns = methods
    pivot = df.pivot_table(index=['task', 'run'], columns='method', values=metric)
    pivot = pivot.dropna()

    if pivot.shape[1] < 3:
        print(f"  [skip] Friedman requires ≥ 3 methods, got {pivot.shape[1]}")
        return

    groups = [pivot[col].values for col in pivot.columns]
    stat, p = friedmanchisquare(*groups)

    print(f"  Friedman ({metric}): χ²={stat:.3f}, p={p:.4e} {'***' if p < ALPHA else '(n.s.)'}")

    if p < ALPHA:
        try:
            import scikit_posthocs as sp
            melted = pivot.melt(var_name='method', value_name=metric)
            posthoc = sp.posthoc_nemenyi_friedman(melted, y_col=metric, group_col='method')
            print(f"  Post-hoc Nemenyi (α={ALPHA}):")
            print(posthoc.to_string())
        except ImportError:
            print("  [warn] scikit-posthocs not installed, skipping post-hoc. pip install scikit-posthocs")
    print()


def main():
    parser = argparse.ArgumentParser(description='MEM experiment analysis')
    parser.add_argument('--results-dir', default='./results', help='Path to results/ directory')
    args = parser.parse_args()

    results_dir = os.path.abspath(args.results_dir)
    if not os.path.isdir(results_dir):
        print(f"Results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    df = load_results(results_dir)
    if df.empty:
        print("No valid data found.")
        sys.exit(1)

    check_matrix(df)
    descriptive_stats(df)

    print(f"── Friedman Tests (Bonferroni α={ALPHA}) ──")
    for metric in ['totalTokens', 'mor_ao', 'durationSec']:
        friedman_test(df, metric)

    # Pass rate comparison (descriptive, not Friedman — binary outcome)
    print("── Pass Rate by Method ──")
    pass_rate = df.groupby('method')['passed'].agg(['mean', 'sum', 'count'])
    pass_rate.columns = ['pass_rate', 'passed', 'total']
    print(pass_rate.to_string())
    print()


if __name__ == "__main__":
    main()
