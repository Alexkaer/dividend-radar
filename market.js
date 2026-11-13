(() => {
  const $=id=>document.getElementById(id);let sectorPeriod='day',sectorData=null;
  const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=(v,d=2)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
  const pct=v=>v==null?'—':(v>0?'+':'')+fmt(v)+'%';
  const tone=v=>v>0?'up':v<0?'down':'muted';
  function volumeSVG(days){
    const width=1100,height=300,left=65,right=25,top=28,bottom=50,plot=width-left-right,max=Math.max(...days.map(r=>r.amount))*1.18;
    const y=v=>height-bottom-(v/max)*(height-top-bottom),step=plot/days.length;
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="最近10个交易日沪深成交额柱状图，完整数值见下方逐日表">${[0,.5,1].map(f=>`<line x1="${left}" x2="${width-right}" y1="${y(max*f)}" y2="${y(max*f)}" stroke="#253a43" stroke-dasharray="4 7"/><text x="${left-12}" y="${y(max*f)+5}" text-anchor="end" fill="#718c98" font-size="13">${(max*f/1e12).toFixed(1)}</text>`).join('')}<text x="${left}" y="15" fill="#718c98" font-size="12">万亿元</text>${days.map((r,i)=>{const x=left+step*i+step*.2,barWidth=step*.6;return `<g><title>${esc(r.date)}：${fmt(r.amount/1e8)}亿元</title><rect x="${x}" y="${y(r.amount)}" width="${barWidth}" height="${height-bottom-y(r.amount)}" fill="${i===days.length-1?'#dcff75':'#7dfbd3'}" opacity="${i===days.length-1?1:.35+i*.05}"/><text x="${x+barWidth/2}" y="${y(r.amount)-10}" text-anchor="middle" font-size="13" fill="#c2ddd3">${fmt(r.amount/1e12,2)}</text><text x="${x+barWidth/2}" y="${height-bottom+27}" text-anchor="middle" font-size="12" fill="#8da7b0">${r.date.slice(5).replace('-','/')}</text></g>`}).join('')}</svg>`;
  }
  function render(d){
    if(!d.indices?.length||d.turnover?.days?.length!==10||d.sectors?.items?.length!==15)throw Error('快照不完整');
    $('marketAlert').textContent='';$('marketDate').textContent=d.asOf;$('marketDate').previousElementSibling.textContent='行情日期 / '+(d.session||'行情快照');
    $('marketState').textContent='快照生成 '+new Date(d.updatedAt).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
    const today=new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Shanghai'});
    if(d.asOf!==today)$('marketAlert').textContent='当前展示 '+d.asOf+' 的收盘快照，可能因休市或更新延迟。请核对日期。';
    if(d.partialSource)$('marketAlert').textContent+=d.partialSource;
    $('indices').innerHTML=d.indices.map(r=>`<article><div><span>${esc(r.name)}</span><small>${esc(r.code)}</small></div><b>${fmt(r.close)}</b><strong class="${tone(r.change)}">${pct(r.change)}</strong><small>${esc(d.session||'行情快照')} · ${esc(r.date)}</small></article>`).join('');
    const b=d.breadth,m=d.sentiment,l=d.limits;
    $('moodScore').textContent=m.score??'—';$('moodLabel').textContent=m.label;
    $('moodDial').style.setProperty('--score',Math.max(0,Math.min(100,m.score||0))+'%');
    $('moodSummary').textContent=m.score==null?'同日有效数据不足，暂不判断。':`上涨 ${fmt(b.up,0)} 家 / 下跌 ${fmt(b.down,0)} 家，涨停池 ${l.up} 家 / 跌停池 ${l.down} 家。`;
    $('moodMethod').textContent=m.method||'同日有效样本不足。';
    $('breadthScope').textContent='有效行情 '+fmt(b.total,0)+' 家';
    $('breadthNumbers').innerHTML=[['上涨',b.up,'up'],['下跌',b.down,'down'],['平盘 / 停牌',b.flat,'muted']].map(([label,n,cls])=>`<div><small>${label}</small><b class="${cls}">${fmt(n,0)}</b></div>`).join('');
    $('breadthBar').innerHTML=[['#ff869b',b.up],['#7dfbd3',b.down],['#566c78',b.flat]].map(([c,n])=>`<span style="background:${c};width:${n/b.total*100}%"></span>`).join('');
    $('limitUp').textContent=fmt(l.up,0);$('limitDown').textContent=fmt(l.down,0);$('advanceShare').textContent=b.advanceShare==null?'—':fmt(b.advanceShare*100,1)+'%';$('limitScope').textContent=l.scope;
    const v=d.turnover,intraday=d.session==='盘中快照';
    $('volumeMetrics').innerHTML=[[d.partialSource?'成交额 '+v.days.at(-1).date:intraday?'当前累计成交额':'今日成交额',fmt(v.today/1e12)+' 万亿',''],[intraday?'当前累计较昨全日':'较昨日',pct(v.dayChangePct),tone(v.dayChangePct)],[intraday?'近5日比较（含盘中）':'近5日较此前5日',pct(v.fiveDayChangePct),tone(v.fiveDayChangePct)],['最近5日日均',fmt(v.recentFiveDayAverage/1e12)+' 万亿','']].map(([label,value,cls])=>`<div><small>${label}</small><b class="${cls}">${value}</b></div>`).join('');
    $('volumeChart').innerHTML=volumeSVG(v.days);$('volumeScope').textContent=v.scope;
    $('volumeRows').innerHTML=v.days.map(r=>`<tr><td>${r.date}</td><td>${fmt(r.shanghai/1e8)}</td><td>${fmt(r.shenzhen/1e8)}</td><td>${fmt(r.amount/1e8)}</td></tr>`).join('');
    sectorData=d.sectors;renderSectors();
  }
  function renderSectors(){
    if(!sectorData)return;const daily=sectorPeriod==='day',items=daily?sectorData.todayItems||[]:sectorData.items||[],metric=r=>daily?r.change:r.fiveDayChange,max=Math.max(...items.map(r=>Math.abs(metric(r))),1);
    $('sectorTitle').innerHTML=(daily?'当日领涨行业':'近5日领涨行业')+' <span>TOP 15</span>';
    document.querySelectorAll('#sectorPeriods button').forEach(b=>b.classList.toggle('selected',b.dataset.period===sectorPeriod));
    $('sectorWindow').textContent=items.length?(daily?items[0].endDate+' / 当日':items[0].startDate+' → '+items[0].endDate+' / 5个交易日'):'该周期榜单待刷新';
    $('sectorList').innerHTML=items.length?items.map((r,i)=>`<a class="sector-row" href="https://quote.eastmoney.com/bk/90.${esc(r.code)}.html" target="_blank" rel="noopener"><span class="rank">${String(i+1).padStart(2,'0')}</span><div class="sector-name"><b>${esc(r.name)}</b><small>${esc(r.code)}</small></div><div class="sector-track"><i style="width:${Math.abs(metric(r))/max*100}%"></i></div><b class="${tone(metric(r))}">${pct(metric(r))}</b><small>${daily?'当日涨幅':'今日 '+pct(r.change)}</small><span class="sector-arrow">↗</span></a>`).join(''):'<p class="market-footnote">当日榜数据待刷新，不使用5日榜代替。</p>';
    $('sectorScope').textContent=sectorData.scope+' 共比较 '+sectorData.universe+' 个板块指数。';
  }
  $('sectorPeriods').onclick=e=>{const b=e.target.closest('[data-period]');if(b){sectorPeriod=b.dataset.period;renderSectors()}};

  let current=null,busy=false;
  async function refresh(){if(busy)return;busy=true;$('refreshMarket').disabled=true;$('refreshMarket').textContent='↻ 正在刷新…';
    try{const d=await window.RadarLive.refreshMarket(current,message=>{$('marketState').textContent=message});render(d);current=d;window.RadarLive.cache.put('market',d)}
    catch(error){$('marketState').textContent='刷新失败 · 保留上次数据';$('marketAlert').textContent=error.message+'。当前仍为上次有效快照，可点击刷新重试。';}
    finally{busy=false;$('refreshMarket').disabled=false;$('refreshMarket').textContent='↻ 刷新数据';}}
  $('refreshMarket').onclick=refresh;
  (async()=>{
    const cached=window.RadarLive.cache.get('market');
    if(cached){try{render(cached);current=cached}catch{}}
    try{
      const response=await fetch('./data/market.json',{cache:'no-store'});
      if(!response.ok)throw Error('快照暂不可用');
      const published=await response.json();
      if(!current||published.asOf>current.asOf||published.asOf===current.asOf&&Date.parse(published.updatedAt)>Date.parse(current.updatedAt)){
        render(published);current=published;
      }
    }catch{}
    refresh();
  })();
})();
