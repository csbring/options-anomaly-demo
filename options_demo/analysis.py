import base64
import json
from datetime import datetime, timezone
from io import BytesIO
import re

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
import numpy as np
import pandas as pd

from .engine.cleaning import clean_chain
from .engine.scoring import score_with_training_cache
from .fixtures import fixture_pair

SYMBOL = re.compile(r"[A-Z]{1,6}(?:\.[A-Z])?\Z")


def parse_symbol(message: str) -> str:
    parts = message.strip().upper().split()
    if parts and parts[0] in ("FLOW", "!FLOW", "/FLOW", "ANALYZE", "SCAN"):
        parts = parts[1:]
    if len(parts) != 1 or not SYMBOL.fullmatch(parts[0].lstrip("$")):
        raise ValueError("Enter a ticker such as AAPL, or ‘flow AAPL’.")
    return parts[0].lstrip("$")


def prepare(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    # Reject crossed, missing and non-finite quotes rather than using last/close.
    raw = raw.copy()
    numeric = ["bid", "ask", "volume", "spot", "strike"]
    raw[numeric] = raw[numeric].apply(pd.to_numeric, errors="coerce")
    valid = np.isfinite(raw[numeric]).all(axis=1)
    valid &= (raw.bid > 0) & (raw.ask >= raw.bid) & (raw.spot > 0) & (raw.strike > 0)
    raw = raw.loc[valid].copy()
    raw["mid"] = (raw.bid + raw.ask) / 2
    raw["spread_pct"] = (raw.ask - raw.bid) / raw.mid
    raw["price_source"] = "bid_ask"
    return clean_chain(raw, symbol, debug_filter=False)


def plot_report(scored: pd.DataFrame, symbol: str, source: str) -> str:
    fig = Figure(figsize=(13.5, 4.4), facecolor="#101d2b", layout="constrained")
    axes = fig.subplots(1, 3)
    for ax in axes:
        ax.set_facecolor("#101d2b")
        ax.tick_params(colors="#b2c2d3", labelsize=8)
        ax.xaxis.label.set_color("#b2c2d3")
        ax.yaxis.label.set_color("#b2c2d3")
        ax.title.set_color("#f0f5fa")
        ax.grid(alpha=.12, color="#b2c2d3")
        for spine in ax.spines.values():
            spine.set_color("#294053")
    normal = scored[~scored.is_anomaly]
    flagged = scored[scored.is_anomaly]
    axes[0].scatter(normal.open_interest, normal.volume, s=16, alpha=.5, c="#6a899f", label="Other quotes")
    axes[0].scatter(flagged.open_interest, flagged.volume, s=44, c="#ffc47a", label="Flagged")
    axes[0].set(xscale="symlog", yscale="symlog", xlabel="Open interest", ylabel="Volume", title="01  Activity versus positioning")
    axes[0].legend(facecolor="#101d2b", labelcolor="#b2c2d3", fontsize=8)
    for side, color in (("call", "#60dfc2"), ("put", "#a7adff")):
        part = scored[scored.option_type == side]
        axes[1].scatter(part.strike, part.anomaly_score, s=np.where(part.is_anomaly, 48, 15), alpha=.75, color=color, label=side.title())
    axes[1].set(xlabel="Strike", ylabel="Anomaly score · higher is more unusual", title="02  Where the outliers sit")
    axes[1].legend(facecolor="#101d2b", labelcolor="#b2c2d3", fontsize=8)
    axes[2].scatter(scored.spread_pct*100, scored.anomaly_score, c=np.where(scored.is_anomaly, "#ffc47a", "#6a899f"), alpha=.7, s=25)
    axes[2].set(xlabel="Quoted spread / midpoint (%)", ylabel="Anomaly score", title="03  Check the quote quality")
    fig.suptitle(f"{symbol}  /  {source}", color="#f0f5fa", fontsize=14, ha="left", x=.02)
    out = BytesIO()
    fig.savefig(out, format="png", dpi=145, facecolor=fig.get_facecolor())
    return base64.b64encode(out.getvalue()).decode()


def analyze(symbol: str, scenario="call_activity", source="synthetic") -> dict:
    symbol = parse_symbol(symbol)
    if source == "synthetic":
        baseline, raw = fixture_pair(symbol, scenario)
        train = prepare(baseline, symbol)
        label = "SYNTHETIC DATA · invented prices and dates"
        model_basis = f"Separate synthetic baseline · {len(train)} training rows"
        metadata = {"market_data_types": [], "quote_time": "Invented scenario dated 2030-01-02"}
    elif source == "tws":
        from .tws import collect
        raw, metadata = collect(symbol)
        train = pd.DataFrame()
        label = "TWS SNAPSHOT · " + metadata["data_label"]
        model_basis = "Current snapshot fit · cross-sectional outliers, no historical baseline"
    else:
        raise ValueError("Unsupported data source.")
    current = prepare(raw, symbol)
    scored = score_with_training_cache(current, train, n_estimators=150)
    if scored.empty:
        raise ValueError("Not enough usable option quotes. Need at least 20 per side. Check quotes, subscriptions and market hours.")
    scored = scored.sort_values("anomaly_score", ascending=False).reset_index(drop=True)
    flags = scored[scored.is_anomaly]
    counts = {side: int((flags.option_type == side).sum()) for side in ("call", "put")}
    eligible = flags[flags.actionable & ~flags.greeks_missing & ~flags.oi_missing]
    # Legacy 'actionable' is a quote/liquidity filter, not a trade instruction.
    result = {
        "symbol": symbol, "scenario": scenario, "source": source, "source_label": label,
        "generated_at": datetime.now(timezone.utc).isoformat(), "model_basis": model_basis,
        "metadata": metadata, "quotes": len(scored), "excluded": len(raw)-len(scored),
        "flagged": len(flags), "calls": counts["call"], "puts": counts["put"],
        "quality_pass": len(eligible), "spot": round(float(scored.spot.iloc[0]), 2),
        "chart": plot_report(scored, symbol, label),
    }
    cols = ["contract", "option_type", "strike", "expiry", "volume", "open_interest", "volume_oi_ratio", "spread_pct", "anomaly_score", "is_anomaly", "reason"]
    if "quote_received_at" in scored:
        cols += ["quote_received_at", "market_data_type"]
    result["rows"] = json.loads(scored[cols].head(12).to_json(orient="records"))
    result["csv"] = scored[cols].to_csv(index=False)
    result["summary"] = (
        f"{symbol}: {len(flags)} of {len(scored)} option quotes flagged — "
        f"{counts['call']} calls and {counts['put']} puts. "
        f"{len(eligible)} flagged contracts pass the liquidity and Greeks checks. "
        "Start with the highlighted contracts, then compare their volume, open interest and spread. "
        "Anomaly scores measure unusualness; they do not identify buying versus selling or predict returns."
    )
    return result


def explain(report: dict, question: str) -> str:
    q = question.strip().lower().rstrip("?")
    if q in ("summary", "summarize"):
        return report["summary"]
    if q in ("why", "explain", "why flagged", "why flagged these", "why these"):
        top = report["rows"][0]
        return f"The highest-scoring contract is {top['contract']}: {top['reason']}. These are descriptive metrics, not causal model attributions. The model combines eight features, including DTE, distance from spot, spread, volume, OI and repricing."
    if q in ("calls", "puts"):
        return f"{report['symbol']} has {report[q]} flagged {q}. Calls and puts are modeled separately. Contract type alone cannot establish bullish or bearish intent; trade direction and multi-leg context are absent."
    if q in ("quality", "spreads", "risk"):
        return f"{report['quality_pass']} of {report['flagged']} flagged contracts pass the liquidity and Greeks checks. {report['excluded']} input rows were excluded or could not be scored. Wide spreads and missing OI can make unusual activity misleading."
    if q in ("model", "method", "how"):
        return report["model_basis"] + ". Separate call/put Isolation Forests use robust median/IQR scaling and 8% contamination. The threshold is a modeling choice, not a probability of profit."
    raise ValueError("Try ‘why’, ‘calls’, ‘puts’, ‘quality’ or ‘model’, or enter another ticker.")
