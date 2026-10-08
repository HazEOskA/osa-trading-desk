'use client';

/**
 * READ-ONLY Solana Wallet Standard integration.
 * This file never imports or invokes signing/transaction features.
 */
import { useEffect, useRef, useState } from 'react';
import { getWallets } from '@wallet-standard/app';
import type { Wallet, WalletAccount } from '@wallet-standard/base';
import { Check, CircleAlert, Copy, ExternalLink, Link2, LockKeyhole, LogOut, RefreshCcw, ShieldCheck, Wallet as WalletIcon } from 'lucide-react';
import { readPortfolio, selectMainnetAccount, supportedWallets } from '../lib/solana-readonly.mjs';
import type { Portfolio } from '../lib/solana-readonly.mjs';

type ConnectFeature = {connect:()=>Promise<{accounts: readonly WalletAccount[]}>};
type DisconnectFeature = {disconnect:()=>Promise<void>};
type EventsFeature = {on:(event:'change',listener:(change:{accounts?:readonly WalletAccount[]})=>void)=>()=>void};
type Session = {wallet:Wallet;address:string};
const endpoint = process.env.NEXT_PUBLIC_SOLANA_RPC_URL || undefined;

const shortened = (value:string) => value.slice(0,6) + '…' + value.slice(-6);
function reason(error:unknown):string {
  if(error instanceof Error && error.message) return error.message;
  return 'Operacja nie powiodła się. Spróbuj ponownie.';
}

