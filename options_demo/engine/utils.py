import numpy as np
import pandas as pd

from .constants import ETF_SYMBOLS, LIQUID_STOCK_SYMBOLS, SYMBOL_PROFILES


def safe_float(x, default=np.nan):
    try:
        if x is None:
            return default
        x = float(x)
        if not np.isfinite(x):
            return default
        return x
    except Exception:
        return default


def is_num(x):
    return not pd.isna(safe_float(x))


def now_ny():
    return pd.Timestamp.now(tz="America/New_York")


def robust_params(df, cols):
    x = df[cols].copy()
    med = x.median()
    iqr = x.quantile(0.75) - x.quantile(0.25)
    iqr = iqr.replace(0, np.nan)
    return med, iqr


def robust_apply(df, cols, med, iqr, clip=10):
    x = df[cols].copy()
    z = (x - med) / iqr
    z = z.replace([np.inf, -np.inf], np.nan).fillna(0)
    return z.clip(-clip, clip)


def robust_z_clip(df, cols, clip=10):
    med, iqr = robust_params(df, cols)
    return robust_apply(df, cols, med, iqr, clip=clip)


def weighted_avg(df, value_col, weight_col):
    if df is None or df.empty:
        return np.nan

    x = pd.to_numeric(df[value_col], errors="coerce")
    w = pd.to_numeric(df[weight_col], errors="coerce")

    mask = x.notna() & w.notna() & w.gt(0)

    if not mask.any():
        return np.nan

    return float((x[mask] * w[mask]).sum() / w[mask].sum())


def get_symbol_profile_name(symbol):
    symbol = str(symbol).upper()

    if symbol in ETF_SYMBOLS:
        return "ETF"

    if symbol in LIQUID_STOCK_SYMBOLS:
        return "LIQUID_STOCK"

    return "SMALL_CAP"


def get_symbol_profile(symbol):
    return SYMBOL_PROFILES[get_symbol_profile_name(symbol)]


def price_aware_spread_limit(mid, base_limit):
    mid = safe_float(mid)

    if pd.isna(mid) or mid <= 0:
        return base_limit

    # Cheap options naturally have wider quoted spreads.
    # They can be Grade B/C, but sub-$0.25 options should never be Grade A.
    if mid >= 5.00:
        return base_limit
    if mid >= 1.00:
        return max(base_limit, 0.15)
    if mid >= 0.25:
        return max(base_limit, 0.20)
    return max(base_limit, 0.30)


def profile_threshold(df, key, default=np.nan):
    if df is None or df.empty or "symbol" not in df.columns:
        return default

    symbol = str(df["symbol"].dropna().iloc[0]).upper() if df["symbol"].notna().any() else ""
    return get_symbol_profile(symbol).get(key, default)
