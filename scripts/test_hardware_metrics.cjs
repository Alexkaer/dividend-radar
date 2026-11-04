const assert=require('node:assert/strict');const {leadership,leaders,historicalHigh,orderExcerpt}=require('../hardware-metrics.js');
const stamp=Date.parse('2026-11-04T15:00:00+08:00')/1000;
const stock=(code,cap,five,twenty,change=1,extra={})=>({code,group:'材料',cap,amount:1e9,price:20,change,quoteTime:stamp,history:{momentum:{asOf:'2026-11-04',fiveDayChange:five,twentyDayChange:twenty}},...extra});
let pool=[stock('big',1000,-5,-10),stock('small',100,10,20),stock('medium',500,5,10)];
let ranked=leaders(pool);assert.equal(ranked.has('big'),false);assert.equal(ranked.get('small'),1);assert.equal(ranked.get('medium'),2);
assert.equal(leaders([stock('spike',1000,20,-5,20),stock('up',100,2,3)]).has('spike'),false);
assert.equal(leaders([stock('a',10,-2,-3),stock('b',20,-1,-1)]).size,0);
assert.equal(leaders([stock('a',10,2,3),stock('b',20,5,8)].map(s=>({...s,history:undefined}))).size,0);
assert.equal(leaders([stock('a',10,2,3),stock('custom',100,20,30,10,{custom:true})]).size,0);
let stale=stock('stale',1000,40,50);stale.history.momentum.asOf='2026-11-03';assert.equal(leaders([...pool,stale]).has('stale'),false);
assert.equal(leadership([stock('a',10,2,3),stock('b',10,2,3)]).get('a').score,50);
assert.equal(leaders([1,2,3,4].map(n=>stock(String(n),10,2,3))).size,3);
assert.deepEqual([...leaders(pool)],[...leaders(pool.map(s=>({...s,featured:true})))]);
const universe=require('../data/hardware-universe.json');assert.equal(new Set(universe.stocks.map(s=>s.code)).size,universe.stocks.length);assert.ok(universe.stocks.every(s=>!s.featured));
for(const code of ['600584','002428','002409','600206','688432'])assert.ok(universe.stocks.find(s=>s.code===code)?.moat?.source);
const bars=['2026-01-01,1,1,20','2026-01-02,1,1,30','2027-01-01,1,1,100'];
let p=historicalHigh({dktotal:2,klines:bars},15,'2026-01-02');assert.equal(p.high,30);assert.equal(p.drawdownPct,50);assert.equal(p.complete,true);
p=historicalHigh({dktotal:99,klines:bars},15,'2026-01-02');assert.equal(p.complete,false);
p=historicalHigh({dktotal:2,klines:bars},31,'2026-01-02');assert.equal(p.drawdownPct,null);assert.equal(p.aboveRecordedHigh,true);
assert.equal(orderExcerpt('Q1：公司订单是否充足？\nA1：具体客户的订单涉及商业秘密，无法逐一披露。'),'具体客户的订单涉及商业秘密，无法逐一披露');
assert.equal(orderExcerpt('Q1：公司订单是否充足？'),null);


const lines=Array.from({length:21},(_,i)=>`2026-01-${String(i+1).padStart(2,'0')},10,${10+i},${11+i}`);const h=historicalHigh({dktotal:21,klines:lines},30,'2026-01-21');assert.equal(h.momentum.twentyDayChange,200);assert.ok(Math.abs(h.momentum.fiveDayChange-20)<1e-9);assert.equal(historicalHigh({dktotal:21,klines:lines},30,'2026-01-22').momentum.fiveDayChange,null);



const {completedSession,dailySignal}=require('../hardware-metrics.js');
const sessions=[{date:'2026-10-30'},{date:'2026-11-02'},{date:'2026-11-03'},{date:'2026-11-04'}];
assert.equal(completedSession(sessions,Date.parse('2026-11-04T15:04:59+08:00')),'2026-11-03');
assert.equal(completedSession(sessions,Date.parse('2026-11-04T15:05:00+08:00')),'2026-11-04');
assert.equal(completedSession(sessions,Date.parse('2026-11-02T10:00:00+08:00')),'2026-10-30');
assert.equal(completedSession(sessions,Date.parse('2026-11-07T10:00:00+08:00')),'2026-11-04');
const raw=prices=>({klines:prices.map((close,i)=>`${new Date(Date.UTC(2026,0,i+1)).toISOString().slice(0,10)},1,${close},${close+1}`)});
const falling=Array.from({length:60},(_,i)=>200-i*i*.02);
let signal=dailySignal(raw([...falling,128,127,127,129]),'2026-03-05');
assert.equal(signal.matches,true);assert.equal(signal.macd.histogram<0,true);assert.equal(signal.ma5,(130.38+128+127+127+129)/5);
// Three latest bars rising is only two improvements; require all four bars.
assert.equal(dailySignal(raw([...falling,130,125,128,132]),'2026-03-05').macdRising,false);
const flat=dailySignal(raw(Array(64).fill(100)),'2026-03-05');assert.equal(flat.aboveMA5,false);assert.equal(flat.macdRising,false);assert.equal(flat.macd.histogram,0);
const future=raw([...falling,128,127,127,129,9999]);assert.deepEqual(dailySignal(future,'2026-03-05'),signal);
assert.equal(dailySignal(raw(Array(59).fill(100)),'2026-02-28').matches,null);
assert.equal(dailySignal(raw(Array(64).fill(100)),'2026-03-06').status,'stale');
const missing=raw(Array(64).fill(100));missing.klines[60]='2026-03-02,1,-,102';assert.equal(dailySignal(missing,'2026-03-05').matches,null);
assert.equal(dailySignal(future,null).matches,null);
console.log('Hardware momentum, daily MA5/MACD, completed-session and coverage tests passed');
