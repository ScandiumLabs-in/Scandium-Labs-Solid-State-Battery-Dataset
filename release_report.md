# Scandium Dataset — Release Report

- Version: **v1.9.0**
- Generated: 2026-08-07T03:14:47.865943+00:00

## Dataset size

- Verified experimental records: **183**
- Materials (consensus DB): 427
- Papers: 244
- Materials with consensus (n≥3): 20

## Release gates

| Gate | Status |
|---|---|
| tests_passing | PASS |
| validation_passed | PASS |
| no_pending_review_flags | PASS |
| evidence_coverage | PASS |
| duplicate_rate | PASS |
| metadata_completeness | PASS |
| doi_provenance | PASS |
| min_verified_labels | PASS |
| min_total_records | PASS |
| health_report_generated | PASS |
| min_gold_pct | PASS |
| canonical_quality_scored | PASS |
| anomaly_report_passed | PASS |
| unit_normalization_passed | PASS |
| relational_tables_built | PASS |
| measurement_provenance | PASS |
| multi_experiment_preserved | PASS |
| ml_export_built | PASS |
| papers_metadata_recovered | PASS |
| cross_db_validation | PASS |
| negative_results_built | PASS |
| scandium_bench_built | PASS |

## Quality distribution

```json
{
  "records": 244,
  "score_avg": 63.6,
  "score_min": 44,
  "score_max": 78,
  "grade_distribution": {
    "C": 124,
    "B": 119,
    "D": 1
  },
  "tier_distribution": {
    "silver": 239,
    "rejected": 5
  },
  "tier_pct": {
    "gold": 0.0,
    "silver": 98.0,
    "bronze": 0.0,
    "rejected": 2.0
  },
  "gold_records": 0,
  "silver_records": 239,
  "bronze_records": 0,
  "rejected_records": 5,
  "family_scores": {
    "LLZO": {
      "n": 1,
      "avg_score": 54.0,
      "tiers": {
        "silver": 1
      }
    },
    "antiperovskite": {
      "n": 6,
      "avg_score": 59.3,
      "tiers": {
        "silver": 6
      }
    },
    "argyrodite": {
      "n": 20,
      "avg_score": 66.8,
      "tiers": {
        "silver": 19,
        "rejected": 1
      }
    },
    "borohydride": {
      "n": 13,
      "avg_score": 65.5,
      "tiers": {
        "silver": 12,
        "rejected": 1
      }
    },
    "complex_hydride": {
      "n": 2,
      "avg_score": 76.0,
      "tiers": {
        "silver": 2
      }
    },
    "garnet": {
      "n": 41,
      "avg_score": 62.9,
      "tiers": {
        "silver": 41
      }
    },
    "halide": {
      "n": 34,
      "avg_score": 60.6,
      "tiers": {
        "silver": 34
      }
    },
    "hydride": {
      "n": 3,
      "avg_score": 61.7,
      "tiers": {
        "silver": 3
      }
    },
    "nasicon": {
      "n": 34,
      "avg_score": 63.9,
      "tiers": {
        "silver": 34
      }
    },
    "oxide": {
      "n": 16,
      "avg_score": 63.2,
      "tiers": {
        "silver": 16
      }
    },
    "perovskite": {
      "n": 20,
      "avg_score": 67.3,
      "tiers": {
        "silver": 19,
        "rejected": 1
      }
    },
    "polymer_composite": {
      "n": 41,
      "avg_score": 63.8,
      "tiers": {
        "silver": 39,
        "rejected": 2
      }
    },
    "sulfide": {
      "n": 10,
      "avg_score": 63.3,
      "tiers": {
        "silver": 10
      }
    },
    "unknown": {
      "n": 3,
      "avg_score": 59.3,
      "tiers": {
        "silver": 3
      }
    }
  }
}
```

## Family distribution

| Family | Records |
|---|---|
| polymer_composite | 35 |
| garnet | 30 |
| halide | 21 |
| nasicon | 20 |
| perovskite | 15 |
| argyrodite | 15 |
| sulfide | 11 |
| antiperovskite | 9 |
| unknown | 9 |
| oxide | 9 |
| borohydride | 6 |
| hydride | 3 |
