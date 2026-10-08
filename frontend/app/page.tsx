'use client';
import { useCallback, useEffect, useState } from 'react';
import { Activity, ArrowDownUp, Bot, CircleAlert, Cpu, DatabaseZap, Gauge, LockKeyhole, Pause, Play, Radar, RefreshCcw, ShieldCheck, Zap } from 'lucide-react';

type Position = { token:string; pair:string; symbol:string; units:number; spent:number; entry_price:number; opened_at:number };
type Fill = {id:number; time:number; side:string; symbol:string; token:string; units:number; reference:number; execution:number; fee:number; usd:number; realized_pnl:number|null; evidence_hash:string};
type Desk = {mode:string; cash:number; halted:boolean; positions:Position[]; fills:Fill[]; initial_cash:number; equity:number|null; equity_note:string; events:{id:number;time:number;kind:string;hash:string}[]};
type Pair = {token:string;pair:string;symbol:string;price:number;liquidity:number;volume:number;age_hours:number;buys:number;sells:number;fdv:number;url:string;observed_at:number};
type Candidate = {pair:Pair;assessment:{accepted:boolean;score:number;reason:string;checks:Record<string,boolean>}};
const api = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000';
const usd = (n:number) => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n);
const short = (n:number) => n >= 1e6 ? (n/1e6).toFixed(2)+'M' : n>=1000?(n/1000).toFixed(1)+'K':n.toFixed(0);
const stamp = (sec:number) => new Date(sec*1000).toLocaleTimeString('pl-PL',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
const agents = [
  {id:'01',name:'SCANNER',sub:'Odkrywanie tokenów',icon:Radar},
  {id:'02',name:'SHIELD',sub:'Ocena ryzyka',icon:ShieldCheck},
  {id:'03',name:'AI JUDGE',sub:'Analiza decyzji',icon:Bot},
  {id:'04',name:'STRATEGY',sub:'Filtry wejścia',icon:Cpu},
  {id:'05',name:'EXECUTOR',sub:'Symulacja zleceń',icon:ArrowDownUp},
  {id:'06',name:'LEDGER',sub:'Dowód i historia',icon:DatabaseZap},
];
export default function Home() {
  const [desk,setDesk]=useState<Desk|null>(null);
  const [candidates,setCandidates]=useState<Candidate[]>([]);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState('');
  const [lastScan,setLastScan]=useState<number|null>(null);
  const [proof,setProof]=useState<boolean|null>(null);
  const load=useCallback(async()=>{
    try {
      const r=await fetch(api+'/api/state',{cache:'no-store'});
      if(!r.ok) throw new Error('Backend nie odpowiada');
      setDesk(await r.json());setError('');
      const p=await fetch(api+'/api/proof',{cache:'no-store'});
      if(p.ok) setProof((await p.json()).verified);
    }catch{setError('Brak połączenia z API. Uruchom backend lokalnie.');}
  },[]);
  useEffect(()=>{void load();const i=setInterval(()=>void load(),6000);return()=>clearInterval(i)},[load]);
  async function scan(){setBusy('scan');try{
    const r=await fetch(api+'/api/scan',{cache:'no-store'});
    if(!r.ok) throw new Error('Źródło cen niedostępne (fail-closed)');
    const data=await r.json();setCandidates(data.candidates);setLastScan(Date.now());setError('');
  }catch(e){setError(String(e));setCandidates([]);}finally{setBusy('')}}
  async function action(route:string){setBusy(route);try{
    const r=await fetch(api+route,{method:'POST'});
    if(!r.ok) throw new Error('Operacja nie powiodła się: HTTP '+r.status);
    if(route.includes('tick')){const result=await r.json();if(result.outcomes?.length===0)setError('Tick zakończony: brak zleceń spełniających kryteria.');else setError('');}
    await load();
  }catch(e){setError(String(e))}finally{setBusy('')}}
  const realized=desk?.fills.reduce((a,f)=>a+(f.realized_pnl??0),0)??0;
  return <main className="shell">
    <header className="topbar"><div className="brand"><span className="mark">O<span>SA</span></span><span className="brand-sep"/><div><strong>TRADING DESK</strong><small>SOLANA // AUTONOMOUS RESEARCH TERMINAL</small></div></div>
      <div className="top-right"><span className="live-dot"/><span>{desk?'LOKALNY SILNIK ONLINE':'SILNIK OFFLINE'}</span><span className="pill">PAPER ONLY</span></div></header>
    <section className="ticker"><span><Activity size={13}/> SYSTEM MODE: <b>SIMULATION</b></span><span>ŹRÓDŁO: <b>DEXSCREENER</b></span><span>EGZEKUCJA ON-CHAIN: <b>WYŁĄCZONA</b></span><span>RYZYKO: <b>FAIL CLOSED</b></span></section>
    <section className="hero"><div className="hero-copy"><div className="eyebrow"><span className="spark">✦</span> AGENT INTELLIGENCE / V1.0</div><h1>THE MARKET<br/><em>NEVER SLEEPS<span>.</span></em></h1><p>Sześć modułów. Jedna logika ryzyka. Zero fikcyjnych wyników.<br/>System analizuje rzeczywisty rynek, lecz wykonuje tylko symulacje.</p>
      <div className="hero-actions"><button className="primary" disabled={!!busy||!desk} onClick={()=>void scan()}><Radar size={17}/> {busy==='scan'?'SKANOWANIE...':'SKANUJ SOLANA'}</button><button className="outline" disabled={!!busy||!desk||desk.halted} onClick={()=>void action('/api/paper/tick')}><Play size={16}/> WYKONAJ PAPER TICK</button></div></div>
      <div className="orbital" aria-hidden="true"><div className="orbit o1"/><div className="orbit o2"/><div className="orbit o3"/><div className="orb-core"><span>O</span><small>SA</small></div><span className="orbit-label l1">SCAN //</span><span className="orbit-label l2">VERIFY //</span><span className="orbit-label l3">SIMULATE //</span></div></section>
    {error&&<div role="alert" className="alert"><CircleAlert size={17}/>{error}</div>}
    <section className="stat-grid"><div className="metric"><label>GOTÓWKA (SIM)</label><strong>{desk?usd(desk.cash):'—'}</strong><small>Start: $1,000.00</small></div><div className="metric"><label>PNL ZREALIZOWANY</label><strong className={realized>=0?'green':'red'}>{desk?usd(realized):'—'}</strong><small>Po opłatach i slippage</small></div><div className="metric"><label>POZYCJE OTWARTE</label><strong>{desk?.positions.length??'—'} <i>/ 3</i></strong><small>Wycena niezrealizowana: UNKNOWN</small></div><div className="metric"><label>INTEGRALNOŚĆ PROOF</label><strong className={proof===false?'red':'green'}>{proof===null?'—':proof?'PASS':'FAIL'}</strong><small>SHA-256 / chain of evidence</small></div></section>
    <section className="section-heading"><div><span className="overline">01 / OPERATIONS CENTER</span><h2>Agent Network <span className="dim">/ 06</span></h2></div><span className="mini-status"><span className="live-dot"/> MODUŁY GOTOWE</span></section>
    <div className="agents">{agents.map((a,i)=><article className="agent" key={a.id}><div className="agent-top"><span>NODE {a.id}</span><span className={'agent-led '+(desk?'is-on':'')}/></div><div className="agent-art"><div className="agent-ring r1"/><div className="agent-ring r2"/><a.icon size={37} strokeWidth={1.3}/></div><div className="agent-label"><h3>{a.name}</h3><p>{a.sub}</p></div><div className="agent-foot"><span>{desk?'READY':'OFFLINE'}</span><span>{String(98+i).padStart(3,'0')} //</span></div></article>)}</div>
    <div className="content-grid"><section className="panel"><div className="panel-title"><div><span className="overline">02 / MARKET FEED</span><h2>Radar tokenów</h2></div><button className="icon-button" aria-label="Skanuj ponownie" disabled={!!busy} onClick={()=>void scan()}><RefreshCcw size={17}/></button></div><div className="tablewrap"><table><thead><tr><th>ASSET</th><th>CENA</th><th>PŁYNNOŚĆ</th><th>SCORE</th><th>WYNIK</th></tr></thead><tbody>{candidates.map(c=><tr key={c.pair.token}><td><a href={c.pair.url} target="_blank" rel="noopener noreferrer">{c.pair.symbol}</a><small>{c.pair.token.slice(0,6)}…</small></td><td>${c.pair.price.toPrecision(4)}</td><td>${short(c.pair.liquidity)}</td><td>{c.assessment.score}/100</td><td><span className={'status-chip '+(c.assessment.accepted?'pass':'reject')}>{c.assessment.accepted?'PRE-FILTER PASS':'REJECT'}</span></td></tr>)}</tbody></table>{!candidates.length&&<div className="empty">Brak wyników. Kliknij SKANUJ SOLANA, aby pobrać prawdziwe dane.</div>}</div><div className="panel-bottom"><span>Wyłącznie tokeny z aktywnymi boostami. To nie jest audyt kontraktu.</span><span>{lastScan?'SCAN '+new Date(lastScan).toLocaleTimeString('pl-PL'):'NO SCAN'}</span></div></section>
    <section className="panel"><div className="panel-title"><div><span className="overline">03 / RISK & CONTROL</span><h2>Risk Control</h2></div><Gauge size={20} className="accent"/></div><div className="risk-grid"><div><label>MAKS. POZYCJA</label><strong>2%</strong></div><div><label>POZYCJE JEDNOCZEŚNIE</label><strong>03</strong></div><div><label>STOP LOSS</label><strong>−10%</strong></div><div><label>TAKE PROFIT</label><strong>+20%</strong></div></div><div className="risk-note"><LockKeyhole size={17}/><span>AI nie może ominąć filtrów ryzyka. Brak konfiguracji AI = brak automatycznych zakupów.</span></div><button className={'halt '+(desk?.halted?'resume':'')} disabled={!!busy||!desk} onClick={()=>void action(desk?.halted?'/api/paper/resume':'/api/paper/halt')}>{desk?.halted?<Play size={17}/>:<Pause size={17}/>} {desk?.halted?'WZNÓW SYMULACJĘ':'WSTRZYMAJ WSZYSTKIE ZLECENIA'}</button></section></div>
    <section className="panel ledger"><div className="panel-title"><div><span className="overline">04 / VERIFIED TRANSACTION LOG</span><h2>Paper Ledger</h2></div><div className="ledger-count"><DatabaseZap size={16}/>{desk?.fills.length??0} FILLS</div></div><div className="tablewrap"><table><thead><tr><th>CZAS</th><th>TYP</th><th>TOKEN</th><th>KWOTA</th><th>PROWIZJA</th><th>REALIZED PNL</th><th>PROOF HASH</th></tr></thead><tbody>{desk?.fills.map(f=><tr key={f.id}><td>{stamp(f.time)}</td><td><span className={'status-chip '+(f.side==='BUY'?'pass':'sell')}>{f.side}</span></td><td>{f.symbol}</td><td>{usd(f.usd)}</td><td>{usd(f.fee)}</td><td className={(f.realized_pnl??0)>=0?'green':'red'}>{f.realized_pnl===null?'—':usd(f.realized_pnl)}</td><td className="hash" title={f.evidence_hash}>{f.evidence_hash.slice(0,13)}…</td></tr>)}</tbody></table>{!desk?.fills.length&&<div className="empty">Brak transakcji. Żaden wynik nie został wygenerowany ani sfabrykowany.</div>}</div></section>
    <footer><span>© 2026 OSATECHGPT // PAPER ENGINE</span><span>TO NARZĘDZIE EKSPERYMENTALNE. BRAK GWARANCJI ZYSKU. NIE SĄ WYSYŁANE TRANSAKCJE ON-CHAIN.</span></footer>
  </main>
}
