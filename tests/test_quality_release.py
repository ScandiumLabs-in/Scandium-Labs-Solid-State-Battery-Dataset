"""Tests for the A1 schema expansion + A3/A4 quality script + C/D health/release."""

from __future__ import annotations

import json

import pandas as pd

from ssb_dataset.schema import ExperimentBlock, MaterialRecord, TextProvenanceBlock


# ── A1: ExperimentBlock schema expansion ──────────────────────────────────────


def test_experiment_block_has_new_fields():
    exp = ExperimentBlock()
    assert hasattr(exp, "pellet_diameter_mm")
    assert hasattr(exp, "humidity")
    assert hasattr(exp, "instrument")
    assert hasattr(exp, "equivalent_circuit")
    assert hasattr(exp, "dc_bias_V")
    assert hasattr(exp, "annealing_temperature_C")
    assert hasattr(exp, "annealing_time_h")


def test_experiment_block_defaults_none():
    exp = ExperimentBlock()
    for f in ("pellet_diameter_mm", "thickness_mm", "humidity", "instrument",
              "equivalent_circuit", "dc_bias_V", "annealing_temperature_C"):
        assert getattr(exp, f) is None


def test_experiment_block_accepts_values():
    exp = ExperimentBlock(pellet_diameter_mm=13.0, humidity="<0.1 ppm",
                          instrument="Solartron 1260", equivalent_circuit="R1-R2CPE",
                          dc_bias_V=0.01, annealing_temperature_C=900, annealing_time_h=2)
    assert exp.pellet_diameter_mm == 13.0
    assert exp.humidity == "<0.1 ppm"
    assert exp.instrument == "Solartron 1260"
    assert exp.equivalent_circuit == "R1-R2CPE"
    assert exp.dc_bias_V == 0.01


def test_material_record_embeds_new_experiment_fields():
    rec = MaterialRecord.model_validate({
        "identity": {"source_db": "literature_mined", "source_id": "lit-x",
                     "family": "sulfide", "confidence_tier": "verified_human"},
        "experiment": {"pellet_diameter_mm": 13.0, "humidity": "Ar glovebox",
                       "instrument": "SP-300", "equivalent_circuit": "R(Q(RW))"},
    })
    assert rec.experiment.pellet_diameter_mm == 13.0
    assert rec.experiment.equivalent_circuit == "R(Q(RW))"


# ── A2: TextProvenanceBlock evidence/source chain ─────────────────────────────


def test_text_provenance_has_full_evidence_chain():
    tp = TextProvenanceBlock()
    for f in ("source_doi", "source_journal", "source_year", "pdf_path",
              "evidence_page", "evidence_section", "evidence_table_number",
              "evidence_figure_number", "evidence_paragraph", "evidence_sentence"):
        assert hasattr(tp, f)


def test_text_provenance_accepts_figure():
    tp = TextProvenanceBlock(source_doi="10.1/x", evidence_page=3,
                             evidence_figure_number=2, evidence_paragraph="3",
                             evidence_sentence="measured at 25C")
    assert tp.evidence_figure_number == 2
    assert tp.evidence_paragraph == "3"


# ── A3/A4: build_quality.py ───────────────────────────────────────────────────


def test_build_quality_records(tmp_path):
    import scripts.build_quality as bq
    q = tmp_path / "queue.json"
    q.write_text(json.dumps({"items": [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/a", "status": "approved",
         "reviewer": "human-1", "page": "4", "evidence_sentence": "sigma 1e-3",
         "measurement_method": "EIS", "temperature_celsius": 25},
        {"review_id": "b", "composition": "Li6PS5Cl", "property": "activation_energy",
         "value": 0.26, "unit": "eV", "doi": "10.1/b", "status": "approved",
         "reviewer": "human-1", "page": "4", "evidence_sentence": "Ea 0.26"},
    ]}))
    bq.QUEUE = q
    bq.CONSENSUS = tmp_path / "none.json"
    df = bq.build_quality_records()
    assert len(df) == 2
    assert {"quality_score", "quality_grade", "quality_tier"} <= set(df.columns)
    assert df["quality_score"].between(0, 100).all()
    assert (df["quality_tier"] == "silver").all()


