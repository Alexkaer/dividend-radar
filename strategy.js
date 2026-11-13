(() => {
  'use strict';
  let report=null, kind='pullback', epoch=0, quotes={}, quoteBusy=false, quoteEpoch=0, quoteFetchedAt=null, snapshotFingerprint=null, snapshotBusy=false;
  const $=id=>document.getElementById(id);
  const names={pullback:'涨停回调低吸',maPullback:'涨停回调 · MA20止损',second:'二板后回调',triple:'修正版三倍量'};
  const pullbackVersion='2026-11-10-mainboard-reclaim-v4';
  let legacyPullback=false;
  const groupDate=k=>report.groupAsOf?.[k]||(k==='maPullback'?null:report.asOf);
  const rules={pullback:'近20个交易日至少2次真实涨停；仅沪深主板非ST，上市超过365天。回调收盘守住MA20，近3根K线重心连续上移，MA10>MA20且两线向上；回调过程曾破MA5，之后重新站回，当前MA5乖离0%至5%。不要求反包，不再以当日涨幅超过5%为排除条件。工作日09:20竞价观察、14:30盘中确认。',maPullback:'近20个交易日至少2次涨停，现价低于最近一次涨停日收盘价且高于MA20。MA20为止损位，MA5为初步止盈位，两者以策略快照为准。盈亏比至少2:1；按涨停次数降序，同次数按快照盈亏比降序。',second:'近30日真实连续≥2板，断板后3–10日、量不高于断板量的一半，守住启动低点并回踩MA10。一字板或3板以上降级。14:45仍需VWAP与承接确认。',triple:'近5日同一根日K量≥前日3倍、收阳涨幅>3%、收在振幅上半区。信号日只观察；左侧看底部区间，右侧看后续阳线实体收盘突破信号K最高点。不设均线多头硬门槛。'};
  const when=t=>new Date(t*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
  function renderTop(){
    const dates=Object.fromEntries(Object.keys(report.groups).map(k=>[k,groupDate(k)]));
    const ranked=window.StrategyRanking.rank(report.groups,quotes,dates);
    $('topPicks').replaceChildren();$('topEmpty').hidden=ranked.top.length>0;
    $('topCount').textContent=`优先 ${ranked.top.length} / 符合排序条件 ${ranked.eligible}`;
    $('topEmpty').textContent=quoteFetchedAt?'没有同时满足行情、形态与防守条件的标的，不补足5只。':'等待有效最新行情，暂不生成当前优先名单。';
    ranked.top.forEach((item,index)=>{
      const card=document.createElement('article');card.className='top-pick';
      const rank=document.createElement('div');rank.className='pick-rank';rank.textContent=String(index+1).padStart(2,'0')+' / '+item.score.toFixed(1)+'分';card.append(rank);
      const title=document.createElement('h3');title.textContent=item.name;card.append(title);
      const code=document.createElement('small');code.textContent=item.code+' · '+item.strategies.map(k=>names[k]).join(' / ');card.append(code);
      const price=document.createElement('strong');price.textContent=item.price.toFixed(2)+' / '+(item.liveChange>0?'+':'')+item.liveChange.toFixed(2)+'%';card.append(price);
      paragraph(card,item.rationale.join(' · '));
      paragraph(card,'关注 '+item.zone.map(x=>x.toFixed(2)).join('–')+' / 防守 '+item.invalidation.toFixed(2));
      paragraph(card,'形态 '+item.breakdown.structure+' · 支撑 '+item.breakdown.support+' · 防守 '+item.breakdown.defense+' · 缩量 '+item.breakdown.volume+' · 强弱 '+item.breakdown.strength);
      const status=document.createElement('div');status.className='pick-state';status.textContent=item.provisional?'盘中临时观察 · 待收盘及承接确认':'优先观察 · 待承接确认';card.append(status);
      const time=document.createElement('small');time.textContent='行情 '+when(item.quoteTime)+' / 策略基准 '+groupDate(item.kind);card.append(time);
      $('topPicks').append(card);
    });
  }
  async function refreshQuotes(){
    if(quoteBusy||!report)return;
    const current=epoch,request=++quoteEpoch;quoteBusy=true;$('refreshQuotes').disabled=true;
    $('quoteStatus').textContent='正在向东方财富读取候选标的最新行情…';
    const codes=[...new Set(Object.values(report.groups).flat().map(x=>x.code))],next={};let failed=0;
    try{
      for(let i=0;i<codes.length;i+=50){
        const batch=codes.slice(i,i+50);let data=null;
        for(const host of ['push2.eastmoney.com','push2delay.eastmoney.com']){
          try{
            const url=new URL('https://'+host+'/api/qt/ulist.np/get');
            url.search=new URLSearchParams({secids:batch.map(c=>(c.startsWith('6')?'1.':'0.')+c).join(','),fltt:'2',fields:'f12,f2,f3,f6,f124',_:String(Date.now())});
            const response=await fetch(url,{cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer',signal:AbortSignal.timeout(12000)});
            if(!response.ok)throw Error('quote');const body=await response.json();if(body.rc!==0||!body.data?.diff)throw Error('quote');
            data=Array.isArray(body.data.diff)?body.data.diff:Object.values(body.data.diff);break;
          }catch{}
        }
        if(!data){failed+=batch.length;continue;}
        for(const row of data){if(!batch.includes(row.f12))continue;const numeric=v=>v!==null&&v!==''&&v!=='-'&&Number.isFinite(Number(v))?Number(v):null;next[row.f12]={price:numeric(row.f2),change:numeric(row.f3),amount:numeric(row.f6),time:numeric(row.f124)};}
      }
      if(current!==epoch||request!==quoteEpoch||!report)return;
      quotes=next;quoteFetchedAt=Date.now();render();
      const valid=Object.values(quotes).filter(q=>window.StrategyRanking.quoteState(q).valid),times=valid.map(q=>q.time);
      $('quoteStatus').textContent=`行情来源：东方财富公开行情 · 有效 ${valid.length}/${codes.length} · 获取于 ${new Date(quoteFetchedAt).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}`+(times.length?' · 源时间 '+when(Math.min(...times))+' 至 '+when(Math.max(...times)):' · 暂无可确认的今日行情')+(failed?` · ${failed}只请求失败`:'')+'。休市时显示最新收盘行情；日线池不因行情刷新扩充。';
    }finally{if(current===epoch&&request===quoteEpoch){quoteBusy=false;$('refreshQuotes').disabled=false;}}
  }
  async function load(requestEpoch, onlyIfChanged=false){
    const response=await fetch(new URL('data/strategies.json',location.href),{cache:'no-store',credentials:'omit'});
    if(!response.ok)throw Error('snapshot');
    const value=await response.json();
    if(value.version!==1||!value.groups||!value.generatedAt)throw Error('format');
    const fingerprint=value.generatedAt;
    if(requestEpoch!==epoch||(onlyIfChanged&&fingerprint===snapshotFingerprint))return false;
    report=value;
    snapshotFingerprint=fingerprint;
    legacyPullback=report.ruleVersions?.pullback!==pullbackVersion;
    if(legacyPullback) report.groups.pullback=[];
    report.groups.maPullback??=[];
    return true;
  }
  function cell(row,text,cls){const td=document.createElement('td');td.textContent=text;if(cls)td.className=cls;row.append(td);return td;}
  function paragraph(parent,text){const p=document.createElement('p');p.textContent=text;parent.append(p);}
  function render(){
    $('asOf').textContent=groupDate(kind)||'待更新';
    $('generated').textContent=groupDate(kind)?'生成于 '+new Date(report.groupGeneratedAt?.[kind]||report.generatedAt).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'等待首次快照';
    const stats=report.groupStats?.[kind];
    $('verified').textContent=groupDate(kind)?(stats?.verified??report.verified)+' / '+(stats?.universe??report.universe):'—';
    const incomplete=report.coverage[kind]?.complete!==true, failures=(stats?.failures||report.failures).length;
    $('coverageAlert').textContent=(incomplete?'宽筛返回不完整，仅展示实际返回并复核的范围。':'已完成本次宽筛候选覆盖。')+(failures?` ${failures}只历史数据不完整，未计入通过名单。`:'')+' 所有结果为日线观察候选；竞价、分时和板块强度待确认。';
    if(!groupDate(kind))$('coverageAlert').textContent='新策略等待首次筛选快照。';
    if(stats?.source)$('coverageAlert').textContent=stats.source+'。'+$('coverageAlert').textContent;
    if(legacyPullback&&kind==='pullback')$('coverageAlert').textContent='涨停回调策略已切换沪深主板、多头均线新版：旧版名单已停用，等待妙想按新规则完成筛选。其他策略保留各自原日期。'+$('coverageAlert').textContent;
    if(stats?.mode==='auction')$('coverageAlert').textContent+=' 当前为09:20竞价观察：使用上一完整交易日形态，不代表当日已重新站回均线。';
    if(stats?.mode==='intraday')$('coverageAlert').textContent+=' 当前为盘中临时信号，仍需收盘复核。';
    document.querySelectorAll('[data-kind]').forEach(b=>{b.setAttribute('aria-selected',String(b.dataset.kind===kind));b.querySelector('b').textContent=report.groups[b.dataset.kind].length;});
    $('results').setAttribute('aria-labelledby','tab-'+kind);
    $('strategyTitle').textContent=names[kind];$('strategyRule').textContent=rules[kind];
    $('rows').replaceChildren();const values=report.groups[kind];$('empty').hidden=values.length>0;
    $('rewardRiskHeading').textContent=kind==='maPullback'?'盈亏比（快照 / 最新）':'盈亏比';
    $('empty').textContent=!groupDate(kind)?'等待首次筛选结果。':kind==='pullback'&&legacyPullback?'旧版结果已停用；等待新版妙想筛选，暂不展示旧票。':'本次没有通过策略条件的候选，不补足数量。';
    for(const value of values){const tr=document.createElement('tr');const title=cell(tr,'');const strong=document.createElement('strong');strong.textContent=value.name;title.append(strong);const sub=document.createElement('small');sub.textContent=value.code+' / '+value.signalDate+(kind==='maPullback'?' · '+value.limitCount20+'次涨停':'');title.append(sub);cell(tr,value.close.toFixed(2)+' / '+(value.change>0?'+':'')+value.change.toFixed(2)+'%');const quote=quotes[value.code],state=window.StrategyRanking.quoteState(quote);const live=cell(tr,state.valid?quote.price.toFixed(2)+' / '+(quote.change>0?'+':'')+quote.change.toFixed(2)+'%':state.label);if(quote?.time){const stamp=document.createElement('small');stamp.textContent=when(quote.time);live.append(stamp);}const maQuote=kind==='maPullback'&&state.valid?window.StrategyRanking.maPullbackQuote(value,quote,state,groupDate(kind)):null;cell(tr,maQuote?.label??(kind==='pullback'&&state.valid&&value.bullishAverages&&state.date!==groupDate(kind)?'跨日行情 · 等待当日策略复核':kind==='pullback'&&state.valid&&!window.StrategyRanking.stillReclaimed(value,quote.price)?'最新价不再满足MA5乖离/MA10-MA20趋势 · 等待':value.action||value.status),'signal-state');cell(tr,(value.entryRange||value.zone).map(x=>x.toFixed(2)).join(' – '));cell(tr,(value.stopPrice??value.invalidation).toFixed(2),'guard');cell(tr,Number.isFinite(value.firstTarget)?value.firstTarget.toFixed(2):'—');cell(tr,Number.isFinite(value.rewardRisk)?value.rewardRisk.toFixed(2)+':1'+(kind==='maPullback'?' / '+(maQuote?.ratio!=null?maQuote.ratio.toFixed(2)+':1':'—'):''):'—');cell(tr,Number.isFinite(value.recommendedPosition)?value.recommendedPosition.toFixed(0)+'%':'—');cell(tr,value.evidence+'。'+value.confirmation+'。'+value.exit);$('rows').append(tr);}
    renderTop();
    $('method').replaceChildren();
    for(const text of [report.source,report.priceBasis,'涨停回调查询：09:20竞价观察、14:30盘中查询（北京时间，后台排队可能延迟）。',legacyPullback?'涨停回调新版尚未生成，旧版结果未展示。':report.limitations,'涨停回调规则版本：'+pullbackVersion,'仓位为账户占比：A+最多10%，A类最多5%，单笔账户风险不超过0.5%，当日新增仓位不超过20%。防守位为逻辑失效参考；涨停回调不再因当日涨幅超过5%自动排除，但远离MA5或盈亏比不足仍只观察。'])paragraph($('method'),text);
    for(const [key,c] of Object.entries(report.coverage))paragraph($('method'),names[key]+`：策略基准${groupDate(key)}，宽筛总数${c.total}，返回${c.returned}，完整${c.complete?'是':'否'}。\n原始查询：`+report.queries[key]);
    if(failures)paragraph($('method'),'本策略未复核标的：'+(stats?.failures||report.failures).map(x=>x.code+' '+x.name).join('、'));
  }
  async function autoReloadSnapshot(){
    if(snapshotBusy||!report||document.visibilityState!=='visible')return;
    const current=epoch;snapshotBusy=true;
    try{
      if(await load(current,true)){
        quoteEpoch++;quoteBusy=false;quotes={};quoteFetchedAt=null;render();
        $('refreshStatus').textContent='后台策略快照已自动更新：'+new Date().toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
        refreshQuotes();
      }
    }catch{if(current===epoch)$('refreshStatus').textContent='自动检查暂时失败，保留当前有效结果。';}
    finally{snapshotBusy=false;}
  }
  async function openWorkspace(){
    try {
      if(await load(epoch)){
        render();
        $('workspace').hidden=false;
        $('snapshotStatus').hidden=true;
        refreshQuotes();
      }
    } catch {
      $('snapshotStatus').textContent='策略快照暂不可用，稍后会自动重试。';
    }
  }
  $('reload').addEventListener('click',async()=>{const current=epoch;$('reload').disabled=true;$('refreshStatus').textContent='正在获取最新后台快照…';try{if(await load(current)){quoteEpoch++;quoteBusy=false;quotes={};quoteFetchedAt=null;render();$('refreshStatus').textContent='已读取最新可用快照；涨停回调09:20、14:30更新。';refreshQuotes();}}catch{if(current===epoch)$('refreshStatus').textContent='更新失败，保留原日期和当前结果。';}finally{$('reload').disabled=false;}});
  $('refreshQuotes').addEventListener('click',refreshQuotes);
  document.querySelectorAll('[data-kind]').forEach(b=>b.addEventListener('click',()=>{kind=b.dataset.kind;render();}));
  document.querySelector('.strategy-tabs').addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();const buttons=[...document.querySelectorAll('[data-kind]')];const index=buttons.findIndex(b=>b.dataset.kind===kind);buttons[(index+(e.key==='ArrowRight'?1:buttons.length-1))%buttons.length].click();buttons.find(b=>b.dataset.kind===kind).focus();});
  setInterval(()=>report?autoReloadSnapshot():openWorkspace(),60000);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&report)autoReloadSnapshot();});
  openWorkspace();
})();
