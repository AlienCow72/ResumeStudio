(() => {
  const $ = id => document.getElementById(id);
  const el = (tag, text, className) => {const node=document.createElement(tag); if(text !== undefined) node.textContent=text; if(className) node.className=className; return node;};
  let job, draft, mode='resume', dirty=false, busy=false, timer, sequence=0, previewRunning=false, previewPending=false;
  function message(text,error=false) {$('reviewStatus').textContent=text; $('reviewStatus').className=error?'error':'';}
  function button(text,fn) {const node=el('button',text);node.type='button';node.onclick=fn;return node;}
  function setBusy(value) {busy=value; $('reviewEditor').inert=value; for(const id of ['reviewSave','reviewDownload','reviewClose','reviewResume','reviewLetter']) $(id).disabled=value;}
  function payload() {return {runId:draft.runId,revision:draft.revision,draft:{resume:draft.resume,coverLetter:draft.coverLetter}};}
  async function request(action, body=payload()) {
    const response=await fetch(`/api/jobs/${job.id}/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!response.ok) throw Error((await response.json()).error || 'Unable to complete this action.');
    return response;
  }
  function changed() {dirty=true; message('Unsaved edits');clearTimeout(timer);++sequence;$('reviewPreviewStatus').textContent='PDF preview out of date · updating…';$('reviewPreview').setAttribute('aria-busy','true');timer=setTimeout(preview,650);}
  async function preview() {
    if(!draft || !$('reviewDialog').open) return;
    if(previewRunning) {previewPending=true;return;}
    previewRunning=true;previewPending=false;
    const seq=++sequence, selected=mode;
    const container=$('reviewPreview');
    container.setAttribute('aria-busy','true');
    $('reviewPreviewStatus').textContent='Rendering PDF preview…';
    try {
      const response=await request('preview-drafts',{...payload(),document:selected});
      const result=await response.json();
      if(seq!==sequence || !$('reviewDialog').open) return;
      const pages=result.pages.map((page,index)=>{
        const figure=el('figure'),image=el('img');
        image.src=page.image;image.width=page.width;image.height=page.height;
        image.alt=`${selected==='resume'?'Résumé':'Cover letter'}, page ${index+1} of ${result.pageCount}`;
        figure.append(image,el('figcaption',`Page ${index+1} of ${result.pageCount}`));return figure;
      });
      container.replaceChildren(...pages);
      $('reviewPreviewStatus').textContent=`PDF preview · ${result.pageCount} ${result.pageCount===1?'page':'pages'} · US Letter`;
    } catch(error) {
      if(seq===sequence) {
        container.replaceChildren();
        $('reviewPreviewStatus').textContent='PDF preview unavailable: '+error.message;
      }
    } finally {
      previewRunning=false;
      if(seq===sequence) container.setAttribute('aria-busy','false');
      if(previewPending) {previewPending=false;preview();}
    }
  }
  const label = key => key.replace(/([a-z])([A-Z])/g,'$1 $2').replace(/^./,c=>c.toUpperCase());
  function empty(value) {if(Array.isArray(value)) return [];if(value && typeof value==='object') return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,empty(v)]));return typeof value==='number'?0:typeof value==='boolean'?false:'';}
  function fields(parent,value,set,path) {
    if(Array.isArray(value)) {
      const box=el('div',undefined,'draft-array');
      value.forEach((item,index)=>{
        const group=el('fieldset');group.append(el('legend',`${label(path.at(-1))} ${index+1}`));
        fields(group,item,next=>{value[index]=next;},path.concat(index));
        const actions=el('div',undefined,'draft-item-actions');
        const move=direction=>{const next=index+direction;[value[index],value[next]]=[value[next],value[index]];changed();render();};
        const up=button('Move up',()=>move(-1));up.disabled=index===0;
        const down=button('Move down',()=>move(1));down.disabled=index===value.length-1;
        actions.append(up,down,button('Remove',()=>{value.splice(index,1);changed();render();}));group.append(actions);box.append(group);
      });
      box.append(button('+ Add '+label(path.at(-1)),()=>{
        const templates={work:{name:'',position:'',startDate:'',summary:'',highlights:[]},education:{institution:'',studyType:'',area:''},skills:{name:'',keywords:[]},projects:{name:'',description:'',highlights:[]},profiles:{network:'',username:'',url:''}};
        value.push(value.length?empty(value[0]):structuredClone(templates[path.at(-1)] || ''));changed();render();
      }));parent.append(box);
    } else if(value && typeof value==='object') {
      for(const [key,item] of Object.entries(value)) {
        if(item && typeof item==='object') {const details=el('details');details.open=true;details.append(el('summary',label(key)));fields(details,item,next=>{value[key]=next;},path.concat(key));parent.append(details);}
        else fields(parent,item,next=>{value[key]=next;},path.concat(key));
      }
    } else {
      const name=path.map(x=>typeof x==='number'?x+1:label(x)).join(' / ');
      const field=el('label',name), input=el(typeof value==='string' && (value.length>100 || ['summary','description','highlights','reference'].some(x=>path.includes(x)))?'textarea':'input');
      input.value=value ?? '';input.setAttribute('aria-label',name);
      if(typeof value==='boolean') {input.type='checkbox';input.checked=value;}
      else if(typeof value==='number') input.type='number';
      input.oninput=()=>{set(typeof value==='boolean'?input.checked:typeof value==='number'?Number(input.value):input.value);changed();};
      field.append(input);parent.append(field);
    }
  }
  function render() {
    const editor=$('reviewEditor');editor.replaceChildren();
    $('reviewResume').setAttribute('aria-pressed',String(mode==='resume'));$('reviewLetter').setAttribute('aria-pressed',String(mode==='coverLetter'));
    if(mode==='coverLetter') {
      const field=el('label','Cover letter text'),input=el('textarea');input.id='reviewLetterText';input.setAttribute('aria-label','Cover letter text');input.value=draft.coverLetter;input.oninput=()=>{draft.coverLetter=input.value;changed();};field.append(input);editor.append(field);
    } else {
      fields(editor,draft.resume,next=>{draft.resume=next;},[]);

    }
  }
  window.openApplicationReview=async selected=>{
    if(busy) return;
    job=selected;dirty=false;draft=null;mode='resume';++sequence;clearTimeout(timer);
    $('reviewEditor').replaceChildren();$('reviewPreview').replaceChildren();$('reviewJob').textContent=job.title+' · '+job.company;
    $('reviewDialog').showModal();setBusy(true);message('Loading application drafts…');
    try {const response=await fetch(`/api/jobs/${job.id}/drafts/${job.generation.runId}`);const data=await response.json();if(!response.ok)throw Error(data.error);draft=data;render();message('Review and edit both documents. Changes apply only to this application.');preview();}
    catch(error){message(error.message,true);}
    finally{setBusy(false);if(!draft){$('reviewSave').disabled=true;$('reviewDownload').disabled=true;}}
  };
  function close() {if(busy)return;if(dirty && !confirm('Discard unsaved document edits?'))return;dirty=false;++sequence;clearTimeout(timer);$('reviewDialog').close();}
  $('reviewClose').onclick=close;$('reviewDialog').oncancel=event=>{event.preventDefault();close();};
  for(const [id,next] of [['reviewResume','resume'],['reviewLetter','coverLetter']]) $(id).onclick=()=>{if(!draft)return;mode=next;++sequence;clearTimeout(timer);$('reviewPreview').replaceChildren();render();preview();};
  async function save() {
    const response=await request('save-drafts');draft=await response.json();dirty=false;
    const scroll=$('reviewEditor').scrollTop;render();$('reviewEditor').scrollTop=scroll;preview();
  }
  $('reviewSave').onclick=async()=>{
    if(busy || !draft)return;setBusy(true);clearTimeout(timer);++sequence;
    try{await save();message('Drafts saved.');}catch(error){message(error.message,true);}finally{setBusy(false);}
  };
  $('reviewDownload').onclick=async()=>{
    if(busy || !draft)return;setBusy(true);clearTimeout(timer);++sequence;message('Saving edits and rendering PDFs…');
    try {
      await save();
      const response=await request('download-application',{runId:draft.runId,revision:draft.revision});
      const blob=await response.blob(),url=URL.createObjectURL(blob),link=el('a');
      link.href=url;link.download=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || 'application.zip';link.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
      message('Downloaded application ZIP with your saved edits.');
    }catch(error){message(error.message+' Your saved drafts are retained.',true);}finally{setBusy(false);}
  };
  window.addEventListener('beforeunload',event=>{if(dirty || busy){event.preventDefault();event.returnValue='';}});
})();
