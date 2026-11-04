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

console.log('Hardware momentum, leadership, coverage and order tests passed');
