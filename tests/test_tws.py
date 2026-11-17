import asyncio
from types import SimpleNamespace

import pandas as pd
import pytest
import ib_async
from options_demo.tws import collect_async


class FakeIB:
    instances = []
    fail_chain = False

    def __init__(self):
        self.cancelled = []
        self.subscribed = []
        self.disconnected = False
        self.__class__.instances.append(self)

    async def connectAsync(self, host, port, **kwargs):
        self.connection = kwargs

    def reqMarketDataType(self, kind):
        self.kind = kind

    async def qualifyContractsAsync(self, *contracts):
        for c in contracts:
            c.conId = 123
            c.localSymbol = f"{c.symbol}-{c.right}-{c.strike}"
        return list(contracts)

    async def reqSecDefOptParamsAsync(self, *args):
        if self.fail_chain:
            raise RuntimeError("mock failure")
        self.chain_args = args
        today = pd.Timestamp.now(tz="America/New_York")
        return [SimpleNamespace(exchange="SMART", tradingClass="AAPL", expirations=[(today+pd.Timedelta(days=x)).strftime("%Y%m%d") for x in (7, 14, 30)], strikes=list(range(90, 111)))]

    def reqMktData(self, contract, *args):
        self.subscribed.append(contract)
        return SimpleNamespace(contract=contract, marketPrice=lambda: 100., bid=2., ask=2.1, last=2., close=2., callVolume=500, putVolume=400, callOpenInterest=1000, putOpenInterest=900, volume=500, modelGreeks=SimpleNamespace(impliedVol=.3, delta=.4, gamma=.02, theta=-.01, vega=.1), bidGreeks=None, askGreeks=None, lastGreeks=None, marketDataType=3, time=pd.Timestamp.now(tz="UTC"))

    def cancelMktData(self, contract):
        self.cancelled.append(contract)

    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def broker(monkeypatch):
    FakeIB.instances = []
    FakeIB.fail_chain = False
    monkeypatch.setattr(ib_async, "IB", FakeIB)
    async def no_sleep(*args): pass
    monkeypatch.setattr("options_demo.tws.asyncio.sleep", no_sleep)
    return FakeIB


def test_bounded_readonly_collection_and_data_labels(broker):
    frame, meta = asyncio.run(collect_async("AAPL"))
    instance = broker.instances[-1]
    assert len(frame) == 48
    assert instance.connection["readonly"] is True
    assert instance.connection["fetchFields"] == 0
    assert instance.chain_args[-1] == 123  # underlying conId, never exchange
    assert meta["data_label"] == "delayed"
    assert frame.market_data_type.eq(3).all()
    assert len(instance.cancelled) == len(instance.subscribed) == 49
    assert instance.disconnected


def test_subscriptions_cleanup_on_error(broker):
    broker.fail_chain = True
    with pytest.raises(RuntimeError):
        asyncio.run(collect_async("AAPL"))
    instance = broker.instances[-1]
    assert len(instance.cancelled) == 1
    assert instance.disconnected