export default function WalletPanel() {
  const [available,setAvailable] = useState<Wallet[]>([]);
  const [choose,setChoose] = useState(false);
  const [session,setSession] = useState<Session|null>(null);
  const [portfolio,setPortfolio] = useState<Portfolio|null>(null);
  const [loading,setLoading] = useState(false);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [copied,setCopied] = useState(false);
  const seq = useRef(0);

  useEffect(()=>{
    const registry = getWallets();
    const refresh = () => setAvailable([...supportedWallets(registry.get())]);
    refresh();
    const offRegister = registry.on('register',refresh);
    const offUnregister = registry.on('unregister',refresh);
    return ()=>{seq.current++;offRegister();offUnregister();};
  },[]);

  useEffect(()=>{
    if(!session) return;
    const events = session.wallet.features['standard:events'] as EventsFeature|undefined;
    if(!events) return;
    return events.on('change',({accounts})=>{
      if(!accounts) return;
      const next = selectMainnetAccount(accounts);
      if(!next || next.address!==session.address) {
        seq.current++;
        setSession(null);
        setPortfolio(null);
        setError('Konto portfela się zmieniło. Połącz ponownie, aby odczytać nowe saldo.');
      }
    });
  },[session]);

  async function refreshBalances(address:string) {
    const request = ++seq.current;
    setLoading(true);
    setPortfolio(null); // Never display a stale balance as current.
    setError('');
    try {
      const data = await readPortfolio(address,{endpoint});
      if(request===seq.current) setPortfolio(data);
    } catch(e) {
      if(request===seq.current) setError(reason(e));
    } finally {
      if(request===seq.current) setLoading(false);
    }
  }

  async function connect(wallet:Wallet) {
    if(busy) return;
    const request = ++seq.current;
    setBusy(true);
    setError('');
    setPortfolio(null);
    try {
      const feature = wallet.features['standard:connect'] as ConnectFeature|undefined;
      if(!feature) throw new Error('Portfel nie udostępnia Wallet Standard Connect.');
      // Only asks the wallet to reveal an approved PUBLIC address.
      const {accounts} = await feature.connect();
      const account = selectMainnetAccount(accounts);
      if(!account) throw new Error('Nie znaleziono konta Solana Mainnet.');
      if(request!==seq.current) return;
      setSession({wallet,address:account.address});
      setChoose(false);
      await refreshBalances(account.address);
    } catch(e) {
      if(request===seq.current) setError('Połączenie nieudane lub anulowane: ' + reason(e));
    } finally {
      if(request===seq.current || request+1===seq.current) setBusy(false);
    }
  }

  async function disconnect() {
    seq.current++;
    const old = session;
    setSession(null);
    setPortfolio(null);
    setError('');
    setChoose(false);
    setLoading(false);
    if(old) {
      const feature = old.wallet.features['standard:disconnect'] as DisconnectFeature|undefined;
      // If wallet does not expose disconnect, the app still clears its ephemeral state.
      try { await feature?.disconnect(); }
      catch { setError('Sesja odłączona w aplikacji; sprawdź uprawnienia w ustawieniach portfela.'); }
    }
  }

  async function copyAddress() {
    if(!session) return;
    try {
      await navigator.clipboard.writeText(session.address);
      setCopied(true);
    } catch { setError('Schowek jest niedostępny w tej przeglądarce.'); }
  }

  return <section className="wallet-zone" aria-labelledby="wallet-title">
    <div className="wallet-head">
      <div><span className="overline">05 / SOLANA MAINNET · ODCZYT PUBLICZNY</span>
        <h2 id="wallet-title"><WalletIcon size={22}/> Portfel <span className="dim">/ READ ONLY</span></h2></div>
      <span className="wallet-guard"><ShieldCheck size={15}/> BEZ TRANSAKCJI</span>
    </div>
    <div className="wallet-grid">
      <div className="wallet-identity">
        <div className="wallet-status"><span className={session?'wallet-led on':'wallet-led'}/>{session?'POŁĄCZONY — '+session.wallet.name:'PORTFEL NIEPOŁĄCZONY'}</div>
        {session ?
          <>
            <div className="wallet-address"><code title={session.address}>{shortened(session.address)}</code>
              <button type="button" aria-label="Kopiuj adres portfela" onClick={()=>void copyAddress()}><Copy size={15}/>{copied?<Check size={13}/>:null}</button></div>
            <div className="wallet-commands">
              <button type="button" disabled={loading||busy} onClick={()=>void refreshBalances(session.address)}><RefreshCcw size={15}/> {loading?'ODCZYT...':'ODŚWIEŻ SALDO'}</button>
              <button type="button" onClick={()=>void disconnect()}><LogOut size={15}/> ODŁĄCZ</button>
            </div>
          </> :
          <><p>Połącz Phantom lub Solflare, aby sprawdzić publiczny adres i salda. Bez podpisów, seed phrase i kluczy prywatnych.</p>
            <button type="button" className="wallet-connect" onClick={()=>setChoose(v=>!v)} aria-expanded={choose}>
              <Link2 size={16}/> {choose?'ZAMKNIJ WYBÓR':'POŁĄCZ PORTFEL'}</button>
            {choose&&<div className="wallet-options">
              {available.length===0?<p role="status">Nie wykryto Phantom ani Solflare w tej przeglądarce. Na Androidzie otwórz ten adres we wbudowanej przeglądarce aplikacji portfela.</p>:
                available.map((wallet)=><button type="button" key={wallet.name} disabled={busy} onClick={()=>void connect(wallet)}>
                  <WalletIcon size={18}/>{wallet.name}<ExternalLink size={13}/></button>)}
            </div>}
          </>
        }
        <div className="wallet-note"><LockKeyhole size={14}/> Dane publiczne są pobierane w przeglądarce przez RPC. Adres jest widoczny dla operatora RPC; nic nie trafia do API tradingowego.</div>
      </div>
      <div className="wallet-balances" aria-live="polite">
        <div className="wallet-balance-top"><span>SALDO SOL</span><span>MAINNET / RPC</span></div>
        <strong>{loading?'ODCZYT...':portfolio?portfolio.sol+' SOL':'—'}</strong>
        <small>{portfolio?'Odczyt '+new Date(portfolio.fetchedAt).toLocaleTimeString('pl-PL'):'Brak potwierdzonego salda'}</small>
        <div className="wallet-token-head">TOKENY SPL / TOKEN-2022 <span>{portfolio?portfolio.tokens.length:'—'}</span></div>
        {portfolio&&portfolio.tokens.length===0&&<p className="wallet-empty">Brak tokenów o dodatnim saldzie.</p>}
        {portfolio&&portfolio.tokens.length>0&&<div className="wallet-token-list">
          {portfolio.tokens.map(item=><div key={item.mint}><code title={item.mint}>{shortened(item.mint)}</code><span>{item.amount}</span></div>)}
        </div>}
        {!portfolio&&<p className="wallet-empty">Nie pokazujemy przykładowych sald ani fikcyjnych tokenów.</p>}
      </div>
    </div>
    {error&&<p className="wallet-error" role="alert"><CircleAlert size={16}/>{error}</p>}
  </section>;
}
