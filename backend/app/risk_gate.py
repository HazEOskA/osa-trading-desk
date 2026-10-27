"""OSA-STRAT-001: fail-closed CUE evidence gate for PAPER orders only.

MISSION 020 is a historical snapshot, NOT a live buy/sell permission.
The default runtime has no trusted current CUE provider: every BUY is blocked.
No wallet access, signing, RPC side effects, or on-chain execution.
"""
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

STRATEGY_ID = 'OSA-STRAT-001'
MAX_EVIDENCE_AGE_SECONDS = 90
REQUIRED_CHECKS = (
    'exact_mint_pair_role',
    'mint_transfer_controls',
    'holder_supply_reconciliation',
    'complete_account_layout',
    'physical_reserve_reconciliation',
    'current_sellability_and_depth',
    'program_admin_risk',
)

# Derived from MISSION 020 / derived/risk_gate_matrix.json and lp_evidence.json.
# All records are historical and blocked regardless of earlier partial PASS claims.
MISSION020_CAPTURE = '2026-10-05T05:17:21Z / 2026-10-05T05:31:26Z'
MISSION020_CASES = (
    {
        'asset': 'makemerich',
        'mint': '7cV2VmBttrC4BPq4rUxTYuBdGrzSS91wKgWubLX8pump',
        'pair': '4YQ979shY6rPgx7DgnmFFSYwkukoSoc5fpETEeXB7Rj8',
        'status': 'BLOCK',
        'evidence_status': 'UNKNOWN',
        'reason': 'Niezbadane bajty layoutu, brak aktualnego sellability; program z upgrade authority.',
    },
    {
        'asset': 'Agency Arcade',
        'mint': '7Gy1kLnKamjaABizZpEbnHSQVt1XbqcDfy3fnZMxpump',
        'pair': '5hAeJiT8dkdnw7RmkwLQKLYeXLRAr4i4pF3aKULnvAc9',
        'status': 'BLOCK',
        'evidence_status': 'UNKNOWN',
        'reason': 'Niezbadane bajty layoutu, brak aktualnego sellability; program z upgrade authority.',
    },
    {
        'asset': '$CHIMPSHOT',
        'mint': 'DFShY5cJ2fGDCixApzG1uddLjykEfLqngwagoM2Upump',
        'pair': '29N7SW3RPT16eCGBMUfpMzUyjFDjfoPHoYdbhSUDJ2r3',
        'status': 'BLOCK',
        'evidence_status': 'UNKNOWN',
        'reason': 'Rozbieżność 205174 lamportów, nieznany suffix, brak sellability; upgrade authority.',
    },
)


class PairIdentity(Protocol):
    token: str
    pair: str


@dataclass(frozen=True)
class CueReport:
    """Report from an explicitly wired, independently verifying CUE adapter.

    A report is NOT verified merely by using this class. Provider integration
    must independently validate on-chain content, pair role, source provenance,
    route/exit feasibility and expiry before constructing it.
    No production provider is wired in STRAT-001.
    """
    mint: str
    pair: str
    observed_at: int
    evidence_ref: str
    checks: Mapping[str, str]


def _denied(reason: str, source: str = 'CUE_NOT_CONNECTED', evidence_status: str = 'UNKNOWN') -> dict:
    return {
        'allowed': False,
        'status': 'BLOCK',
        'reason': reason,
        'source': source,
        'evidence_status': evidence_status,
        'strategy_id': STRATEGY_ID,
    }


class RiskGate:
    def __init__(self, provider: Callable[[PairIdentity], CueReport | None] | None = None):
        # No report approvals are accepted via HTTP API or token metadata.
        self._provider = provider

    def assess(self, pair: PairIdentity, now: int | None = None) -> dict:
        if not pair.token or not pair.pair:
            return _denied('INVALID_MINT_OR_PAIR')
        historical = next((r for r in MISSION020_CASES if r['mint'] == pair.token), None)
        if historical and historical['pair'] != pair.pair:
            return _denied('EXACT_PAIR_REQUIRES_NEW_VERIFICATION', 'MISSION020_HISTORICAL')
        if self._provider is None:
            return _denied('MISSION020_NO_FORWARD' if historical else 'CUE_FRESH_REPORT_REQUIRED',
                           'MISSION020_HISTORICAL' if historical else 'CUE_NOT_CONNECTED')
        try:
            report = self._provider(pair)
        except Exception:
            return _denied('CUE_PROVIDER_ERROR')
        if not isinstance(report, CueReport):
            return _denied('CUE_REPORT_MISSING_OR_INVALID')
        if report.mint != pair.token or report.pair != pair.pair:
            return _denied('CUE_EXACT_MINT_PAIR_MISMATCH', 'CUE_PROVIDER')
        at = int(time.time()) if now is None else now
        if (not isinstance(report.observed_at, int) or report.observed_at > at + 10
                or at - report.observed_at > MAX_EVIDENCE_AGE_SECONDS):
            return _denied('CUE_REPORT_EXPIRED_OR_FUTURE', 'CUE_PROVIDER')
        if not report.evidence_ref or not isinstance(report.evidence_ref, str):
            return _denied('CUE_PROVENANCE_MISSING', 'CUE_PROVIDER')
        if not isinstance(report.checks, Mapping):
            return _denied('CUE_CHECKS_INVALID', 'CUE_PROVIDER')
        failed = [key for key in REQUIRED_CHECKS if report.checks.get(key) != 'PASS']
        if failed:
            return {**_denied('CUE_CHECKS_NOT_PASSED', 'CUE_PROVIDER'), 'failed_checks': failed}
        return {
            'allowed': True, 'status': 'PASS', 'reason': 'CUE_CURRENT_CHECKS_PASS',
            'source': 'CUE_PROVIDER', 'evidence_status': 'DERIVED',
            'evidence_ref': report.evidence_ref, 'observed_at': report.observed_at,
            'strategy_id': STRATEGY_ID,
        }

    def public_state(self) -> dict:
        return {
            'strategy_id': STRATEGY_ID,
            'mode': 'PAPER_ONLY',
            'risk_gate': 'BLOCKED_NO_PROVIDER' if self._provider is None else 'PROVIDER_CONNECTED',
            'onchain_execution': False,
            'max_evidence_age_seconds': MAX_EVIDENCE_AGE_SECONDS,
            'required_checks': list(REQUIRED_CHECKS),
            'mission020_capture': MISSION020_CAPTURE,
            'cases': list(MISSION020_CASES),
            'notice': 'Historyczny raport nie upoważnia do BUY; brak aktualnego weryfikatora oznacza BLOCK.',
        }
