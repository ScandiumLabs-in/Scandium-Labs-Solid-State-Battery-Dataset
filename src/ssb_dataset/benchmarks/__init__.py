"""Scandium Benchmark Suite — standard ML benchmark tasks over the canonical
dataset (v0.8.0). Each task is a declarative definition (target column, metric,
label filter) evaluated by scripts/run_benchmarks.py on the leakage-checked
train/test splits.
"""

from ssb_dataset.benchmarks.tasks import (
    BENCHMARK_TASKS,
    BenchmarkTask,
    get_task,
)

__all__ = ["BENCHMARK_TASKS", "BenchmarkTask", "get_task"]
