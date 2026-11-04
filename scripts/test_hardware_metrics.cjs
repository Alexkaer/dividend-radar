const assert=require('node:assert/strict');const {leaders,historicalHigh,orderExcerpt}=require('../hardware-metrics.js');
assert.deepEqual([...leaders([{code:'1',group:'a',cap:20},{code:'2',group:'a',cap:30},{code:'3',group:'a',cap:90,custom:true},{code:'4',group:'b',cap:10}])],[['2',1],['1',2],['4',1]]);
const bars=['2026-01-01,1,1,20','2026-01-02,1,1,30','2027-01-01,1,1,100'];
let p=historicalHigh({dktotal:2,klines:bars},15,'2026-01-02');assert.equal(p.high,30);assert.equal(p.drawdownPct,50);assert.equal(p.complete,true);
p=historicalHigh({dktotal:99,klines:bars},15,'2026-01-02');assert.equal(p.complete,false);
p=historicalHigh({dktotal:2,klines:bars},31,'2026-01-02');assert.equal(p.drawdownPct,null);assert.equal(p.aboveRecordedHigh,true);
assert.equal(orderExcerpt('Q1：公司订单是否充足？\nA1：具体客户的订单涉及商业秘密，无法逐一披露。'),'具体客户的订单涉及商业秘密，无法逐一披露');
assert.equal(orderExcerpt('Q1：公司订单是否充足？'),null);
console.log('Hardware metric/date/leader/order tests passed');
