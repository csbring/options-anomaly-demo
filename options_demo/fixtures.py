"""Deterministic invented quotes. Never imports a market dataset."""
from datetime import date, timedelta
import hashlib

import numpy as np
import pandas as pd

SCENARIOS = {
    "call_activity": "Unusual call activity",
    "put_activity": "Unusual put activity",
    "wide_spreads": "Activity with poor quote quality",
}


def make_snapshot(symbol: str, seed: int = 0, scenario: str | None = None) -> pd.DataFrame:
    digest = int.from_bytes(hashlib.sha256(symbol.encode()).digest()[:4], "big")
    rng = np.random.default_rng(digest + seed)
    spot = float(100 + digest % 150)
    rows = []
    for dte in (7, 14, 30, 45):
        expiry = (date(2030, 1, 2) + timedelta(days=dte)).strftime("%Y%m%d")
        for ratio in np.linspace(.90, 1.10, 15):
            strike = round(spot * ratio, 2)
            for right in ("call", "put"):
                intrinsic = max(spot - strike, 0) if right == "call" else max(strike - spot, 0)
                mid = intrinsic + spot * .024 * np.sqrt(dte / 30) * np.exp(-abs(1-ratio)*8)
                mid *= rng.uniform(.9, 1.1)
                volume = int(rng.lognormal(4.8, .8))
                oi = int(rng.lognormal(7.1, .6))
                spread = rng.uniform(.025, .09)
                target = "put" if scenario == "put_activity" else "call"
                if scenario and right == target and abs(ratio-1) < .017 and dte in (14, 30):
                    volume *= 70
                    oi = max(20, int(oi / 4))
                    if scenario == "wide_spreads":
                        spread = .34
                delta_call = float(np.clip(.5 + (1-ratio)*4, .08, .92))
                rows.append(dict(
                    symbol=symbol, contract=f"{symbol} {expiry} {right[0].upper()}{strike:g}",
                    option_type=right, expiry=expiry, dte=dte, strike=strike, spot=spot,
                    bid=mid*(1-spread/2), ask=mid*(1+spread/2), mid=mid, last=mid,
                    close=mid*rng.uniform(.9, 1.1), spread_pct=spread, volume=volume,
                    open_interest=oi, iv=.28+rng.uniform(-.04, .04),
                    delta=delta_call if right == "call" else delta_call-1,
                    gamma=.02, theta=-.03, vega=.12, moneyness=ratio,
                    otm_pct=ratio-1 if right == "call" else 1-ratio,
                    abs_otm_pct=abs(1-ratio), price_source="bid_ask",
                ))
    return pd.DataFrame(rows)


def fixture_pair(symbol: str, scenario: str):
    if scenario not in SCENARIOS:
        raise ValueError("Choose one of the supplied demo scenarios.")
    baseline = pd.concat([make_snapshot(symbol, seed=i) for i in range(4)], ignore_index=True)
    return baseline, make_snapshot(symbol, seed=100, scenario=scenario)
