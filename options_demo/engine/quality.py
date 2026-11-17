import numpy as np
import pandas as pd

from .utils import get_symbol_profile, price_aware_spread_limit, robust_z_clip


def add_quality_columns(df):
    df = df.copy()

    symbol = str(df["symbol"].dropna().iloc[0]).upper() if df["symbol"].notna().any() else ""
    profile = get_symbol_profile(symbol)

    df["delta_abs"] = df["delta"].abs()
    df["delta_valid"] = df["delta"].notna() & df["delta"].ne(0)

    df["spread_limit_a"] = df["mid"].apply(lambda x: price_aware_spread_limit(x, profile["max_a_spread"]))
    df["spread_limit_b"] = df["mid"].apply(lambda x: price_aware_spread_limit(x, profile["max_b_spread"]))
    df["spread_limit_c"] = df["mid"].apply(lambda x: price_aware_spread_limit(x, profile["max_c_spread"]))

    df["tight_spread"] = (
        df["price_source"].eq("bid_ask")
        & df["spread_pct"].fillna(1).le(df["spread_limit_a"])
    )

    df["b_spread_ok"] = (
        df["price_source"].eq("bid_ask")
        & df["spread_pct"].fillna(1).le(df["spread_limit_b"])
    )

    df["c_spread_ok"] = (
        df["price_source"].eq("bid_ask")
        & df["spread_pct"].fillna(1).le(df["spread_limit_c"])
    )

    df["near_atm"] = df["abs_otm_pct"].fillna(1).le(0.05)

    df["deep_itm"] = (
        ((df["option_type"].eq("call")) & (df["moneyness"].le(0.90)))
        | ((df["option_type"].eq("put")) & (df["moneyness"].ge(1.10)))
    )

    df["far_otm"] = df["abs_otm_pct"].fillna(0).ge(0.15)
    df["lotto"] = df["far_otm"] & df["delta_abs"].fillna(0).lt(0.15)

    # Grade A: real tradable anomaly. Strict, but price-aware for cheap names.
    grade_a_base = (
        df["tight_spread"]
        & df["mid"].fillna(0).ge(0.25)
        & df["dollar_volume"].fillna(0).ge(profile["min_a_dollar_volume"])
        & df["volume"].fillna(0).ge(profile["min_a_volume"])
        & df["delta_valid"]
        & df["delta_abs"].between(0.15, 0.85)
    )

    grade_a_deep_itm = (
        df["deep_itm"]
        & df["tight_spread"]
        & df["dollar_volume"].fillna(0).ge(max(profile["min_a_dollar_volume"], 500_000))
    )

    grade_a_far_otm = (
        df["far_otm"]
        & ~df["lotto"]
        & df["tight_spread"]
        & df["dollar_volume"].fillna(0).ge(max(profile["min_a_dollar_volume"], 250_000))
    )

    grade_a = grade_a_base | grade_a_deep_itm | grade_a_far_otm

    # Grade B: watchlist. Useful for small caps without letting junk drive alerts.
    grade_b = (
        ~grade_a
        & df["b_spread_ok"]
        & df["dollar_volume"].fillna(0).ge(profile["min_b_dollar_volume"])
        & df["volume"].fillna(0).ge(profile["min_b_volume"])
        & df["delta_valid"]
        & df["delta_abs"].between(0.10, 0.90)
        & ~df["lotto"]
    )

    # Grade C: speculative/weird but worth logging. Do not use for net read.
    grade_c = (
        ~grade_a
        & ~grade_b
        & df["c_spread_ok"]
        & df["dollar_volume"].fillna(0).ge(profile["min_c_dollar_volume"])
        & df["volume"].fillna(0).ge(profile["min_c_volume"])
    )

    df["quality_tier"] = np.select(
        [grade_a, grade_b, grade_c],
        ["A_actionable", "B_watchlist", "C_speculative"],
        default="D_junk",
    )

    # Keep the old boolean for backward compatibility.
    df["actionable"] = df["quality_tier"].isin(["A_actionable", "B_watchlist"])
    df["quality"] = df["quality_tier"]

    def build_tags(row):
        tags = []

        if row.get("near_atm", False):
            tags.append("near_atm")
        if row.get("far_otm", False):
            tags.append("far_otm")
        if row.get("deep_itm", False):
            tags.append("deep_itm")
        if row.get("lotto", False):
            tags.append("lotto")
        if row.get("stale_close", False):
            tags.append("stale_close")
        if row.get("spread_pct", 0) >= 0.10:
            tags.append("wide_spread")
        if row.get("deep_itm", False):
            tags.append("stock_replacement")
        elif row.get("dte", 999) <= 7 and row.get("near_atm", False):
            tags.append("gamma_bet")

        if not tags:
            tags.append("standard")

        return ",".join(tags)

    df["tags"] = df.apply(build_tags, axis=1)

    return df


