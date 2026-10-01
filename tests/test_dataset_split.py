from datetime import datetime, timedelta, timezone

import pytest

from research_os.research.dataset_split import (
    assert_split_is_leakage_free,
    purged_train_validation_test_split,
)
from research_os.research.research_dataset import ResearchDataset, ResearchDatasetRow


def row(i):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i)
    return ResearchDatasetRow(
        "BTCUSDT", t, 100.0, 1, t + timedelta(minutes=1),
        0.01, 0.02, -0.01, (), (), 0, 0, None, 0.0, (), ()
    )


def test_three_way_split_is_chronological_and_purged():
    dataset = ResearchDataset("BTCUSDT", "v1", tuple(row(i) for i in range(30)), 0)
    split = purged_train_validation_test_split(dataset, purge_minutes=0)
    assert split.train.rows[-1].decision_time < split.validation.rows[0].decision_time
    assert split.validation.rows[-1].decision_time < split.test.rows[0].decision_time
    assert_split_is_leakage_free(split)


def test_nonzero_purge_uses_outcome_boundary():
    dataset = ResearchDataset("BTCUSDT", "v1", tuple(row(i) for i in range(30)), 0)
    split = purged_train_validation_test_split(dataset, purge_minutes=2)
    assert split.validation.rows[0].decision_time > split.train.rows[-1].outcome_time
    assert split.test.rows[0].decision_time > split.validation.rows[-1].outcome_time


def test_invalid_ratios_rejected():
    dataset = ResearchDataset("BTCUSDT", "v1", tuple(row(i) for i in range(10)), 0)
    with pytest.raises(ValueError):
        purged_train_validation_test_split(dataset, train_ratio=0.8, validation_ratio=0.2)
