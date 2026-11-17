"""Bounded read-only TWS market-data adapter; no order or account exports."""
import asyncio
from datetime import datetime, timezone
import os
import socket

import numpy as np
import pandas as pd

from .engine.quotes import ticker_to_quote_row

DATA_TYPES = {1: "live", 2: "frozen", 3: "delayed", 4: "delayed frozen"}


class TWSUnavailable(RuntimeError):
    pass


def reachable():
    try:
        with socket.create_connection((os.getenv("TWS_HOST", "127.0.0.1"), int(os.getenv("TWS_PORT", "7497"))), timeout=1):
            return True
    except (OSError, ValueError):
        return False


async def collect_async(symbol):
    from ib_async import IB, Stock, Option
    ib = IB()
    ib.RequestTimeout = 12
    subscriptions = []
    try:
        try:
            await ib.connectAsync(
                os.getenv("TWS_HOST", "127.0.0.1"), int(os.getenv("TWS_PORT", "7497")),
                clientId=int(os.getenv("TWS_CLIENT_ID", "76")), timeout=8,
                readonly=True, fetchFields=0,
            )
        except Exception:
            raise TWSUnavailable("TWS connectivity is not available.") from None
        market_type = int(os.getenv("TWS_MARKET_DATA_TYPE", "1"))
        if market_type not in DATA_TYPES:
            raise ValueError("TWS_MARKET_DATA_TYPE must be 1, 2, 3 or 4.")
        ib.reqMarketDataType(market_type)
        stocks = await ib.qualifyContractsAsync(Stock(symbol, "SMART", "USD"))
        if len(stocks) != 1:
            raise ValueError("Ticker could not be resolved to one stock contract.")
        stock = stocks[0]
        ticker = ib.reqMktData(stock, "", False, False)
        subscriptions.append(stock)
        await asyncio.sleep(3)
        spot = ticker.marketPrice()
        if not np.isfinite(spot) or spot <= 0:
            raise ValueError("No usable underlying price from TWS.")
        chains = await ib.reqSecDefOptParamsAsync(symbol, "", stock.secType, stock.conId)
        chain = next((c for c in chains if c.exchange == "SMART" and c.tradingClass == stock.symbol), None)
        if chain is None:
            raise ValueError("No matching SMART option chain found.")
        today = pd.Timestamp.now(tz="America/New_York").normalize().tz_localize(None)
        expiries = sorted(e for e in chain.expirations if 1 <= (pd.Timestamp(e)-today).days <= 60)[:2]
        strikes = sorted((s for s in chain.strikes if spot*.9 <= s <= spot*1.1), key=lambda s: abs(s-spot))[:12]
        contracts = [Option(symbol, e, s, r, "SMART", tradingClass=chain.tradingClass) for e in expiries for s in strikes for r in ("C", "P")]
        if not contracts:
            raise ValueError("No nearby option contracts available.")
        contracts = await ib.qualifyContractsAsync(*contracts)
        ticks = []
        for contract in contracts:
            ticks.append(ib.reqMktData(contract, "100,101,104,106", False, False))
            subscriptions.append(contract)
        await asyncio.sleep(5)
        rows = []
        for t in ticks:
            row = ticker_to_quote_row(t, spot, today)
            row["quote_received_at"] = t.time.isoformat() if t.time else None
            row["market_data_type"] = t.marketDataType
            rows.append(row)
        kinds = sorted({t.marketDataType for t in ticks})
        return pd.DataFrame(rows), {
            "market_data_types": kinds,
            "data_label": ", ".join(DATA_TYPES.get(k, "unknown") for k in kinds),
            "quote_time": datetime.now(timezone.utc).isoformat(),
            "timestamp_note": "Collection time; per-contract receipt times are not exchange trade timestamps.",
            "underlying_data_type": DATA_TYPES.get(ticker.marketDataType, "unknown"),
        }
    finally:
        try:
            for contract in subscriptions:
                ib.cancelMktData(contract)
        finally:
            ib.disconnect()


def collect(symbol):
    # The app calls this in its bounded worker, which owns this event loop.
    async def bounded():
        return await asyncio.wait_for(collect_async(symbol), timeout=55)
    return asyncio.run(bounded())