def add_reason_columns(df):
    if df is None or df.empty:
        return df

    df = df.copy()

    reason_metric_cols = [
        "volume",
        "open_interest",
        "volume_oi_ratio_model",
        "dollar_volume",
        "spread_pct",
        "abs_otm_pct",
        "mid",
    ]

    z_parts = []

    for _option_type, part in df.groupby("option_type"):
        z = robust_z_clip(part, reason_metric_cols)
        z.columns = [f"z_{c}" for c in z.columns]
        z_parts.append(z)

    if z_parts:
        z_all = pd.concat(z_parts).sort_index()
        df = pd.concat([df, z_all], axis=1)

    df["greeks_missing"] = (
        df["iv"].fillna(0).eq(0)
        | df["delta"].fillna(0).eq(0)
    )

    df["bid_ask_missing"] = (
        df["bid"].fillna(0).le(0)
        | df["ask"].fillna(0).le(0)
        | df["price_source"].ne("bid_ask")
    )

    def explain(row):
        reasons = []

        if row.get("oi_missing", False):
            reasons.append("OI unavailable/0")
        else:
            if row["volume_oi_ratio"] >= 10:
                reasons.append(f"volume/OI {row['volume_oi_ratio']:.1f}x")
            elif row["volume_oi_ratio"] >= 5:
                reasons.append(f"volume/OI {row['volume_oi_ratio']:.1f}x")

        if row.get("z_dollar_volume", 0) >= 2.5 or row["dollar_volume"] >= 500_000:
            reasons.append(f"large $vol ${row['dollar_volume']:,.0f}")

        if row.get("z_volume", 0) >= 2.5:
            reasons.append(f"high volume {row['volume']:.0f}")

        if row["spread_pct"] >= 0.08:
            reasons.append(f"wide spread {row['spread_pct']:.1%}")

        if row["option_type"] == "call" and row["moneyness"] <= 0.90:
            reasons.append("deep ITM call")
        elif row["option_type"] == "put" and row["moneyness"] >= 1.10:
            reasons.append("deep ITM put")

        if row["abs_otm_pct"] >= 0.15:
            reasons.append(f"far from spot {row['abs_otm_pct']:.1%}")

        if row.get("stale_close", False):
            reasons.append("stale/tiny prev close ignored")
        elif pd.notna(row.get("mid_vs_close_pct", np.nan)):
            if row["mid_vs_close_pct"] <= -0.30:
                reasons.append(f"down {abs(row['mid_vs_close_pct']):.0%} vs prev close")
            elif row["mid_vs_close_pct"] >= 0.30:
                reasons.append(f"up {row['mid_vs_close_pct']:.0%} vs prev close")

        if row["bid_ask_missing"]:
            reasons.append(f"missing bid/ask, used {row['price_source']}")

        if row["greeks_missing"]:
            reasons.append("missing Greeks")

        if not reasons:
            reasons.append("unusual feature mix")

        return "; ".join(reasons)

    df["reason"] = df.apply(explain, axis=1)

    return df
