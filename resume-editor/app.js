
const schemas={basics:{name:'',label:'',email:'',phone:'',url:'',summary:'',location:{address:'',postalCode:'',city:'',region:'',countryCode:''},profiles:[{network:'',username:'',url:''}]},work:{name:'',position:'',location:'',url:'',startDate:'',endDate:'',summary:'',highlights:['']},education:{institution:'',studyType:'',area:'',startDate:'',endDate:'',score:'',url:'',courses:['']},skills:{name:'',level:'',keywords:['']},projects:{name:'',description:'',startDate:'',endDate:'',url:'',highlights:[''],keywords:[''],roles:[''],entity:'',type:''},volunteer:{organization:'',position:'',startDate:'',endDate:'',summary:'',url:'',highlights:['']},certificates:{name:'',issuer:'',date:'',url:''},awards:{title:'',awarder:'',date:'',summary:''},publications:{name:'',publisher:'',releaseDate:'',url:'',summary:''},languages:{language:'',fluency:''},interests:{name:'',keywords:['']},references:{name:'',reference:''}};
let data,state,revision,active='master',section='basics',dirty=false,timer,previewVersion=0,busy=false;
let baseline;const expanded=new Map();
const $=id=>document.getElementById(id),copy=v=>structuredClone(v),title=k=>k.replace(/([a-z])([A-Z])/g,'$1 $2').replace(/^./,c=>c.toUpperCase());
const nodeFor=v=>{const n={id:crypto.randomUUID()};if(Array.isArray(v))n.children=v.map(nodeFor);else if(v&&typeof v==='object')n.children=Object.fromEntries(Object.entries(v).map(([k,x])=>[k,nodeFor(x)]));return n};
const version=()=>state.versions.find(v=>v.id===active);
function status(message,error=false){$('status').textContent=message;$('status').className=error?'error':''}
function mark(){dirty=true;status('Unsaved changes');clearTimeout(timer);timer=setTimeout(preview,250)}
function button(text,fn,label){const b=document.createElement('button');b.textContent=text;b.onclick=fn;if(label){b.setAttribute('aria-label',label);b.title=label}return b}
function pack(value,node){
  if(Array.isArray(value)){const pairs=value.map((v,i)=>pack(v,node.children[i])).filter(Boolean);return pairs.length?[pairs.map(p=>p[0]),{id:node.id,children:pairs.map(p=>p[1])}]:null}
  if(value&&typeof value==='object'){const entries=Object.entries(value).map(([k,v])=>[k,pack(v,node.children[k])]).filter(([,p])=>p);return entries.length?[Object.fromEntries(entries.map(([k,p])=>[k,p[0]])),{id:node.id,children:Object.fromEntries(entries.map(([k,p])=>[k,p[1]]))}]:null}
  return value===''?null:[value,node];
}
function payload(){if(active!=='master')return {data:baseline.data,state:{...state,tree:baseline.state.tree},revision,active};const [d,t]=pack(data,state.tree)||[{}, {id:state.tree.id,children:{}}];return {data:d,state:{...state,tree:t},revision,active}}
async function request(path){const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});if(!r.ok)throw Error((await r.json()).error||'Request failed');return r}
async function preview(){if(!state)return;const seq=++previewVersion;try{const r=await request('preview');const source=await r.text();if(seq===previewVersion)$('preview').srcdoc=source}catch(e){status(e.message,true)}}
function accept(result){data=result.data;state=result.state;revision=result.revision;baseline=copy({data,state});dirty=false;if(active!=='master'&&!version())active='master';status(result.warning||'All changes saved')}
async function save(){if(busy)return false;busy=true;$('save').disabled=true;$('editPane').inert=true;document.querySelector('.version-picker').inert=true;$('export').disabled=true;try{const r=await request('save');accept(await r.json());render();status('Saved · backup created');return true}catch(e){status(e.message,true);return false}finally{busy=false;$('save').disabled=false;$('editPane').inert=false;document.querySelector('.version-picker').inert=false;$('export').disabled=false}}
function choose(message,options){return new Promise(resolve=>{const dialog=document.createElement('dialog');const text=document.createElement('p');text.textContent=message;dialog.append(text);const choices=document.createElement('div');choices.className='choices';for(const option of options)choices.append(button(option,()=>{dialog.close();dialog.remove();resolve(option)}));dialog.append(choices);dialog.oncancel=e=>{e.preventDefault();dialog.close();dialog.remove();resolve('Cancel')};document.body.append(dialog);dialog.showModal()})}
async function guard(){if(!dirty)return true;const result=await choose('Save your changes before switching versions?', ['Save','Discard','Cancel']);if(result==='Save')return save();if(result==='Discard'){data=copy(baseline.data);state=copy(baseline.state);dirty=false;return true}return false}
async function switchVersion(id){if(busy)return;if(!await guard()){$('version').value=active;return}active=id;if(active!=='master'&&!version())active='master';render();preview();status('All changes saved')}
function selected(node){return active==='master'||!version().excluded.includes(node.id)}
function check(node,label,blocked=false){const input=document.createElement('input');input.type='checkbox';input.checked=selected(node);input.disabled=blocked;input.setAttribute('aria-label','Include '+label);input.onchange=()=>{const v=version();v.excluded=v.excluded.filter(id=>id!==node.id);if(!input.checked)v.excluded.push(node.id);mark();render()};return input}
function ensure(obj,n,key,value){if(!(key in obj)){obj[key]=copy(value);n.children[key]=nodeFor(obj[key])}return n.children[key]}
function refreshHeader(){
  const select=$('version');select.replaceChildren();for(const [id,name]of [['master','Master — All information'],...state.versions.map(v=>[v.id,v.name])]){const option=document.createElement('option');option.value=id;option.textContent=name;select.append(option)}select.value=active;select.disabled=false;
  $('destination').textContent='resume-editor/'+(active==='master'?'resume.json':`resume-${active}.json`);
  for(const id of ['renameVersion','deleteVersion'])$(id).disabled=active==='master';
  $('save').textContent=active==='master'?'Save master':'Save version';
  $('editMaster').hidden=active==='master';
  $('modeHint').textContent=active==='master'?'Edit master facts here. All versions inherit this content. Dates: YYYY, YYYY-MM, or YYYY-MM-DD.':'Choose what this version includes. Text comes from the master; the objective can be customized. Unchecked content is retained in the master.';
}
function render(){if(!state)return;refreshHeader();const nav=$('nav');nav.replaceChildren();const keys=[...new Set([...Object.keys(schemas),...Object.keys(data)])];for(const k of keys){const b=button(k==='basics'?'Objective & contact':title(k),()=>{section=k;render()});b.className=section===k?'active':'';nav.append(b)}nav.append(button('Advanced JSON',editJSON));
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
    if(active!=='master'&&!(key in obj)&&!(path.length===1&&path[0]==='basics'&&key==='summary'))continue;
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
  const n=node.children[key];if(active!=='master'&&path.join('.')==='basics.summary'&&!Object.hasOwn(baseline.data.basics||{},'summary'))n.id=baseline.state.tree.children.basics.id+'-summary';const off=blocked||!selected(n),isSummary=path.join('.')==='basics.summary';
  const wrapper=document.createElement('div');wrapper.className='field'+(off?' excluded':'');const label=document.createElement('label');const labelText=document.createElement('span');labelText.className='field-title';
  if(active!=='master')labelText.append(check(n,isSummary?'Objective':path.join(' '),blocked));labelText.append(document.createTextNode(isSummary?'Objective':title(key)));
  const multiline=['summary','description','reference'].includes(key);const input=document.createElement(multiline?'textarea':'input');
  input.setAttribute('aria-label',isSummary?'Objective':path.join(' '));const custom=active!=='master'&&isSummary&&Object.hasOwn(version(),'summaryOverride');input.value=custom?version().summaryOverride:(obj[key]??'');input.readOnly=active!=='master'&&!custom;
  input.disabled=off;
  input.oninput=()=>{if(custom)version().summaryOverride=input.value;else obj[key]=typeof obj[key]==='number'?Number(input.value):typeof obj[key]==='boolean'?input.value==='true':input.value;mark()};label.append(labelText,input);wrapper.append(label);
  if(active!=='master'&&isSummary){const tools=document.createElement('div');tools.className='override-tools';const action=button(custom?'Reset to master':'Customize for this version',()=>{if(custom)delete version().summaryOverride;else version().summaryOverride=obj[key]||'';mark();render()});action.disabled=blocked;tools.append(action);const hint=document.createElement('span');hint.textContent=custom?'Custom objective':'Using master objective';tools.append(hint);wrapper.append(tools)}
  parent.append(wrapper)
}
function arrayFields(parent,arr,node,template,label,blocked,path){
  const redraw=()=>{if(parent.tagName==='DETAILS')expanded.set(node.id,parent.open);mark();render()};
  arr.forEach((value,i)=>{
    const n=node.children[i],off=blocked||!selected(n),isObject=value&&typeof value==='object';const card=document.createElement(isObject?'fieldset':'div');card.className=(isObject?'':'compact-item')+(off?' excluded':'');
    const row=document.createElement('div');row.className='row';
    const move=delta=>{[arr[i],arr[i+delta]]=[arr[i+delta],arr[i]];[node.children[i],node.children[i+delta]]=[node.children[i+delta],node.children[i]];redraw()};
    if(active==='master'){
      const up=button('↑',()=>move(-1),`Move ${label.toLowerCase()} item ${i+1} up`);up.disabled=i===0;
      const down=button('↓',()=>move(1),`Move ${label.toLowerCase()} item ${i+1} down`);down.disabled=i===arr.length-1;
      row.append(up,down,button(isObject?'Remove':'×',()=>{if(confirm('Remove this master item from all versions?')){arr.splice(i,1);node.children.splice(i,1);redraw()}},`Remove ${label.toLowerCase()} item ${i+1}`));
    }
    if(isObject){const legend=document.createElement('legend');if(active!=='master')legend.append(check(n,`${label} entry ${i+1}`,blocked));legend.append(document.createTextNode(value.name||value.position||value.institution||`${label} ${i+1}`));card.append(legend,row);objectFields(card,value,n,typeof template==='object'?template:{},off,path.concat(i))}
    else{
      if(active!=='master')card.append(check(n,`${label} item ${i+1}`,blocked));
      const input=document.createElement(['Keywords','Roles'].includes(label)?'input':'textarea');input.setAttribute('aria-label',`${label} item ${i+1}`);input.value=value;input.readOnly=active!=='master';input.disabled=off;input.oninput=()=>{arr[i]=input.value;mark()};card.append(input);
      if(active!=='master'&&path[0]==='work'&&label==='Highlights'){
        const level=version().indent[n.id]||0;const number=document.createElement('span');number.className='indent-label';number.textContent='Level '+level;
        const outdent=button('←',()=>{version().indent[n.id]=Math.max(0,level-1);redraw()},`Outdent highlight ${i+1}`);outdent.disabled=off||level===0;
        const indent=button('→',()=>{version().indent[n.id]=Math.min(3,level+1);redraw()},`Indent highlight ${i+1}`);indent.disabled=off||level===3||i===0;
        row.append(number,outdent,indent)
      }
      card.append(row)
    }
    parent.append(card)
  });
  if(active==='master')parent.append(button('+ Add '+label.toLowerCase(),()=>{const value=typeof template==='object'?{}:'';arr.push(value);node.children.push(nodeFor(value));expanded.set(node.id,true);mark();render()}))
}
function slug(name){return name.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,50).replace(/-$/,'')||'version'}
function uniqueId(name){const base=slug(name);let id=base,i=2;while(id==='master'||state.versions.some(v=>v.id===id))id=base+'-'+i++;return id}
function askName(defaultValue=''){const name=prompt('Version name',defaultValue)?.trim();if(!name)return null;if(name.length>80||state.versions.some(v=>v.name.toLowerCase()===name.toLowerCase())){alert('Use a unique name with 1–80 characters.');return null}return name}
async function createVersion(duplicate=false){if(!await guard())return;const from=version()?copy(version()):null;const name=askName(duplicate&&from?from.name+' copy':'');if(!name){render();return}const v=duplicate&&from?from:{excluded:[],indent:{}};v.id=uniqueId(name);v.name=name;state.versions.push(v);active=v.id;mark();render()}
$('newVersion').onclick=()=>createVersion();$('duplicateVersion').onclick=()=>createVersion(true);
$('renameVersion').onclick=()=>{if(!version())return;const name=askName(version().name);if(name){const v=version();v.name=name;v.id=uniqueId(name);active=v.id;mark();render()}};
$('deleteVersion').onclick=async()=>{if(!version())return;const result=await choose('Delete this version? Master information is retained. Deletion takes effect when you save.', ['Delete','Cancel']);if(result==='Delete'){state.versions=state.versions.filter(v=>v.id!==active);active='master';mark();render()}};
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
