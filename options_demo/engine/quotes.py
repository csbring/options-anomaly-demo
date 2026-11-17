import numpy as np
import pandas as pd

from .constants import QUOTE_COLS
from .utils import is_num, now_ny, safe_float


def chunks(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def get_greeks(ticker):
    greeks = (
        ticker.modelGreeks
        or ticker.bidGreeks
        or ticker.askGreeks
        or ticker.lastGreeks
    )

    return {
        "iv": safe_float(getattr(greeks, "impliedVol", np.nan)),
        "delta": safe_float(getattr(greeks, "delta", np.nan)),
        "gamma": safe_float(getattr(greeks, "gamma", np.nan)),
        "theta": safe_float(getattr(greeks, "theta", np.nan)),
        "vega": safe_float(getattr(greeks, "vega", np.nan)),
    }


def calc_mid_and_spread(bid, ask, last, close):
    if is_num(bid) and is_num(ask) and bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid if mid > 0 else np.nan
        return mid, spread_pct, "bid_ask"

    if is_num(last) and last > 0:
        return last, np.nan, "last"

    if is_num(close) and close > 0:
        return close, np.nan, "close"

    return np.nan, np.nan, "missing"


def ticker_to_quote_row(ticker, spot, today):
    c = ticker.contract
    option_type = "call" if c.right == "C" else "put"

    bid = safe_float(ticker.bid)
    ask = safe_float(ticker.ask)
    last = safe_float(ticker.last)
    close = safe_float(ticker.close)

    mid, spread_pct, price_source = calc_mid_and_spread(bid, ask, last, close)

    if option_type == "call":
        volume = safe_float(getattr(ticker, "callVolume", np.nan))
        oi = safe_float(getattr(ticker, "callOpenInterest", np.nan))
    else:
        volume = safe_float(getattr(ticker, "putVolume", np.nan))
        oi = safe_float(getattr(ticker, "putOpenInterest", np.nan))

    fallback_volume = safe_float(getattr(ticker, "volume", np.nan))

    if not is_num(volume):
        volume = fallback_volume

    if not is_num(volume):
        volume = 0

    if not is_num(oi):
        oi = 0

    greeks = get_greeks(ticker)

    expiry = pd.to_datetime(c.lastTradeDateOrContractMonth[:8])
    dte = (expiry - today).days

    strike = float(c.strike)
    moneyness = strike / spot

    if option_type == "call":
        otm_pct = (strike - spot) / spot
    else:
        otm_pct = (spot - strike) / spot

    return {
        "snapshot_ts": np.nan,
        "scan_id": np.nan,
        "symbol": c.symbol,
        "contract": c.localSymbol,
        "option_type": option_type,
        "expiry": c.lastTradeDateOrContractMonth[:8],
        "dte": dte,
        "strike": strike,
        "spot": spot,
        "bid": bid,
        "ask": ask,
        "last": last,
        "close": close,
        "mid": mid,
        "spread_pct": spread_pct,
        "volume": volume,
        "open_interest": oi,
        "oi_missing": oi <= 0,
        "volume_oi_ratio": np.nan,
        "volume_oi_ratio_model": 0.0,
        "dollar_volume": np.nan,
        "log_dollar_volume": 0.0,
        "mid_vs_close_pct": np.nan,
        "mid_vs_close_pct_model": 0.0,
        "stale_close": False,
        "iv": greeks["iv"],
        "delta": greeks["delta"],
        "gamma": greeks["gamma"],
        "theta": greeks["theta"],
        "vega": greeks["vega"],
        "moneyness": moneyness,
        "otm_pct": otm_pct,
        "abs_otm_pct": abs(otm_pct),
        "price_source": price_source,
    }


def pull_option_quotes_snapshot(ib, contracts, spot, batch_size=2000):
    if not contracts:
        return pd.DataFrame(columns=QUOTE_COLS)

    rows = []
    today = now_ny().normalize().tz_localize(None)

    for batch_num, batch in enumerate(chunks(contracts, batch_size), start=1):
        qualified = [c for c in batch if getattr(c, "conId", 0)]

        missing_conid = [c for c in batch if not getattr(c, "conId", 0)]
        if missing_conid:
            qualified += ib.qualifyContracts(*missing_conid)

        if not qualified:
            print(f"Batch {batch_num}: no contracts qualified")
            continue

        tickers = ib.reqTickers(*qualified)

        for t in tickers:
            rows.append(ticker_to_quote_row(t, spot, today))

        print(f"Batch {batch_num}: snapshot rows={len(tickers)}")

    return pd.DataFrame(rows, columns=QUOTE_COLS)


def pull_option_quotes_stream(
    ib,
    contracts,
    spot,
    batch_size=2000,
    stream_seconds=1.0,
    settle_seconds=2.0,
    generic_ticks="100,101,104,106",
):
    """Stream option quotes in batches and return one latest row per contract.

    This keeps the rest of the scanner unchanged: output columns match QUOTE_COLS.
    Each batch opens live market-data lines, waits for updates, reads latest values,
    then cancels subscriptions before moving to the next batch.
    """
    if not contracts:
        return pd.DataFrame(columns=QUOTE_COLS)

    rows = []
    today = now_ny().normalize().tz_localize(None)

    for batch_num, batch in enumerate(chunks(contracts, batch_size), start=1):
        qualified = [c for c in batch if getattr(c, "conId", 0)]

        missing_conid = [c for c in batch if not getattr(c, "conId", 0)]
        if missing_conid:
            qualified += ib.qualifyContracts(*missing_conid)

        if not qualified:
            print(f"Batch {batch_num}: no contracts qualified")
            continue

        tickers = []

        try:
            for c in qualified:
                tickers.append(
                    ib.reqMktData(
                        c,
                        genericTickList=generic_ticks,
                        snapshot=False,
                        regulatorySnapshot=False,
                    )
                )

            # Give TWS time to attach subscriptions, then collect updates.
            if settle_seconds > 0:
                ib.sleep(settle_seconds)

            if stream_seconds > 0:
                ib.sleep(stream_seconds)

            batch_rows = [ticker_to_quote_row(t, spot, today) for t in tickers]
            rows.extend(batch_rows)

            valid_bid_ask = sum(
                1 for r in batch_rows
                if is_num(r["bid"]) and is_num(r["ask"]) and r["bid"] > 0 and r["ask"] > 0
            )
            valid_greeks = sum(
                1 for r in batch_rows
                if is_num(r["iv"]) or is_num(r["delta"])
            )

            print(
                f"Batch {batch_num}: streamed contracts={len(tickers)} "
                f"bid/ask={valid_bid_ask} greeks={valid_greeks}"
            )

        finally:
            for t in tickers:
                try:
                    ib.cancelMktData(t.contract)
                except Exception as e:
                    print(f"Batch {batch_num}: cancelMktData failed for {t.contract}: {e}")

            # Small pause so cancelled market-data lines release before next batch.
            ib.sleep(0.5)

    return pd.DataFrame(rows, columns=QUOTE_COLS)


def pull_option_quotes(
    ib,
    contracts,
    spot,
    batch_size=2000,
    quote_mode="stream",
    stream_seconds=8.0,
    settle_seconds=2.0,
    generic_ticks="100,101,104,106",
):
    if quote_mode == "snapshot":
        return pull_option_quotes_snapshot(
            ib=ib,
            contracts=contracts,
            spot=spot,
            batch_size=batch_size,
        )

    if quote_mode != "stream":
        raise ValueError(f"Unknown quote_mode: {quote_mode}")

    return pull_option_quotes_stream(
        ib=ib,
        contracts=contracts,
        spot=spot,
        batch_size=batch_size,
        stream_seconds=stream_seconds,
        settle_seconds=settle_seconds,
        generic_ticks=generic_ticks,
    )
