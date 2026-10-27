"""OSA-STRAT-001 CUE gate acceptance / fail-closed scenarios. PAPER ONLY."""
import time
import pytest
from app.engine import Ledger, Pair
from app.risk_gate import CueReport, MISSION020_CASES, REQUIRED_CHECKS, RiskGate


def sample(price=1):
    return Pair(
        'TOKEN123', 'PAIR123', 'OSA', price, 50000, 200000, 5, 200, 150, 500000,
        'https://dexscreener.com/solana/PAIR123', int(time.time()),
    )


def report(pair, **changes):
    data = {
        'mint': pair.token,
        'pair': pair.pair,
        'observed_at': int(time.time()),
        'evidence_ref': 'TEST_ONLY_NOT_ONCHAIN',
        'checks': {c: 'PASS' for c in REQUIRED_CHECKS},
    }
    data.update(changes)
    return CueReport(**data)


def test_mission020_exact_mints_remain_blocked_by_default(tmp_path):
    gate = RiskGate()
    for index, case in enumerate(MISSION020_CASES):
        p = sample()
        p = p.__class__(
            case['mint'], case['pair'], p.symbol, p.price, p.liquidity, p.volume,
            p.age_hours, p.buys, p.sells, p.fdv, p.url, p.observed_at,
        )
        assert gate.assess(p)['reason'] == 'MISSION020_NO_FORWARD'
        l = Ledger(str(tmp_path / f'm020_{index}.sqlite3'))
        assert l.buy(p)['reason'] == 'CUE_RISK_BLOCKED'
        assert l.state()['fills'] == []


def test_unknown_token_never_buys_without_cue(tmp_path):
    p = sample()
    l = Ledger(str(tmp_path / 'blocked.sqlite3'))
    result = l.buy(p)
    assert result['reason'] == 'CUE_RISK_BLOCKED'
    assert l.state()['cash'] == 1000
    assert l.state()['fills'] == []


def test_expired_future_wrong_pair_or_missing_provenance(tmp_path):
    p = sample()
    cases = [
        report(p, observed_at=int(time.time()) - 91),
        report(p, observed_at=int(time.time()) + 11),
        report(p, pair='WRONG_PAIR'),
        report(p, evidence_ref=''),
    ]
    for index, proof in enumerate(cases):
        gate = RiskGate(lambda _, proof=proof: proof)
        assert not gate.assess(p)['allowed']
        assert Ledger(str(tmp_path / f'{index}.db'), risk_gate=gate).buy(p)['reason'] == 'CUE_RISK_BLOCKED'


def test_unknown_check_and_provider_exception_fail_closed():
    p = sample()
    checks = {key: 'PASS' for key in REQUIRED_CHECKS}
    checks['current_sellability_and_depth'] = 'UNKNOWN'
    decision = RiskGate(lambda _: report(p, checks=checks)).assess(p)
    assert not decision['allowed']
    assert decision['failed_checks'] == ['current_sellability_and_depth']

    def broken(_):
        raise OSError('rpc unavailable')
    assert RiskGate(broken).assess(p)['reason'] == 'CUE_PROVIDER_ERROR'


def test_test_only_verifier_allows_paper_with_receipt(tmp_path):
    p = sample()
    gate = RiskGate(lambda pair: report(pair))
    l = Ledger(str(tmp_path / 'proof.sqlite3'), risk_gate=gate)
    assert l.buy(p)['executed'] is True
    assert l.sell(sample(price=1.3))['executed'] is True
    assert l.verify_evidence()
    assert l.state()['mode'] == 'PAPER_ONLY'


def test_strategy_metadata_distinguishes_history_from_current():
    meta = RiskGate().public_state()
    assert meta['risk_gate'] == 'BLOCKED_NO_PROVIDER'
    assert meta['onchain_execution'] is False
    assert len(meta['cases']) == 3
    assert all(c['status'] == 'BLOCK' for c in meta['cases'])


@pytest.mark.asyncio
async def test_tick_skips_ai_for_missing_cue(tmp_path, monkeypatch):
    from app import main as api

    class OnePairScanner:
        async def candidates(self):
            return [sample()]

    async def forbidden_ai(_):
        raise AssertionError('AI must not be called before CUE')

    ledger = Ledger(str(tmp_path / 'tick.sqlite3'))
    monkeypatch.setattr(api, 'ledger', ledger)
    monkeypatch.setattr(api, 'market', OnePairScanner())
    monkeypatch.setattr(api, 'judge', forbidden_ai)
    result = await api.tick()
    assert result['outcomes'][0]['reason'] == 'CUE_RISK_BLOCKED'
    assert result['scanned'] == 1
    assert ledger.state()['fills'] == []
