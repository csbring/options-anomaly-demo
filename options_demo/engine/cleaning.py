import numpy as np
import pandas as pd

from .constants import (
    DEFAULT_MIN_PREV_CLOSE_FOR_REPRICE,
    EMPTY_COLS,
    FEATURE_COLS,
    QUOTE_COLS,
)
from .utils import now_ny


def clean_chain(
    df,
    symbol,
    min_mid=0.05,
    min_oi=0,
    min_volume=1,
    max_spread_pct=0.40,
    debug_filter=True,
    min_prev_close_for_reprice=DEFAULT_MIN_PREV_CLOSE_FOR_REPRICE,
):
    if df is None or df.empty:
        return pd.DataFrame(columns=EMPTY_COLS)

    df = df.copy()

    for col in QUOTE_COLS:
        if col not in df.columns:
            df[col] = np.nan

    numeric_cols = [
        "dte",
        "strike",
        "spot",
        "bid",
        "ask",
        "last",
        "close",
        "mid",
        "spread_pct",
        "volume",
        "open_interest",
        "volume_oi_ratio",
        "volume_oi_ratio_model",
        "dollar_volume",
        "log_dollar_volume",
        "mid_vs_close_pct",
        "mid_vs_close_pct_model",
        "iv",
        "delta",
        "gamma",
        "theta",
        "vega",
        "moneyness",
        "otm_pct",
        "abs_otm_pct",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["volume"] = df["volume"].fillna(0)
    df["open_interest"] = df["open_interest"].fillna(0)
    df["oi_missing"] = df["open_interest"].le(0)

    if debug_filter:
        print("\nFilter diagnostics:")
        print("rows:", len(df))
        print("mid valid:", df["mid"].notna().sum())
        print("bid valid:", df["bid"].gt(0).sum())
        print("ask valid:", df["ask"].gt(0).sum())
        print("spread valid:", df["spread_pct"].notna().sum())
        print("volume > 0:", df["volume"].gt(0).sum())
        print("OI > 0:", df["open_interest"].gt(0).sum())
        print("price_source counts:")
        print(df["price_source"].value_counts(dropna=False).to_string())

    # Snapshot can return last/close without bid/ask.
    df["spread_pct"] = df["spread_pct"].fillna(0)

    mask = (
        df["mid"].notna()
        & df["mid"].ge(min_mid)
        & df["open_interest"].ge(min_oi)
        & df["volume"].ge(min_volume)
        & df["spread_pct"].between(0, max_spread_pct)
    )

    df = df.loc[mask].copy()

    if df.empty:
        return pd.DataFrame(columns=EMPTY_COLS)

    scan_id = now_ny().strftime("%Y%m%d_%H%M%S")
    snapshot_ts = now_ny().isoformat()

    df["snapshot_ts"] = snapshot_ts
    df["scan_id"] = scan_id
    df["symbol"] = symbol.upper()

    df["log_volume"] = np.log1p(df["volume"])
    df["log_oi"] = np.log1p(df["open_interest"])

    df["volume_oi_ratio"] = np.where(
        df["open_interest"] > 0,
        df["volume"] / df["open_interest"],
        np.nan,
    )

    # Model-safe version. OI=0 does not become fake 5000x OI.
    df["volume_oi_ratio_model"] = df["volume_oi_ratio"].fillna(0)

    df["dollar_volume"] = df["volume"] * df["mid"] * 100
    df["log_dollar_volume"] = np.log1p(df["dollar_volume"].fillna(0))

    df["stale_close"] = (
        df["close"].isna()
        | df["close"].le(0)
        | df["close"].lt(min_prev_close_for_reprice)
    )

    df["mid_vs_close_pct"] = np.where(
        (~df["stale_close"]) & df["mid"].notna(),
        (df["mid"] - df["close"]) / df["close"],
        np.nan,
    )

    df["mid_vs_close_pct_model"] = df["mid_vs_close_pct"].fillna(0)

    df[FEATURE_COLS] = (
        df[FEATURE_COLS]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0)
    )

    return df.reset_index(drop=True)