def test_build_quality_summarize(tmp_path):
    from scripts.build_quality import summarize
    df = pd.DataFrame({
        "quality_score": [90, 60],
        "quality_grade": ["A+", "C"],
        "quality_tier": ["gold", "silver"],
        "family": ["sulfide", "sulfide"],
    })
    s = summarize(df)
    assert s["records"] == 2
    assert s["gold_records"] == 1
    assert s["silver_records"] == 1
    assert s["family_scores"]["sulfide"]["n"] == 2


# ── C: health report extensions ───────────────────────────────────────────────


def test_health_missing_recommendations(tmp_path):
    from scripts.build_health_report import _missing_recommendations
    items = [
        {"status": "approved", "review_id": "r1", "composition": "Li6PS5Cl",
         "experiment": {"relative_density_pct": 97}},
        {"status": "approved", "review_id": "r2", "composition": "LLZO",
         "experiment": {}},
        {"status": "rejected", "review_id": "r3"},
    ]
    recs = _missing_recommendations(items)
    # Only approved records counted (2).
    assert recs["pelletizing_pressure_MPa"]["missing_count"] == 2
    assert recs["relative_density_pct"]["missing_count"] == 1
    assert "r1" not in recs["relative_density_pct"]["top_records"]


def test_health_quality_summary(tmp_path):
    from scripts.build_health_report import _quality_summary
    import scripts.build_health_report as hb
    p = tmp_path / "quality.parquet"
    pd.DataFrame({
        "quality_score": [95, 70],
        "quality_grade": ["A+", "B"],
        "quality_tier": ["gold", "silver"],
    }).to_parquet(p)
    hb.QUALITY = p
    s = _quality_summary()
    assert s["records"] == 2
    assert s["gold_pct"] == 50.0


def test_health_drift_baseline_established(tmp_path):
    from scripts.build_health_report import _drift_vs_previous
    import scripts.build_health_report as hb
    out = tmp_path / "health_report.json"
    hb.OUT_JSON = out
    report = {"verified_records": 44, "coverage": {"page": 45.5}, "family_balance": {"garnet": 10}}
    d = _drift_vs_previous(report)
    assert d.get("baseline_established") is True


def test_health_drift_detects_coverage_change(tmp_path):
    from scripts.build_health_report import _drift_vs_previous
    import scripts.build_health_report as hb
    out = tmp_path / "health_report.json"
    out.write_text(json.dumps({"verified_records": 40, "coverage": {"page": 30.0},
                               "family_balance": {"garnet": 10}}))
    hb.OUT_JSON = out
    report = {"verified_records": 50, "coverage": {"page": 55.0},
              "family_balance": {"garnet": 14}}
    d = _drift_vs_previous(report)
    assert d["coverage_drift_gt_5pct"]["page"] == 25.0
    assert d["family_drift_gt_2"]["garnet"] == 4
    assert d["record_count_change"] == 10


# ── D: release gates ──────────────────────────────────────────────────────────


def test_release_gates_evaluate(tmp_path):
    import scripts.release as rel

    # Populate a fake root with passing-gate inputs.
    root = tmp_path
    (root / "validation_output").mkdir()
    (root / "validation_output" / "validation_report.json").write_text(
        json.dumps({"passed": True, "family_distribution_flags": 0})
    )
    (root / "review_output").mkdir()
    (root / "review_output" / "queue.json").write_text(json.dumps({"items": []}))
    (root / "literature_output").mkdir()
    (root / "literature_output" / "health_report.json").write_text(json.dumps({
        "verified_records": 150,
        "total_records": 26000,
        "coverage": {"page": 97.0, "evidence_sentence": 98.0, "doi": 100.0,
                     "temperature_celsius": 95.0, "measurement_method": 88.0},
        "family_balance": {"sulfide": 3},
    }))
    (root / "review_output" / "duplicates.json").write_text(
        json.dumps({"duplicate_rate_pct": 0.0})
    )

    # Monkeypatch ROOT so check_gates reads the tmp tree.
    rel.ROOT = root
    gates = rel.check_gates()
    assert gates["validation_passed"]["ok"] is True
    assert gates["no_pending_review_flags"]["ok"] is True
    assert gates["evidence_coverage"]["ok"] is True
    assert gates["metadata_completeness"]["ok"] is True
    assert gates["doi_provenance"]["ok"] is True
    assert gates["min_verified_labels"]["ok"] is True
    assert gates["duplicate_rate"]["ok"] is True
    assert gates["min_total_records"]["ok"] is True


