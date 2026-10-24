
import pandas as pd
import pytest

from features import build_features


def test_pregame_features_exclude_current_result():
    games = pd.DataFrame([
        {
            "game_id": "2025_01_A_B",
            "season": 2025,
            "week": 1,
            "game_type": "REG",
            "gameday": "2025-09-07",
            "gametime": "13:00",
            "home_team": "B",
            "away_team": "A",
            "home_score": 10,
            "away_score": 24,
        },
        {
            "game_id": "2025_02_C_A",
            "season": 2025,
            "week": 2,
            "game_type": "REG",
            "gameday": "2025-09-14",
            "gametime": "13:00",
            "home_team": "A",
            "away_team": "C",
            "home_score": 7,
            "away_score": 21,
        },
        {
            "game_id": "2025_03_A_D",
            "season": 2025,
            "week": 3,
            "game_type": "REG",
            "gameday": "2025-09-21",
            "gametime": "13:00",
            "home_team": "D",
            "away_team": "A",
            "home_score": 14,
            "away_score": 28,
        },
    ])

    result = build_features(games).set_index("game_id")

    # Team A has no history entering Week 1.
    assert result.loc[
        "2025_01_A_B", "away_win_pct"
    ] == pytest.approx(0.5)

    # Team A won Week 1, so enters Week 2 at 1-0.
    assert result.loc[
        "2025_02_C_A", "home_win_pct"
    ] == pytest.approx(1.0)

    # Team A lost Week 2, so enters Week 3 at 1-1.
    # The Week 3 victory must NOT be included.
    assert result.loc[
        "2025_03_A_D", "away_win_pct"
    ] == pytest.approx(0.5)


def test_input_order_does_not_change_features():
    games = pd.DataFrame([
        {
            "game_id": "2025_01_A_B",
            "season": 2025,
            "week": 1,
            "game_type": "REG",
            "gameday": "2025-09-07",
            "gametime": "13:00",
            "home_team": "A",
            "away_team": "B",
            "home_score": 24,
            "away_score": 10,
        },
        {
            "game_id": "2025_02_A_C",
            "season": 2025,
            "week": 2,
            "game_type": "REG",
            "gameday": "2025-09-14",
            "gametime": "13:00",
            "home_team": "A",
            "away_team": "C",
            "home_score": 14,
            "away_score": 21,
        },
    ])

    forward = build_features(games)
    reversed_input = build_features(
        games.iloc[::-1].reset_index(drop=True)
    )

    pd.testing.assert_frame_equal(
        forward,
        reversed_input,
    )
