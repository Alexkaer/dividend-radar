(function(root){
  'use strict';
  const finite=x=>typeof x==='number'&&Number.isFinite(x);
  const round=x=>Math.round(x*100)/100;
  function quoteState(quote,now=Date.now()){
    if(!quote || !finite(quote.price) || quote.price<=0 || !finite(quote.change) || !finite(quote.time))return {valid:false,label:'行情缺失'};
    const stamp=new Date(quote.time*1000),current=new Date(now);
    const date=stamp.toLocaleDateString('sv-SE',{timeZone:'Asia/Shanghai'}),today=current.toLocaleDateString('sv-SE',{timeZone:'Asia/Shanghai'});
    if(stamp.getTime()>now+60000)return {valid:false,label:'行情时间异常',date};
    const hm=current.toLocaleTimeString('en-GB',{timeZone:'Asia/Shanghai',hour12:false}).slice(0,5);
    const dayName=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Shanghai',weekday:'short'}).format(current);
    const tradingDay=dayName!=='Sat'&&dayName!=='Sun';
    const tradingHours=tradingDay&&((hm>='09:30'&&hm<='11:35')||(hm>='13:00'&&hm<='15:05'));
    if(tradingHours&&(date!==today||now-stamp.getTime()>10*60*1000))return {valid:false,label:'盘中行情滞后',date};
    if(date!==today){
      const age=now-stamp.getTime();
      if((!tradingDay||hm<'09:25')&&age<=4*86400000)return {valid:true,label:'最近收盘',date};
      return {valid:false,label:'非今日行情',date};
    }
    return {valid:true,label:tradingHours?'盘中行情':'当日最新 / 收盘',date};
  }
  function rank(groups,quotes,asOf,now=Date.now()){
    const candidates=new Map();let total=0;
    for(const [kind,items] of Object.entries(groups))for(const item of items){
      total++;
      const quote=quotes?.[item.code],state=quoteState(quote,now);
      if(!state.valid || quote.change>=5 || quote.change<=-5 || quote.price<=item.invalidation || !finite(item.invalidation)||!Array.isArray(item.zone)||item.zone.length!==2||!item.zone.every(finite))continue;
      if(state.date<asOf || (Date.parse(state.date)-Date.parse(asOf))/86400000>4)continue;
      if(/高风险|跳空|信号日|仅观察/.test(item.status))continue;
      const [low,high]=item.zone;
      if(low>high||high<=item.invalidation)continue;
      const risk=(quote.price-item.invalidation)/quote.price*100;
      if(risk<=0||risk>8)continue;
      const distance=quote.price<low?(low/quote.price-1)*100:quote.price>high?(quote.price/high-1)*100:0;
      const structure=kind==='second'?30:kind==='pullback'?26:item.status.includes('实体突破')?30:item.status.includes('底部区间')?26:18;
      const support=Math.max(0,25-distance*5),defense=risk<=3?20:risk<=5?15:8;
      const volume=finite(item.volumeRatio)?item.volumeRatio<=1/3?15:item.volumeRatio<=.5?12:item.volumeRatio<=.75?8:3:0;
      const strength=quote.change>0?Math.min(10,quote.change*2.5):Math.max(0,5+quote.change);
      const score=round(structure+support+defense+volume+strength);
      const entry={...item,kind,price:quote.price,liveChange:quote.change,quoteTime:quote.time,score,risk:round(risk),distance:round(distance),
        breakdown:{structure:round(structure),support:round(support),defense,volume,strength:round(strength)},strategies:[kind],
        rationale:[distance===0?'当前位于关注区间':`距关注区间${distance.toFixed(2)}%`,`距防守位${risk.toFixed(2)}%`,finite(item.volumeRatio)?`日线量/参考K量${item.volumeRatio.toFixed(2)}`:'缩量信息不足',`当日${quote.change>=0?'+':''}${quote.change.toFixed(2)}%`]};
      const old=candidates.get(item.code);
      if(old){const combined=[...new Set([...old.strategies,kind])];if(score>old.score){entry.strategies=combined;candidates.set(item.code,entry);}else old.strategies=combined;}
      else candidates.set(item.code,entry);
    }
    const ranked=[...candidates.values()].sort((a,b)=>b.score-a.score||a.risk-b.risk||a.code.localeCompare(b.code));
    return {top:ranked.slice(0,5),eligible:ranked.length,total};
  }
  const api={rank,quoteState};if(typeof module==='object'&&module.exports)module.exports=api;else root.StrategyRanking=api;
})(typeof window!=='undefined'?window:globalThis);