def test_release_gates_block_pending(tmp_path):
    import scripts.release as rel
    root = tmp_path
    (root / "review_output").mkdir()
    (root / "review_output" / "queue.json").write_text(json.dumps(
        {"items": [{"status": "pending", "review_id": "p1"}]}))
    rel.ROOT = root
    gates = rel.check_gates()
    assert gates["no_pending_review_flags"]["ok"] is False


def test_release_gates_tolerate_known_benign_benchmark(tmp_path):
    import scripts.release as rel
    root = tmp_path
    (root / "validation_output").mkdir()
    (root / "validation_output" / "validation_report.json").write_text(json.dumps({
        "passed": False, "family_distribution_flags": [], "cross_source_failed": 0,
        "extraction_audit": {"passed": True},
        "benchmark_compounds_failed": ["Li3xLa2/3-xTiO3"],
    }))
    (root / "review_output").mkdir()
    (root / "review_output" / "queue.json").write_text(json.dumps({"items": []}))
    (root / "literature_output").mkdir()
    (root / "literature_output" / "health_report.json").write_text(json.dumps({
        "verified_records": 150, "total_records": 26000,
        "coverage": {"page": 97.0, "evidence_sentence": 98.0, "doi": 100.0,
                     "temperature_celsius": 95.0, "measurement_method": 88.0},
    }))
    (root / "review_output" / "duplicates.json").write_text(json.dumps({"duplicate_rate_pct": 0.0}))
    rel.ROOT = root
    gates = rel.check_gates()
    assert gates["validation_passed"]["ok"] is True


def test_release_gates_block_unexpected_benchmark_failure(tmp_path):
    import scripts.release as rel
    root = tmp_path
    (root / "validation_output").mkdir()
    (root / "validation_output" / "validation_report.json").write_text(json.dumps({
        "passed": False, "family_distribution_flags": [], "cross_source_failed": 0,
        "extraction_audit": {"passed": True},
        "benchmark_compounds_failed": ["Li7La3Zr2O12"],
    }))
    (root / "review_output").mkdir()
    (root / "review_output" / "queue.json").write_text(json.dumps({"items": []}))
    (root / "literature_output").mkdir()
    (root / "literature_output" / "health_report.json").write_text(json.dumps({
        "verified_records": 150, "total_records": 26000,
        "coverage": {"page": 97.0, "evidence_sentence": 98.0, "doi": 100.0,
                     "temperature_celsius": 95.0, "measurement_method": 88.0},
    }))
    rel.ROOT = root
    gates = rel.check_gates()
    assert gates["validation_passed"]["ok"] is False


def test_release_report_renders(tmp_path):
    import scripts.release as rel
    report = {
        "version": "v0.2.0", "generated_at": "2026-08-01", "verified_records": 44,
        "materials_total": 65, "papers_total": 30, "consensus_n3": 9,
        "family_distribution": {"garnet": 10}, "quality_distribution": {},
        "gates": {"a": True, "b": False}, "gate_failures": ["b"],
    }
    md = rel.render_release_report_md(report)
    assert "v0.2.0" in md
    assert "PASS" in md and "FAIL" in md
    assert "b" in md


def test_release_artifacts_staged_with_checksums(tmp_path):
    import scripts.release as rel
    (tmp_path / "cleaning_output").mkdir()
    (tmp_path / "cleaning_output" / "canonical_dataset.parquet").write_bytes(b"x" * 100)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog")
    rel.ROOT = tmp_path
    rel.RELEASE_DIR = tmp_path / "release"
    staged = rel.stage_artifacts("v0.2.0")
    checksum = tmp_path / "release" / "v0.2.0" / "checksums.txt"
    assert checksum.exists()
    text = checksum.read_text()
    assert "scandium_dataset.parquet" in text
    assert len(text.splitlines()) == len(staged) - 1  # staged includes checksums.txt itself


# ── Release config (D: config-driven thresholds) ──────────────────────────────


