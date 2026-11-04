/* Dismiss only a primary click that both starts and ends on the backdrop. */
(() => {
  for(const dialog of document.querySelectorAll('dialog')){
    let startedOutside=false;
    const outside=event=>{
      const box=dialog.getBoundingClientRect();
      return event.target===dialog&&(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom);
    };
    dialog.addEventListener('pointerdown',event=>{startedOutside=event.isPrimary&&event.button===0&&outside(event)});
    dialog.addEventListener('pointercancel',()=>{startedOutside=false});
    dialog.addEventListener('click',event=>{
      const dismiss=startedOutside&&event.button===0&&outside(event);startedOutside=false;
      if(dismiss&&dialog.open)dialog.close();
    });
    dialog.addEventListener('close',()=>{startedOutside=false});
  }
})();
