# Scandium Benchmark Suite — v0.8.0 baseline results

Generated 2026-08-06T18:41:09 · None canonical rows · deterministic sklearn baselines (dummy / linear / random forest) on the leakage-checked test split **+ dataset_ml GCN baseline (v1.3.0)**.

| Task | Type | n_train | n_test | Best model | Primary metric | Value |
|---|---|---:|---:|---|---|---:|
| Band gap regression | regression | 16394 | 3248 | rf | mae | 0.4390 |
| Conductive-candidate ranking | ranking | 166 | 166 | rf | ndcg10 | 0.5726 |
| Crystal system prediction | classification | 15064 | 3228 | rf | macro_f1 | 0.8376 |
| Density regression | regression | 15064 | 3228 | rf | mae | 0.1088 |
| Energy above hull regression | regression | 15064 | 3228 | rf | mae | 0.0353 |
| Family classification | classification | 17046 | 3370 | rf | macro_f1 | 0.8476 |
| Formation energy regression | regression | 16394 | 3248 | rf | mae | 0.0762 |
| Ionic-radius regression | regression | 15064 | 3228 | rf | mae | 0.0081 |
| Space group prediction | classification | 15064 | 3228 | rf | top5_accuracy | 0.8869 |
| Stable vs unstable classification | classification | 15064 | 3228 | rf | macro_f1 | 0.9307 |
| Volume regression | regression | 15064 | 3228 | rf | mae | 14.9705 |
| Wide-gap classification (E_g > 4 eV) | classification | 11566 | 2298 | rf | macro_f1 | 0.8292 |

## GCN baseline details (dataset_ml crystal graphs)

| Task | GCN n_train | GCN n_test | Epochs | Architecture |
|---|---|---:|---:|---|
| Band gap regression | 15064 | 3228 | 40 | GCN hidden=64 layers=3 |
| Conductive-candidate ranking | 164 | 35 | 9 | GCN hidden=64 layers=3 |
| Crystal system prediction | 15064 | 3228 | 40 | GCN hidden=64 layers=3 |
| Density regression | 15064 | 3228 | 37 | GCN hidden=64 layers=3 |
| Energy above hull regression | 15064 | 3228 | 20 | GCN hidden=64 layers=3 |
| Family classification | 15064 | 3228 | 40 | GCN hidden=64 layers=3 |
| Formation energy regression | 15064 | 3228 | 25 | GCN hidden=64 layers=3 |
| Ionic-radius regression | 15064 | 3228 | 40 | GCN hidden=64 layers=3 |
| Space group prediction | 15064 | 3228 | 40 | GCN hidden=64 layers=3 |
| Stable vs unstable classification | 15064 | 3228 | 9 | GCN hidden=64 layers=3 |
| Volume regression | 15064 | 3228 | 40 | GCN hidden=64 layers=3 |
| Wide-gap classification (E_g > 4 eV) | 10744 | 2279 | 40 | GCN hidden=64 layers=3 |
