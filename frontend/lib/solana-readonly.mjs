/**
 * OSA Trading Desk V1.1 — public Solana RPC reads ONLY.
 * No private key, signer, wallet secrets, transaction construction or broadcast APIs.
 */
export const DEFAULT_RPC = 'https://api.mainnet-beta.solana.com';
export const LEGACY_TOKEN_PROGRAM = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';
export const TOKEN_2022_PROGRAM = 'TokenzQdBNbLqP5VEhdkAS6EP5MZ2CzKmq7ECbTnW';
const PUBLIC_KEY_RE = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

export function validSolanaAddress(address) {
  return typeof address === 'string' && PUBLIC_KEY_RE.test(address);
}

export function supportedWallets(wallets) {
  return wallets.filter(wallet =>
    (wallet.name === 'Phantom' || wallet.name === 'Solflare') &&
    wallet.chains.includes('solana:mainnet') &&
    typeof wallet.features?.['standard:connect']?.connect === 'function'
  );
}

export function selectMainnetAccount(accounts) {
  return accounts.find(account => validSolanaAddress(account.address) &&
    account.chains.includes('solana:mainnet')) || null;
}

export function exactUnits(raw, decimals, precision = 6) {
  if (!/^\d+$/.test(raw) || !Number.isInteger(decimals) || decimals < 0 || decimals > 18) {
    throw new Error('Nieprawidłowy format salda tokena');
  }
  const padded = raw.padStart(decimals + 1, '0');
  const whole = decimals === 0 ? padded : padded.slice(0, -decimals);
  const fractional = decimals === 0 ? '' : padded.slice(-decimals).slice(0, precision).replace(/0+$/, '');
  return fractional ? whole + '.' + fractional : whole;
}

function endpointGuard(endpoint) {
  let parsed;
  try { parsed = new URL(endpoint); } catch { throw new Error('Nieprawidłowy adres RPC'); }
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password) {
    throw new Error('RPC musi korzystać z HTTPS bez danych logowania w adresie');
  }
  return endpoint;
}

async function callRpc(endpoint, method, params, fetcher, signal) {
  let response;
  try {
    response = await fetcher(endpoint, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({jsonrpc:'2.0', id:1, method, params}),
      cache: 'no-store',
      signal,
    });
  } catch {
    throw new Error('RPC Solana jest niedostępne — odczyt przerwany');
  }
  if (!response.ok) throw new Error('RPC Solana odrzuciło odczyt (HTTP ' + response.status + ')');
  let payload;
  try { payload = await response.json(); } catch { throw new Error('RPC zwróciło nieprawidłowy JSON'); }
  if (payload?.error || !payload?.result) throw new Error('RPC nie zwróciło poprawnego wyniku');
  return payload.result;
}

/**
 * Independent from trading API. Atomic result: any failed RPC query hides all balances.
 * Reads SOL and both classic SPL Token / Token-2022 accounts by public address.
 */
export async function readPortfolio(address, {
  endpoint = DEFAULT_RPC,
  fetcher = fetch,
  signal,
} = {}) {
  if (!validSolanaAddress(address)) throw new Error('Nieprawidłowy adres publiczny Solana');
  endpointGuard(endpoint);
  const [balance, legacy, token2022] = await Promise.all([
    callRpc(endpoint, 'getBalance', [address, {commitment:'confirmed'}], fetcher, signal),
    callRpc(endpoint, 'getTokenAccountsByOwner', [address,
      {programId:LEGACY_TOKEN_PROGRAM}, {encoding:'jsonParsed',commitment:'confirmed'}], fetcher, signal),
    callRpc(endpoint, 'getTokenAccountsByOwner', [address,
      {programId:TOKEN_2022_PROGRAM}, {encoding:'jsonParsed',commitment:'confirmed'}], fetcher, signal),
  ]);
  const lamports = balance?.value;
  if (!Number.isSafeInteger(lamports) || lamports < 0) throw new Error('Nieprawidłowe saldo SOL z RPC');
  if (!Array.isArray(legacy?.value) || !Array.isArray(token2022?.value)) {
    throw new Error('Niekompletna odpowiedź RPC dotycząca tokenów');
  }
  const combined = new Map();
  for (const record of [...legacy.value, ...token2022.value]) {
    const info = record?.account?.data?.parsed?.info;
    const mint = info?.mint, owner = info?.owner, amount = info?.tokenAmount?.amount;
    const decimals = info?.tokenAmount?.decimals;
    if (!validSolanaAddress(mint) || owner !== address ||
        typeof amount !== 'string' || !/^\d+$/.test(amount) ||
        !Number.isInteger(decimals) || decimals < 0 || decimals > 18) {
      throw new Error('Odrzucono niepoprawną odpowiedź tokenów z RPC');
    }
    const previous = combined.get(mint);
    if (previous && previous.decimals !== decimals) {
      throw new Error('Niespójna precyzja tokenów z RPC');
    }
    combined.set(mint,{decimals,amount:(previous?.amount || 0n) + BigInt(amount)});
  }
  const tokens = [...combined.entries()].filter(([,v]) => v.amount > 0n)
    .map(([mint,v]) => ({mint,amount:exactUnits(v.amount.toString(),v.decimals),decimals:v.decimals}))
    .sort((a,b) => a.mint.localeCompare(b.mint));
  return {
    address,
    network:'Solana Mainnet',
    sol:exactUnits(String(lamports),9,9),
    tokens,
    fetchedAt:new Date().toISOString(),
  };
}
