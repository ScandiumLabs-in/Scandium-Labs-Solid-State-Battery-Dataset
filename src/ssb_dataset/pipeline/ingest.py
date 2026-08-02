"""Phase 2 — Ingestion pipeline orchestrator.

Runs all source connectors in sequence, writes partitioned Parquet to staging.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from ssb_dataset.schema import MaterialRecord


def _flatten(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            items.append((new_key, [vv.model_dump() if hasattr(vv, "model_dump") else vv for vv in v]))
        elif hasattr(v, "model_dump"):
            items.append((new_key, v.model_dump()))
        else:
            items.append((new_key, v))
    return dict(items)


def material_record_to_dict(record: MaterialRecord) -> dict:
    return _flatten(record.model_dump())


def write_partition(
    records: list[MaterialRecord],
    staging_dir: str | Path,
    source_db: str,
    family: str,
    part_num: int = 0,
) -> Path:
    staging_dir = Path(staging_dir)
    partition_dir = staging_dir / source_db / family
    partition_dir.mkdir(parents=True, exist_ok=True)

    path = partition_dir / f"part-{part_num:04d}.parquet"
    df = pd.DataFrame([material_record_to_dict(r) for r in records])
    table = pa.Table.from_pandas(df)
    pq.write_table(table, path)
    return path


def run_ingestion(
    connectors: dict[str, Generator[MaterialRecord, None, None]],
    staging_dir: str | Path = "staging",
    batch_size: int = 100,
    max_records_per_source: int = 0,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    staging_dir = Path(staging_dir)

    for source_name, record_gen in connectors.items():
        batch: list[MaterialRecord] = []
        part_num = 0
        total = 0

        for record in tqdm(record_gen, desc=f"Ingesting {source_name}"):
            batch.append(record)
            total += 1

            if max_records_per_source and total >= max_records_per_source:
                break

            if len(batch) >= batch_size:
                family = record.identity.family.value
                write_partition(batch, staging_dir, source_name, family, part_num)
                batch = []
                part_num += 1

        if batch:
            family = batch[0].identity.family.value if batch else "unknown"
            write_partition(batch, staging_dir, source_name, family, part_num)

        counts[source_name] = total

    return counts
