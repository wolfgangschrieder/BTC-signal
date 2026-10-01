from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .research_dataset import ResearchDataset, ResearchDatasetRow


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    train: ResearchDataset
    validation: ResearchDataset
    test: ResearchDataset


def _subset(dataset: ResearchDataset, suffix: str, rows: tuple[ResearchDatasetRow, ...], skipped: int = 0) -> ResearchDataset:
    return ResearchDataset(dataset.symbol, f"{dataset.version}:{suffix}", rows, skipped)


def purged_train_validation_test_split(
    dataset: ResearchDataset,
    *,
    train_ratio: float = 0.60,
    validation_ratio: float = 0.20,
    purge_minutes: int | None = None,
) -> DatasetSplit:
    if train_ratio <= 0 or validation_ratio <= 0 or train_ratio + validation_ratio >= 1:
        raise ValueError("train_ratio and validation_ratio must be positive and leave room for test")

    rows = tuple(sorted(dataset.rows, key=lambda row: (row.decision_time, row.outcome_time)))
    if len(rows) < 3:
        raise ValueError("dataset must contain at least three rows")

    train_cut = int(len(rows) * train_ratio)
    validation_cut = int(len(rows) * (train_ratio + validation_ratio))
    if train_cut < 1 or validation_cut <= train_cut or validation_cut >= len(rows):
        raise ValueError("split ratios produce an empty partition")

    purge = rows[0].horizon_minutes if purge_minutes is None else purge_minutes
    if purge < 0:
        raise ValueError("purge_minutes must be non-negative")

    train = rows[:train_cut]
    validation_candidates = rows[train_cut:validation_cut]
    test_candidates = rows[validation_cut:]

    train_boundary = train[-1].outcome_time + timedelta(minutes=purge)
    validation = tuple(row for row in validation_candidates if row.decision_time > train_boundary)
    if not validation:
        raise ValueError("purge removed the entire validation partition")

    validation_boundary = validation[-1].outcome_time + timedelta(minutes=purge)
    test = tuple(row for row in test_candidates if row.decision_time > validation_boundary)
    if not test:
        raise ValueError("purge removed the entire test partition")

    return DatasetSplit(
        _subset(dataset, "train", train),
        _subset(dataset, "validation", validation, len(validation_candidates) - len(validation)),
        _subset(dataset, "test", test, len(test_candidates) - len(test)),
    )


def assert_split_is_leakage_free(split: DatasetSplit) -> None:
    if split.train.rows[-1].outcome_time >= split.validation.rows[0].decision_time:
        raise AssertionError("train outcome overlaps validation decision boundary")
    if split.validation.rows[-1].outcome_time >= split.test.rows[0].decision_time:
        raise AssertionError("validation outcome overlaps test decision boundary")
