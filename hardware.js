(() => {
  const $=id=>document.getElementById(id),KEY='radar-hardware-custom-v1';
  const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=(v,d=2)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
  const pct=v=>v==null?'—':(v>0?'+':'')+fmt(v)+'%';
  const tone=v=>v>0?'up':v<0?'down':'muted';
  const name=s=>s.nameVerified||s.name||s.code;
  const valid=s=>s.price>0&&Number.isFinite(s.change);
  const when=stamp=>stamp?new Date(stamp*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'行情时间待更新';
  let universe={groups:[],stocks:[]},custom=[],snapshot=null,visible=[],busy=false;
  try{custom=JSON.parse(localStorage.getItem(KEY)||'[]');if(!Array.isArray(custom))custom=[];custom=custom.filter(s=>/^\d{6}$/.test(s.code)&&typeof s.group==='string').slice(0,100)}catch{custom=[]}
  function definitions(){const map=new Map(universe.stocks.map(s=>[s.code,s]));for(const s of custom)if(!map.has(s.code))map.set(s.code,{...s,custom:true});return [...map.values()]}
  function saveCustom(){try{localStorage.setItem(KEY,JSON.stringify(custom));return true}catch{$('hardwareAlert').textContent='浏览器未允许本地保存，本次添加仅在当前页面有效。';return false}}
  function render(){
    if(!snapshot)return;
    const wanted=new Map(definitions().map(s=>[s.code,s]));let rows=snapshot.stocks.filter(s=>wanted.has(s.code)).map(s=>({...s,...wanted.get(s.code),nameVerified:s.nameVerified||s.name}));
    const known=new Set(rows.map(s=>s.code));for(const item of wanted.values())if(!known.has(item.code))rows.push({...item,price:null,change:null});
    const available=rows.filter(valid),up=available.filter(s=>s.change>0).length,down=available.filter(s=>s.change<0).length;
    $('hardwareCount').textContent=rows.length;$('hardwareBreadth').innerHTML=`<span class="up">${up}</span><span class="breadth-slash"> / </span><span class="down">${down}</span>`;
    const mean=available.length?available.reduce((sum,s)=>sum+s.change,0)/available.length:null;
    $('hardwareMean').textContent=pct(mean);$('hardwareMean').className=tone(mean);
    $('hardwareAmount').textContent=available.length?fmt(available.reduce((sum,s)=>sum+(s.amount||0),0)/1e8,0):'—';
    const groups=[...new Set([...universe.groups,...custom.map(s=>s.group)])];
    $('segmentCards').innerHTML=groups.map((group,i)=>{const members=rows.filter(s=>s.group===group),values=members.filter(valid),avg=values.length?values.reduce((sum,s)=>sum+s.change,0)/values.length:null;return `<button class="segment-card ${$('hardwareGroup').value===group?'selected':''}" data-group="${esc(group)}"><small>${String(i+1).padStart(2,'0')} / ${members.length} 只</small><b>${esc(group)}</b><strong class="${tone(avg)}">${pct(avg)}</strong><span>${values.filter(s=>s.change>0).length} 涨 / ${values.filter(s=>s.change<0).length} 跌</span></button>`}).join('');
    const query=$('hardwareSearch').value.trim().toLowerCase(),group=$('hardwareGroup').value;
    visible=rows.filter(s=>(group==='all'||s.group===group)&&`${name(s)} ${s.code} ${s.business||''} ${s.industry||''}`.toLowerCase().includes(query));
    const field=$('hardwareSort').value;visible.sort((a,b)=>field==='code'?a.code.localeCompare(b.code):((b[field]??-Infinity)-(a[field]??-Infinity))||a.code.localeCompare(b.code));
    $('hardwareRows').innerHTML=visible.map((s,i)=>`<tr><td class="hardware-rank">${String(i+1).padStart(2,'0')}</td><td><b>${esc(name(s))}</b><small>${esc(s.code)}${s.custom?' · 自定义':''}</small><small>${esc(when(s.quoteTime))}</small></td><td><span class="badge">${esc(s.group)}</span></td><td>${s.price>0?'¥ '+fmt(s.price):'待更新'}</td><td class="hardware-change ${tone(s.change)}">${pct(s.change)}</td><td>${s.amount==null?'—':fmt(s.amount/1e8)}</td><td>${s.cap==null?'—':fmt(s.cap/1e8,0)}</td><td>${s.pe==null?'—':s.pe<=0?'<span class="muted" title="市盈率非正，暂不作估值比较">亏损 / 非正</span>':fmt(s.pe)}</td><td>${s.turnover==null?'—':fmt(s.turnover)+'%'}</td><td><button class="analysis-button" data-detail="${s.code}" aria-label="查看${esc(name(s))}公司资料">主营资料 ↗</button></td><td>${s.custom?`<button class="remove-hardware" data-remove="${s.code}" aria-label="移除${esc(name(s))}">移除</button>`:'<span class="muted">预置</span>'}</td></tr>`).join('');
    $('hardwareEmpty').hidden=visible.length>0;$('hardwareResults').textContent=`${visible.length} ASSETS`;$('hardwareShowing').textContent=`显示 ${visible.length} / ${rows.length} 只 · 有效行情 ${available.length} 只 · 平盘 ${available.length-up-down} 只`;$('exportHardware').disabled=!visible.length;
  }
  async function refresh(){
    if(busy)return;busy=true;$('refreshHardware').disabled=true;$('addHardware').disabled=true;$('refreshHardware').textContent='↻ 正在刷新…';
    try{const next=await window.RadarLive.refreshHardware(definitions(),message=>{$('hardwareState').textContent=message});snapshot=next;window.RadarLive.cache.put('hardware',next);render();$('hardwareState').textContent='已刷新 '+new Date(next.updatedAt).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
      const warnings=next.warnings||[];const latest=Math.max(...next.stocks.map(s=>s.quoteTime||0));if(latest&&Date.now()-latest*1000>36*3600000)warnings.push('行情超过36小时，可能因休市或停牌，请核对日期');$('hardwareAlert').textContent=warnings.join('；');
    }catch(error){$('hardwareState').textContent='刷新失败 · 保留上次数据';$('hardwareAlert').textContent=error.message+'。可点击刷新重试；原行情日期不变。';}
    finally{busy=false;$('refreshHardware').disabled=false;$('addHardware').disabled=false;$('refreshHardware').textContent='↻ 刷新数据';}
  }
  function openDetail(code){const s=snapshot?.stocks.find(s=>s.code===code);if(!s)return;
    $('hardwareDetailBody').innerHTML=`<div class="eyebrow">COMPANY / 主营资料</div><h2 id="hardwareDetailTitle">${esc(name(s))} ${s.code}</h2><p>${esc(s.group)} · 源站行业 ${esc(s.industry||'待更新')}</p><div class="hardware-detail-price"><b>¥ ${fmt(s.price)}</b><span class="${tone(s.change)}">${pct(s.change)}</span></div><p>成交额 ${s.amount==null?'—':fmt(s.amount/1e8)+'亿元'} · 市值 ${s.cap==null?'—':fmt(s.cap/1e8)+'亿元'}</p><h3>源站主营摘要</h3><p>${esc(s.business||'主营资料暂不可用，请查看源站。')}</p><p>行情时间：${esc(when(s.quoteTime))}</p><p>产业链方向是观察分类，不代表全部收入来自AI。主题相关性、订单与收入贡献需结合公司公告核实。</p><a class="cyan" href="${esc(s.source||'https://data.eastmoney.com/stockdata/')}" target="_blank" rel="noopener">查看源站公司资料 ↗</a>`;$('hardwareDetail').showModal();}
  $('hardwareRows').onclick=e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.detail)openDetail(b.dataset.detail);if(b.dataset.remove){custom=custom.filter(s=>s.code!==b.dataset.remove);saveCustom();render()}};
  $('segmentCards').onclick=e=>{const b=e.target.closest('[data-group]');if(b){$('hardwareGroup').value=$('hardwareGroup').value===b.dataset.group?'all':b.dataset.group;render()}};
  $('hardwareGroup').onchange=render;$('hardwareSearch').oninput=render;$('hardwareSort').onchange=render;
  $('clearHardwareFilter').onclick=()=>{$('hardwareGroup').value='all';$('hardwareSearch').value='';render()};
  $('refreshHardware').onclick=refresh;$('addHardware').onclick=()=>{$('hardwareAddMessage').textContent='';$('hardwareAddDialog').showModal()};$('closeHardwareAdd').onclick=()=>$('hardwareAddDialog').close();$('closeHardwareDetail').onclick=()=>$('hardwareDetail').close();
  $('hardwareAddForm').onsubmit=async e=>{e.preventDefault();const code=$('newHardwareCode').value.trim(),group=$('newHardwareGroup').value;if(!/^(?:00|30|60|68|43|83|87|88|92)\d{4}$/.test(code)){$('hardwareAddMessage').textContent='请输入有效A股六位代码。';return}if(definitions().some(s=>s.code===code)){$('hardwareAddMessage').textContent='该股票已在观察池中，无需重复添加。';return}if(custom.length>=100){$('hardwareAddMessage').textContent='自定义标的已达100只，请先移除不再观察的股票。';return}
    $('confirmHardwareAdd').disabled=true;$('hardwareAddMessage').textContent='正在查询名称与行情…';
    try{const next=await window.RadarLive.refreshHardware([{code,group,custom:true}]),stock=next.stocks[0];if(!stock?.available)throw Error('该代码未取得有效股票行情，请核对代码');if(!stock.companyVerified)throw Error('暂未核实到上市公司资料，请稍后重试');custom.push({code,name:name(stock),group,custom:true});const persisted=saveCustom();snapshot={...(snapshot||{}),stocks:[...(snapshot?.stocks||[]).filter(s=>s.code!==code),stock]};window.RadarLive.cache.put('hardware',snapshot);render();$('hardwareAddDialog').close();$('newHardwareCode').value='';$('hardwareAlert').textContent='已添加 '+name(stock)+'（'+code+'）'+(persisted?'，仅保存在当前浏览器。':'；当前页面可用，浏览器未允许本地保存。');}
    catch(error){$('hardwareAddMessage').textContent=error.message+'，未添加。'}finally{$('confirmHardwareAdd').disabled=false}};
  $('exportHardware').onclick=()=>{if(!visible.length)return;const rows=[['代码','名称','方向','最新价','涨跌幅%','成交额亿元','市值亿元','PE TTM','换手率%','行情时间'],...visible.map(s=>[s.code,name(s),s.group,s.price,s.change,s.amount==null?'':s.amount/1e8,s.cap==null?'':s.cap/1e8,s.pe,s.turnover,when(s.quoteTime)])];const csv=rows.map(r=>r.map(v=>'"'+String(v??'').replace(/^[=+@-]/,"'").replaceAll('"','""')+'"').join(',')).join('\r\n');const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='硬件AI科技观察池.csv';a.click();URL.revokeObjectURL(url)};
  (async()=>{try{const response=await fetch('./data/hardware-universe.json',{cache:'no-store'});if(!response.ok)throw Error('观察池配置载入失败');universe=await response.json();const groups=[...new Set([...universe.groups,...custom.map(s=>s.group),'自定义'])];$('hardwareGroup').innerHTML='<option value="all">全部方向</option>'+groups.map(g=>`<option value="${esc(g)}">${esc(g)}</option>`).join('');$('newHardwareGroup').innerHTML=groups.map(g=>`<option value="${esc(g)}">${esc(g)}</option>`).join('');
      snapshot=window.RadarLive.cache.get('hardware');if(!snapshot){try{const r=await fetch('./data/hardware.json',{cache:'no-store'});if(r.ok)snapshot=await r.json()}catch{}}if(snapshot)render();refresh();
    }catch(error){$('hardwareState').textContent='观察池配置暂不可用';$('hardwareAlert').textContent=error.message;}})();
})();
