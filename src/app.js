
const schemas={basics:{name:'',label:'',email:'',phone:'',url:'',summary:'',location:{address:'',postalCode:'',city:'',region:'',countryCode:''},profiles:[{network:'',username:'',url:''}]},work:{name:'',position:'',location:'',url:'',startDate:'',endDate:'',summary:'',highlights:['']},education:{institution:'',studyType:'',area:'',startDate:'',endDate:'',score:'',url:'',courses:['']},skills:{name:'',level:'',keywords:['']},projects:{name:'',description:'',startDate:'',endDate:'',url:'',highlights:[''],keywords:[''],roles:[''],entity:'',type:''},volunteer:{organization:'',position:'',startDate:'',endDate:'',summary:'',url:'',highlights:['']},certificates:{name:'',issuer:'',date:'',url:''},awards:{title:'',awarder:'',date:'',summary:''},publications:{name:'',publisher:'',releaseDate:'',url:'',summary:''},languages:{language:'',fluency:''},interests:{name:'',keywords:['']},references:{name:'',reference:''}};
let data,state,revision,active=new URLSearchParams(location.search).get('version')||'master',section='basics',dirty=false,timer,previewVersion=0,busy=false;
let baseline,cancelReorder;const expanded=new Map();
const $=id=>document.getElementById(id),copy=v=>structuredClone(v),title=k=>k.replace(/([a-z])([A-Z])/g,'$1 $2').replace(/^./,c=>c.toUpperCase());
const nodeFor=v=>{const n={id:crypto.randomUUID()};if(Array.isArray(v))n.children=v.map(nodeFor);else if(v&&typeof v==='object')n.children=Object.fromEntries(Object.entries(v).map(([k,x])=>[k,nodeFor(x)]));return n};
const version=()=>state.versions.find(v=>v.id===active);
function status(message,error=false){$('status').textContent=message;$('status').className=error?'error':''}
function mark(){if(version()){version().reviewStatus='unreviewed';delete version().markReviewed}dirty=true;status('Unsaved changes');++previewVersion;if(previewMode==='pdf'){previewStatus('PDF changes pending…');$('pdfPages').classList.add('stale')}clearTimeout(timer);timer=setTimeout(preview,previewMode==='pdf'?700:250)}
function button(text,fn,label){const b=document.createElement('button');b.textContent=text;b.onclick=fn;if(label){b.setAttribute('aria-label',label);b.title=label}return b}
function pack(value,node){
  if(Array.isArray(value)){const pairs=value.map((v,i)=>pack(v,node.children[i])).filter(Boolean);return pairs.length?[pairs.map(p=>p[0]),{id:node.id,children:pairs.map(p=>p[1])}]:null}
  if(value&&typeof value==='object'){const entries=Object.entries(value).map(([k,v])=>[k,pack(v,node.children[k])]).filter(([,p])=>p);return entries.length?[Object.fromEntries(entries.map(([k,p])=>[k,p[0]])),{id:node.id,children:Object.fromEntries(entries.map(([k,p])=>[k,p[1]]))}]:null}
  return value===''?null:[value,node];
}
function payload(){if(active!=='master')return {data:baseline.data,state:{...state,tree:baseline.state.tree},revision,active};const [d,t]=pack(data,state.tree)||[{}, {id:state.tree.id,children:{}}];return {data:d,state:{...state,tree:t},revision,active}}
async function request(path){const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});if(!r.ok){const error=Error((await r.json()).error||'Request failed');error.code=r.status;throw error}return r}
let previewMode='html',pdfInFlight=false,pdfQueued=false;
function previewStatus(message,className=''){const el=$('previewStatus');el.textContent=message;el.className=className}
async function preview(){
  if(!state)return;
  const seq=++previewVersion,mode=previewMode;
  if(mode==='pdf'&&pdfInFlight){pdfQueued=true;return}
  try{
    if(mode==='html'){
      previewStatus('HTML layout · select PDF to check printed page count');
      const r=await request('preview');const source=await r.text();if(seq===previewVersion&&previewMode===mode)$('preview').srcdoc=source;
    }else{
      pdfInFlight=true;pdfQueued=false;$('pdfPages').classList.add('stale');$('pdfPanel').setAttribute('aria-busy','true');previewStatus('Rendering PDF pages…');
      const r=await request('preview/pdf');const result=await r.json();if(seq!==previewVersion||previewMode!==mode)return;
      const pages=$('pdfPages');pages.replaceChildren();result.pages.forEach((page,i)=>{const figure=document.createElement('figure'),image=document.createElement('img'),caption=document.createElement('figcaption');image.src=page.image;image.alt=`Resume PDF page ${i+1} of ${result.pageCount}`;image.width=page.width;image.height=page.height;caption.textContent=`Page ${i+1} of ${result.pageCount}`;figure.append(image,caption);pages.append(figure)});pages.classList.remove('stale');
      previewStatus(result.pageCount===1?'1 page · '+result.paper:`${result.pageCount} pages · ${result.paper} · Longer than one page`,result.pageCount>1?'overflow':'');
    }
  }catch(e){if(seq===previewVersion&&previewMode===mode){previewStatus(e.message,'error');if(mode==='pdf')$('pdfPages').replaceChildren()}}
  finally{if(mode==='pdf'){pdfInFlight=false;$('pdfPanel').removeAttribute('aria-busy');if(pdfQueued&&previewMode==='pdf'){pdfQueued=false;preview()}}}
}
function setPreviewMode(mode){previewMode=mode;clearTimeout(timer);for(const kind of ['html','pdf']){const selected=kind===mode;$(kind+'Tab').setAttribute('aria-selected',String(selected));$(kind+'Tab').tabIndex=selected?0:-1;$(kind+'Panel').hidden=!selected}preview()}
for(const mode of ['html','pdf']){const tab=$(mode+'Tab');tab.onclick=()=>setPreviewMode(mode);tab.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?'html':e.key==='End'?'pdf':mode==='html'?'pdf':'html';setPreviewMode(next);$(next+'Tab').focus()}}}
function accept(result){data=result.data;state=result.state;revision=result.revision;baseline=copy({data,state});dirty=false;if(active!=='master'&&!version())active='master';status(result.warning||'All changes saved')}
async function save(){if(busy)return false;busy=true;$('save').disabled=true;$('editPane').inert=true;document.querySelector('.version-picker').inert=true;$('export').disabled=true;try{const r=await request('save');accept(await r.json());render();status('Saved · backup created');return true}catch(e){status(e.message,true);if(e.code===409)$('reconcile').hidden=false;return false}finally{busy=false;$('save').disabled=false;$('editPane').inert=false;document.querySelector('.version-picker').inert=false;$('export').disabled=false}}
function choose(message,options){return new Promise(resolve=>{const dialog=document.createElement('dialog');const text=document.createElement('p');text.textContent=message;dialog.append(text);const choices=document.createElement('div');choices.className='choices';for(const option of options)choices.append(button(option,()=>{dialog.close();dialog.remove();resolve(option)}));dialog.append(choices);dialog.oncancel=e=>{e.preventDefault();dialog.close();dialog.remove();resolve('Cancel')};document.body.append(dialog);dialog.showModal()})}
async function guard(){if(!dirty)return true;const result=await choose('Save your changes before switching versions?', ['Save','Discard','Cancel']);if(result==='Save')return save();if(result==='Discard'){data=copy(baseline.data);state=copy(baseline.state);dirty=false;return true}return false}
async function switchVersion(id){if(busy)return;if(!await guard()){$('version').value=active;return}active=id;if(active!=='master'&&!version())active='master';render();preview();status('All changes saved')}
function selected(node){return active==='master'||!version().excluded.includes(node.id)}
function check(node,label,blocked=false){const input=document.createElement('input');input.type='checkbox';input.checked=selected(node);input.disabled=blocked;input.setAttribute('aria-label','Include '+label);input.onchange=()=>{const v=version();v.excluded=v.excluded.filter(id=>id!==node.id);if(!input.checked)v.excluded.push(node.id);mark();render()};return input}
function ensure(obj,n,key,value){if(!(key in obj)){obj[key]=copy(value);n.children[key]=nodeFor(obj[key])}return n.children[key]}
function highlightGroup(n,text){state.highlights??={};state.masterIndent??={};return state.highlights[n.id]??={defaultWording:n.id,wordings:[{id:n.id,text,reviewStatus:'unreviewed'}]}}
function refreshHeader(){
  const select=$('version');select.replaceChildren();for(const [id,name]of [['master','Master — All information'],...state.versions.map(v=>[v.id,v.name])]){const option=document.createElement('option');option.value=id;option.textContent=name;select.append(option)}select.value=active;select.disabled=false;
  $('destination').textContent=(active==='master'?'data/resume.json':`output/resume-${active}.json`);
  for(const id of ['renameVersion','deleteVersion'])$(id).disabled=active==='master';
  $('save').textContent=active==='master'?'Save master':'Save version';
  $('editMaster').hidden=active==='master';
  $('markReviewed').hidden=active==='master';
  $('reviewNotice').textContent=active==='master'?'':version().reviewStatus==='reviewed'?'Reviewed':'Unreviewed content · downloads remain available';
  $('modeHint').textContent=active==='master'?'Edit master facts here. All versions inherit this content. Dates: YYYY, YYYY-MM, or YYYY-MM-DD.':'Choose content, wording, and order. Customize prose and indentation for this version. Unchecked content stays in Master.';
}
function render(){cancelReorder?.();if(!state)return;refreshHeader();const nav=$('nav');nav.replaceChildren();const keys=[...new Set([...Object.keys(schemas),...Object.keys(data)])];for(const k of keys){const b=button(k==='basics'?'Objective & contact':title(k),()=>{section=k;render()});b.className=section===k?'active':'';nav.append(b)}nav.append(button('Advanced JSON',editJSON));
  $('sectionTitle').textContent=section==='basics'?'Objective & contact':title(section);const fields=$('fields');fields.replaceChildren();
  const schema=schemas[section];let n;
  if(!(section in data)){
    if(active!=='master'){
      const empty=document.createElement('p');empty.textContent='No master content in this section yet.';fields.append(empty);return
    }
    n=ensure(data,state.tree,section,section==='basics'?{}:schema?[]:'');
  }else n=state.tree.children[section];
  const enabled=selected(n);
  if(active!=='master'){const label=document.createElement('label');label.className='selection-label section-control';label.append(check(n,title(section)),document.createTextNode('Include entire '+(section==='basics'?'objective and contact':section)+' section'));fields.append(label)}
  const area=document.createElement('div');if(!enabled)area.className='excluded';fields.append(area);
  if(Array.isArray(data[section]))arrayFields(area,data[section],n,schema||{},title(section),!enabled,[section]);
  else if(data[section]&&typeof data[section]==='object')objectFields(area,data[section],n,schema||{},!enabled,[section]);
  else leaf(area,data,state.tree,section,!enabled,[section]);
}
function objectFields(parent,obj,node,schema,blocked,path){
  for(const key of new Set([...Object.keys(schema),...Object.keys(obj)])){
    if(active!=='master'&&!(key in obj)&&!(['summary','description'].includes(key)||(path.length===1&&path[0]==='basics'&&key==='label')))continue;
    const template=schema[key];const initial=Array.isArray(template)?[]:(template&&typeof template==='object'?{}:'');
    const n=ensure(obj,node,key,initial),value=obj[key],p=path.concat(key),off=blocked||!selected(n);
    if(Array.isArray(value)){
      const details=document.createElement('details');details.className='list-group'+(off?' excluded':'');details.open=expanded.get(n.id)??false;
      details.ontoggle=()=>expanded.set(n.id,details.open);const summary=document.createElement('summary');
      if(active!=='master'){const checkbox=check(n,title(key),blocked);checkbox.onclick=e=>e.stopPropagation();summary.append(checkbox)}
      summary.append(document.createTextNode(title(key)+' ('+value.length+')'));details.append(summary);arrayFields(details,value,n,template?.[0]??'',title(key),off,p);parent.append(details)
    }else if(value&&typeof value==='object'){
      const fieldset=document.createElement('fieldset');if(off)fieldset.className='excluded';const legend=document.createElement('legend');if(active!=='master')legend.append(check(n,title(key),blocked));legend.append(document.createTextNode(title(key)));fieldset.append(legend);objectFields(fieldset,value,n,template||{},off,p);parent.append(fieldset)
    }else leaf(parent,obj,node,key,blocked,p)
  }
}
function leaf(parent,obj,node,key,blocked,path){
  const n=node.children[key],isSummary=path.join('.')==='basics.summary',isProse=isSummary||['summary','description'].includes(key)||(path.join('.')==='basics.label');const originalParent=path.slice(0,-1).reduce((obj,k)=>obj?.[k],baseline.data);if(active!=='master'&&isProse&&!Object.hasOwn(originalParent||{},key))n.id=node.id+'-'+key;const selectionNode=active!=='master'&&version().excluded.includes(node.id+'-'+key)?{id:node.id+'-'+key}:n;const off=blocked||!selected(selectionNode);
  const wrapper=document.createElement('div');wrapper.className='field'+(off?' excluded':'');const label=document.createElement('label');const labelText=document.createElement('span');labelText.className='field-title';
  if(active!=='master')labelText.append(check(selectionNode,isSummary?'Objective':path.join(' '),blocked));labelText.append(document.createTextNode(isSummary?'Objective':title(key)));
  const multiline=['summary','description','reference'].includes(key);const input=document.createElement(multiline?'textarea':'input');
  input.setAttribute('aria-label',isSummary?'Objective':path.join(' '));const overrideKey=isSummary?'summaryOverride':Object.hasOwn(version()?.prose||{},node.id+'-'+key)?node.id+'-'+key:n.id,overrides=isSummary?version():version()?.prose;const custom=active!=='master'&&isProse&&Object.hasOwn(overrides||{},overrideKey);input.value=custom?overrides[overrideKey]:(obj[key]??'');input.readOnly=active!=='master'&&!custom;
  input.disabled=off;
  input.oninput=()=>{if(custom)overrides[overrideKey]=input.value;else obj[key]=typeof obj[key]==='number'?Number(input.value):typeof obj[key]==='boolean'?input.value==='true':input.value;mark()};label.append(labelText,input);wrapper.append(label);
  if(active!=='master'&&isProse){const tools=document.createElement('div');tools.className='override-tools';const action=button(custom?'Reset to master':'Customize for this version',()=>{version().prose??={};const target=isSummary?version():version().prose;if(custom)delete target[overrideKey];else target[overrideKey]=obj[key]||'';mark();render()});action.disabled=blocked;tools.append(action);const hint=document.createElement('span');hint.textContent=custom?'Custom prose':'Using master prose';tools.append(hint);wrapper.append(tools)}
  parent.append(wrapper)
}
// Reordering uses IDs; moving a master item must move its value and tree node together.
function reorderItems(arr,node,ids,from,to,currentVersion){
  if(from===to)return false;
  const ordered=ids.slice();ordered.splice(to,0,ordered.splice(from,1)[0]);
  if(currentVersion){currentVersion.order??={};currentVersion.order[node.id]=ordered}
  else{
    const items=new Map(node.children.map((child,i)=>[child.id,{value:arr[i],node:child}]));
    arr.splice(0,arr.length,...ordered.map(id=>items.get(id).value));
    node.children.splice(0,node.children.length,...ordered.map(id=>items.get(id).node));
  }
  return true;
}
function reorderHandle(list,card,label,position,disabled,commit){
  const handle=button('⠿',()=>{},`Move ${label.toLowerCase()} item ${position+1}`);
  handle.className='drag-handle';handle.disabled=disabled;
  handle.setAttribute('aria-describedby','reorderHelp');
  const announce=message=>{$('reorderStatus').textContent=message};
  let drag;
  const clearMarkers=()=>{for(const item of list.children)item.classList.remove('drop-before','drop-after')};
  const cleanup=()=>{
    if(!drag)return;
    cancelAnimationFrame(drag.frame);drag.badge?.remove();clearMarkers();card.classList.remove('drag-source');
    handle.setAttribute('aria-pressed','false');
    const pointerId=drag.pointerId;drag=null;cancelReorder=null;
    if(pointerId!==undefined&&handle.hasPointerCapture(pointerId))handle.releasePointerCapture(pointerId);
  };
  const showTarget=()=>{
    clearMarkers();
    if(!drag.valid||drag.to===position)return;
    const remaining=[...list.children].filter(item=>item!==card);
    const target=remaining[drag.to]||remaining.at(-1);
    target?.classList.add(remaining[drag.to]?'drop-before':'drop-after');
  };
  const begin=keyboard=>{
    cancelReorder?.();drag={to:position,valid:true,keyboard};cancelReorder=cleanup;
    handle.setAttribute('aria-pressed','true');card.classList.add('drag-source');
    announce(`Picked up ${label.toLowerCase()} item ${position+1} of ${list.children.length}. ${keyboard?'Use arrow keys to choose a position, Space to drop, or Escape to cancel.':''}`);
  };
  const finish=()=>{
    const {to,valid}=drag;cleanup();
    if(valid&&to!==position){commit(to);announce(`Moved ${label.toLowerCase()} item to position ${to+1} of ${list.children.length}.`)}
    else announce('Order unchanged.');
  };
  const updatePointer=()=>{
    const bounds=list.getBoundingClientRect(),pane=$('editPane').getBoundingClientRect();
    drag.valid=drag.x>=bounds.left&&drag.x<=bounds.right&&drag.y>=Math.max(bounds.top,pane.top,0)&&drag.y<=Math.min(bounds.bottom,pane.bottom,innerHeight);
    const remaining=[...list.children].filter(item=>item!==card);
    drag.to=remaining.findIndex(item=>{const rect=item.getBoundingClientRect();return drag.y<rect.top+rect.height/2});
    if(drag.to===-1)drag.to=remaining.length;
    drag.badge.style.left=`${Math.max(12,Math.min(drag.x+14,innerWidth-drag.badge.offsetWidth-12))}px`;drag.badge.style.top=`${Math.max(12,Math.min(drag.y+14,innerHeight-drag.badge.offsetHeight-12))}px`;
    showTarget();
  };
  const scroll=()=>{
    if(!drag||drag.keyboard)return;
    const pane=$('editPane'),rect=pane.getBoundingClientRect();
    if(drag.x>=rect.left&&drag.x<=rect.right){
      const edge=48,top=Math.max(0,rect.top),bottom=Math.min(innerHeight,rect.bottom);
      const speed=drag.y<top+edge?-Math.min(18,(top+edge-drag.y)/3):drag.y>bottom-edge?Math.min(18,(drag.y-bottom+edge)/3):0;
      if(speed){pane.scrollTop+=speed;updatePointer()}
    }
    drag.frame=requestAnimationFrame(scroll);
  };
  handle.onpointerdown=e=>{
    if(disabled||!e.isPrimary||e.button!==0)return;
    e.preventDefault();handle.focus({preventScroll:true});begin(false);
    Object.assign(drag,{pointerId:e.pointerId,startX:e.clientX,startY:e.clientY,x:e.clientX,y:e.clientY,started:false});
    // Keep touch scrolling available everywhere except the grip itself.
    handle.setPointerCapture(e.pointerId);
  };
  handle.onpointermove=e=>{
    if(!drag||drag.keyboard||e.pointerId!==drag.pointerId)return;
    drag.x=e.clientX;drag.y=e.clientY;
    if(!drag.started){
      if(Math.hypot(drag.x-drag.startX,drag.y-drag.startY)<5)return;
      drag.started=true;drag.badge=document.createElement('div');drag.badge.className='drag-badge';drag.badge.textContent=`Moving ${label.toLowerCase()} item ${position+1}`;drag.badge.setAttribute('aria-hidden','true');document.body.append(drag.badge);scroll();
    }
    updatePointer();
  };
  handle.onpointerup=e=>{if(drag&&!drag.keyboard&&e.pointerId===drag.pointerId){if(drag.started){drag.x=e.clientX;drag.y=e.clientY;updatePointer();finish()}else{cleanup();announce('Order unchanged.')}}};
  handle.onpointercancel=handle.onlostpointercapture=()=>{if(drag&&!drag.keyboard){cleanup();announce('Move canceled.')}};
  handle.onkeydown=e=>{
    if(e.key==='Escape'&&drag){e.preventDefault();cleanup();announce('Move canceled.');return}
    if([' ','Enter'].includes(e.key)){
      e.preventDefault();if(drag?.keyboard)finish();else if(!drag)begin(true);return;
    }
    if(!drag?.keyboard||!['ArrowUp','ArrowDown','Home','End'].includes(e.key))return;
    e.preventDefault();drag.to=Math.max(0,Math.min(list.children.length-1,e.key==='Home'?0:e.key==='End'?list.children.length-1:drag.to+(e.key==='ArrowUp'?-1:1)));
    showTarget();announce(`Position ${drag.to+1} of ${list.children.length}. Space to drop, Escape to cancel.`);
    const remaining=[...list.children].filter(item=>item!==card);(remaining[drag.to]||remaining.at(-1))?.scrollIntoView({block:'nearest'});
  };
  handle.onblur=()=>{if(drag?.keyboard){cleanup();announce('Move canceled.')}};
  handle.setAttribute('aria-pressed','false');
  return handle;
}
function arrayFields(parent,arr,node,template,label,blocked,path){
  const redraw=()=>{if(parent.tagName==='DETAILS')expanded.set(node.id,parent.open);mark();render()};
  const display=arr.map((value,i)=>({value,i}));const ordering=version()?.order?.[node.id]||[];display.sort((a,b)=>(ordering.includes(node.children[a.i].id)?ordering.indexOf(node.children[a.i].id):ordering.length)-(ordering.includes(node.children[b.i].id)?ordering.indexOf(node.children[b.i].id):ordering.length));
  const list=document.createElement('div');list.className='reorder-list';list.dataset.reorderList=node.id;parent.append(list);
  const ids=display.map(({i})=>node.children[i].id);
  display.forEach(({value,i},position)=>{
    const n=node.children[i],off=blocked||!selected(n),isObject=value&&typeof value==='object';const card=document.createElement(isObject?'fieldset':'div');card.className=(isObject?'':'compact-item')+(off?' excluded':'');
    const row=document.createElement('div');row.className='row';
    const handle=reorderHandle(list,card,label,position,blocked||arr.length<2,to=>{
      const pane=$('editPane'),scrollTop=pane.scrollTop;
      if(reorderItems(arr,node,ids,position,to,version())){
        redraw();pane.scrollTop=scrollTop;
        const next=[...document.querySelectorAll('.reorder-list')].find(el=>el.dataset.reorderList===node.id);
        next?.children[to]?.querySelector('.drag-handle')?.focus({preventScroll:true});
      }
    });
    if(active==='master')row.append(button(isObject?'Remove':'×',()=>{if(confirm('Remove this master item from all versions?')){arr.splice(i,1);node.children.splice(i,1);redraw()}},`Remove ${label.toLowerCase()} item ${i+1}`));
    if(isObject)row.prepend(handle);else card.append(handle);
    if(isObject){const legend=document.createElement('legend');if(active!=='master')legend.append(check(n,`${label} entry ${i+1}`,blocked));legend.append(document.createTextNode(value.name||value.position||value.institution||`${label} ${i+1}`));card.append(legend,row);objectFields(card,value,n,typeof template==='object'?template:{},off,path.concat(i))}
    else{
      if(active!=='master')card.append(check(n,`${label} item ${i+1}`,blocked));
      const isHighlight=label==='Highlights',group=isHighlight?highlightGroup(n,value):null;
      const selectedWording=group?(group.wordings.find(w=>w.id===(version()?.wording?.[n.id]||group.defaultWording))||group.wordings[0]):null;
      const input=document.createElement(['Keywords','Roles'].includes(label)?'input':'textarea');input.setAttribute('aria-label',`${label} item ${position+1}`);input.value=active==='master'?value:(selectedWording?.text??value);input.readOnly=active!=='master';input.disabled=off;input.oninput=()=>{arr[i]=input.value;if(group){const w=group.wordings.find(w=>w.id===group.defaultWording);w.text=input.value;w.reviewStatus='unreviewed'}mark()};card.append(input);
      if(group){
        const labelFor=w=>`${w.reviewStatus==='reviewed'?'Reviewed':'Needs review'}${w.provenance?.runId?' · Generated for job '+w.provenance.jobId:''}${w.provenance?.sourceHighlights?.length?' · Sources: '+w.provenance.sourceHighlights.join(', '):''}`;
        const included=(v,current)=>{if(v.excluded.includes(current.id))return false;if(current.id===n.id)return true;const children=current.children;return children?Object.values(children).some(child=>included(v,child)):false};const affected=w=>state.versions.filter(v=>included(v,state.tree)&&(v.wording?.[n.id]||group.defaultWording)===w.id).map(v=>v.name).join(', ')||'None';
        if(active==='master'){
          const info=document.createElement('small');info.textContent=labelFor(group.wordings[0])+' · Versions using this wording: '+affected(group.wordings[0]);card.append(info);
          for(const w of group.wordings.filter(w=>w.id!==group.defaultWording)){
            const field=document.createElement('label');field.className='wording-alternative';field.textContent='Alternative · '+labelFor(w)+' · Affected versions: '+affected(w);const edit=document.createElement('textarea');edit.value=w.text;edit.setAttribute('aria-label','Alternative wording');edit.oninput=()=>{w.text=edit.value;w.reviewStatus='unreviewed';mark()};field.append(edit);card.append(field)
          }
          row.append(button('Add alternative',()=>{const text=prompt('Alternative wording');if(text&&!group.wordings.some(w=>w.text===text)){group.wordings.push({id:crypto.randomUUID(),text,reviewStatus:'unreviewed'});redraw()}}));
        }else{
          const select=document.createElement('select');select.setAttribute('aria-label',`Wording for highlight ${position+1}`);for(const w of group.wordings){const option=document.createElement('option');option.value=w.id;option.textContent=w.text;select.append(option)}select.value=selectedWording.id;select.disabled=off;select.onchange=()=>{version().wording??={};version().wording[n.id]=select.value;redraw()};card.append(select);
          const info=document.createElement('small');info.textContent=labelFor(selectedWording);card.append(info);
          const edit=button('Edit wording for this version',()=>{const text=prompt('Wording for this version',selectedWording.text);if(text===null||!text.trim())return;let w=group.wordings.find(w=>w.text===text);if(!w){w={id:crypto.randomUUID(),text,reviewStatus:'unreviewed'};group.wordings.push(w)}version().wording??={};version().wording[n.id]=w.id;redraw()});edit.disabled=off;row.append(edit);
        }
        const levels=active==='master'?state.masterIndent:version().indent;
        const level=levels[n.id]??state.masterIndent[n.id]??0;const number=document.createElement('span');number.className='indent-label';number.textContent='Level '+level+(active!=='master'&&!Object.hasOwn(levels,n.id)?' · master':'');
        const outdent=button('←',()=>{levels[n.id]=Math.max(0,level-1);redraw()},`Outdent highlight ${position+1}`);outdent.disabled=off||level===0;
        const indent=button('→',()=>{levels[n.id]=Math.min(3,level+1);redraw()},`Indent highlight ${position+1}`);indent.disabled=off||level===3;
        row.append(number,outdent,indent);
        if(active!=='master')row.append(button('Reset to master',()=>{delete levels[n.id];redraw()}));
      }
      card.append(row)
    }
    list.append(card)
  });
  if(active==='master')parent.append(button('+ Add '+label.toLowerCase(),()=>{const value=typeof template==='object'?{}:'';arr.push(value);const added=nodeFor(value);node.children.push(added);if(label==='Highlights'){highlightGroup(added,value);state.versions.forEach(v=>v.excluded.push(added.id))}expanded.set(node.id,true);mark();render()}))
}
function slug(name){return name.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,50).replace(/-$/,'')||'version'}
function uniqueId(name){const base=slug(name);let id=base,i=2;while(id==='master'||state.versions.some(v=>v.id===id))id=base+'-'+i++;return id}
function askName(defaultValue=''){const name=prompt('Version name',defaultValue)?.trim();if(!name)return null;if(name.length>80||state.versions.some(v=>v.name.toLowerCase()===name.toLowerCase())){alert('Use a unique name with 1–80 characters.');return null}return name}
async function createVersion(duplicate=false){if(!await guard())return;const from=version()?copy(version()):null;const name=askName(duplicate&&from?from.name+' copy':'');if(!name){render();return}const v=duplicate&&from?from:{excluded:[],indent:{}};v.id=uniqueId(name);v.name=name;state.versions.push(v);active=v.id;mark();render()}
$('newVersion').onclick=()=>createVersion();$('duplicateVersion').onclick=()=>createVersion(true);
$('renameVersion').onclick=()=>{if(!version())return;const name=askName(version().name);if(name){const v=version();v.name=name;active=v.id;mark();render()}};
$('deleteVersion').onclick=async()=>{if(!version())return;if(version().provenance?.jobId){alert('This version is linked to a job and must be retained.');return}const result=await choose('Delete this version? Master information is retained. Deletion takes effect when you save.', ['Delete','Cancel']);if(result==='Delete'){state.versions=state.versions.filter(v=>v.id!==active);active='master';mark();render()}};
$('markReviewed').onclick=()=>{mark();version().markReviewed=true;version().reviewStatus='reviewed';render();status('Review will be recorded when saved')};
$('version').onchange=e=>switchVersion(e.target.value);$('editMaster').onclick=()=>switchVersion('master');$('save').onclick=save;
$('export').onclick=()=>{const menu=$('exportMenu');menu.hidden=!menu.hidden;$('export').setAttribute('aria-expanded',String(!menu.hidden))};
document.querySelectorAll('[data-format]').forEach(b=>b.onclick=async()=>{try{const format=b.dataset.format;status('Exporting '+format.toUpperCase()+'…');const name=active==='master'?'resume':'resume-'+active;const r=await request('export/'+format);const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download=name+'.'+format;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);$('exportMenu').hidden=true;$('export').setAttribute('aria-expanded','false');status('Exported '+format.toUpperCase()+(dirty?' · unsaved draft':''))}catch(e){status(e.message,true)}});
window.addEventListener('beforeunload',e=>{if(dirty||rawDirty){e.preventDefault();e.returnValue=''}});
async function load(){try{const r=await fetch('/api/resume');const result=await r.json();if(!r.ok)throw Error(result.error||'Unable to load resume');accept(result);render();preview();$('save').disabled=false;$('export').disabled=false}catch(e){status(e.message,true)}}
load();

