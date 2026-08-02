#!/usr/bin/env python3
"""Scandium Labs SSB Dataset — pipeline CLI orchestrator.

Usage:
    python run.py survey          # Phase 1: source inventory survey
    python run.py ingest          # Phase 2: run ingestion pipeline
    python run.py literature      # Phase 3: literature discovery + extraction
    python run.py clean           # Phase 4: clean, deduplicate, canonicalize
    python run.py dft             # Phase 5: DFT gap-filling compute
    python run.py featurize       # Phase 6: feature engineering
    python run.py validate        # Phase 7: validation + QC
    python run.py docs            # Phase 8: documentation generation
    python run.py release         # Phase 9-10: publish release
    python run.py all             # Run all phases sequentially
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from ssb_dataset.config.settings import settings  # noqa: E402
from ssb_dataset.pipeline.ingest import run_ingestion  # noqa: E402
from ssb_dataset.pipeline.validation import generate_report, run_validation  # noqa: E402
from ssb_dataset.sources import (  # noqa: E402
    AFLOWConnector,
    ICSDConnector,
    JARVISConnector,
    MPConnector,
    NOMADConnector,
    OQMDConnector,
)


def phase1_survey() -> None:
    print("=" * 60)
    print("Phase 1: Source Survey")
    print("=" * 60)
    survey = {
        "materials_project": {"families": 8, "status": "ready"},
        "jarvis": {"families": 8, "status": "ready"},
        "aflow": {"families": 8, "status": "ready"},
        "oqmd": {"families": 8, "status": "ready (requires oqmd package)"},
        "nomad": {"families": 8, "status": "ready"},
        "icsd": {"families": 8, "status": "ready (requires ICSD_API_KEY)"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    output = Path("survey_output")
    output.mkdir(exist_ok=True)
    (output / "source_inventory.json").write_text(json.dumps(survey, indent=2))
    print(json.dumps(survey, indent=2))
    print(f"\nInventory written to {output / 'source_inventory.json'}")


def phase2_ingest() -> None:
    print("=" * 60)
    print("Phase 2: Ingestion Pipeline")
    print("=" * 60)
    from ssb_dataset.schema import MaterialRecord

    staging = Path(settings.storage.staging_dir)
    staging.mkdir(parents=True, exist_ok=True)

    connectors: dict[str, Generator[MaterialRecord, None, None]] = {}

    def _wrap(connector: Any, **kwargs: Any) -> Generator[MaterialRecord, None, None]:
        for raw in connector.fetch_records(**kwargs):
            yield connector.to_material_record(raw)

    if settings.mp.api_key:
        print("  Connecting to Materials Project...")
        mp = MPConnector()
        mp.connect()
        connectors["materials_project"] = _wrap(mp, chemsys="Li-*", limit=settings.pipeline.batch_size)
        print("  MP connected")

    try:
        print("  Connecting to JARVIS-DFT...")
        jv = JARVISConnector()
        jv.connect()
        connectors["jarvis"] = _wrap(jv, limit=settings.pipeline.batch_size)
    except Exception as e:
        print(f"  Skipping JARVIS: {e}")

    for name, ConnCls in [("aflow", AFLOWConnector), ("oqmd", OQMDConnector), ("nomad", NOMADConnector)]:
        try:
            conn = ConnCls()
            conn.connect()
            connectors[name] = _wrap(conn, limit=settings.pipeline.batch_size)
            print(f"  Connected to {name}")
        except Exception as e:
            print(f"  Skipping {name}: {e}")

    counts = run_ingestion(connectors, staging_dir=str(staging), batch_size=100)
    total = sum(counts.values())
    print(f"\nIngestion complete: {total} records across {len(counts)} sources")
    for source, count in counts.items():
        print(f"  {source}: {count}")


def _s2_key() -> str | None:
    return settings.semantic_scholar.api_key or None


def phase3_literature() -> None:
    print("=" * 60)
    print("Phase 3: Literature Mining")
    print("=" * 60)
    from ssb_dataset.literature.discovery import run_discovery
    from ssb_dataset.literature.seed import get_seed_records, validate_extraction_against_seed

    results = run_discovery(api_key=_s2_key())
    total = sum(len(v) for v in results.values())
    print(f"Discovered {total} candidate papers across {len(results)} families")
    output = Path("literature_output")
    output.mkdir(exist_ok=True)
    by_family = {fam.value: len(papers) for fam, papers in results.items()}
    (output / "discovery_results.json").write_text(json.dumps(by_family, indent=2))
    for family, papers in results.items():
        print(f"  {family.value}: {len(papers)} candidates")

    print("\n--- Seed Set ---")
    seed = get_seed_records()
    print(f"Seed set: {len(seed)} hand-curated records across {len(set(r.identity.family for r in seed))} families")
    for r in seed:
        print(f"  {r.identity.family.value}: {r.text_provenance.source_doi[:50]}... ({r.ion_transport.sigma_RT:.1e} S/cm)")


def phase3_extract(pdf_path: str | None = None, ensemble_size: int = 1) -> None:
    """Run extraction on a single PDF, a batch from discovery, or validate seed."""
    from ssb_dataset.literature.seed import get_seed_records, validate_extraction_against_seed

    if pdf_path:
        from ssb_dataset.literature.extraction import extract_from_pdf
        records = extract_from_pdf(pdf_path, skip_grobid=True, ensemble_size=ensemble_size)
        print(f"Extracted {len(records)} records from {pdf_path}")
        for r in records:
            print(f"  {r.identity.family.value}: {r.ion_transport.sigma_RT}")
        return

    print("No PDF path provided.")
    print("Options:")
    print("  python run.py literature --pdf <path>         Single PDF extraction")
    print("  python run.py literature --extract-batch N    Extract top N papers per family from discovery")
    print("  python run.py literature --validate-seed      Validate seed set and test extraction")


def phase3_extract_batch(max_per_family: int = 3) -> None:
    """Run discovery, then extract from top papers per family."""
    print("=" * 60)
    print("Phase 3: Batch Extraction from Discovery")
    print("=" * 60)
    from ssb_dataset.literature.discovery import run_discovery
    from ssb_dataset.literature.extraction import batch_extract_from_discovery

    print("Running discovery...")
    results = run_discovery(api_key=_s2_key())
    total = sum(len(v) for v in results.values())
    print(f"Discovered {total} candidates. Extracting top {max_per_family} per family...")

    records = batch_extract_from_discovery(results, max_per_family=max_per_family)

    output = Path("literature_output")
    output.mkdir(parents=True, exist_ok=True)
    if records:
        save_path = output / "extracted_records.parquet"
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq
        rows = []
        for r in records:
            rows.append({
                "material_id": r.identity.material_id or r.identity.source_id,
                "family": r.identity.family.value,
                "sigma_RT": r.ion_transport.sigma_RT,
                "Ea": r.ion_transport.activation_energy_Ea,
                "doi": r.text_provenance.source_doi,
                "title": r.text_provenance.source_paper_title,
            })
        df = pd.DataFrame(rows)
        pq.write_table(pa.Table.from_pandas(df), save_path)
        print(f"Extracted records saved to {save_path}")
    print(f"Total extracted records: {len(records)}")


def phase3_validate_seed() -> None:
    from ssb_dataset.literature.seed import get_seed_records
    seed = get_seed_records()
    print(f"\nSeed set validation: {len(seed)} records loaded")
    families: dict[str, int] = {}
    for r in seed:
        f = r.identity.family.value
        families[f] = families.get(f, 0) + 1
    for fam, count in sorted(families.items()):
        print(f"  {fam}: {count} records")


def phase4_clean() -> None:
    print("=" * 60)
    print("Phase 4: Cleaning & Canonicalization")
    print("=" * 60)
    staging = Path(settings.storage.staging_dir)
    if not staging.exists():
        print("No staging data found. Run 'ingest' first.")
        print("Demonstrating with synthetic data instead...")

    from ssb_dataset.pipeline.cleaning import run_cleaning, save_cleaning_report
    import pandas as pd

    if staging.exists():
        import pyarrow as pa
        import pyarrow.parquet as pq
        files = list(staging.rglob("*.parquet"))
        if files:
            tables = [pq.read_table(f) for f in files]
            if len(tables) > 1:
                unified = pa.concat_tables(tables, promote_options="permissive")
            else:
                unified = tables[0]
            df = unified.to_pandas()
            print(f"Loaded {len(df)} records from staging ({len(files)} files)")
        else:
            df = _make_demo_data()
    else:
        df = _make_demo_data()

    report = run_cleaning(df)
    output = Path("cleaning_output")
    output.mkdir(exist_ok=True)
    save_cleaning_report(report, output / "cleaning_report.json")
    save_path = output / "canonical_dataset.parquet"
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.Table.from_pandas(df)
    pq.write_table(table, save_path)

    print(f"Input: {report.total_input} records")
    print(f"Output: {report.total_output} records")
    print(f"Deduplicated: {report.dedup_report.cross_source_deduped} cross-source duplicates")
    print(f"Arrhenius failures: {len(report.arrhenius_failures)}")
    print(f"Missing-data violations: {len(report.missing_data_report.silent_imputation_detected)}")
    print(f"Passed: {report.passed}")
    print(f"\nCanonical dataset saved to {save_path}")
    print(f"Cleaning report saved to {output / 'cleaning_report.json'}")


def _make_demo_data() -> pd.DataFrame:
    """Generate synthetic data for demonstration/testing."""
    from ssb_dataset.schema import MaterialRecord, IdentityProvenance, SourceDB, Family, ConfidenceTier, IonTransportBlock
    records = [
        MaterialRecord(
            identity=IdentityProvenance(
                material_id="demo-Li6PS5Cl-1",
                source_db=SourceDB.materials_project,
                source_id="mp-001",
                family=Family.sulfide,
                confidence_tier=ConfidenceTier.dft_native,
            ),
            ion_transport=IonTransportBlock(
                sigma_RT=1e-3,
                activation_energy_Ea=0.30,
                label_available=True,
            ),
        ),
        MaterialRecord(
            identity=IdentityProvenance(
                material_id="demo-Li6PS5Cl-2",
                source_db=SourceDB.oqmd,
                source_id="oqmd-001",
                family=Family.sulfide,
                confidence_tier=ConfidenceTier.dft_native,
            ),
            ion_transport=IonTransportBlock(
                sigma_RT=1.2e-3,
                activation_energy_Ea=0.28,
                label_available=True,
            ),
        ),
        MaterialRecord(
            identity=IdentityProvenance(
                material_id="demo-Li7La3Zr2O12",
                source_db=SourceDB.materials_project,
                source_id="mp-002",
                family=Family.garnet,
                confidence_tier=ConfidenceTier.dft_native,
            ),
            ion_transport=IonTransportBlock(
                sigma_RT=3e-4,
                activation_energy_Ea=0.35,
                label_available=True,
            ),
        ),
        MaterialRecord(
            identity=IdentityProvenance(
                material_id="demo-bad-arrhenius",
                source_db=SourceDB.literature_mined,
                source_id="lit-001",
                family=Family.sulfide,
                confidence_tier=ConfidenceTier.high_confidence_extraction,
            ),
            ion_transport=IonTransportBlock(
                sigma_RT=1e-3,
                activation_energy_Ea=2.5,
                label_available=True,
            ),
        ),
        MaterialRecord(
            identity=IdentityProvenance(
                material_id="demo-missing-label",
                source_db=SourceDB.literature_mined,
                source_id="lit-002",
                family=Family.halide,
                confidence_tier=ConfidenceTier.low_confidence_extraction,
            ),
            ion_transport=IonTransportBlock(
                sigma_RT=0,
                activation_energy_Ea=None,
                label_available=False,
            ),
        ),
    ]
    from ssb_dataset.pipeline.ingest import material_record_to_dict
    return pd.DataFrame([material_record_to_dict(r) for r in records])


def phase5_dft(subcommand: str = "queue", **kwargs: str) -> None:
    print("=" * 60)
    print("Phase 5: DFT Compute Pipeline")
    print("=" * 60)
    from ssb_dataset.dft.priority import compute_queue
    from ssb_dataset.dft.monitor import JobMonitor

    if subcommand == "queue":
        queue = compute_queue()
        queue.sort()
        print(f"Priority queue: {len(queue)} items")
        critical = [c for c in queue.compositions if c["priority"] == 1]
        high = [c for c in queue.compositions if c["priority"] == 2]
        print(f"  Critical (unmatched lit. structures): {len(critical)}")
        print(f"  High (family gaps): {len(high)}")
        if queue.compositions:
            (Path("dft_output") / "priority_queue.json").parent.mkdir(exist_ok=True)
            (Path("dft_output") / "priority_queue.json").write_text(
                json.dumps(queue.compositions, indent=2)
            )
            print(f"Queue saved to dft_output/priority_queue.json")

    elif subcommand == "generate":
        composition = kwargs.get("composition", "unknown")
        cif_data = kwargs.get("cif", "")
        output_dir = Path(kwargs.get("output_dir", "dft_jobs")) / composition
        from ssb_dataset.dft.inputs import write_inputs
        code = kwargs.get("code", "vasp")
        inputs = write_inputs(cif_data, output_dir, code=code)
        print(f"Generated {code} inputs for {composition} in {output_dir}")
        for k, v in inputs.items():
            print(f"  {k}: {v}")

    elif subcommand == "status":
        monitor_path = Path("dft_output") / "monitor_log.json"
        if monitor_path.exists():
            monitor_data = json.loads(monitor_path.read_text())
            print(f"Job summary: {monitor_data.get('summary', {})}")
            print(f"Success rate: {monitor_data.get('success_rate', 0):.1%}")
        else:
            print("No monitor log found — run DFT jobs first")

    elif subcommand == "summary":
        from ssb_dataset.dft.monitor import JobMonitor
        monitor = JobMonitor(log_path="dft_output/monitor_log.json")
        summary = monitor.summary()
        print(f"DFT pipeline summary: {summary}")
        print(f"Success rate: {monitor.success_rate:.1%}")
        if monitor.failures():
            print("Failures:")
            for f in monitor.failures():
                print(f"  {f['name']}: {f.get('error', 'unknown')}")


def phase6_featurize(subcommand: str = "all", **kwargs: str) -> None:
    print("=" * 60)
    print("Phase 6: Feature Engineering")
    print("=" * 60)
    import pandas as pd

    output = Path("features_output")
    output.mkdir(parents=True, exist_ok=True)
    from ssb_dataset.featurization import (
        build_gold_benchmark,
        compute_composition_descriptors,
        compute_symmetry_descriptors,
        create_splits,
        featurize_polymer_records,
        write_splits,
    )

    dataset_path = kwargs.get("dataset", "cleaning_output/canonical_dataset.parquet")
    if not Path(dataset_path).exists():
        print(f"Dataset not found at {dataset_path}. Run 'clean' first or specify --dataset.")
        print("Demonstrating with synthetic data instead.")
        df = _make_demo_data()
    else:
        import pyarrow.parquet as pq
        df = pq.read_table(dataset_path).to_pandas()
        print(f"Loaded {len(df)} records from {dataset_path}")

    if subcommand in ("all", "descriptors"):
        print("\n--- Composition Descriptors ---")
        df = compute_composition_descriptors(df)
        n_desc = [c for c in df.columns if c.startswith(("n_", "frac_", "atomic_", "electro"))]
        print(f"Added {len(n_desc)} composition descriptor columns")

        print("\n--- Symmetry Descriptors ---")
        df = compute_symmetry_descriptors(df)
        print(f"Added space_group_number, crystal_system, li_fraction, has_li_sublattice")

        poly_mask = df.get("is_polymer", pd.Series([False] * len(df)))
        print(f"\n--- Polymer Records ---")
        df = featurize_polymer_records(df)
        print(f"Polymer records identified: {df['is_polymer'].sum()}")

        desc_path = output / "descriptors.parquet"
        import pyarrow as pa
        import pyarrow.parquet as pq
        pq.write_table(pa.Table.from_pandas(df), desc_path)
        print(f"Descriptors saved to {desc_path}")

    if subcommand in ("all", "splits"):
        print("\n--- Train/Val/Test Splits ---")
        gold = build_gold_benchmark(df)
        splits = create_splits(df)
        write_splits(splits, output, gold_df=gold)

        from ssb_dataset.featurization.splits import check_split_leakage
        leakage = check_split_leakage(splits)
        print(f"Splits: train={len(splits.get('train', []))}, val={len(splits.get('val', []))}, test={len(splits.get('test', []))}")
        print(f"Gold benchmark: {len(gold)} records")
        print(f"Leakage check: {'PASSED' if leakage['passed'] else 'FAILED - see leakage_check.json'}")
        print(f"Splits saved to {output}")


def phase7_validate(subcommand: str = "all") -> None:
    print("=" * 60)
    print("Phase 7: Validation & QC")
    print("=" * 60)
    from ssb_dataset.pipeline.validation import (
        run_validation,
        generate_report,
        check_family_distributions,
        verify_benchmark_compounds,
        audit_cross_source_consistency,
        audit_extraction_accuracy,
        BENCHMARK_COMPOUNDS,
    )

    dataset_path = Path("cleaning_output/canonical_dataset.parquet")
    if dataset_path.exists():
        import pyarrow.parquet as pq
        df = pq.read_table(dataset_path).to_pandas()
        print(f"Loaded {len(df)} records from {dataset_path}")
    else:
        print("No canonical dataset found. Using synthetic demo data.")
        df = _make_demo_data()

    output = Path("validation_output")
    output.mkdir(parents=True, exist_ok=True)

    if subcommand in ("all", "distributions"):
        print("\n--- Family Distribution Checks ---")
        dists = check_family_distributions(df)
        for d in dists:
            flags = ", ".join(d.flags) if d.flags else "OK"
            sigma_med = f"{d.sigma_median:.2e}" if d.sigma_median is not None else "N/A"
            ea_mean = f"{d.ea_mean:.2f}" if d.ea_mean is not None else "N/A"
            print(f"  {d.family}: {d.count} records, sigma median={sigma_med} S/cm, Ea mean={ea_mean} eV [{flags}]")

    if subcommand in ("all", "benchmarks"):
        print("\n--- Benchmark Compound Validation ---")
        results = verify_benchmark_compounds(df)
        for r in results:
            status = "PASS" if r.sigma_passes else ("NOT FOUND" if r.error else "FAIL")
            sigma_str = f"{r.sigma_value:.2e}" if r.sigma_value is not None else "N/A"
            expected_str = f"{r.sigma_expected:.2e}" if r.sigma_expected is not None else "N/A"
            ratio_str = f"{r.sigma_ratio:.1f}" if r.sigma_ratio is not None else "N/A"
            print(f"  {r.compound}: {status} (sigma={sigma_str}, expected={expected_str}, ratio={ratio_str})")

    if subcommand in ("all", "cross-source"):
        print("\n--- Cross-Source Consistency ---")
        entries = audit_cross_source_consistency(df)
        for e in entries[:10]:
            print(f"  {e.material_id}: {len(e.sources)} sources, sigma range={e.sigma_range:.1f}x {'OK' if e.passes else 'FAIL'}")

    if subcommand in ("all", "extraction"):
        print("\n--- Extraction Accuracy Re-Audit ---")
        audit = audit_extraction_accuracy(df)
        print(f"  Seed records: {audit.seed_count}, Validated: {audit.validated_count}")
        print(f"  Accuracy: {audit.accuracy:.1%} {'PASS' if audit.passed else 'FAIL (threshold 85%)'}")

    if subcommand == "all":
        print("\n--- Full Validation Report ---")
        full = run_validation(df)
        report_path = output / "validation_report.json"
        generate_report(full, report_path)
        print(f"  Passed: {full.passed}")
        print(f"  Benchmark verified: {full.benchmark_verified}/{len(BENCHMARK_COMPOUNDS)}")
        print(f"  Cross-source entries: {len(full.cross_source_entries)}, failed: {full.cross_source_failed}")
        print(f"  Family distribution flags: {len(full.family_distribution_flags)}")
        print(f"  Report saved to {report_path}")


def phase8_docs(subcommand: str = "all") -> None:
    print("=" * 60)
    print("Phase 8: Documentation")
    print("=" * 60)
    from ssb_dataset.documentation import (
        generate_citation_cff,
        generate_confidence_tier_doc,
        generate_datasheet,
        generate_family_readme,
        update_changelog,
    )
    from ssb_dataset.documentation.generator import FAMILY_NAMES

    output = Path("docs_output")
    output.mkdir(parents=True, exist_ok=True)

    dataset_path = Path("features_output") / "descriptors.parquet"
    if dataset_path.exists():
        import pyarrow.parquet as pq
        df = pq.read_table(dataset_path).to_pandas()
    else:
        df = _make_demo_data()

    family_col = None
    for c in ["identity.family", "family"]:
        if c in df.columns:
            family_col = c
            break

    sigma_col = None
    for c in ["ion_transport.sigma_RT", "sigma_RT"]:
        if c in df.columns:
            sigma_col = c
            break

    if subcommand in ("all", "datasheet"):
        print("\n--- Datasheet ---")
        path = output / "datasheet.md"
        generate_datasheet(df, path)
        print(f"  Written to {path}")

    if subcommand in ("all", "family-readmes"):
        print("\n--- Per-Family READMEs ---")
        families_dir = output / "families"
        families_dir.mkdir(exist_ok=True)
        n_per_family: dict[str, int] = {}
        n_sigma_per_family: dict[str, int] = {}

        if family_col:
            for fam in df[family_col].unique():
                fam_df = df[df[family_col] == fam]
                n_per_family[str(fam)] = len(fam_df)
                n_sigma_per_family[str(fam)] = int(fam_df[sigma_col].notna().sum()) if sigma_col else 0

        for fam_name in FAMILY_NAMES:
            n = n_per_family.get(fam_name, 0)
            ns = n_sigma_per_family.get(fam_name, 0)
            path = families_dir / f"{fam_name}.md"
            generate_family_readme(fam_name, n, ns, path)
            print(f"  {fam_name}: {n} records, {ns} with sigma → {path}")

    if subcommand in ("all", "confidence"):
        print("\n--- Confidence Tier Doc ---")
        path = output / "confidence_tiers.md"
        generate_confidence_tier_doc(path)
        print(f"  Written to {path}")

    if subcommand in ("all", "citation"):
        print("\n--- CITATION.cff ---")
        path = Path("CITATION.cff")
        generate_citation_cff(path)
        print(f"  Written to {path}")

    if subcommand in ("all", "changelog"):
        print("\n--- CHANGELOG.md ---")
        path = Path("CHANGELOG.md")
        update_changelog(path)
        print(f"  Updated {path}")

    print(f"\nDocumentation complete. All files in {output.absolute()}")


def phase10_maintenance() -> None:
    print("=" * 60)
    print("Phase 10: Maintenance Docs")
    print("=" * 60)
    from ssb_dataset.maintenance import (
        generate_contributing,
        generate_maintenance_plan,
        generate_deprecation_policy,
        generate_usage_guide,
        generate_issue_templates,
        generate_pr_template,
    )

    output = Path(".")

    print("\n--- CONTRIBUTING.md ---")
    path = output / "CONTRIBUTING.md"
    generate_contributing(path)
    print(f"  Written to {path}")

    print("\n--- MAINTENANCE.md ---")
    path = output / "MAINTENANCE.md"
    generate_maintenance_plan(path)
    print(f"  Written to {path}")

    print("\n--- DEPRECATION.md ---")
    path = output / "DEPRECATION.md"
    generate_deprecation_policy(path)
    print(f"  Written to {path}")

    print("\n--- USAGE_GUIDE.md ---")
    path = output / "USAGE_GUIDE.md"
    generate_usage_guide(path)
    print(f"  Written to {path}")

    print("\n--- Issue Templates ---")
    templates_dir = output / ".github" / "ISSUE_TEMPLATE"
    paths = generate_issue_templates(templates_dir)
    for p in paths:
        print(f"  Written to {p}")

    print("\n--- Pull Request Template ---")
    path = output / ".github" / "PULL_REQUEST_TEMPLATE.md"
    generate_pr_template(path)
    print(f"  Written to {path}")

    print("\nMaintenance documentation complete.")


def phase9_release(
    subcommand: str = "check",
    dry_run: bool = False,
    hf_token: str = "",
    zenodo_token: str = "",
    github_token: str = "",
    version: str = "v0.1.0",
    sandbox: bool = False,
) -> None:
    print("=" * 60)
    print(f"Phase 9: Release — {subcommand}")
    print("=" * 60)

    from ssb_dataset.release import HuggingFacePublisher, ZenodoPublisher, GitHubReleaser, ReleaseManager

    hf = HuggingFacePublisher(token=hf_token or None)
    zenodo = ZenodoPublisher(token=zenodo_token or None, sandbox=sandbox)
    gh = GitHubReleaser(token=github_token or None)
    manager = ReleaseManager(hf_publisher=hf, zenodo_publisher=zenodo, github_releaser=gh)

    if subcommand == "check":
        checklist = manager.build_checklist(human_signoff=args.signoff)
        manager.print_summary(checklist)
        if not checklist.ready:
            print("\nSome checks failed. Fix issues above, then run with --release-cmd publish.")
            print("Use --release-cmd check --dry-run to see what would be published.")

    elif subcommand == "publish":
        checklist = manager.build_checklist(human_signoff=args.signoff)
        if not checklist.human_signoff:
            print("WARNING: Human sign-off not confirmed. Set --signoff to confirm you have reviewed the release.")
            print("Running in dry-run mode. Pass --signoff to actually publish.")
            dry_run = True

        if dry_run:
            print("\n[DRY RUN] Full publish preview:")
            manager.publish_all(version, targets=("hf", "zenodo", "github"), dry_run=True)
            print("\nDry run complete. Run with --release-cmd publish --signoff to publish for real.")
        else:
            print("\nPublishing to all targets...")
            results = manager.publish_all(version, targets=("hf", "zenodo", "github"))
            print("\nRelease complete!")
            for target, res in results.items():
                print(f"  {target}: {res}")

    elif subcommand == "rollback":
        print(f"Rolling back release {version}...")
        manager.rollback_all(version)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scandium Labs SSB Dataset Pipeline")
    parser.add_argument(
        "command",
        choices=["survey", "ingest", "literature", "extract", "validate-seed", "clean", "dft", "featurize", "validate", "docs", "maintenance", "release", "all"],
        help="Pipeline phase to execute",
    )
    parser.add_argument("--pdf", type=str, default=None, help="Path to PDF for extraction")
    parser.add_argument("--ensemble", type=int, default=1, help="Run extraction N times and keep consensus records (default: 1 = single pass)")
    parser.add_argument("--extract-batch", type=int, default=0, help="Extract top N papers per family from discovery")
    parser.add_argument("--dft-cmd", type=str, default="queue", choices=["queue", "generate", "status", "summary"], help="DFT subcommand")
    parser.add_argument("--composition", type=str, default="", help="Composition for DFT input generation")
    parser.add_argument("--cif", type=str, default="", help="CIF path for DFT input generation")
    parser.add_argument("--code", type=str, default="vasp", choices=["vasp", "qe"], help="DFT code for input generation")
    parser.add_argument("--output-dir", type=str, default="dft_jobs", help="Output directory for DFT inputs")
    parser.add_argument("--feat-cmd", type=str, default="all", choices=["all", "descriptors", "splits"], help="Featurization subcommand")
    parser.add_argument("--dataset", type=str, default="cleaning_output/canonical_dataset.parquet", help="Path to canonical dataset Parquet")
    parser.add_argument("--validate-cmd", type=str, default="all", choices=["all", "distributions", "benchmarks", "cross-source", "extraction"], help="Validation subcommand")
    parser.add_argument("--docs-cmd", type=str, default="all", choices=["all", "datasheet", "family-readmes", "confidence", "citation", "changelog"], help="Documentation subcommand")
    parser.add_argument("--release-cmd", type=str, default="check", choices=["check", "publish", "rollback"], help="Release subcommand")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Preview release without publishing")
    parser.add_argument("--signoff", action="store_true", default=False, help="Confirm human sign-off for release")
    parser.add_argument("--hf-token", type=str, default="", help="Hugging Face Hub API token")
    parser.add_argument("--zenodo-token", type=str, default="", help="Zenodo API token")
    parser.add_argument("--github-token", type=str, default="", help="GitHub API token")
    parser.add_argument("--version", type=str, default="v0.1.0", help="Release version tag")
    parser.add_argument("--sandbox", action="store_true", default=False, help="Use Zenodo sandbox (for testing)")
    args, extra = parser.parse_known_args()

    command_map: dict[str, Any] = {
        "survey": phase1_survey,
        "ingest": phase2_ingest,
        "literature": phase3_literature,
        "extract": lambda: phase3_extract_batch(args.extract_batch) if args.extract_batch else phase3_extract(args.pdf, ensemble_size=args.ensemble),
        "validate-seed": phase3_validate_seed,
        "clean": phase4_clean,
        "dft": lambda: phase5_dft(args.dft_cmd, composition=args.composition, cif=args.cif, code=args.code, output_dir=args.output_dir),
        "featurize": lambda: phase6_featurize(args.feat_cmd, dataset=args.dataset),
        "validate": lambda: phase7_validate(args.validate_cmd),
    "docs": lambda: phase8_docs(args.docs_cmd),
    "maintenance": phase10_maintenance,
    "release": lambda: phase9_release(
            subcommand=args.release_cmd,
            dry_run=args.dry_run or not args.signoff,
            hf_token=args.hf_token,
            zenodo_token=args.zenodo_token,
            github_token=args.github_token,
            version=args.version,
            sandbox=args.sandbox,
        ),
    }

    if args.command == "all":
        for name, fn in command_map.items():
            fn()
            print()
    else:
        command_map[args.command]()


if __name__ == "__main__":
    main()