def test_load_config_defaults_when_missing(tmp_path):
    import scripts.release as rel
    rel.CONFIG_PATH = tmp_path / "none.toml"
    cfg = rel.load_config()
    assert cfg["min_verified_labels"] == 100
    assert cfg["evidence_threshold"] == 95.0
    assert cfg["duplicate_threshold"] == 1.0


def test_load_config_reads_toml(tmp_path):
    import scripts.release as rel
    cfg_path = tmp_path / "release_config.toml"
    cfg_path.write_text("""
[release]
min_verified_labels = 250
evidence_threshold = 90
duplicate_threshold = 2
""")
    rel.CONFIG_PATH = cfg_path
    cfg = rel.load_config()
    assert cfg["min_verified_labels"] == 250
    assert cfg["evidence_threshold"] == 90.0
    # Untouched keys fall back to defaults.
    assert cfg["doi_threshold"] == 100.0


def test_config_drives_gate_thresholds(tmp_path):
    import scripts.release as rel
    root = tmp_path
    (root / "review_output").mkdir()
    (root / "review_output" / "queue.json").write_text(json.dumps({"items": []}))
    (root / "literature_output").mkdir()
    (root / "literature_output" / "health_report.json").write_text(json.dumps({
        "verified_records": 120, "total_records": 30000,
        "coverage": {"page": 92.0, "evidence_sentence": 92.0, "doi": 100.0,
                     "temperature_celsius": 95.0, "measurement_method": 85.0},
    }))
    (root / "review_output" / "duplicates.json").write_text(json.dumps({"duplicate_rate_pct": 0.0}))
    rel.ROOT = root
    # Evidence threshold 95 blocks at 92; a relaxed config passes.
    strict = dict(rel.DEFAULT_CONFIG, evidence_threshold=95.0, min_verified_labels=100)
    gates = rel.check_gates(strict)
    assert gates["evidence_coverage"]["ok"] is False
    relaxed = dict(rel.DEFAULT_CONFIG, evidence_threshold=90.0, min_verified_labels=100)
    gates2 = rel.check_gates(relaxed)
    assert gates2["evidence_coverage"]["ok"] is True


# ── C3 duplicate detection ────────────────────────────────────────────────────


def test_detect_duplicates_finds_intra_paper_duplicate():
    from scripts.detect_duplicates import detect_duplicates
    items = [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/x", "status": "approved"},
        {"review_id": "b", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/x", "status": "approved"},
        {"review_id": "c", "composition": "Li7La3Zr2O12", "property": "conductivity",
         "value": 1e-4, "unit": "S/cm", "doi": "10.2/y", "status": "approved"},
    ]
    report = detect_duplicates(items)
    assert report["duplicate_record_count"] == 2
    assert report["duplicate_rate_pct"] > 0.0
    assert report["duplicates_by_type"]["measurement"] == 1


def test_detect_duplicates_ignores_cross_paper_same_value():
    from scripts.detect_duplicates import detect_duplicates
    items = [
        {"review_id": "a", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.1/x", "status": "approved"},
        {"review_id": "b", "composition": "Li6PS5Cl", "property": "conductivity",
         "value": 1e-3, "unit": "S/cm", "doi": "10.2/y", "status": "approved"},
    ]
    report = detect_duplicates(items)
    assert report["duplicate_rate_pct"] == 0.0


def test_detect_duplicates_keeps_bulk_vs_total_distinct():
    from scripts.detect_duplicates import detect_duplicates
    items = [
        {"review_id": "a", "composition": "Li1.3Al0.3Ti1.7(PO4)3", "property": "conductivity",
         "value": 3e-4, "unit": "S/cm", "doi": "10.1/x", "status": "approved",
         "conductivity_type": "bulk", "temperature_celsius": 25},
        {"review_id": "b", "composition": "Li1.3Al0.3Ti1.7(PO4)3", "property": "conductivity",
         "value": 3e-4, "unit": "S/cm", "doi": "10.1/x", "status": "approved",
         "conductivity_type": "total", "temperature_celsius": 200},
    ]
    report = detect_duplicates(items)
    assert report["duplicate_rate_pct"] == 0.0


def test_detect_duplicates_empty():
    from scripts.detect_duplicates import detect_duplicates
    report = detect_duplicates([])
    assert report["total_records_checked"] == 0
    assert report["duplicate_rate_pct"] == 0.0
