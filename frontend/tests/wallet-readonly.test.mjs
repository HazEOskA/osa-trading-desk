import test from 'node:test';
import assert from 'node:assert/strict';
import {DEFAULT_RPC,LEGACY_TOKEN_PROGRAM,TOKEN_2022_PROGRAM,validSolanaAddress,
  supportedWallets,selectMainnetAccount,exactUnits,readPortfolio} from '../lib/solana-readonly.mjs';

const owner='11111111111111111111111111111111';
const mint='So11111111111111111111111111111111111111112';
const other='TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';
function record(token=mint,amount='2500000',decimals=6) {
  return {account:{data:{parsed:{info:{mint:token,owner,tokenAmount:{amount,decimals}}}}}};
}
function rpcMock({balance=2000000000,legacy=[record()],token2022=[record(mint,'500000',6),record(other,'900',2)],errorMethod}={}) {
  const calls=[];
  const fetcher=async(url,options)=>{
    assert.equal(url,DEFAULT_RPC);
    assert.equal(options.method,'POST');
    assert.equal(options.cache,'no-store');
    const req=JSON.parse(options.body);
    calls.push(req);
    if(req.method===errorMethod) return {ok:false,status:429};
    if(req.method==='getBalance') return {ok:true,json:async()=>({jsonrpc:'2.0',result:{value:balance}})};
    const program=req.params[1].programId;
    assert.equal(req.params[2].encoding,'jsonParsed');
    return {ok:true,json:async()=>({jsonrpc:'2.0',result:{value:program===LEGACY_TOKEN_PROGRAM?legacy:token2022}})};
  };
  return {calls,fetcher};
}
test('adres i wallet mainnet: wyłącznie Phantom/Solflare z obsługą connect',()=>{
  assert.ok(validSolanaAddress(owner));
  assert.equal(validSolanaAddress('not-a-wallet'),false);
  const wallet=(name,chains,connect=true)=>({name,chains,features:connect?{'standard:connect':{connect(){}}}:{}});
  const list=supportedWallets([
    wallet('Phantom',['solana:mainnet']),wallet('Solflare',['solana:mainnet']),
    wallet('Phantom fake',['solana:mainnet']),wallet('Phantom',['solana:devnet']),wallet('Solflare',['solana:mainnet'],false),
  ]);
  assert.deepEqual(list.map(w=>w.name),['Phantom','Solflare']);
  assert.equal(selectMainnetAccount([{address:owner,chains:['solana:devnet']}]),null);
  assert.equal(selectMainnetAccount([{address:owner,chains:['solana:mainnet']}]).address,owner);
});
test('format dokładny bez utraty precyzji BigInt',()=>{
  assert.equal(exactUnits('123456789012345678901',9,9),'123456789012.345678901');
  assert.equal(exactUnits('0',9),'0');
  assert.equal(exactUnits('900',2),'9');
  assert.throws(()=>exactUnits('1e9',6));
});
test('SOL + SPL + Token-2022: 3 metody READ RPC, scalanie tych samych mintów',async()=>{
  const rpc=rpcMock();
  const result=await readPortfolio(owner,{fetcher:rpc.fetcher});
  assert.equal(result.sol,'2');
  assert.equal(result.network,'Solana Mainnet');
  assert.deepEqual(result.tokens.map(t=>[t.mint,t.amount]),[[mint,'3'],[other,'9']].sort((a,b)=>a[0].localeCompare(b[0])));
  assert.deepEqual(rpc.calls.map(c=>c.method),['getBalance','getTokenAccountsByOwner','getTokenAccountsByOwner']);
  assert.deepEqual(rpc.calls.filter(c=>c.method==='getTokenAccountsByOwner').map(c=>c.params[1].programId),[LEGACY_TOKEN_PROGRAM,TOKEN_2022_PROGRAM]);
  assert.ok(rpc.calls.every(c=>JSON.stringify(c).includes(owner)));
});
test('błąd jednej części RPC powoduje brak kompletnego wyniku',async()=>{
  await assert.rejects(readPortfolio(owner,{fetcher:rpcMock({errorMethod:'getBalance'}).fetcher}),/odrzuciło odczyt/);
  await assert.rejects(readPortfolio(owner,{fetcher:rpcMock({legacy:null,token2022:null}).fetcher}),/Niekompletna/);
});
test('nieprawidłowe dane tokena są odrzucane',async()=>{
  const rpc=rpcMock({legacy:[{account:{data:{parsed:{info:{mint,owner:'OTHER',tokenAmount:{amount:'1',decimals:6}}}}}}]});
  await assert.rejects(readPortfolio(owner,{fetcher:rpc.fetcher}),/Odrzucono/);
});
test('błędny RPC / HTTP oraz niepoprawny adres są blokowane przed wysłaniem',async()=>{
  let count=0;
  const fetcher=async()=>{count++;throw new Error('should never fetch')};
  await assert.rejects(readPortfolio('evil',{fetcher}),/adres publiczny/);
  await assert.rejects(readPortfolio(owner,{endpoint:'http://example.com',fetcher}),/HTTPS/);
  await assert.rejects(readPortfolio(owner,{endpoint:'https://user:pass@example.com',fetcher}),/HTTPS/);
  assert.equal(count,0);
});
test('brak API do podpisywania w module RPC',async()=>{
  const {readFile} = await import('node:fs/promises');
  const source=await readFile(new URL('../lib/solana-readonly.mjs',import.meta.url),'utf8');
  assert.doesNotMatch(source,/signTransaction|signAndSendTransaction|sendRawTransaction|privateKey|seedPhrase|secretKey/);
});
