/* Comparable prices and reproducible scale-leader selection. */
(function(root){
  function leaders(stocks,count=2){const groups=new Map();for(const s of stocks){if(s.custom||!Number.isFinite(s.cap)||s.cap<=0)continue;if(!groups.has(s.group))groups.set(s.group,[]);groups.get(s.group).push(s)}const ranks=new Map();for(const list of groups.values())list.sort((a,b)=>b.cap-a.cap||a.code.localeCompare(b.code)).slice(0,count).forEach((s,i)=>ranks.set(s.code,i+1));return ranks}
  function historicalHigh(data,price,asOf){
    const rows=(data?.klines||[]).map(line=>{const r=line.split(',');return {date:r[0],high:Number(r[3])}}).filter(r=>r.date<=asOf&&Number.isFinite(r.high)).sort((a,b)=>a.date.localeCompare(b.date));
    if(!rows.length)throw Error('历史K线不可用');let peak=rows[0];for(const r of rows)if(r.high>peak.high)peak=r;if(peak.high<=0)throw Error('高点价格无效');
    const complete=rows.length===Number(data.dktotal)&&rows.at(-1).date===asOf;
    return {high:peak.high,date:peak.date,coverageFrom:rows[0].date,coverageTo:rows.at(-1).date,bars:rows.length,totalBars:Number(data.dktotal)||null,complete,adjustment:'前复权',drawdownPct:price>0&&price<=peak.high?(1-price/peak.high)*100:null,aboveRecordedHigh:price>peak.high,checkedAt:new Date().toISOString()};
  }
  function orderExcerpt(text){
    const clean=String(text||'').replace(/\r/g,'').replace(/[ \t]+/g,' ');
    const answerParts=clean.split(/(?=\b[QA]\d+\s*[：:])/).filter(s=>!/^\s*Q\d+\s*[：:]/.test(s));
    const candidates=answerParts.flatMap(s=>s.split(/[。；\n]/)).map(s=>s.trim()).filter(s=>s.length>=12&&/订单|在手合同|合同金额|中标金额|中标项目/.test(s)&&!/^\s*(?:问|问题|Q\d+)\s*[：:]/.test(s)&&!/[？?]$/.test(s));
    if(!candidates.length)return null;const nonquestion=candidates.find(s=>/^A\d+\s*[：:]/.test(s))||candidates[0];return nonquestion.replace(/^A\d+\s*[：:]\s*/,'').slice(0,110);
  }
  const api={leaders,historicalHigh,orderExcerpt};root.HardwareMetrics=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
