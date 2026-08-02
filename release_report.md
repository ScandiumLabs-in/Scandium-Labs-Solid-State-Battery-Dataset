# Scandium Dataset — Release Report

- Version: **v0.2.0**
- Generated: 2026-08-02T20:31:27.479637+00:00

## Dataset size

- Verified experimental records: **116**
- Materials (consensus DB): 387
- Papers: 154
- Materials with consensus (n≥3): 20

## Release gates

| Gate | Status |
|---|---|
| tests_passing | PASS |
| validation_passed | FAIL |
| no_pending_review_flags | FAIL |
| evidence_coverage | FAIL |
| duplicate_rate | PASS |
| metadata_completeness | FAIL |
| doi_provenance | PASS |
| min_verified_labels | PASS |
| min_total_records | PASS |
| health_report_generated | PASS |

**Failing gates:** validation_passed, no_pending_review_flags, evidence_coverage, metadata_completeness

## Quality distribution

```json
{
  "records": 143,
  "score_avg": 47.7,
  "score_min": 35,
  "score_max": 66,
  "grade_distribution": {
    "C": 87,
    "D": 51,
    "B": 5
  },
  "tier_distribution": {
    "silver": 138,
    "rejected": 5
  },
  "tier_pct": {
    "gold": 0.0,
    "silver": 96.5,
    "bronze": 0.0,
    "rejected": 3.5
  },
  "gold_records": 0,
  "silver_records": 138,
  "bronze_records": 0,
  "rejected_records": 5,
  "family_scores": {
    "LLZO": {
      "n": 1,
      "avg_score": 47.0,
      "tiers": {
        "silver": 1
      }
    },
    "antiperovskite": {
      "n": 5,
      "avg_score": 45.4,
      "tiers": {
        "silver": 5
      }
    },
    "argyrodite": {
      "n": 11,
      "avg_score": 50.2,
      "tiers": {
        "silver": 10,
        "rejected": 1
      }
    },
    "borohydride": {
      "n": 12,
      "avg_score": 46.2,
      "tiers": {
        "silver": 11,
        "rejected": 1
      }
    },
    "garnet": {
      "n": 20,
      "avg_score": 45.3,
      "tiers": {
        "silver": 20
      }
    },
    "halide": {
      "n": 12,
      "avg_score": 47.7,
      "tiers": {
        "silver": 12
      }
    },
    "hydride": {
      "n": 2,
      "avg_score": 44.0,
      "tiers": {
        "silver": 2
      }
    },
    "nasicon": {
      "n": 22,
      "avg_score": 48.0,
      "tiers": {
        "silver": 22
      }
    },
    "oxide": {
      "n": 9,
      "avg_score": 43.9,
      "tiers": {
        "silver": 9
      }
    },
    "perovskite": {
      "n": 14,
      "avg_score": 49.6,
      "tiers": {
        "silver": 13,
        "rejected": 1
      }
    },
    "polymer_composite": {
      "n": 28,
      "avg_score": 49.4,
      "tiers": {
        "silver": 26,
        "rejected": 2
      }
    },
    "sulfide": {
      "n": 7,
      "avg_score": 50.6,
      "tiers": {
        "silver": 7
      }
    }
  }
}
```

## Family distribution

| Family | Records |
|---|---|
| polymer_composite | 24 |
| garnet | 18 |
| nasicon | 13 |
| perovskite | 10 |
| sulfide | 9 |
| halide | 9 |
| antiperovskite | 8 |
| unknown | 7 |
| argyrodite | 6 |
| borohydride | 5 |
| oxide | 5 |
| hydride | 2 |
