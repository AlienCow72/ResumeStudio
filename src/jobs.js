(() => {
  const $ = id => document.getElementById(id);
  const stages = {applying: 'Applying', waiting: 'Waiting on response', interview: 'Interview'};
  const hints = {applying: 'Prepare your next application', waiting: 'Applications sent. Stay in the loop.', interview: 'Make the next conversation count'};
  let jobs = [], editing = null, changed = false, saving = false, loading = false;
  const pending = new Set();
  const generationActive = state => ['queued','extracting','writing','rendering','cancelling'].includes(state?.status);
  const element = (tag, className, text) => {const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node;};
  function button(text, action, className) {const node = element('button', className, text); node.type = 'button'; node.onclick = action; return node;}
  function status(text, error = false) {$('status').textContent = text; $('status').className = error ? 'error' : '';}
  const displayDate = value => new Date(value.length === 10 ? value + 'T12:00:00' : value).toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'});
  const today = () => {const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  async function api(path, payload) {
    const response = await fetch(path, payload ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)} : {});
    const result = await response.json();
    if (!response.ok) {const error = new Error(result.error || 'Unable to save this job.'); error.duplicates = result.duplicates; throw error;}
    return result;
  }
  function replace(job) {jobs = [job, ...jobs.filter(item => item.id !== job.id)].sort((a,b) => b.createdAt.localeCompare(a.createdAt)); render();}
  function render() {
    const focusLabel = document.activeElement?.getAttribute('aria-label');
    const query = $('search').value.trim().toLowerCase();
    const filtered = jobs.filter(job => [job.company, job.title, job.notes].some(value => value.toLowerCase().includes(query)));
    $('jobCount').textContent = query ? `${filtered.length} of ${jobs.length} applications` : `${jobs.length} application${jobs.length === 1 ? '' : 's'}`;
    $('board').replaceChildren();
    for (const [stage, label] of Object.entries(stages)) {
      const column = element('section', 'column ' + stage), heading = element('div', 'column-header');
      const title = element('h2', '', label); title.id = 'stage-' + stage; column.setAttribute('aria-labelledby', title.id);
      const group = filtered.filter(job => job.stage === stage);
      heading.append(element('span', 'stage-dot'), title, element('span', 'stage-count', group.length));
      column.append(heading, element('p', 'column-hint', hints[stage]));
      for (const job of group) column.append(card(job));
      if (!group.length) {
        const empty = element('div', 'empty-column');
        empty.append(element('strong', '', query ? 'No matching applications' : stage === 'applying' ? 'Your next opportunity starts here' : stage === 'waiting' ? 'Room for your first application' : 'Conversations ahead'));
        empty.append(document.createTextNode(query ? 'Try another company or role.' : stage === 'applying' ? 'Save a posting you want to pursue.' : stage === 'waiting' ? 'Mark a job applied once you’ve sent it.' : 'Move a job here when an interview is arranged.'));
        if (!query && stage === 'applying') empty.append(button('＋ Add a job', () => open()));
        column.append(empty);
      }
      $('board').append(column);
    }
    if (focusLabel) [...document.querySelectorAll('.stage-field select')].find(node => node.getAttribute('aria-label') === focusLabel)?.focus();
  }
  function card(job) {
    const article = element('article', 'job-card');
    article.append(element('p', 'company', job.company));
    const heading = element('h3'); heading.style.margin = '0'; heading.append(button(job.title, () => open(job), 'job-title')); article.append(heading);
    article.append(element('p', 'job-date', job.appliedOn ? 'Applied ' + displayDate(job.appliedOn) : 'Added ' + displayDate(job.createdAt)));
    if (job.notes) article.append(element('p', 'job-note', job.notes));
    const footer = element('div', 'card-footer'), link = element('a', 'posting-link', 'View posting ↗');
    link.href = job.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
    footer.append(link, button(job.stage === 'applying' ? 'Mark applied' : 'View details', () => job.stage === 'applying' ? setStage(job, 'waiting', true) : open(job)));
    article.append(footer);
    const label = element('label', 'stage-field', 'Stage'), select = element('select');
    select.setAttribute('aria-label', 'Stage for ' + job.title + ' at ' + job.company);
    for (const [value, text] of Object.entries(stages)) {const option = element('option', '', text); option.value = value; select.append(option);}
    select.value = job.stage; select.onchange = () => setStage(job, select.value);
    label.append(select); article.append(label);
    article.append(generationPanel(job));
    if (pending.has(job.id)) {article.setAttribute('aria-busy', 'true'); article.querySelectorAll('button,select').forEach(control => control.disabled = true);}
    return article;
  }
  async function load(silent = false) {
    if (loading || pending.size) return;
    loading = true; $('refresh').disabled = true;
    try {const result = await api('/api/jobs'); const differs = JSON.stringify(jobs) !== JSON.stringify(result.jobs); jobs = result.jobs; if (differs || !silent) render(); if (!silent) status(jobs.length ? 'All applications saved locally.' : 'Ready when you are. Add your first job to get started.'); if (editing && $('jobDialog').open && differs) detailGeneration(jobs.find(job => job.id === editing.id) || editing);}
    catch (error) {if (!silent) status('Could not load applications. ' + error.message, true);}
    finally {loading = false; $('refresh').disabled = false;}
  }
  async function setStage(job, stage, markApplied = false) {
    if (pending.has(job.id)) return;
    pending.add(job.id); render();
    try {
      const update = {stage};
      if ((markApplied || stage === 'waiting') && !job.appliedOn) update.appliedOn = today();
      const saved = await api('/api/jobs/' + job.id, {job: update, revision: job.revision});
      replace(saved); status(`${job.company} moved to ${stages[stage]}.`);
    } catch (error) {status(error.message, true);}
    finally {pending.delete(job.id); render(); const control = [...document.querySelectorAll('.stage-field select')].find(node => node.getAttribute('aria-label') === 'Stage for ' + job.title + ' at ' + job.company); control?.focus();}
  }
  function open(job = null) {
    editing = job; changed = false; $('jobForm').reset(); $('duplicates').replaceChildren(); $('duplicates').hidden = true; $('formError').textContent = '';
    $('dialogTitle').textContent = job ? 'Application details' : 'Add an opportunity';
    $('formIntro').textContent = job ? 'Update details, generate documents, and download your application files.' : 'Add a posting link. We’ll extract it and prepare your application documents.';
    $('generationNotice').hidden = !!job; $('submitJob').textContent = job ? 'Save job' : 'Save & generate';
    $('postingTextSection').open = job?.generation?.status === 'needs_input';
    $('postingText').value = ''; detailGeneration(job);
    for (const [key, id] of Object.entries({url:'jobUrl',company:'jobCompany',title:'jobTitle',stage:'jobStage',appliedOn:'jobApplied',notes:'jobNotes'})) $(id).value = job?.[key] || (key === 'stage' ? 'applying' : '');
    $('historySection').hidden = !job; $('historySection').open = false; $('history').replaceChildren();
    if (job) for (const event of job.history) $('history').append(element('li', '', `${displayDate(event.at)} · ${event.from ? stages[event.from] + ' → ' : 'Added to '}${stages[event.to]}`));
    if (!$('jobDialog').open) $('jobDialog').showModal();
    $('jobUrl').focus();
  }
  function close() {if (saving) return; if (changed && !confirm('Discard unsaved job details?')) return; changed = false; $('jobDialog').close();}
  $('jobForm').addEventListener('input', () => {changed = true;});
  $('jobUrl').addEventListener('input', () => {$('duplicates').replaceChildren(); $('duplicates').hidden = true;});
  $('jobForm').onsubmit = async event => {
    event.preventDefault(); if (saving) return;
    const job = Object.fromEntries(new FormData($('jobForm'))); delete job.allowDuplicate;
    if (job.stage === 'waiting' && !job.appliedOn && editing?.stage !== 'waiting') job.appliedOn = today();
    saving = true; $('submitJob').disabled = true; $('submitJob').textContent = 'Saving…'; $('formError').textContent = '';
    // Keep the submitted snapshot and visible fields in sync while the request runs.
    $('jobForm').querySelectorAll('input,textarea,select').forEach(node => node.disabled = true);
    try {
      const saved = await api('/api/jobs' + (editing ? '/' + editing.id : ''), {job, revision: editing?.revision, allowDuplicate: !!$('allowDuplicate')?.checked, sourceText: $('postingText').value});
      replace(saved); changed = false; $('jobDialog').close(); status('Saved ' + saved.title + ' at ' + saved.company + '.');
    } catch (error) {
      $('formError').textContent = error.message;
      if (error.duplicates) {
        const box = $('duplicates'); box.replaceChildren(); box.hidden = false;
        box.append(element('p', '', 'Already on your board:'));
        for (const duplicate of error.duplicates) box.append(button(duplicate.company + ' · ' + duplicate.title, () => {if (!changed || confirm('Discard this draft and open the existing job?')) {const existing = jobs.find(job => job.id === duplicate.id); if (existing) open(existing); else {$('formError').textContent = 'Refresh the board to load this application.';}}}));
        const label = element('label'), checkbox = element('input'); checkbox.type = 'checkbox'; checkbox.id = 'allowDuplicate';
        label.append(checkbox, document.createTextNode('Add as a separate application to this posting')); box.append(label);
      }
    } finally {saving = false; $('submitJob').disabled = false; $('submitJob').textContent = editing ? 'Save job' : 'Save & generate'; $('jobForm').querySelectorAll('input,textarea,select').forEach(node => node.disabled = false);}
  };
  $('addJob').onclick = () => open(); $('closeDialog').onclick = close; $('cancelDialog').onclick = close;
  $('jobDialog').addEventListener('cancel', event => {event.preventDefault(); close();});
  $('search').oninput = render; $('refresh').onclick = () => load();
  window.addEventListener('beforeunload', event => {if (changed || saving || pending.size) {event.preventDefault(); event.returnValue = '';}});
  load();
  setInterval(() => {if (!saving && jobs.some(job => generationActive(job.generation))) load(true);}, 2000);

  function generationPanel(job, detail = false) {
    const state = job.generation || {status:'not_started'}, panel = element('div', 'generation-panel');
    const active = generationActive(state);
    const labels = {not_started:'Prepare application documents',queued:'Queued',extracting:'1 / 2 · Job description',writing:'2 / 2 · Writing drafts',rendering:'Finishing previous run',ready:'Drafts ready for review',needs_input:'Posting text needed',failed:'Generation needs attention',cancelled:'Generation cancelled',interrupted:'Generation interrupted',cancelling:'Cancelling…'};
    panel.append(element('p', 'generation-heading ' + (active ? 'running' : ''), labels[state.status] || state.status));
    if (state.message) panel.append(element('p', 'generation-message', state.message));
    if (state.sourceChanged) panel.append(element('p', 'error', 'These files use the previous posting link. Generate a new set for this link.'));
    if (state.status === 'ready') panel.append(button('Review & edit documents', () => window.openApplicationReview(job), 'primary'));
    if (detail && state.reviewNotes) {const review = element('details'); review.append(element('summary', '', 'Tailoring notes & qualification gaps'), element('p', 'review-notes', state.reviewNotes)); panel.append(review);}
    const actions = element('div', 'generation-actions');
    if (active) actions.append(button('Cancel generation', () => runGeneration(job, 'cancel')));
    else {
      const label = state.status === 'ready' ? 'Generate new set' : state.status === 'needs_input' && !detail ? 'Paste posting text' : state.status === 'not_started' ? 'Generate documents' : 'Retry generation';
      actions.append(button(label, () => state.status === 'needs_input' && !detail ? open(job) : runGeneration(job, 'generate', detail, state.status === 'ready')));
    }
    panel.append(actions); return panel;
  }
  function detailGeneration(job) {
    $('detailGeneration').hidden = !job; $('detailGeneration').replaceChildren();
    if (job) $('detailGeneration').append(generationPanel(job, true));
  }
  async function runGeneration(job, action, detail = false, regenerate = false) {
    if (pending.has(job.id) || saving) return;
    if (detail && $('jobUrl').value.trim() !== job.url) {$('formError').textContent = 'Save the new posting link before generating documents.'; return;}
    const sourceText = detail ? $('postingText').value : '';
    pending.add(job.id);
    try {
      const generation = await api(`/api/jobs/${job.id}/${action}`, {sourceText, regenerate});
      const latest = jobs.find(item => item.id === job.id) || job;
      replace({...latest, generation});
      if ($('jobDialog').open && editing?.id === job.id) {detailGeneration({...latest, generation}); $('formError').textContent = '';}
      status(action === 'cancel' ? 'Cancellation requested.' : 'Generation started. Drafts will be available for review when ready.');
    } catch (error) {if (detail) $('formError').textContent = error.message; else status(error.message, true);}
    finally {pending.delete(job.id); render();}
  }
})();
