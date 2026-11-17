import base64
from io import BytesIO
import json

import numpy as np
import pytest
from PIL import Image

from options_demo.analysis import analyze, explain, parse_symbol, prepare
from options_demo.fixtures import fixture_pair, make_snapshot


@pytest.mark.parametrize("text,expected", [("aapl", "AAPL"), ("flow NVDA", "NVDA"), ("/flow SPY", "SPY"), ("$AAPL", "AAPL"), ("BRK.B", "BRK.B")])
def test_ticker_commands(text, expected):
    assert parse_symbol(text) == expected


@pytest.mark.parametrize("text", ["AAPL;ls", "../../file", "$(id)", "AAPL MSFT", "", "<script>", "TOOLONGNAME"])
def test_invalid_commands(text):
    with pytest.raises(ValueError):
        parse_symbol(text)


def test_fixture_is_deterministic_and_baseline_separate():
    train, current = fixture_pair("AAPL", "call_activity")
    assert len(train) == 480 and len(current) == 120
    assert current.equals(fixture_pair("AAPL", "call_activity")[1])
    assert current.volume.max() > train.volume.max()


def test_bad_quotes_are_excluded_and_missing_oi_does_not_explode():
    raw = make_snapshot("AAPL")
    raw.loc[0, "bid"] = raw.loc[0, "ask"] + 1
    raw.loc[1, "ask"] = np.inf
    raw.loc[2, "bid"] = np.nan
    raw.loc[3, "open_interest"] = 0
    out = prepare(raw, "AAPL")
    assert len(out) == len(raw)-3
    missing = out[out.oi_missing]
    assert len(missing) == 1
    assert missing.volume_oi_ratio_model.iloc[0] == 0


@pytest.fixture(scope="module")
def call_report():
    return analyze("AAPL", "call_activity")


def test_report_contains_real_plot_and_strict_json(call_report):
    image = Image.open(BytesIO(base64.b64decode(call_report["chart"])))
    assert image.format == "PNG" and image.width > 1500
    json.dumps(call_report, allow_nan=False)
    assert call_report["calls"] > 0
    assert call_report["source"] == "synthetic"
    assert "480 training" in call_report["model_basis"]
    assert "not identify buying" in call_report["summary"]


def test_scenarios_change_evidence_and_quality(call_report):
    puts = analyze("AAPL", "put_activity")
    wide = analyze("AAPL", "wide_spreads")
    assert puts["puts"] > call_report["puts"]
    assert call_report["calls"] > puts["calls"]
    assert wide["quality_pass"] < call_report["quality_pass"]


def test_followups_grounded_in_report(call_report):
    assert call_report["rows"][0]["contract"] in explain(call_report, "why")
    assert str(call_report["quality_pass"]) in explain(call_report, "quality")
    assert "not a probability" in explain(call_report, "model")
    with pytest.raises(ValueError):
        explain(call_report, "invent a trade")
