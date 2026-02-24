# V6.2 Weight Optimization (Colab-Ready)

Self-contained implementation of the V6.2 sector-weight optimization playbook
from `weight-optimization-suggestions.md`. Upload this **entire folder** to Colab
and run the included notebook.

## Package contents

| File / folder                      | Purpose                                                                   |
| ---------------------------------- | ------------------------------------------------------------------------- |
| `v6_2_optimization.ipynb`          | **Colab notebook** — open this first                                      |
| `run_weight_optimization.py`       | CLI pipeline (discrete, LHS, TPE, NSGA-II, nested WF, deployment ranking) |
| `engine/sector_engine_v6_2_opt.py` | V6.2 engine with optional `sector_weights` / `bias_threshold` params      |
| `engine/v6lite/`                   | Local copies of `config.py` and `brain.py` (no broker deps)               |
| `engine/indicators.py`             | Broker-free indicator math                                                |
| `config/universe.json`             | Stock/sector universe definition                                          |
| `requirements.txt`                 | Python dependencies                                                       |

## Data requirement

The pipeline reads OHLCV parquet data. Provide a folder containing:

```
<data_root>/
  daily/*.parquet
  5minute/*.parquet
```

Point `--data-root` to this folder, or use your existing `backtest_v6/data`.

## Colab quick start (notebook)

1. Upload this folder to `/content/v6_2_weight_opt_colab_package/`
2. Upload your parquet data to Google Drive (or alongside the package)
3. Open **`v6_2_optimization.ipynb`** in Colab
4. Edit `DATA_ROOT` in cell 3 to point to your data
5. Run cells in order — smoke test first, then full optimization

## Colab quick start (CLI)

```bash
!pip install -q optuna>=3.6.0 pyarrow>=14.0.0 scipy>=1.10.0
```

### Smoke test (~2-5 min)

```bash
!python /content/v6_2_weight_opt_colab_package/run_weight_optimization.py \
  --data-root /content/drive/MyDrive/backtest_v6/data \
  --start-date 2025-03-01 --end-date 2025-05-31 \
  --train-months 1 --test-months 1 --min-folds 1 \
  --discrete-trials 4 --coarse-trials 4 --tpe-trials 4 --nsga-trials 4 \
  --shortlist-from-each 2 --shortlist-size 4 \
  --min-trades 1 --min-total-trades 1 \
  --results-dir /content/v6_2_weight_opt_colab_package/results_smoke
```

### Medium run (~2-4 hours)

```bash
!python /content/v6_2_weight_opt_colab_package/run_weight_optimization.py \
  --data-root /content/drive/MyDrive/backtest_v6/data \
  --start-date 2025-03-01 --end-date 2025-12-31 \
  --train-months 4 --test-months 1 --min-folds 5 \
  --discrete-trials 32 --coarse-trials 80 --tpe-trials 200 --nsga-trials 120 \
  --shortlist-from-each 20 --shortlist-size 30 \
  --results-dir /content/v6_2_weight_opt_colab_package/results
```

### Full institutional run (~6-12 hours)

```bash
!python /content/v6_2_weight_opt_colab_package/run_weight_optimization.py \
  --data-root /content/drive/MyDrive/backtest_v6/data \
  --start-date 2025-03-01 --end-date 2025-12-31 \
  --train-months 4 --test-months 1 --min-folds 5 \
  --discrete-trials 64 --coarse-trials 200 --tpe-trials 600 --nsga-trials 400 \
  --shortlist-from-each 30 --shortlist-size 40 \
  --results-dir /content/v6_2_weight_opt_colab_package/results
```

Optional: pass your V6.2 analysis JSON to auto-load baseline hurdles:

```bash
--baseline-analysis-json /content/drive/MyDrive/backtest_v6/analysis_v6.2/advanced_analysis_24-02-2026_03-34_pm.json
```

## Output artifacts

Each run creates `results/weight_opt_<timestamp>/` containing:

| File                         | Description                                        |
| ---------------------------- | -------------------------------------------------- |
| `run_config.json`            | Full configuration snapshot (folds, args, hurdles) |
| `baseline_fold_test.csv`     | Default V6.2 OOS metrics per fold                  |
| `phase_discrete.csv`         | Discrete grid search results                       |
| `phase_coarse_lhs.csv`       | Latin Hypercube exploration results                |
| `phase_tpe.csv`              | Bayesian TPE optimization results                  |
| `phase_nsga2.csv`            | NSGA-II multi-objective results                    |
| `shortlist.csv`              | Top candidates from all phases                     |
| `deployment_ranking.csv`     | Final ranking with eligibility flags               |
| `nested_walk_forward.json`   | Nested WF inner/outer fold details                 |
| `best_candidate_report.json` | Winner params, stats, bootstrap CIs                |

## Optimization objectives

The composite objective (from Section 5 of the playbook):

```
score = 0.30 * norm(Return)
      + 0.20 * norm(Sortino)
      + 0.15 * norm(ProfitFactor, capped)
      + 0.15 * norm(Expectancy)
      + 0.05 * norm(WinRate)
      - 0.15 * norm(MaxDrawdown)
      - trade_penalty - instability_penalty - concentration_penalty
```

## Deployment criteria

A candidate is **eligible** only if it:

1. Beats default V6.2 on a **majority** of OOS folds (return > base, DD ≤ base, PF > base)
2. Passes **absolute hurdles** (Return > 15.32%, DD < 9.12%, PF > 1.09, Expectancy > ₹64.43)
3. Overfit gap ≤ 0.12 (train score − test score)
4. Total OOS trades ≥ 700

## Cleanup before uploading

Delete `__pycache__/` folders and `results_smoke/` before uploading to Colab:

```bash
# Windows
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Remove-Item -Recurse -Force results_smoke

# Linux/Mac
find . -type d -name __pycache__ -exec rm -rf {} +
rm -rf results_smoke
```
