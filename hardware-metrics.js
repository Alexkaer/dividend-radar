/* Comparable prices and reproducible scale-leader selection. */
(function(root){
  const finite=v=>typeof v==='number'&&Number.isFinite(v);
  function leadership(stocks,count=3){
    const result=new Map(),groups=new Map();
    for(const s of stocks){result.set(s.code,{rank:null,score:null,reason:s.custom?'自定义标的不参与预置池排名':'数据待核验'});if(!s.custom){if(!groups.has(s.group))groups.set(s.group,[]);groups.get(s.group).push(s)}}
    for(const members of groups.values()){
      const dated=members.filter(s=>s.quoteTime>0),date=dated.length?new Date(Math.max(...dated.map(s=>s.quoteTime))*1000).toLocaleDateString('sv-SE',{timeZone:'Asia/Shanghai'}):null;
      const valid=members.filter(s=>s.price>0&&finite(s.change)&&finite(s.amount)&&s.amount>0&&finite(s.cap)&&s.cap>0&&s.history?.momentum?.asOf===date&&new Date(s.quoteTime*1000).toLocaleDateString('sv-SE',{timeZone:'Asia/Shanghai'})===date&&finite(s.history.momentum.fiveDayChange)&&finite(s.history.momentum.twentyDayChange));
      if(valid.length<2)continue;
      const median=key=>{const v=valid.map(key).sort((a,b)=>a-b),m=Math.floor(v.length/2);return v.length%2?v[m]:(v[m-1]+v[m])/2};
      const m5=median(s=>s.history.momentum.fiveDayChange),m20=median(s=>s.history.momentum.twentyDayChange);
      const percentile=(stock,key)=>{const value=key(stock),less=valid.filter(s=>key(s)<value).length,equal=valid.filter(s=>key(s)===value).length;return (less+(equal-1)/2)/(valid.length-1)*100};
      for(const s of valid){const m=s.history.momentum,score=.35*percentile(s,x=>x.history.momentum.twentyDayChange)+.25*percentile(s,x=>x.history.momentum.fiveDayChange)+.15*percentile(s,x=>x.change)+.15*percentile(s,x=>x.amount)+.10*percentile(s,x=>x.cap),qualified=m.fiveDayChange>0&&m.twentyDayChange>0&&m.fiveDayChange>=m5&&m.twentyDayChange>=m20;
        result.set(s.code,{rank:null,score:Math.round(score*100)/100,qualified,asOf:date,fiveDayChange:m.fiveDayChange,twentyDayChange:m.twentyDayChange,medianFive:m5,medianTwenty:m20,sample:valid.length,universe:members.length,reason:qualified?'满足领涨门槛，综合排序':'未同时满足5日、20日上涨且不低于方向中位数'})}
      valid.filter(s=>result.get(s.code).qualified).sort((a,b)=>result.get(b.code).score-result.get(a.code).score||a.code.localeCompare(b.code)).slice(0,count).forEach((s,i)=>{result.get(s.code).rank=i+1;result.get(s.code).reason='方向内综合领涨候选'});
    }return result;
  }
  function leaders(stocks,count=3){return new Map([...leadership(stocks,count)].filter(([,v])=>v.rank).map(([code,v])=>[code,v.rank]))}
  function completedSession(bars,now=Date.now()){
    const date=new Date(now).toLocaleDateString('sv-SE',{timeZone:'Asia/Shanghai'}),time=new Date(now).toLocaleTimeString('en-GB',{timeZone:'Asia/Shanghai',hour12:false}),minutes=Number(time.slice(0,2))*60+Number(time.slice(3,5));
    return (bars||[]).filter(r=>r.date<=date&&(r.date!==date||minutes>=905)).map(r=>r.date).sort().at(-1)||null;
  }
  function dailySignal(data,asOf){
    const missing=reason=>({status:'unavailable',asOf:asOf||null,matches:null,reason});
    if(!asOf)return missing('已收盘交易日暂未核验');
    const rows=(data?.klines||[]).map(line=>{const r=line.split(',');return {date:r[0],close:r[2]?.trim()?Number(r[2]):NaN}}).filter(r=>r.date<=asOf).sort((a,b)=>a.date.localeCompare(b.date));
    if(!rows.length||rows.at(-1).date!==asOf)return {...missing('日K日期落后于最近已收盘交易日'),status:'stale'};
    if(rows.length<60)return missing('有效日K不足60根');
    if(new Set(rows.map(r=>r.date)).size!==rows.length||rows.some(r=>!finite(r.close)))return missing('日K含缺失值或重复日期');
    const close=rows.at(-1).close,ma5=rows.slice(-5).reduce((sum,r)=>sum+r.close,0)/5;
    if(close<=0||ma5<=0)return missing('收盘价或MA5无效');
    let fast=rows[0].close,slow=fast,dea=0;const series=[];
    for(const r of rows){fast+=(r.close-fast)*2/13;slow+=(r.close-slow)*2/27;const dif=fast-slow;dea+=(dif-dea)*2/10;series.push({date:r.date,dif,dea,histogram:2*(dif-dea)})}
    const lastFour=series.slice(-4),macdRising=lastFour.slice(1).every((r,i)=>r.histogram>lastFour[i].histogram+1e-10),aboveMA5=close>ma5+1e-10;
    return {status:'ready',asOf,close,ma5,aboveMA5,macdRising,matches:aboveMA5&&macdRising,macd:series.at(-1),lastFour,bars:rows.length,method:'前复权收盘；MA5含当日；MACD(12,26,9)，柱=2×(DIF−DEA)，连续3天抬升指4根柱严格递增，绿柱缩短也计入；EMA以首根收盘初始化，至少60根日K。'};
  }
  function historicalHigh(data,price,asOf){
    const rows=(data?.klines||[]).map(line=>{const r=line.split(',');return {date:r[0],high:Number(r[3]),close:Number(r[2])}}).filter(r=>r.date<=asOf&&Number.isFinite(r.high)).sort((a,b)=>a.date.localeCompare(b.date));
    if(!rows.length)throw Error('历史K线不可用');let peak=rows[0];for(const r of rows)if(r.high>peak.high)peak=r;if(peak.high<=0)throw Error('高点价格无效');
    const complete=rows.length===Number(data.dktotal)&&rows.at(-1).date===asOf;
    const aligned=rows.at(-1).date===asOf,change=period=>aligned&&rows.length>period&&rows.at(-period-1).close>0&&price>0?(price/rows.at(-period-1).close-1)*100:null;
    const momentum={asOf:rows.at(-1).date,fiveDayChange:change(5),twentyDayChange:change(20)};
    return {momentum,high:peak.high,date:peak.date,coverageFrom:rows[0].date,coverageTo:rows.at(-1).date,bars:rows.length,totalBars:Number(data.dktotal)||null,complete,adjustment:'前复权',drawdownPct:price>0&&price<=peak.high?(1-price/peak.high)*100:null,aboveRecordedHigh:price>peak.high,checkedAt:new Date().toISOString()};
  }
  function orderExcerpt(text){
    const clean=String(text||'').replace(/\r/g,'').replace(/[ \t]+/g,' ');
    const answerParts=clean.split(/(?=\b[QA]\d+\s*[：:])/).filter(s=>!/^\s*Q\d+\s*[：:]/.test(s));
    const candidates=answerParts.flatMap(s=>s.split(/[。；\n]/)).map(s=>s.trim()).filter(s=>s.length>=12&&/订单|在手合同|合同金额|中标金额|中标项目/.test(s)&&!/^\s*(?:问|问题|Q\d+)\s*[：:]/.test(s)&&!/[？?]$/.test(s));
    if(!candidates.length)return null;const nonquestion=candidates.find(s=>/^A\d+\s*[：:]/.test(s))||candidates[0];return nonquestion.replace(/^A\d+\s*[：:]\s*/,'').slice(0,110);
  }
  const api={leadership,leaders,historicalHigh,orderExcerpt,completedSession,dailySignal};root.HardwareMetrics=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
