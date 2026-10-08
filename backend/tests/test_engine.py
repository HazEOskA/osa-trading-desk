import asyncio
import sqlite3
import time
import httpx
import pytest
from app.engine import Ledger, Pair, evaluate, parse_pair
from app.judge import judge
from app.market import Market, MarketUnavailable


def sample(price=1, age=5, observed=None):
    return Pair('TOKEN123','PAIR123','OSA',price,50000,200000,age,200,150,500000,
                'https://dexscreener.com/solana/PAIR123', observed or int(time.time()))


def test_risk_rejects_unknowns():
    p = sample(age=-1)
    assert not evaluate(p)['accepted']
    assert not evaluate(sample(price=0))['accepted']


def test_paper_buy_sell_and_proof(tmp_path):
    l = Ledger(str(tmp_path / 'paper.db'))
    assert l.state()['cash'] == 1000
    buy = l.buy(sample())
    assert buy['executed'] and buy['side'] == 'BUY'
    assert l.state()['cash'] == 980
    assert not l.buy(sample())['executed']  # no duplicate
    sell = l.sell(sample(price=1.3))
    assert sell['executed'] and sell['realized_pnl'] > 0
    assert len(l.state()['positions']) == 0
    assert l.verify_evidence()
    l2 = Ledger(str(tmp_path / 'paper.db'))
    assert len(l2.state()['fills']) == 2
    assert l2.verify_evidence()


def test_halt_and_stale_fail_closed(tmp_path):
    l = Ledger(str(tmp_path / 'paper.db'))
    assert l.buy(sample(observed=int(time.time()) - 300))['reason'] == 'STALE_MARKET_DATA'
    l.set_halt(True)
    assert l.buy(sample())['reason'] == 'HALTED'
    l.set_halt(False)
    assert l.buy(sample())['executed']


def test_event_tamper_detected(tmp_path):
    path = str(tmp_path / 'paper.db')
    l = Ledger(path)
    l.buy(sample())
    with sqlite3.connect(path) as db:
        db.execute("UPDATE events SET payload='{}' WHERE id=1")
    assert not l.verify_evidence()


@pytest.mark.asyncio
async def test_ai_no_credentials_never_approves(monkeypatch):
    for k in ('AI_API_URL', 'AI_API_KEY', 'AI_MODEL'):
        monkeypatch.delenv(k, raising=False)
    assert (await judge(sample()))['decision'] == 'WAIT'


@pytest.mark.asyncio
async def test_market_live_contract_mock():
    raw = {'chainId':'solana','pairAddress':'PAIR123','baseToken':{'address':'TOKEN123','symbol':'OSA'},
           'priceUsd':'1.0','liquidity':{'usd':50000},'volume':{'h24':200000},
           'txns':{'h24':{'buys':200,'sells':150}},'fdv':500000,
           'pairCreatedAt':int(time.time()*1000)-3600000*5}
    def handler(request):
        if request.url.path == '/token-boosts/top/v1':
            return httpx.Response(200,json=[{'chainId':'solana','tokenAddress':'TOKEN123'}])
        return httpx.Response(200,json=[raw])
    m = Market(transport=httpx.MockTransport(handler))
    result = await m.candidates()
    assert len(result) == 1 and evaluate(result[0])['accepted']
    quote = await m.quote('TOKEN123','PAIR123')
    assert quote.price == 1


@pytest.mark.asyncio
async def test_market_failure_closed():
    m = Market(transport=httpx.MockTransport(lambda req: httpx.Response(500)))
    with pytest.raises(MarketUnavailable):
        await m.candidates()
