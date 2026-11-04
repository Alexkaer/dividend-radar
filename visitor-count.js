/* Public host-wide totals. Never substitute local visits for shared counts. */
(() => {
  const values=['vercount_value_site_uv','vercount_value_site_pv'].map(id=>document.getElementById(id)).filter(Boolean);
  if(!values.length)return;
  if(!['https:','http:'].includes(location.protocol)||['localhost','127.0.0.1','::1'].includes(location.hostname)){
    values.forEach(el=>el.textContent='上线后统计');return;
  }
  const unavailable=()=>values.forEach(el=>{if(!/^\d+$/.test(el.textContent.trim()))el.textContent='暂不可用'});
  const script=document.createElement('script');script.src='https://events.vercount.one/js';script.defer=true;script.onerror=unavailable;document.head.append(script);
  setTimeout(unavailable,10000);
})();
