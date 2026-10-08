"""Actual DexScreener market requests. Network errors fail closed."""
import time
import httpx
from .engine import Pair, parse_pair

BASE = 'https://api.dexscreener.com'


class MarketUnavailable(RuntimeError):
    pass


class Market:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def candidates(self, limit: int = 12) -> list[Pair]:
        try:
            async with httpx.AsyncClient(timeout=8, transport=self.transport) as client:
                r = await client.get(BASE + '/token-boosts/top/v1')
                r.raise_for_status()
                boosts = r.json()
                if not isinstance(boosts, list):
                    raise MarketUnavailable('Niepoprawna odpowiedź boostów')
                addresses = list(dict.fromkeys(str(x.get('tokenAddress')) for x in boosts
                             if isinstance(x, dict) and x.get('chainId') == 'solana' and x.get('tokenAddress')))[:limit]
                if not addresses:
                    return []
                r = await client.get(BASE + '/tokens/v1/solana/' + ','.join(addresses))
                r.raise_for_status()
                raw_pairs = r.json()
                if not isinstance(raw_pairs, list):
                    raise MarketUnavailable('Niepoprawna odpowiedź par')
                matches: dict[str, Pair] = {}
                for raw in raw_pairs:
                    if not isinstance(raw, dict) or raw.get('chainId') != 'solana':
                        continue
                    pair = parse_pair(raw)
                    if pair.token not in addresses or not pair.pair:
                        continue
                    if pair.token not in matches or pair.liquidity > matches[pair.token].liquidity:
                        matches[pair.token] = pair
                return sorted(matches.values(), key=lambda p: p.liquidity, reverse=True)
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            raise MarketUnavailable(f'Źródło rynku niedostępne: {type(exc).__name__}') from exc

    async def quote(self, token: str, pair_address: str) -> Pair:
        if not token or not pair_address or not all(ch.isalnum() for ch in token + pair_address):
            raise MarketUnavailable('Niepoprawny adres tokena lub pary')
        try:
            async with httpx.AsyncClient(timeout=8, transport=self.transport) as client:
                r = await client.get(BASE + '/token-pairs/v1/solana/' + token)
                r.raise_for_status()
                candidates = r.json()
                for raw in candidates if isinstance(candidates, list) else []:
                    if raw.get('chainId') == 'solana' and raw.get('pairAddress') == pair_address and (raw.get('baseToken') or {}).get('address') == token:
                        return parse_pair(raw)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise MarketUnavailable('Nie można pobrać ceny zamknięcia') from exc
        raise MarketUnavailable('Para nie istnieje albo wycofano notowania')
