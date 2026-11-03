window.__ModuleLoader__.load({
  id:'@unitqc/company-workspace-ui',
  factory:require=>{
    const React=require('react');
    const {jsx,jsxs}=require('react/jsx-runtime');
    const RESOURCE_TASK_FETCH='/company-workspace/workbench/tasks';
    const RESOURCE_TASK_STATES=new Set(['completed','unknown','refused']);
    const button=(label,props={})=>jsx('button',{type:'button',className:'cw-button',...props,children:label});
    const resourceStatus = status => !status ? '检测中…'
      : status.connected ? '资源已连接'
      : status.portal ? '门户可用，资源未连接'
      : status.reason === 'missing_api_key' ? '未开通云平台'
      : status.reason === 'unconfigured' ? '未配置集群'
      : status.reason === 'auth_failed' ? '认证失败'
      : '资源不可用';
    const resourceTone = status => !status ? 'pending'
      : status.connected ? 'ok'
      : status.portal ? 'partial'
      : status.reason === 'missing_api_key' || status.reason === 'unconfigured' ? 'pending' : 'fail';
    function ResourceRows({rows,columns,empty}){
      if(!Array.isArray(rows)||rows.length===0)return jsx('p',{className:'cw-resource-empty',children:empty});
      return jsx('div',{className:'cw-resource-table-wrap',children:jsx('table',{className:'cw-resource-table',children:[jsx('thead',{children:jsx('tr',{children:columns.map(([key,label])=>jsx('th',{children:label},key))})}),jsx('tbody',{children:rows.slice(0,32).map((row,index)=>jsx('tr',{children:columns.map(([key])=>jsx('td',{children:row[key]===undefined||row[key]===''?'—':String(row[key])},key))},`${index}-${row.id||row.job||row.name||''}`))})]})});
    }
    const restoreTaskSnapshot=tasks=>Array.isArray(tasks)
      ? tasks.filter(row=>row&&typeof row==='object').map(row=>({...row,connection_state:'reconnecting',source:'server-facts-reconnect'}))
      : [];
    function ResourceCenter({kind}){
      const name=kind==='cloud'?'云平台':'超算';
      const [tab,setTab]=React.useState('summary');
      const [snapshot,setSnapshot]=React.useState({status:null,overview:null,tasks:null,loading:true,error:null});
      const load=React.useCallback(async()=>{
        if(typeof fetch!=='function'){setSnapshot(previous=>({...previous,status:{connected:false,reason:'fetch_failed'},overview:null,tasks:{available:false,tasks:restoreTaskSnapshot(previous.tasks&&previous.tasks.tasks),reason:'reconnecting'},loading:false,error:'客户端服务不可用'}));return;}
        setSnapshot(previous=>({...previous,loading:true,error:null}));
        try{
          const statusResponse=await fetch(`/company-workspace/${kind}/status`);
          const status=statusResponse.ok?await statusResponse.json():{connected:false,reason:'fetch_failed'};
          let overview=null;
          if(status.connected){
            const overviewResponse=await fetch(`/company-workspace/${kind}/overview`);
            overview=overviewResponse.ok?await overviewResponse.json():{reason:'fetch_failed'};
          }
          const taskResponse=await fetch('/company-workspace/workbench/tasks');
          const rawTasks=taskResponse.ok?await taskResponse.json():{available:false,tasks:[],reason:'fetch_failed'};
          const previousTasks=snapshot.tasks&&snapshot.tasks.tasks;
          const projectedTasks=rawTasks&&Array.isArray(rawTasks.tasks)
            ? {...rawTasks,tasks:rawTasks.tasks.filter(row=>row&&RESOURCE_TASK_STATES.has(row.status)&&['server_facts','reconnecting'].includes(row.connection_state||'server_facts'))}
            : {available:false,tasks:[],reason:'invalid_task_projection'};
          if(projectedTasks.available===false)projectedTasks.tasks=restoreTaskSnapshot(previousTasks);
          setSnapshot({status,overview,tasks:projectedTasks,loading:false,error:null});
        }catch(error){setSnapshot(previous=>({...previous,loading:false,tasks:{available:false,tasks:restoreTaskSnapshot(previous.tasks&&previous.tasks.tasks),reason:'reconnecting'},error:String(error?.message||'资源服务不可用').slice(0,120)}));}
      },[kind]);
      React.useEffect(()=>{setTab('summary');load();},[load]);
      const status=snapshot.status;
      const overview=snapshot.overview||{};
      const tasks=snapshot.tasks&&Array.isArray(snapshot.tasks.tasks)?snapshot.tasks.tasks:[];
      const portal=`/company-workspace/portal/${kind}/`;
      const tabButton=(id,label)=>jsx('button',{type:'button',className:'cw-resource-tab','aria-pressed':tab===id,onClick:()=>setTab(id),children:label},id);
      const summary=kind==='cloud'
        ? jsxs('div',{className:'cw-resource-sections',children:[
          jsxs('section',{children:[jsx('h4',{children:'设备目录'}),jsx(ResourceRows,{rows:overview.devices,columns:[['name','设备'],['kind','类型'],['state','状态'],['qubits','量子比特'],['max_shots','最大 shots']],empty:'设备数据暂不可用；可在右侧对话中让 Agent 查询云平台设备。'})]}),
          jsxs('section',{children:[jsx('h4',{children:'任务事实'}),jsx(ResourceRows,{rows:overview.jobs,columns:[['id','任务'],['device','设备'],['status','状态'],['submitted','提交'],['updated','更新']],empty:'云平台 SDK 不提供任务历史列表；提交后的任务请在右侧对话中用回执查询，完整记录保留在云平台页面。'})]})
        ]})
        : jsxs('div',{className:'cw-resource-sections',children:[
          jsxs('section',{children:[jsx('h4',{children:'运行 / 排队作业'}),jsx(ResourceRows,{rows:overview.running,columns:[['job','作业'],['part','分区'],['state','状态'],['elapsed','时长'],['start','开始'],['nodes','节点']],empty:'当前没有可展示的运行或排队作业。'})]}),
          jsxs('section',{children:[jsx('h4',{children:'近期历史作业'}),jsx(ResourceRows,{rows:overview.history,columns:[['job','作业'],['part','分区'],['state','状态'],['elapsed','时长'],['end','结束']],empty:'近期开启的历史作业暂无记录。'})]})
        ]});
      const files=kind==='hpc'&&Array.isArray(overview.files)?overview.files:[];
      return jsxs('div',{className:'cw-resource-center',children:[
        jsxs('div',{className:'cw-resource-head',children:[jsxs('div',{children:[jsx('div',{className:'cw-resource-kicker',children:'DSH 资源视图'}),jsx('h2',{children:`${name}资源中心`}),jsx('p',{children:'状态来自受管服务端投影；执行动作仍由 DSH Agent 工具、审批和平台回执完成。'})]}),jsxs('div',{className:'cw-resource-actions',children:[jsx('span',{className:`cw-resource-status ${resourceTone(status)}`,children:resourceStatus(status)}),jsx('button',{type:'button',className:'cw-button',onClick:load,disabled:snapshot.loading,children:snapshot.loading?'刷新中…':'刷新'})]})]}),
        snapshot.error&&jsx('p',{className:'cw-resource-error',children:snapshot.error}),
        jsxs('nav',{className:'cw-resource-tabs','aria-label':`${name}资源视图`,children:[tabButton('summary','资源概览'),tabButton('jobs','作业与回执'),tabButton('files','文件资产'),tabButton('portal','平台页面')]}),
        tab==='portal'
          ? jsxs('section',{className:'cw-resource-portal',children:[jsx('p',{className:'cw-resource-note',children:'门户用于登录、查看平台原生详情和完整历史；Agent 的提交、审批、状态核对和结果取回仍以 DSH 工具合同为准。'}),jsx('iframe',{title:`${name}原生页面`,src:portal,className:'cw-resource-portal-frame',referrerPolicy:'no-referrer',sandbox:'allow-forms allow-scripts allow-popups allow-popups-to-escape-sandbox allow-same-origin'})]})
          : tab==='files'
            ? jsx('section',{className:'cw-resource-sections',children:jsx(ResourceRows,{rows:files,columns:[['name','名称'],['kind','类型']],empty:kind==='hpc'?(overview.filesNote||'远端目录暂无可展示文件；文件取回由 hpc_file_fetch 写入当前 DSH 工作区。'):'云平台 SDK 没有远端文件夹浏览接口；文件通过 Agent 工具上传和结果回收。'})})
            : tab==='jobs'
              ? jsxs('section',{className:'cw-resource-sections',children:[jsx('p',{className:'cw-resource-note',children:'作业提交、取消和未知结果核对不由面板按钮直接触发。请在对话中让 Agent 使用对应工具；DSH 会记录调用、审批、短结果和持久回执。'}),jsx('section',{children:[jsx('h4',{children:'平台作业投影'}),jsx(ResourceRows,{rows:tasks,columns:[['request_id','请求'],['operation','操作'],['status','执行状态'],['execution_state','平台状态'],['approval_state','审批状态'],['connection_state','连接事实'],['business_ref','业务引用'],['result_state','结果'],['billing_state','计费']],empty:snapshot.tasks&&snapshot.tasks.available===false?'服务端回执不可用，暂不显示任务。':'没有可展示的绑定作业。'})]}),summary]})
              : summary
      ]});
    }

    const RECEIPT_TARGET='company-agent-receipts';
    const RECEIPT_TOOLS=new Set(['quantum_cloud_submit','quantum_cloud_status','quantum_cloud_result','hpc_queue','hpc_submit','hpc_job_status','hpc_file_fetch','hpc_stage_file','hpc_job_cancel','hpc_resources','hpc_file_list','hpc_dir_create','hpc_file_remove']);
    const EMPTY_RECEIPTS={items:[],active:false};
    const receiptText=block=>{
      if(!block||typeof block!=='object')return '';
      if(typeof block.text==='string')return block.text;
      // Real DSH tool results arrive wrapped: content[0] is a tool-result
      // block whose payload sits in its own content list (durable session
      // event shape recorded from the pinned engine lifecycle).
      if(Array.isArray(block.content))return block.content.map(receiptText).filter(Boolean).join('\n');
      if(typeof block.content==='string')return block.content;
      return '';
    };
    const receiptResult=event=>{const blocks=event?.data?.message?.content;return Array.isArray(blocks)?blocks.map(receiptText).filter(Boolean).join('\n').slice(0,400):'';};
    const receiptArgs=raw=>{if(typeof raw!=='string')return '';try{const value=JSON.parse(raw);if(!value||typeof value!=='object'||Array.isArray(value))return '';return Object.entries(value).filter(([key])=>!/program|path|script|token|secret|password|authorization/i.test(key)).slice(0,6).map(([key,item])=>`${key}=${typeof item==='string'?item.slice(0,80):String(item)}`).join(' · ');}catch{return '';}};
    // Definition state model: one receipt row. The Conversation engine keys each
    // Context by the business identity returned from match(), so context.matches
    // always describes exactly one company tool call and its result.
    const receiptFold=matches=>{
      let row=null;
      for(const match of matches||[]){
        const event=match?.event;
        if(event?.type==='tool/call'&&RECEIPT_TOOLS.has(event.data.name))
          row={id:String(event.data.callId),tool:event.data.name,args:receiptArgs(event.data.arguments),seq:Number(event.seq),anchorSeq:Number(event.seq),status:'运行中',result:''};
        else if(event?.type==='tool/result'&&row!==null){
          const failed=Boolean(event.data?.error)||event.data?.message?.content?.some(block=>block?.isError);
          row={...row,status:failed?'失败':'已完成',result:receiptResult(event)};
        }
      }
      return row;
    };
    const receiptDefinition={
      kind:'company-agent-resource-receipt',
      target:RECEIPT_TARGET,
      match(event){
        if(event.type==='tool/call'&&RECEIPT_TOOLS.has(event.data.name))return {id:String(event.data.callId),role:'start'};
        if(event.type==='tool/result'){const id=String(event.data?.message?.source?.callId||'');return id?{id,role:'update'}:null;}
        return null;
      },
      start(context,match,reader){return receiptFold(context.matches);},
      update(context,match){return receiptFold(context.matches);},
      publication:match=>match.event.type==='tool/call'?'animation-frame':'immediate',
      buildViewNode(context){
        const row=context.state;
        if(!row)return null;
        return {key:context.key,kind:'company-agent-resource-receipt',id:context.id,target:RECEIPT_TARGET,anchorSeq:row.anchorSeq,location:context.start?.location||{kind:'unresolved'},data:{...row}};
      }
    };
    // Per-Session snapshot builder, same replace/apply shape as the native
    // TrajectorySnapshotBuilder: the engine sends complete node sets or only
    // changed nodes and the snapshot always re-derives from the node store.
    function receiptBuilder(){
      const nodes=new Map();
      const snapshot=()=>{const rows=[...nodes.values()].map(node=>node&&node.data).filter(Boolean).sort((left,right)=>(Number(left.anchorSeq)||0)-(Number(right.anchorSeq)||0)||String(left.id).localeCompare(String(right.id))).slice(-24);return {items:rows,active:rows.some(row=>row.status==='运行中')};};
      return {empty:EMPTY_RECEIPTS,replace(input){nodes.clear();for(const node of input?.nodes||[])nodes.set(node.key,node);return snapshot();},apply(input){for(const node of input?.upserts||[])nodes.set(node.key,node);return snapshot();}};
    }
    const receiptSnapshot=receipts=>receipts&&typeof receipts.getSnapshot==='function'?receipts.getSnapshot()||EMPTY_RECEIPTS:EMPTY_RECEIPTS;
    function ReceiptView({receipts,viewRequest,completeViewRequest}){
      const [snapshot,setSnapshot]=React.useState(()=>receiptSnapshot(receipts));
      React.useEffect(()=>{
        setSnapshot(receiptSnapshot(receipts));
        return receipts?.subscribe?.(next=>setSnapshot(next||EMPTY_RECEIPTS));
      },[viewRequest,completeViewRequest]);
      if(!snapshot.items.length)return jsx('section',{'data-empty':true,className:'company-agent-receipt-view',children:[jsx('h3',{children:'资源回执'}),jsx('p',{children:'本会话暂无企业工具调用的持久回执；提交、审批和结果核对请继续在对话中进行。'})]});
      return jsxs('div',{className:'company-agent-receipt-view',children:[jsx('h3',{children:'资源回执'}),jsx('p',{children:'从持久 DSH 会话事件折叠的只读回执；执行、审批和平台事实仍由 Agent 工具与平台服务负责。'}),...snapshot.items.map(item=>jsxs('div',{className:'company-agent-receipt-row',children:[jsx('strong',{children:item.tool}),jsx('span',{'data-receipt-state':item.status,children:item.status}),item.args&&jsx('small',{children:item.args}),item.result&&jsx('pre',{children:item.result})]},item.id))]});
    }
    // uiConversation is supplied by the native conversation plugin, which in the
    // rc.3 web bundle itself depends on uiWorkspace supplied by the native
    // workspace plugin; registering the receipt view on a hard root inject
    // would couple this order to unrelated services. Resolve in a child scope.
    function registerReceiptView(ctx, uiConversation){
      if(!uiConversation)return;
      uiConversation.events.register(receiptDefinition);
      uiConversation.views.register({target:RECEIPT_TARGET,create:receiptBuilder});
      ctx.slots.inject('conversation.view',()=>ctx.slots.register({name:'conversation.view',id:RECEIPT_TARGET,order:20,label:()=>'资源回执',inject:sessionId=>{const target=uiConversation.binding(sessionId).target(RECEIPT_TARGET);return {receipts:{getSnapshot:()=>target.getSnapshot()||EMPTY_RECEIPTS,subscribe:listener=>target.subscribe(listener)}};}},ReceiptView));
    }

    // Shared live snapshot for the native Plugins card and the General row:
    // cloud/HPC connection status plus the server-managed access plan state.
    const SERVICE_NAMES={cloud:'云平台',hpc:'超算'};
    function useWorkspaceState(){
      const [state,setState]=React.useState(null);
      React.useEffect(()=>{
        if(typeof fetch!=='function')return;
        let cancelled=false;
        let timer=null;
        const poll=async()=>{
          clearTimeout(timer);
          const next=await Promise.all(['cloud','hpc'].map(async kind=>{
            let status=null;
            try{
              const res=await fetch(`/company-workspace/${kind}/status`);
              if(res.ok)status=await res.json();
            }catch{status={connected:false,reason:'fetch_failed'};}
            return [kind,{status,access:null}];
          }));
          let access=null;
          try{
            const res=await fetch('/company-workspace/access');
            if(res.ok)access=await res.json();
          }catch{access=null;}
          let agent=null;
          try{
            const res=await fetch('/company-workspace/agent/state');
            if(res.ok)agent=await res.json();
          }catch{agent=null;}
          const merged=Object.fromEntries(next.map(([kind,entry])=>{
            const open=Boolean(access&&access[kind]&&access[kind].open);
            const pending=Boolean(access&&Array.isArray(access.requests)&&access.requests.some(r=>r.kind===kind&&r.status==='pending'));
            return [kind,{...entry,open,pending}];
          }));
          merged.agent=agent;
          if(!cancelled)setState(merged);
          if(!cancelled)timer=setTimeout(poll,30000);
        };
        poll();
        return()=>{cancelled=true;clearTimeout(timer);};
      },[]);
      return state;
    }
    const stateText = s => !s ? '检测中…'
      : s.open ? '已开通'
      : s.pending ? '已申请，等待开通'
      : !s.status ? '检测中…'
      : s.status.connected ? '已连接'
      : s.status.reason === 'missing_api_key' ? '未配置密钥'
      : s.status.reason === 'auth_failed' ? '认证失败'
      : s.status.reason === 'unconfigured' ? '未配置'
      : s.status.reason === 'fetch_failed' ? '重试中…'
      : '未连接';
    function PlatformCard({t}){
      const [busy,setBusy]=React.useState(null);
      const [note,setNote]=React.useState(null);
      const state=useWorkspaceState();
      const request = async kind => {
        if(busy)return;
        setBusy(kind);setNote(null);
        try{
          const res=await fetch('/company-workspace/access',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({kind})});
          const body=await res.json().catch(()=>({}));
          if(!res.ok||body.error)setNote({tone:'fail',text:t('requestFailed')+String(body.error||('HTTP '+res.status)).slice(0,120)});
        }catch{setNote({tone:'fail',text:t('requestOffline')});}
        setBusy(null);
      };
      return jsxs('div',{'data-platform-card':true,children:[
        jsxs('p',{className:'cw-plugin-note',children:[t('intro'),' ',jsx('a',{href:'/?native=1',target:'_blank',rel:'noopener noreferrer',children:t('standalone')})]}),
        ['cloud','hpc'].map(kind=>jsxs('div',{className:'cw-plugin-service','data-service':kind,children:[
          jsxs('div',{className:'cw-plugin-row',children:[
            jsx('strong',{children:SERVICE_NAMES[kind]}),
            jsx('span',{className:'cw-plugin-status',children:stateText(state&&state[kind])})
          ]}),
          state&&state[kind]&&(state[kind].open||state[kind].pending)
            ? jsx('p',{className:'cw-plugin-note',children:state[kind].open?t('openNote'):t('pendingNote')})
            : jsx('button',{type:'button',className:'cw-plugin-request',disabled:busy!==null,onClick:()=>request(kind),children:busy===kind?t('requesting'):t('request')})
        ]},kind)),
        note&&jsx('p',{className:'cw-plugin-note','data-tone':note.tone,children:note.text}),
        jsx('p',{className:'cw-plugin-note',children:t('credentialNote')})
      ]});
    }
    function PlatformRow({t}){
      const state=useWorkspaceState();
      const agent=state&&state.agent;
      const agentBits=[];
      if(agent&&agent.available){
        agentBits.push(`技能库 ${agent.skills_governance&&agent.skills_governance.valid?'已准入':'未校验'}`);
        agentBits.push(`知识典 ${agent.knowledge_governance&&agent.knowledge_governance.valid?'已准入':'未校验'}`);
        const tenants=agent.tenants_governance;
        if(tenants){
          if(tenants.regime==='registry') agentBits.push(`开通注册表 ${tenants.approved_services} 项有效`);
          else if(tenants.regime==='unavailable') agentBits.push('开通注册表 未生效');
          else agentBits.push('开通 旧单用户模式');
        }
        const unknown=(agent.receipts&&agent.receipts.unknown_outcomes)||0;
        agentBits.push(unknown>0?`待对账外发 ${unknown} 条`:'外发无待对账');
      } else {
        agentBits.push('内核状态不可用');
      }
      return jsxs('div',{className:'cw-general-row','data-platform-row':true,children:[
        jsx('div',{className:'cw-general-title',children:t('rowTitle')}),
        jsxs('div',{className:'cw-general-status',children:[
          jsxs('span',{children:[SERVICE_NAMES.cloud,' ',stateText(state&&state.cloud)]}),
          jsxs('span',{children:[SERVICE_NAMES.hpc,' ',stateText(state&&state.hpc)]})
        ]}),
        jsx('p',{className:'cw-plugin-note','data-agent-governance':true,children:agentBits.join(' · ')}),
        jsx('p',{className:'cw-plugin-note',children:t('rowHint')})
      ]});
    }
    // Native right-sidebar tab: the resource center lives in the dock the same
    // way the native Files and Preview tabs do — a registered tab definition
    // plus a keyed body slot. It only presents server-managed projections;
    // submissions and approvals stay in the conversation.
    function ResourceTabHome({open}){
      return jsxs('section',{className:'cw-center-home',children:[jsx('div',{className:'cw-resource-kicker',children:'原生 DSH 侧栏'}),jsx('h2',{children:'选择资源中心'}),jsx('p',{children:'云平台和超算的资源事实显示在这里。对作业提交、审批、状态核对和结果回收，请使用对话中的 Agent 工具。'}),jsxs('div',{className:'cw-center-home-actions',children:[button('云平台资源中心',{onClick:()=>open('cloud')}),button('超算资源中心',{onClick:()=>open('hpc')})]})]});
    }
    function ResourceTabBody(){
      const [kind,setKind]=React.useState(null);
      return kind==='cloud'||kind==='hpc'
        ? jsx('div',{className:'cw-center-main',children:jsx(ResourceCenter,{kind},kind)})
        : jsx(ResourceTabHome,{open:setKind});
    }
    function apply(ctx){
      // Company resource receipts register on the native conversation service.
      ctx.inject(['uiConversation'], scope=>registerReceiptView(ctx, scope.get('uiConversation')));
      ctx.locale.register('companyPlugins',{zh:{
        title:'UNITQC 平台连接',
        intro:'云平台与超算由公司统一账号管理，无需填写账号密码；服务端批准后凭据自动注入。',
        standalone:'独立打开 DSH ↗',
        request:'申请开通',
        requesting:'正在提交开通申请…',
        pendingNote:'已申请开通，等待管理员批准后自动生效。',
        openNote:'已开通：服务端统一账号已就绪，凭据由服务端注入（0600 权限保存，用户不经手）。',
        requestFailed:'申请失败：',
        requestOffline:'提交失败：客户端服务不可达。',
        credentialNote:'凭据保存在客户端服务端配置（0600 权限），不进入本页存储与对话。',
        rowTitle:'平台连接',
        rowHint:'云平台与超算的开通和凭据由服务端管理；管理入口在「设置」中的「平台连接」页。',
        sectionTitle:'平台连接'
      },en:{
        title:'UNITQC Platform Connections',
        intro:'Cloud and HPC use the company central account; credentials are injected server-side after approval.',
        standalone:'Open DSH standalone ↗',
        request:'Request access',
        requesting:'Submitting request…',
        pendingNote:'Access requested; pending administrator approval.',
        openNote:'Open: the central account is ready and credentials are injected server-side (mode 0600).',
        requestFailed:'Request failed: ',
        requestOffline:'Submission failed: client service unreachable.',
        credentialNote:'Credentials stay in the server-side config (mode 0600); they never enter this page storage or the conversation.',
        rowTitle:'Platform Connections',
        rowHint:'Cloud and HPC access is server-managed; the management page lives in Settings → Platform Connections.',
        sectionTitle:'Platform Connections'
      }});
      // Connection management lives in the native Settings dialog as a
      // section page (order 12 puts it after Models, before Plugins), with a
      // General-section row for discoverability — the same seats native
      // features use. Both read the pinned access-seam endpoints.
      ctx.slots.inject('settings.section',()=>ctx.slots.register({
        name:'settings.section',id:'platform',order:12,locale:'companyPlugins',
        label:()=>ctx.locale.bind('companyPlugins')('sectionTitle')
      },PlatformCard));
      ctx.slots.inject('settings.general.item',()=>ctx.slots.register({
        name:'settings.general.item',id:'platform-connections',order:25,locale:'companyPlugins'
      },PlatformRow));
      const TAB_ID='@unitqc/company-workspace-ui';
      ctx.effect(()=>ctx.sidebarRightTabs.register({
        id:TAB_ID,
        kind:'company-resources',
        title:()=>'资源中心',
        guide:[{
          order:20,
          title:()=>'资源中心',
          description:()=>'云平台与超算的资源概览、作业与回执和平台页面；提交与审批仍在对话中进行。'
        }]
      }), 'company-workspace: resource tab');
      ctx.effect(()=>ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({
        name:'sidebar.right.pane.tab',
        key:TAB_ID
      },ResourceTabBody)), 'company-workspace: resource tab body');
    }
    return {inject:['slots','locale','sidebarRightTabs'],apply};
  }
});
