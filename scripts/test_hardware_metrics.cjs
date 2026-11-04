const assert=require('node:assert/strict');const {leaders,historicalHigh,orderExcerpt}=require('../hardware-metrics.js');
assert.deepEqual([...leaders([1,2,3,4].map(n=>({code:String(n),group:'materials',cap:n*10})))],[['4',1],['3',2],['2',3]]);
const universe=require('../data/hardware-universe.json');
assert.equal(new Set(universe.stocks.map(s=>s.code)).size,universe.stocks.length);
for(const code of ['600584','002428','002409','600206','688432']){const s=universe.stocks.find(s=>s.code===code);assert.equal(s?.featured,true);assert.ok(s.moat?.source.startsWith('https://'));assert.ok(s.moat?.inference);assert.ok(universe.groups.includes(s.group));}
assert.deepEqual([...leaders([{code:'1',group:'a',cap:20},{code:'2',group:'a',cap:30},{code:'3',group:'a',cap:90,custom:true},{code:'4',group:'b',cap:10}])],[['2',1],['1',2],['4',1]]);
const bars=['2026-01-01,1,1,20','2026-01-02,1,1,30','2027-01-01,1,1,100'];
let p=historicalHigh({dktotal:2,klines:bars},15,'2026-01-02');assert.equal(p.high,30);assert.equal(p.drawdownPct,50);assert.equal(p.complete,true);
p=historicalHigh({dktotal:99,klines:bars},15,'2026-01-02');assert.equal(p.complete,false);
p=historicalHigh({dktotal:2,klines:bars},31,'2026-01-02');assert.equal(p.drawdownPct,null);assert.equal(p.aboveRecordedHigh,true);
assert.equal(orderExcerpt('Q1：公司订单是否充足？\nA1：具体客户的订单涉及商业秘密，无法逐一披露。'),'具体客户的订单涉及商业秘密，无法逐一披露');
assert.equal(orderExcerpt('Q1：公司订单是否充足？'),null);
console.log('Hardware metric/date/leader/order tests passed');
