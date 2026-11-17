# Shared constants for the options flow scanner.

# ---------------------------------------------------------------------
# Model features
# ---------------------------------------------------------------------
# Important:
# - volume_oi_ratio_model uses 0 when OI is unavailable/0.
# - Raw volume/OI is still printed, but not allowed to explode when OI=0.
# - Prediction always uses fresh IB snapshot rows.
# - Historical per-ticker snapshot cache is used only for training.
FEATURE_COLS = [
    "dte",
    "abs_otm_pct",
    "spread_pct",
    "log_volume",
    "log_oi",
    "volume_oi_ratio_model",
    "log_dollar_volume",
    "mid_vs_close_pct_model",
]


# Previous closes below this level are often stale/tiny option marks.
# Example: close=0.01 and mid=1.20 creates a fake +11,900% reprice.
DEFAULT_MIN_PREV_CLOSE_FOR_REPRICE = 0.10
DEFAULT_SNAPSHOT_SUMMARY_CACHE_DIR = "data/snapshot_summaries"


ETF_SYMBOLS = {
    "SPY", "QQQ", "IWM", "DIA", "SMH", "XLK", "XLF", "XLE", "XLY",
    "XLC", "XLI", "XLV", "XLP", "XLU", "XBI", "KRE", "TLT", "GLD",
    "SLV", "USO", "UNG",
}


LIQUID_STOCK_SYMBOLS = {
    "AAPL", "AMD", "AMZN", "AVGO", "COIN", "GOOGL", "GOOG", "META",
    "MSFT", "MSTR", "MU", "NFLX", "NVDA", "PLTR", "SMCI", "TSLA",
}


SYMBOL_PROFILES = {
    "ETF": {
        "min_a_dollar_volume": 500_000,
        "min_b_dollar_volume": 100_000,
        "min_c_dollar_volume": 25_000,
        "min_a_volume": 100,
        "min_b_volume": 50,
        "min_c_volume": 10,
        "max_a_spread": 0.10,
        "max_b_spread": 0.15,
        "max_c_spread": 0.30,
        "net_read_threshold": 1_000_000,
    },
    "LIQUID_STOCK": {
        "min_a_dollar_volume": 250_000,
        "min_b_dollar_volume": 75_000,
        "min_c_dollar_volume": 25_000,
        "min_a_volume": 100,
        "min_b_volume": 50,
        "min_c_volume": 10,
        "max_a_spread": 0.10,
        "max_b_spread": 0.15,
        "max_c_spread": 0.30,
        "net_read_threshold": 500_000,
    },
    "SMALL_CAP": {
        "min_a_dollar_volume": 75_000,
        "min_b_dollar_volume": 25_000,
        "min_c_dollar_volume": 5_000,
        "min_a_volume": 50,
        "min_b_volume": 20,
        "min_c_volume": 5,
        "max_a_spread": 0.15,
        "max_b_spread": 0.25,
        "max_c_spread": 0.35,
        "net_read_threshold": 100_000,
    },
}


QUOTE_COLS = [
    "snapshot_ts",
    "scan_id",
    "symbol",
    "contract",
    "option_type",
    "expiry",
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
    "oi_missing",
    "volume_oi_ratio",
    "volume_oi_ratio_model",
    "dollar_volume",
    "log_dollar_volume",
    "mid_vs_close_pct",
    "mid_vs_close_pct_model",
    "stale_close",
    "iv",
    "delta",
    "gamma",
    "theta",
    "vega",
    "moneyness",
    "otm_pct",
    "abs_otm_pct",
    "price_source",
]


CONTRACT_CACHE_COLS = [
    "symbol",
    "expiry",
    "strike",
    "right",
    "conId",
    "localSymbol",
    "tradingClass",
    "exchange",
    "currency",
    "fetched_at",
]


SNAPSHOT_SUMMARY_COLS = [
    "timestamp",
    "symbol",
    "spot",
    "call_contracts",
    "put_contracts",
    "call_actionable_count",
    "put_actionable_count",
    "call_total_volume",
    "put_total_volume",
    "call_total_premium",
    "put_total_premium",
    "call_actionable_premium",
    "put_actionable_premium",
    "put_call_premium_ratio",
    "avg_call_spread",
    "avg_put_spread",
    "call_mid_vs_close_weighted_avg",
    "put_mid_vs_close_weighted_avg",
    "near_atm_call_premium",
    "near_atm_put_premium",
    "call_delta_proxy",
    "put_delta_proxy",
    "net_read",
    "top_call_contracts",
    "top_put_contracts",
]


EMPTY_COLS = list(dict.fromkeys(QUOTE_COLS + FEATURE_COLS + [
    "is_anomaly",
    "anomaly_score",
    "quality",
    "quality_tier",
    "tags",
    "actionable",
    "training_source",
    "reason",
]))