let rawDirty=false;
function reconcile(next,previous,oldNode){
  if(!oldNode)return nodeFor(next);
  const n={id:oldNode.id};
  if(Array.isArray(next)){
    const old=Array.isArray(previous)?previous:[],used=new Set();
    n.children=next.map(value=>{
      let i=old.findIndex((v,j)=>!used.has(j)&&JSON.stringify(v)===JSON.stringify(value));
      if(i<0&&value&&typeof value==='object'&&!Array.isArray(value)){
        const key=['name','institution','organization','title','language'].find(k=>value[k]);
        const candidates=key?old.map((v,j)=>[v,j]).filter(([v,j])=>!used.has(j)&&v&&v[key]===value[key]):[];
        if(candidates.length===1)i=candidates[0][1];
      }
      if(i<0)return nodeFor(value);used.add(i);return reconcile(value,old[i],oldNode.children?.[i]);
    });
  }else if(next&&typeof next==='object')n.children=Object.fromEntries(Object.entries(next).map(([k,v])=>[k,reconcile(v,previous?.[k],oldNode.children?.[k])]));
  return n;
}
function editJSON(){
  const dialog=document.createElement('dialog');dialog.style.width='min(900px,90vw)';dialog.style.maxWidth='900px';
  const heading=document.createElement('h2');heading.textContent=active==='master'?'Edit master JSON':'Master JSON (read-only)';dialog.append(heading);
  const hint=document.createElement('p');hint.textContent='Use form fields to preserve selections when rewriting highlights or keywords. Directly rewritten list text is treated as a new item; exact matches keep their IDs.';dialog.append(hint);
  const input=document.createElement('textarea');input.style.cssText='height:60vh;font-family:monospace';input.setAttribute('aria-label','Master JSON');input.value=JSON.stringify(payload().data,null,2);input.readOnly=active!=='master';input.oninput=()=>rawDirty=true;dialog.append(input);
  const error=document.createElement('p');error.style.color='#ae382b';dialog.append(error);
  const actions=document.createElement('div');actions.className='choices';
  const close=()=>{if(rawDirty&&!confirm('Discard unapplied JSON changes?'))return;rawDirty=false;dialog.close();dialog.remove()};
  if(active==='master')actions.append(button('Apply JSON',async()=>{try{
    const candidate=JSON.parse(input.value);if(!candidate||Array.isArray(candidate)||typeof candidate!=='object')throw Error('Use a JSON object.');
    const t=reconcile(candidate,data,state.tree);const r=await fetch('/api/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data:candidate,state:{...state,tree:t},active:'master'})});if(!r.ok)throw Error((await r.json()).error);
    data=candidate;state.tree=t;rawDirty=false;dialog.close();dialog.remove();mark();render();
  }catch(e){error.textContent=e.message}}));
  actions.append(button('Close',close));dialog.append(actions);dialog.oncancel=e=>{e.preventDefault();close()};document.body.append(dialog);dialog.showModal();
}

function mergeSaved(base,local,remote,path=''){
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  if(same(local,base))return copy(remote);if(same(remote,base)||same(local,remote))return copy(local);
  if([base,local,remote].every(x=>Array.isArray(x)&&x.every(item=>item&&typeof item==='object'&&typeof item.id==='string'))){const map=x=>Object.fromEntries(x.map(item=>[item.id,item])),b=map(base),l=map(local),r=map(remote);const common=x=>x.filter(item=>b[item.id]).map(item=>item.id);const baseOrder=base.map(item=>item.id),localOrder=common(local),remoteOrder=common(remote);if(!same(localOrder,baseOrder)&&!same(remoteOrder,baseOrder)&&!same(localOrder,remoteOrder))throw Error('Concurrent ordering changes at '+path+'. Your draft remains in the editor.');const first=same(localOrder,baseOrder)?remote:local;const ids=[...new Set([...first.map(item=>item.id),...remote.map(item=>item.id),...local.map(item=>item.id)])];return ids.map(id=>mergeSaved(b[id],l[id],r[id],path+'/'+id)).filter(item=>item!==undefined)}
  if(base&&local&&remote&&[base,local,remote].every(x=>typeof x==='object'&&!Array.isArray(x))){const result={};for(const k of new Set([...Object.keys(base),...Object.keys(local),...Object.keys(remote)])){const next=mergeSaved(base[k],local[k],remote[k],path+'/'+k);if(next!==undefined)result[k]=next}return result}
  throw Error('Concurrent changes overlap at '+path+'. Your draft remains in the editor. Export it before loading saved content.');
}
$('reconcile').onclick=async()=>{
  try{const response=await fetch('/api/resume'),remote=await response.json();if(!response.ok)throw Error(remote.error);const local=payload();const merged=mergeSaved(baseline,{data:local.data,state:local.state},{data:remote.data,state:remote.state});data=merged.data;state=merged.state;state.versions.forEach(v=>{if(v.markReviewed){delete v.markReviewed;v.reviewStatus='unreviewed'}});revision=remote.revision;baseline=copy({data:remote.data,state:remote.state});mark();render();preview();status('Saved changes reconciled with your draft. Save to finish.');$('reconcile').hidden=true}catch(error){status(error.message,true)}
};
window.addEventListener('focus',async()=>{if(!state||busy)return;try{const r=await fetch('/api/resume'),next=await r.json();if(r.ok&&next.revision!==revision){status('Saved Studio content changed. Reconcile to keep your edits.',true);$('reconcile').hidden=false}}catch{}});
