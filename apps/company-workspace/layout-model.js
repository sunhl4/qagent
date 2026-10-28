window.__ModuleLoader__.load({id:'@unitqc/company-layout-model',factory:()=>{
  const PANELS = ['left','center','chat'];
  const DEFAULT = {left:260,chat:580,visible:{left:true,center:true,chat:true},focus:'chat'};
  const clamp=(n,min,max)=>Math.max(min,Math.min(max,n));
  function restore(raw) {
    const value=raw&&typeof raw==='object'?raw:{};
    const visible=Object.fromEntries(PANELS.map(k=>[k,typeof value.visible?.[k]==='boolean'?value.visible[k]:true]));
    if(!PANELS.some(k=>visible[k]))visible.chat=true;
    return {left:Number.isFinite(value.left)?clamp(value.left,190,520):260,chat:Number.isFinite(value.chat)?clamp(value.chat,320,1200):580,visible,focus:PANELS.includes(value.focus)?value.focus:'chat'};
  }
  function toggle(state,panel) {
    if(!PANELS.includes(panel))return state;
    const visible={...state.visible,[panel]:!state.visible[panel]};
    if(!PANELS.some(k=>visible[k]))return state;
    return {...state,visible,focus:visible[panel]?panel:state.focus};
  }
  function solve(state,viewport) {
    const width=Math.max(0,viewport);
    let panels=PANELS.filter(k=>state.visible[k]);
    const narrow=width<900;
    if(narrow){panels=[panels.includes(state.focus)?state.focus:panels.at(-1)];}
    const gaps=Math.max(0,panels.length-1)*6;
    const available=Math.max(0,width-gaps);
    const sizes={left:0,center:0,chat:0};
    if(panels.length===1)sizes[panels[0]]=available;
    else {
      const min={left:190,center:240,chat:320};
      const wanted={left:state.left,center:Math.max(240,available-(panels.includes('left')?state.left:0)-(panels.includes('chat')?state.chat:0)),chat:state.chat};
      const total=panels.reduce((sum,k)=>sum+wanted[k],0);
      const floor=panels.reduce((sum,k)=>sum+min[k],0);
      if(total<=available){for(const k of panels)sizes[k]=wanted[k];sizes[panels.includes('center')?'center':panels.at(-1)]+=available-total;}
      else {const budget=Math.max(0,available-floor);const flex=total-floor;for(const k of panels)sizes[k]=available<floor?available*min[k]/floor:min[k]+budget*(wanted[k]-min[k])/Math.max(1,flex);}
    }
    return {sizes,panels,narrow};
  }
  function resize(state,side,delta,viewport,initial) {
    const layout=initial||solve(state,viewport);
    if(layout.narrow)return state;
    if(side==='left')return {...state,left:clamp(layout.sizes.left+delta,190,Math.min(520,viewport-326))};
    if(side==='chat')return {...state,chat:clamp(layout.sizes.chat-delta,320,Math.max(320,viewport-246))};
    return state;
  }
  return {PANELS,DEFAULT,restore,toggle,solve,resize};
}});
