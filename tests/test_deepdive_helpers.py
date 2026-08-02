import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "space-app"))

from deepdive import classify_closing_gap


def test_price_window_trims_to_first_available_point():
    hist = pd.DataFrame(
        {"Close": [100.0, 110.0, 120.0]},
        index=pd.to_datetime(["2022-01-01", "2022-02-01", "2022-03-01"]),
    )
    anchor = pd.Timestamp("2021-01-01")
    window = hist.loc[hist.index >= anchor]
    assert window.index[0] == pd.Timestamp("2022-01-01")


def test_classify_closing_gap_uses_recent_periods():
    status, periods = classify_closing_gap(
        [0.02, 0.03, 0.04, 0.05],
        ["2022", "2023", "2024", "2025"],
    )
    assert status == "Closing the gap"
    assert periods == ["2023", "2024", "2025"]


def test_classify_closing_gap_requires_three_of_last_four():
    status, periods = classify_closing_gap(
        [0.02, 0.01, 0.01, 0.01],
        ["2022", "2023", "2024", "2025"],
    )
    assert status == "Not yet closing the gap"
    assert periods == []
