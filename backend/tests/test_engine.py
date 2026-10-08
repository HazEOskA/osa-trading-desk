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

@pytest.mark.parametrize("exit_price", [1.3, 0.8])
@pytest.mark.asyncio
async def test_scanner_outage_still_exits_open_position(tmp_path, monkeypatch, exit_price):
    from app import main as api
    l = Ledger(str(tmp_path / 'scan_failure.db'))
    assert l.buy(sample())['executed']
    order = []

    class BrokenScanner:
        async def candidates(self):
            order.append('scan')
            raise MarketUnavailable('scanner offline')

        async def quote(self, token, pair):
            order.append('quote')
            assert (token, pair) == ('TOKEN123', 'PAIR123')
            return sample(price=exit_price)

    async def unexpected_judge(_):
        raise AssertionError('No AI approval or buy on scanner failure')

    monkeypatch.setattr(api, 'ledger', l)
    monkeypatch.setattr(api, 'market', BrokenScanner())
    monkeypatch.setattr(api, 'judge', unexpected_judge)
    result = await api.tick()
    assert order == ['quote', 'scan']
    assert result['scanner_status'] == 'DEGRADED'
    assert result['reason'] == 'SCAN_UNAVAILABLE'
    assert result['scanned'] == 0
    assert len(result['outcomes']) == 1 and result['outcomes'][0]['side'] == 'SELL'
    assert not l.state()['positions']
    assert l.verify_evidence()


@pytest.mark.asyncio
async def test_scanner_and_position_quote_outage_fails_closed(tmp_path, monkeypatch):
    from app import main as api
    l = Ledger(str(tmp_path / 'both_down.db'))
    assert l.buy(sample())['executed']

    class AllDown:
        async def candidates(self):
            raise MarketUnavailable('scanner offline')

        async def quote(self, token, pair):
            raise MarketUnavailable('quote offline')

    monkeypatch.setattr(api, 'ledger', l)
    monkeypatch.setattr(api, 'market', AllDown())
    result = await api.tick()
    assert result['reason'] == 'SCAN_UNAVAILABLE'
    assert result['outcomes'] == [{'executed': False, 'reason': 'POSITION_QUOTE_UNAVAILABLE', 'token': 'TOKEN123'}]
    assert len(l.state()['positions']) == 1
    assert len(l.state()['fills']) == 1  # No synthetic close
    assert l.verify_evidence()


@pytest.mark.asyncio
async def test_scanner_get_still_returns_503_on_outage(tmp_path, monkeypatch):
    from app import main as api
    from fastapi import HTTPException

    class BrokenScanner:
        async def candidates(self):
            raise MarketUnavailable('offline')

    monkeypatch.setattr(api, 'market', BrokenScanner())
    with pytest.raises(HTTPException) as exc:
        await api.scan()
    assert exc.value.status_code == 503


@pytest.mark.parametrize(('field', 'changed', 'side'), [
    ('usd', 999999, 'BUY'),
    ('units', 1, 'BUY'),
    ('fee', 42, 'SELL'),
    ('reference', 0.1, 'SELL'),
    ('execution', 0.1, 'BUY'),
    ('realized_pnl', 8000, 'SELL'),
    ('token', 'FAKE', 'BUY'),
    ('symbol', 'FAKE', 'SELL'),
    ('time', 1, 'BUY'),
    ('market_observed_at', 1, 'BUY'),
    ('evidence_hash', 'fake-hash', 'SELL'),
])
def test_fill_mutations_break_evidence(tmp_path, field, changed, side):
    path = str(tmp_path / 'tamper.db')
    l = Ledger(path)
    assert l.buy(sample())['executed']
    assert l.sell(sample(price=1.3))['executed']
    assert l.verify_evidence()
    with sqlite3.connect(path) as db:
        db.execute(f'UPDATE fills SET {field}=? WHERE side=?', (changed, side))
    assert not l.verify_evidence()


@pytest.mark.parametrize('mutation', [
    'DELETE FROM fills WHERE side="BUY"',
    'DELETE FROM fills WHERE side="SELL"',
    'INSERT INTO fills(time,side,token,symbol,units,reference,execution,fee,usd,realized_pnl,market_observed_at,evidence_hash) SELECT time,side,token,symbol,units,reference,execution,fee,usd,realized_pnl,market_observed_at,evidence_hash FROM fills WHERE side="BUY"',
    'UPDATE fills SET evidence_hash=(SELECT evidence_hash FROM fills WHERE side="SELL") WHERE side="BUY"',
])
def test_fill_missing_extra_or_duplicate_binding_breaks_evidence(tmp_path, mutation):
    path = str(tmp_path / 'tamper.db')
    l = Ledger(path)
    assert l.buy(sample())['executed']
    assert l.sell(sample(price=1.3))['executed']
    assert l.verify_evidence()
    with sqlite3.connect(path) as db:
        db.execute(mutation)
    assert not l.verify_evidence()


def test_missing_fill_event_breaks_evidence(tmp_path):
    path = str(tmp_path / 'tamper.db')
    l = Ledger(path)
    assert l.buy(sample())['executed']
    with sqlite3.connect(path) as db:
        db.execute('DELETE FROM events WHERE kind="PAPER_FILL"')
    assert not l.verify_evidence()


def test_old_fill_without_symbol_binding_fails_closed(tmp_path):
    """Legacy local fills cannot be advertised as fully verified after upgrade."""
    path = str(tmp_path / 'legacy.db')
    l = Ledger(path)
    assert l.buy(sample())['executed']
    with sqlite3.connect(path) as db:
        row = db.execute('SELECT * FROM events WHERE kind="PAPER_FILL"').fetchone()
        payload = __import__('json').loads(row[3]); payload.pop('symbol')
        content = __import__('json').dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        digest = __import__('hashlib').sha256(f'GENESIS|{row[1]}|PAPER_FILL|{content}'.encode()).hexdigest()
        db.execute('UPDATE events SET payload=?,hash=? WHERE id=?', (content, digest, row[0]))
        db.execute('UPDATE fills SET evidence_hash=?', (digest,))
    assert not l.verify_evidence()

@pytest.mark.asyncio
async def test_http_tick_degraded_and_proof_detects_fill_tamper(tmp_path, monkeypatch):
    from app import main as api
    l = Ledger(str(tmp_path / 'http.db'))
    assert l.buy(sample())['executed']

    class PartialDown:
        async def candidates(self):
            raise MarketUnavailable('scanner offline')

        async def quote(self, token, pair):
            return sample(price=0.8)  # stop loss works despite scanner failure

    monkeypatch.setattr(api, 'ledger', l)
    monkeypatch.setattr(api, 'market', PartialDown())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url='http://test') as client:
        r = await client.post('/api/paper/tick')
        assert r.status_code == 200
        assert r.json()['scanner_status'] == 'DEGRADED'
        assert r.json()['outcomes'][0]['side'] == 'SELL'
        assert (await client.get('/api/proof')).json()['verified'] is True
        with sqlite3.connect(l.path) as conn:
            conn.execute("UPDATE fills SET usd=999999 WHERE side='BUY'")
        assert (await client.get('/api/proof')).json()['verified'] is False
        assert (await client.get('/api/health')).json()['onchain_enabled'] is False
