(() => {
  'use strict';
  let report=null, credentials=null, kind='pullback', epoch=0;
  const $=id=>document.getElementById(id);
  const names={pullback:'涨停回调低吸',second:'二板后回调',triple:'修正版三倍量'};
  const rules={pullback:'近20日真实涨停 → 至少2%回调 → 守住启动低点 → 收阳转强并收复MA10。9:25竞价、9:40承接为核心，14:40补充检查。',second:'近30日真实连续≥2板，断板后3–10日、量不高于断板量的一半，守住启动低点并回踩MA10。一字板或3板以上降级。14:45仍需VWAP与承接确认。',triple:'近5日同一根日K量≥前日3倍、收阳涨幅>3%、收在振幅上半区。信号日只观察；左侧看底部区间，右侧看后续阳线实体收盘突破信号K最高点。不设均线多头硬门槛。'};
  const decode=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
  async function load(user, pass, requestEpoch) {
    const response=await fetch('data/strategies.enc.json',{cache:'no-store',credentials:'omit'});
    if(!response.ok) throw new Error('snapshot');
    const envelope=await response.json();
    if(envelope.version!==1 || envelope.kdf!=='PBKDF2-SHA256' || envelope.iterations!==600000) throw new Error('format');
    const salt=decode(envelope.salt);
    let key;
    if(user !== null) {
      const material=await crypto.subtle.importKey('raw',new TextEncoder().encode(user+'\0'+pass),'PBKDF2',false,['deriveBits']);
      const bits=await crypto.subtle.deriveBits({name:'PBKDF2',hash:'SHA-256',salt,iterations:envelope.iterations},material,256);
      key=await crypto.subtle.importKey('raw',bits,'AES-GCM',false,['decrypt']);
      // Keep password-derived base material, not the password, for new daily salts.
      if(requestEpoch===epoch) credentials=material;
    } else {
      const bits=await crypto.subtle.deriveBits({name:'PBKDF2',hash:'SHA-256',salt,iterations:envelope.iterations},credentials,256);
      key=await crypto.subtle.importKey('raw',bits,'AES-GCM',false,['decrypt']);
    }
    const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:decode(envelope.iv),additionalData:new TextEncoder().encode('dividend-strategy-v1'),tagLength:128},key,decode(envelope.ciphertext));
    const value=JSON.parse(new TextDecoder().decode(plain));
    if(requestEpoch!==epoch)return false;
    report=value;
    return true;
  }
  function cell(row,text,cls){const td=document.createElement('td');td.textContent=text;if(cls)td.className=cls;row.append(td);return td;}
  function paragraph(parent,text){const p=document.createElement('p');p.textContent=text;parent.append(p);}
  function render(){
    $('asOf').textContent=report.asOf;
    $('generated').textContent='生成于 '+new Date(report.generatedAt).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
    $('verified').textContent=report.verified+' / '+report.universe;
    const incomplete=Object.values(report.coverage).some(x=>!x.complete), failures=report.failures.length;
    $('coverageAlert').textContent=(incomplete?'宽筛返回不完整，仅展示实际返回并复核的范围。':'已完成本次宽筛候选覆盖。')+(failures?` ${failures}只历史数据不完整，未计入通过名单。`:'')+' 所有结果为日线观察候选；竞价、分时和板块强度待确认。';
    document.querySelectorAll('[data-kind]').forEach(b=>{b.setAttribute('aria-selected',String(b.dataset.kind===kind));b.querySelector('b').textContent=report.groups[b.dataset.kind].length;});
    $('results').setAttribute('aria-labelledby','tab-'+kind);
    $('strategyTitle').textContent=names[kind];$('strategyRule').textContent=rules[kind];
    $('rows').replaceChildren();const values=report.groups[kind];$('empty').hidden=values.length>0;
    for(const value of values){const tr=document.createElement('tr');const title=cell(tr,'');const strong=document.createElement('strong');strong.textContent=value.name;title.append(strong);const sub=document.createElement('small');sub.textContent=value.code+' / '+value.signalDate;title.append(sub);cell(tr,value.close.toFixed(2)+' / '+(value.change>0?'+':'')+value.change.toFixed(2)+'%');cell(tr,value.status,'signal-state');cell(tr,value.zone.map(x=>x.toFixed(2)).join(' – '));cell(tr,value.invalidation.toFixed(2),'guard');cell(tr,value.evidence+'。'+value.confirmation+'。'+value.exit);$('rows').append(tr);}
    $('method').replaceChildren();
    for(const text of [report.source,report.priceBasis,report.schedule,report.limitations,'规则版本：'+report.ruleVersion,'防守位为逻辑失效参考；涨幅≥5%的三倍量信号仅观察，跳空突破需回踩确认，不追涨。三倍量收盘低于信号低点失效；普通盘中下影不单独认定失效。'])paragraph($('method'),text);
    for(const [key,c] of Object.entries(report.coverage))paragraph($('method'),names[key]+`：宽筛总数${c.total}，返回${c.returned}，完整${c.complete?'是':'否'}。\n原始查询：`+report.queries[key]);
    if(failures)paragraph($('method'),'未复核标的：'+report.failures.map(x=>x.code+' '+x.name).join('、'));
  }
  function lock(){epoch++;report=null;credentials=null;$('workspace').hidden=true;$('loginPanel').hidden=false;$('logout').hidden=true;$('rows').replaceChildren();$('method').replaceChildren();for(const id of ['asOf','generated','verified','coverageAlert','refreshStatus'])$(id).textContent='';$('password').value='';$('loginStatus').textContent='已退出，策略内容已清除。';}
  $('loginForm').addEventListener('submit',async e=>{e.preventDefault();const current=++epoch;const user=$('username').value,pass=$('password').value;$('password').value='';$('loginButton').disabled=true;$('loginStatus').textContent='正在安全解锁…';try{if(await load(user,pass,current)){render();$('loginPanel').hidden=true;$('workspace').hidden=false;$('logout').hidden=false;$('loginStatus').textContent='';}}catch(error){if(current===epoch){credentials=null;$('loginStatus').textContent=error.name==='OperationError'?'账号或密码不正确。':'无法读取策略快照，请稍后重试。';}}finally{$('loginButton').disabled=false;}});
  $('logout').addEventListener('click',lock);
  $('reload').addEventListener('click',async()=>{const current=epoch;$('reload').disabled=true;$('refreshStatus').textContent='正在获取最新后台快照…';try{if(await load(null,null,current)){render();$('refreshStatus').textContent='已读取最新可用快照；日线筛选由后台每日15:45运行。';}}catch{if(current===epoch)$('refreshStatus').textContent='更新失败，保留原日期和当前结果。';}finally{$('reload').disabled=false;}});
  document.querySelectorAll('[data-kind]').forEach(b=>b.addEventListener('click',()=>{kind=b.dataset.kind;render();}));
  document.querySelector('.strategy-tabs').addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();const buttons=[...document.querySelectorAll('[data-kind]')];const index=buttons.findIndex(b=>b.dataset.kind===kind);buttons[(index+(e.key==='ArrowRight'?1:2))%3].click();buttons.find(b=>b.dataset.kind===kind).focus();});
  window.addEventListener('pagehide',lock);
})();
