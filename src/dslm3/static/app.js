const $ = s => document.querySelector(s),
    $$ = s => [...document.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
} [c]));
const pretty = v => esc(JSON.stringify(v, null, 2));
const badge = (v, label = v) => `<span class="badge ${esc(v)}">${esc(label)}</span>`;
const short = v => String(v || '').slice(0, 19) + '…';
const empty = t => `<div class="empty">${esc(t)}</div>`;
const button = (label, action, extra = '', cls = '') => `<button class="${cls}" data-action="${action}" ${extra}>${label}</button>`;
const download = (path, label = 'Scarica') => `<a href="/api/download?path=${encodeURIComponent(path)}" download>${label}</a>`;
const table = (headers, rows) => `<div class="table-wrap"><table><thead><tr>${headers.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
const titles = {
    overview: 'Panoramica',
    sources: 'Fonti ed evidenze',
    review: 'Proposte e review',
    ai: 'Interpretazione AI',
    temporal: 'Temporalità',
    knowledge: 'Conoscenza consolidata',
    exports: 'Output e confronto',
    settings: 'Impostazioni e attività'
};
let token = '',
    data = {},
    page = 'overview',
    busy = false,
    selected = new Set(),
    filter = 'pending';
const errorText = e => e?.message || String(e);

function toast(text) {
    $('#toast').textContent = text;
    $('#toast').hidden = false;
    setTimeout(() => $('#toast').hidden = true, 6500)
}
async function api(path, options = {}) {
    options.headers = {
        ...(options.headers || {}),
        'X-DSLM3-Token': token
    };
    if (options.body && !(options.body instanceof FormData)) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(options.body)
    }
    const r = await fetch('/api/' + path, options);
    const d = await r.json();
    if (!r.ok) throw new Error(d.message || d.detail || r.statusText);
    return d
}

function show(title, html) {
    $('#detail-title').textContent = title;
    $('#detail-body').innerHTML = html;
    if (!$('#detail').open) $('#detail').showModal()
}
async function action(operation, args = {}) {
    if (busy) {
        toast('È già in corso un’operazione.');
        return
    }
    busy = true;
    $('#job-banner').hidden = false;
    $('#job-banner').textContent = 'Elaborazione in corso…';
    try {
        const j = await api('action', {
            method: 'POST',
            body: {
                operation,
                args
            }
        });
        let result;
        for (;;) {
            await new Promise(r => setTimeout(r, 500));
            result = await api('jobs/' + j.job_id);
            if (!['queued', 'running'].includes(result.status)) break;
            $('#job-banner').textContent = `${operation.replaceAll('_',' ')} · in elaborazione`;
        }
        if (result.status === 'error') throw new Error(result.error.message);
        toast(result.status === 'partial' ? 'Operazione conclusa con risultati parziali: consulta l’attività.' : 'Operazione completata.');
        await refresh();
        return result.result
    } catch (e) {
        toast(errorText(e));
        show('Operazione non completata', `<p>${esc(errorText(e))}</p><p class="muted">Lo stato e il dettaglio sono disponibili in Impostazioni e attività.</p>`)
    } finally {
        busy = false;
        $('#job-banner').hidden = true
    }
}
async function refresh() {
    const names = ['status', 'sources', 'candidates', 'knowledge', 'plans', 'packages', 'snapshots', 'temporal', 'config', 'runs', 'workspaces'];
    const values = await Promise.all(names.map(x => api(x)));
    data = Object.fromEntries(names.map((x, i) => [x, values[i]]));
    render()
}

function route() {
    page = location.hash.slice(1) || 'overview';
    if (!titles[page]) page = 'overview';
    selected.clear();
    render()
}

function render() {
    if (!data.status) return;
    $('#page-title').textContent = titles[page];
    $$('nav a').forEach(a => a.classList.toggle('active', a.dataset.page === page));
    $('#content').innerHTML = views[page]();
    renderWorkspaceControls();
    decoratePage();
    bindFilters()
}

function formField(id, label, value = '', type = 'text') {
    return `<label for="${id}">${label}</label><input id="${id}" type="${type}" value="${esc(value)}">`
}

function prepareNavigation() {
    const nav = $('nav'),
        settings = $('nav a[data-page=settings]');
    if (!nav || !settings) return;
    settings.innerHTML = '<b>00</b> Impostazioni';
    nav.insertBefore(settings, $('nav a[data-page=sources]'));
    const labels = {
        sources: '<b>01</b> Fonti ed evidenze',
        review: '<b>02</b> Review + consolida',
        ai: '<b>03</b> AI (opzionale)',
        temporal: '<b>04</b> Temporalità (opzionale)',
        knowledge: '<b>05</b> Conoscenza',
        exports: '<b>06</b> Output e confronto'
    };
    for (const [name, html] of Object.entries(labels)) {
        const link = $(`nav a[data-page=${name}]`);
        if (link) link.innerHTML = html
    }
}

function renderWorkspaceControls() {
    if (!data.workspaces) return;
    let box = $('#workspace-switcher');
    if (!box) {
        $('.aside-bottom').insertAdjacentHTML('beforebegin', `<div id="workspace-switcher" class="workspace-switcher"><label for="workspace-select">Workspace attivo</label><select id="workspace-select"></select>${button('Gestisci workspace','workspace-manage')}</div>`);
        box = $('#workspace-switcher')
    }
    const select = $('#workspace-select');
    select.innerHTML = data.workspaces.items.map(w => `<option value="${esc(w.id)}" ${w.id===data.workspaces.active_id?'selected':''}>${esc(w.name)}${w.available?'':' · non disponibile'}</option>`).join('');
    select.onchange = async () => {
        if (select.value === data.workspaces.active_id) return;
        const result = await workspaceAction('switch', {
            id: select.value
        });
        if (result) location.hash = 'overview'
    };
    const active = data.workspaces.items.find(w => w.id === data.workspaces.active_id);
    $('#workspace-path').textContent = active?.path || data.status.workspace
}

function decoratePage() {
    if (page !== 'overview') return;
    const pipeline = $('[data-action=pipeline]');
    if (pipeline) pipeline.textContent = 'Pipeline rapida';
    const flow = $('.flow');
    if (flow) flow.insertAdjacentHTML('afterend', `<div class="hint"><strong>Il passaggio 02 è il gate ricorrente.</strong> Dopo l’AI (03) e dopo la temporalità (04) torna sempre a <a href="#review">Review + consolida</a>: decisione → merge → riconcilia. La pipeline rapida comprime parsing, derivazione, policy automatiche, merge e riconciliazione; per un test leggibile usa i passaggi espliciti.</div>`)
}

async function workspaceAction(operation, args = {}) {
    if (busy) {
        toast('È già in corso un’operazione.');
        return
    }
    busy = true;
    $('#job-banner').hidden = false;
    $('#job-banner').textContent = 'Cambio workspace…';
    try {
        const result = await api('workspaces', {
            method: 'POST',
            body: {
                operation,
                ...args
            }
        });
        toast('Workspace aggiornato.');
        await refresh();
        return result
    } catch (e) {
        toast(errorText(e));
        show('Workspace non aggiornato', `<p>${esc(errorText(e))}</p>`)
    } finally {
        busy = false;
        $('#job-banner').hidden = true
    }
}
const views = {
    overview() {
        const c = data.status.counts;
        const stages = [
            ['00', 'Configura', 'Identità del revisore, policy, dialetto SQL, esclusioni e budget.'],
            ['01', 'Acquisisci e analizza', 'Importa le fonti, analizzale e genera candidati deterministici.'],
            ['02', 'Review + consolida', 'Gate ricorrente: decidi, esegui merge e poi riconcilia.'],
            ['03 → 02', 'AI opzionale', 'Prepara package, importa JSONL e torna alla review.'],
            ['04 → 02', 'Temporalità opzionale', 'Estrai/proponi intervalli e torna alla review.'],
            ['05 → 06', 'Verifica ed esporta', 'Controlla provenienza/conflitti, poi crea snapshot e grafi.']
        ];
        return `<p class="lead">Segui ogni informazione dal documento originale alla conoscenza accettata. Ogni passaggio conserva la propria evidenza.</p><div class="stats">${[['Fonti attive',data.sources.filter(s=>s.status==='active').length,'File con revisioni verificabili'],['Evidenze',c.evidence,'Testo e strutture estratte'],['In attesa',c.review_states.pending||0,'Proposte ancora da valutare'],['Consolidati',c.effective_objects,'Fatti, relazioni e intervalli effettivi']].map(([label,n,note])=>`<div class="stat"><div class="number">${n}</div><div class="label">${label}</div><div class="note">${note}</div></div>`).join('')}</div><div class="grid"><div><div class="card"><div class="card-head"><h2>Il percorso dei dati</h2>${badge('info','6 passaggi')}</div><div class="flow">${stages.map(([n,t,p])=>`<div class="flow-step"><span>${n}</span><strong>${t}</strong><p>${p}</p></div>`).join('')}</div><div class="actions">${button('Elabora il corpus','pipeline','','primary')}<a href="#sources">Gestisci le fonti →</a></div><p class="small muted">Esegue parsing, derivazione e consolidamento. La review automatica usa solo le policy che hai abilitato; le altre proposte restano in attesa.</p></div>${c.confirmed_unmerged?`<div class="hint warn"><strong>${c.confirmed_unmerged} proposte confermate attendono il merge.</strong> ${button('Consolida ora','merge')}</div>`:''}${c.open_reconciliations?`<div class="hint warn">${c.open_reconciliations} revisioni della conoscenza da riconciliare. ${button('Riconcilia','reconcile')}</div>`:''}</div><div><div class="card"><div class="eyebrow">LABORATORIO VEGA</div><h2>Un caso completo, sei fonti</h2><p class="muted">Schema Oracle, procedura e trigger, Forms, log, manuale e matrice Excel. Un percorso per verificare l’intera applicazione.</p>${button('Carica il laboratorio','vega')}<div class="hint">Il manuale indica P1 = 30 minuti. La matrice indica P1 = 1 ora. L’interpretazione deve conservare entrambe le fonti e rendere visibile la discordanza.</div></div><div class="card"><h2>Stato della review</h2><p>${data.config.config.automatic_policies.length?`${data.config.config.automatic_policies.length} policy tecniche abilitate.`:'Review manuale: nessuna policy automatica abilitata.'}</p><a href="#settings">Configura il profilo →</a></div></div></div>`
    },
    sources() {
        return `<p class="lead">Aggiungi file o un’intera cartella. Apri una fonte per vedere l’evidenza estratta e il punto preciso da cui proviene.</p><div class="card"><div class="split"><label class="file-drop">Aggiungi file<input id="upload-files" type="file" multiple></label><label class="file-drop">Importa una cartella<input id="upload-folder" type="file" webkitdirectory multiple></label></div><div class="actions">${button('Analizza le fonti','parse','','primary')}${button('Genera proposte','derive')}${button('Rileggi il corpus locale','scan')}</div><details><summary>Importa da un percorso locale</summary>${formField('scan-directory','Percorso assoluto della cartella sul computer dove gira DSLM3')}<div class="actions">${button('Scansiona cartella','scan-directory')}</div></details></div>${data.sources.length?table(['Fonte','Revisione','Analisi','Evidenze',''],data.sources.map(s=>`<tr><td><div class="source-name">${esc(s.path)}</div><div class="sub">${(s.size/1024).toFixed(1)} KB · ${esc(s.status)}</div></td><td class="mono">${esc(short(s.current_revision))}</td><td>${badge(s.parse?.status||'pending',s.parse?.status||'Da analizzare')}<div class="sub">${esc(s.parse?.parser||'')}</div></td><td>${s.parse?.evidence_count??'—'}</td><td>${button('Esplora','source-detail',`data-id="${s.current_revision}"`)}</td></tr>`)):empty('Non ci sono ancora fonti. Aggiungi file o carica Vega dalla panoramica.')}`
    },
    review() {
        const candidates = data.candidates.filter(c => c.leaf && c.current_parse && c.current_revision && c.source_status === 'active' && (filter === 'all' || c.state === filter));
        return `<p class="lead">La proposta è un’interpretazione verificabile. Leggi la citazione, decidi e poi esegui il merge per includerla nella conoscenza.</p><div class="toolbar"><select id="review-filter">${[['pending','In attesa'],['confirmed','Confermate'],['rejected','Rifiutate'],['all','Tutte le foglie correnti']].map(([v,l])=>`<option value="${v}" ${filter===v?'selected':''}>${l}</option>`).join('')}</select><input type="search" id="search-review" placeholder="Cerca entità, proprietà o testo…">${button('Applica policy abilitate','auto_review')}</div><div class="actions"><label class="inline"><input type="checkbox" id="select-all"> Seleziona visibili</label>${button('Conferma selezionate','review-confirm','','primary')}${button('Rifiuta selezionate','review-reject','','danger')}${button('Merge delle confermate','merge')}${button('Riconcilia','reconcile')}</div>${candidates.length?table(['','Proposta','Origine / tipo','Stato',''],candidates.map(c=>{const p=c.payload;const label=p.entity_name||p.source_entity||p.target_subject_id||p.subject;const value=p.property_name?`${p.property_name} = ${typeof p.property_value==='object'?JSON.stringify(p.property_value):p.property_value}`:p.relation_type?`${p.relation_type} → ${p.target_entity}`:p.normalized_start||p.question_text||p.record_type;return `<tr class="candidate-row" data-search="${esc(JSON.stringify(p).toLowerCase())}"><td><input type="checkbox" class="candidate-check" value="${c.id}"></td><td><div class="source-name">${esc(label)}</div><div class="sub">${esc(String(value).slice(0,180))}</div></td><td>${esc(c.rule||'Interpretazione / review')}<div class="sub">${esc(p.record_type)}</div></td><td>${badge(c.state)}<div class="sub">${c.materialized?'Merge eseguito':'Non consolidata'}</div></td><td>${button('Valuta','candidate-detail',`data-id="${c.id}"`)}</td></tr>`})):empty('Nessuna proposta con questo stato. Le fonti analizzate possono generare proposte dal passaggio 01.')}`
    },
    ai() {
        return `<p class="lead">Esporta evidenze e istruzioni per un modello esterno. Importa le risposte JSONL come proposte, poi valuta e consolida.</p><div class="grid equal"><div class="card"><h2>Estrazione tecnica</h2><p class="muted">Cerca strutture ancora da interpretare. Esclude l’evidenza tecnica già confermata.</p>${button('Calcola piano tecnico','select',`data-route="technical_extraction"`)}</div><div class="card"><h2>Interpretazione di dominio</h2><p class="muted">Collega manuali, dati e codice. Mantiene anche evidenze tecniche già confermate per fornire contesto.</p>${button('Calcola piano di dominio','select',`data-route="domain_interpretation"`)}</div></div><div class="card"><div class="card-head"><h2>Piani di selezione</h2>${button('Prepara entrambe le route','package_all','','primary')}</div>${data.plans.length?table(['Piano','Route','Incluse','Dimensione',''],data.plans.slice(0,12).map(p=>`<tr><td class="mono">${esc(short(p.id))}</td><td>${esc(p.route)}</td><td>${p.selected_count}</td><td>${p.selected_chars.toLocaleString('it')} caratteri</td><td>${button('Motivi','plan-detail',`data-id="${p.id}"`)} ${button('Crea package','package',`data-id="${p.id}"`)}</td></tr>`)):empty('Calcola un piano per vedere quali evidenze sono incluse e perché.')}</div><div class="card-head"><h2>Pacchetti e risposte</h2>${button('Scarica selezionati','download-packages')}</div><div class="package-grid">${data.packages.map(p=>`<div class="card"><label class="checkrow"><input type="checkbox" class="package-check" value="${esc(p.archive)}"><strong>${esc(p.route)}</strong>${badge(p.stale?'partial':'success',p.stale?'Fonte cambiata':'Pronto')}</label><p class="mono">${esc(p.id)}</p><p class="muted small">${p.evidence_ids.length} evidenze · ${download(p.archive,'Package ZIP')}</p><label class="file-drop small">Importa una o più risposte per questo package<input type="file" class="ai-response" data-id="${p.id}" accept=".jsonl,.ndjson,.txt" multiple></label></div>`).join('')||empty('Nessun package ancora creato.')}</div><div class="hint">Una risposta importata resta in attesa. Il percorso si chiude in <a href="#review">Proposte e review</a>: conferma → merge → conoscenza.</div>`
    },
    temporal() {
        const raw = data.temporal.raw;
        return `<p class="lead">Una data trovata nel file è un segnale. Un intervallo di validità nasce da una proposta valutata, con precisione e timezone esplicite.</p><div class="actions">${button('Estrai segnali temporali','temporal_extract','','primary')}</div><div class="grid equal"><div class="card"><h2>Consolida i segnali di una fonte</h2><label>Revisione</label><select id="temporal-revision">${data.sources.map(s=>`<option value="${s.current_revision}">${esc(s.path)}</option>`).join('')}</select><div class="actions">${button('Confronta e proponi intervalli','temporal-consolidate')}</div><p class="small muted">Date indipendenti concordi e copie correlate vengono distinte. Le proposte rimangono in attesa.</p></div><div class="card"><h2>Propagazione esplicita</h2><label>Soggetti di origine (tipo:ID, uno per riga)</label><textarea id="prop-sources" placeholder="source_revision:REV_…"></textarea><div class="split"><div><label>Tipo destinazione</label><select id="prop-type"><option>fact</option><option>relation</option><option>source_revision</option></select></div><div><label>Policy</label><select id="prop-policy"><option>explicit_copy</option><option>intersection</option><option>aggregation</option><option>conflict</option></select></div></div>${formField('prop-target','ID destinazione')}<div class="actions">${button('Crea proposte','temporal-propagate')}</div></div></div><div class="card"><h2>Segnali raccolti <span class="muted">${raw.length}</span></h2>${raw.length?table(['Valore','Natura','Precisione / timezone','Fonte',''],raw.slice(0,500).map(r=>`<tr><td class="mono">${esc(r.payload.raw_value)}</td><td>${esc(r.payload.date_role)}<div class="sub">${esc(r.payload.source_format)}</div></td><td>${esc(r.payload.precision||'Non risolta')}<div class="sub">${esc(r.payload.timezone_status||'')}</div></td><td class="mono">${esc(short(r.revision_id))}</td><td>${button('Dettagli','temporal-detail',`data-id="${r.id}"`)}</td></tr>`)):empty('Estrai i segnali dopo aver acquisito le fonti.')}</div><details><summary>Gruppi e conflitti temporali (${data.temporal.groups.length})</summary><pre>${pretty(data.temporal.groups)}</pre></details>`
    },
    knowledge() {
        const objs = data.knowledge.objects,
            conflicts = data.knowledge.conflicts;
        return `<p class="lead">Questa vista contiene solo oggetti con almeno un supporto corrente confermato e consolidato. Puoi risalire alle fonti di ogni affermazione.</p>${conflicts.length?`<div class="card"><h2>Conflitti da interpretare ${badge('partial',conflicts.length)}</h2>${conflicts.map(c=>`<div class="hint warn"><strong>${esc(c.entity)} · ${esc(c.property)}</strong><p>${esc(JSON.stringify(c.left_value))} ↔ ${esc(JSON.stringify(c.right_value))}</p><span class="small">${esc(c.reason)}</span></div>`).join('')}</div>`:`<div class="hint">Nessun conflitto fra i fatti attualmente consolidati.</div>`}<div class="toolbar"><input id="search-knowledge" type="search" placeholder="Cerca nella conoscenza…">${button('Crea snapshot DSL','snapshot','','primary')}</div>${objs.length?table(['Oggetto','Contenuto','Supporti',''],objs.map(o=>`<tr class="knowledge-row" data-search="${esc(JSON.stringify(o.payload).toLowerCase())}"><td>${badge('info',o.kind)}<div class="sub mono">${esc(o.id)}</div></td><td><div class="source-name">${esc(o.payload.entity_name||o.payload.source_entity||o.payload.target_subject_id)}</div><div class="sub">${esc(o.payload.property_name?`${o.payload.property_name} = ${JSON.stringify(o.payload.property_value)}`:o.payload.relation_type?`${o.payload.relation_type} → ${o.payload.target_entity}`:`${o.payload.normalized_start||'…'} → ${o.payload.normalized_end||'…'}`)}</div></td><td>${o.supports.length}</td><td>${button('Traccia','object-detail',`data-id="${o.id}"`)}</td></tr>`)):empty('Nessuna conoscenza consolidata. Conferma le proposte e completa il merge.')}<details><summary>Mappa delle relazioni</summary>${objs.filter(o=>o.kind==='relation').map(o=>`<div class="graph-list"><strong>${esc(o.payload.source_entity)}</strong><span class="relation">${esc(o.payload.relation_type)} →</span><strong>${esc(o.payload.target_entity)}</strong></div>`).join('')}</details>`
    },
    exports() {
        return `<p class="lead">Crea snapshot immutabili, confronta le versioni e scarica JSON, YAML, Markdown o un grafo GEXF con temporalità.</p><div class="card"><div class="toolbar"><label class="inline">Profilo <select id="schema-profile"><option value="2">2 · effettivo con temporalità</option><option value="1">1 · statico fisico</option></select></label>${button('Crea snapshot','snapshot-profile','','primary')}</div>${data.snapshots.length?table(['Snapshot','Profilo','Fatti / relazioni','Download','Grafo'],data.snapshots.map(s=>`<tr><td class="mono">${esc(s.id)}<div class="sub">${esc(s.created_at.slice(0,19))}</div></td><td>${s.schema_version}</td><td>${s.counts.facts} / ${s.counts.relations}</td><td>${['json','yaml','md'].map(e=>download(`artifacts/${s.id}/dsl.${e}`,e.toUpperCase())).join(' · ')}</td><td>${button('Statico','graph',`data-id="${s.id}"`)} ${s.schema_version===2?button('Dinamico','graph',`data-id="${s.id}" data-dynamic="true"`):''}</td></tr>`)):empty('Crea uno snapshot dopo aver consolidato la conoscenza.')}</div><div class="card"><h2>Confronta due snapshot</h2><div class="split"><div><label>Prima</label><select id="diff-before">${data.snapshots.map(s=>`<option>${s.id}</option>`).join('')}</select></div><div><label>Dopo</label><select id="diff-after">${data.snapshots.map(s=>`<option>${s.id}</option>`).join('')}</select></div></div><label class="inline"><input type="checkbox" id="cross-schema"> Consenti confronto fra profili diversi</label><div class="actions">${button('Calcola differenze','diff')}</div></div>`
    },
    settings() {
        const c = data.config.config;
        return `<div class="grid equal"><div class="card"><h2>Review e identità</h2><p class="muted">La modalità manuale è il default. Il profilo conservativo abilita solo regole tecniche nominate; i candidati AI e temporali restano da valutare.</p>${formField('actor-id','Identificativo stabile del revisore',c.actor_id)}<div class="actions">${button('Salva identità','save-actor')}${button('Profilo conservativo','profile',`data-profile="conservative"`)}${button('Tutto manuale','profile',`data-profile="manual"`)}</div><details><summary>Policy abilitate (${c.automatic_policies.length})</summary><pre>${pretty(c.automatic_policies)}</pre></details></div><div class="card"><h2>Parser e limiti</h2><label>Dialetto SQL</label><select id="sql-dialect">${['auto',...data.config.catalog.ast_dialects,...data.config.catalog.lexical_only].map(d=>`<option ${d===c.sql_dialect?'selected':''}>${d}</option>`).join('')}</select><div class="split"><div>${formField('max-chars','Budget AI: caratteri',c.ai_max_chars,'number')}</div><div>${formField('max-evidence','Budget AI: evidenze',c.ai_max_evidence,'number')}</div></div><label>Esclusioni corpus (un pattern per riga)</label><textarea id="exclude">${esc(c.exclude.join('\n'))}</textarea><div class="actions">${button('Salva impostazioni','save-config')}</div><p class="small muted">Un dialetto riconosciuto non certifica la versione. DB2, Firebird, Informix e Sybase hanno riconoscimento lessicale: i costrutti non analizzabili restano evidenze con diagnostica.</p></div></div><div class="card"><div class="card-head"><h2>Registro delle operazioni</h2>${button('Apri log','logs')}</div>${data.runs.length?table(['Operazione','Stato','Avvio',''],data.runs.map(r=>`<tr><td>${esc(r.operation)}</td><td>${badge(r.status)}</td><td>${esc(r.created_at.slice(0,19))}</td><td>${button('Report','run-detail',`data-id="${r.id}"`)}</td></tr>`)):empty('Le operazioni eseguite saranno registrate qui.')}</div>`
    }
};

function bindFilters() {
    const rf = $('#review-filter');
    if (rf) rf.onchange = () => {
        filter = rf.value;
        selected.clear();
        render()
    };
    for (const [input, row] of [
            ['#search-review', '.candidate-row'],
            ['#search-knowledge', '.knowledge-row']
        ]) {
        const e = $(input);
        if (e) e.oninput = () => {
            const q = e.value.toLowerCase();
            $$(row).forEach(r => r.hidden = !r.dataset.search.includes(q))
        }
    }
    const selectAll = $('#select-all');
    if (selectAll) selectAll.onchange = () => $$('.candidate-row:not([hidden]) .candidate-check').forEach(c => {
        c.checked = selectAll.checked;
        c.checked ? selected.add(c.value) : selected.delete(c.value)
    });
    $$('.candidate-check').forEach(c => c.onchange = () => c.checked ? selected.add(c.value) : selected.delete(c.value));
    for (const id of ['#upload-files', '#upload-folder'])
        if ($(id)) $(id).onchange = async ev => {
            try {
                const files = [...ev.target.files],
                    f = new FormData();
                files.forEach(x => f.append('files', x));
                f.append('paths', JSON.stringify(files.map(x => x.webkitRelativePath || x.name)));
                const r = await api('upload', {
                    method: 'POST',
                    body: f
                });
                toast(`${r.files.length} file acquisiti.`);
                await refresh()
            } catch (e) {
                toast(errorText(e))
            }
        };
    $$('.ai-response').forEach(input => input.onchange = async () => {
        for (const f of input.files) await action('ai_import', {
            package_id: input.dataset.id,
            text: await f.text()
        })
    })
}
async function clickAction(a) {
    const op = a.dataset.action,
        id = a.dataset.id;
    if (op === 'workspace-manage') {
        const w = data.workspaces;
        show('Workspace', `<p class="muted">Ogni workspace conserva un registry, corpus, revisioni, review, package AI, snapshot e log indipendenti. Dimenticare una voce non cancella nessun file.</p><div class="item-list">${w.items.map(x=>`<div class="item"><div class="item-head"><strong>${esc(x.name)}</strong>${x.active?badge('success','Attivo'):badge(x.available?'info':'error',x.available?'Disponibile':'Non disponibile')}</div><p class="mono">${esc(x.path)}</p>${x.active?'':`<div class="actions">${button('Dimentica','workspace-forget',`data-id="${x.id}"`)}</div>`}</div>`).join('')}</div><div class="card"><h3>Crea o registra</h3>${formField('workspace-name','Nome visualizzato (opzionale)')}${formField('workspace-path-input','Percorso assoluto del workspace')}<div class="actions">${button('Crea nuovo e attiva','workspace-create','','primary')}${button('Registra esistente e attiva','workspace-register')}</div><p class="small muted">Crea nuovo accetta solo una directory assente o vuota. Registra esistente richiede project.json e registry.sqlite3.</p></div>`);
        return
    }
    if (op === 'workspace-create' || op === 'workspace-register') {
        const result = await workspaceAction(op === 'workspace-create' ? 'create' : 'register', {
            name: $('#workspace-name').value,
            path: $('#workspace-path-input').value,
            activate: true
        });
        if (result) {
            $('#detail').close();
            location.hash = 'overview'
        }
        return
    }
    if (op === 'workspace-forget') {
        const result = await workspaceAction('forget', {
            id
        });
        if (result) $('#detail').close();
        return
    }
    const simple = ['vega', 'pipeline', 'parse', 'derive', 'auto_review', 'merge', 'reconcile', 'scan', 'temporal_extract', 'package_all', 'snapshot'];
    if (simple.includes(op)) {
        await action(op);
        return
    }
    if (op === 'scan-directory') return action('scan', {
        directory: $('#scan-directory').value
    });
    if (op === 'source-detail') {
        const s = data.sources.find(s => s.current_revision === id);
        const es = await api('evidence?revision=' + id);
        show(s.path, `<p>${badge(s.parse?.status||'pending')} <span class="mono">${esc(id)}</span></p>${s.parse?.diagnostics?.length?`<pre>${pretty(s.parse.diagnostics)}</pre>`:''}<div class="item-list">${es.map(e=>`<details class="item"><summary>${esc(e.type)} · ${esc(e.kind)} · ${esc(e.locator.sheet_name||e.locator.line_start||'')}</summary><p class="mono">${esc(e.id)} · ${esc(JSON.stringify(e.locator))}</p><pre>${esc(e.text)}</pre><details><summary>Struttura riconosciuta</summary><pre>${pretty(e.data)}</pre></details></details>`).join('')||empty('Nessuna evidenza disponibile. Analizza la fonte.')} </div>${s.parse?`<details><summary>Report parser</summary><pre>${pretty(s.parse)}</pre>${s.parse.log?download(s.parse.log,'Log elaborazione'):''}</details>`:''}`);
        return
    }
    if (op === 'candidate-detail') {
        const c = data.candidates.find(c => c.id === id),
            p = c.payload;
        show('Valuta la proposta', `<p>${badge(c.state)} <span class="mono">${esc(id)}</span></p><pre>${pretty(Object.fromEntries(Object.entries(p).filter(([k])=>!['evidence_text'].includes(k))))}</pre><h3>Citazione a supporto</h3><pre>${esc(p.evidence_text)}</pre><label>Motivo della decisione</label><input id="review-reason" type="text"><div class="actions">${button('Conferma','review-one',`data-id="${id}" data-outcome="confirmed"`,'primary')}${button('Rifiuta','review-one',`data-id="${id}" data-outcome="rejected"`,'danger')}${button('Lascia in attesa','review-one',`data-id="${id}" data-outcome="pending"`)}</div><details><summary>Correggi creando una nuova versione</summary><textarea id="correction-json">${pretty(p)}</textarea><div class="actions">${button('Registra correzione','correct',`data-id="${id}"`)}</div></details>`);
        return
    }
    if (op === 'review-one') {
        const c = data.candidates.find(c => c.id === id);
        const result = await action('review', {
            candidate_id: id,
            outcome: a.dataset.outcome,
            reason: $('#review-reason').value,
            expected_head: c.decision_id
        });
        if (result) $('#detail').close();
        return
    }
    if (op === 'correct') {
        try {
            const p = JSON.parse($('#correction-json').value);
            const result = await action('correct', {
                candidate_id: id,
                payload: p,
                expected_head: data.candidates.find(c => c.id === id).decision_id
            });
            if (result) $('#detail').close()
        } catch (e) {
            toast(errorText(e))
        }
        return
    }
    if (op === 'review-confirm' || op === 'review-reject') {
        if (!selected.size) return toast('Seleziona almeno una proposta.');
        await action('review', {
            ids: [...selected],
            outcome: op === 'review-confirm' ? 'confirmed' : 'rejected'
        });
        selected.clear();
        return
    }
    if (op === 'select') return action('select', {
        route: a.dataset.route
    });
    if (op === 'package') return action('package', {
        selection_id: id
    });
    if (op === 'plan-detail') {
        const p = data.plans.find(p => p.id === id);
        show('Motivi della selezione', table(['Fonte / evidenza', 'Copertura', 'Esito', 'Motivo'], p.items.map(i => `<tr><td>${esc(i.path)}<div class="sub mono">${esc(i.evidence_id)}</div></td><td>${esc(i.coverage)}</td><td>${badge(i.outcome)}</td><td>${esc(i.reason_codes.join(', '))}</td></tr>`)));
        return
    }
    if (op === 'download-packages') {
        const chosen = $$('.package-check:checked');
        if (!chosen.length) return toast('Seleziona almeno un package.');
        for (const c of chosen) {
            const link = document.createElement('a');
            link.href = '/api/download?path=' + encodeURIComponent(c.value);
            link.download = '';
            document.body.appendChild(link);
            link.click();
            link.remove();
            await new Promise(r => setTimeout(r, 250))
        }
        return
    }
    if (op === 'temporal-consolidate') {
        const rev = $('#temporal-revision').value;
        return action('temporal_consolidate', {
            subject_type: 'source_revision',
            subject_id: rev
        })
    }
    if (op === 'temporal-propagate') return action('temporal_propagate', {
        sources: $('#prop-sources').value.split('\n').map(s => s.trim()).filter(Boolean),
        target_type: $('#prop-type').value,
        target_id: $('#prop-target').value,
        policy: $('#prop-policy').value
    });
    if (op === 'temporal-detail') {
        const r = data.temporal.raw.find(r => r.id === id);
        show('Segnale temporale', `<pre>${pretty(r)}</pre>`);
        return
    }
    if (op === 'object-detail') {
        const o = data.knowledge.objects.find(o => o.id === id);
        show('Provenienza della conoscenza', `<pre>${pretty(o.payload)}</pre>${o.supports.map(s=>`<div class="item"><p class="mono">${esc(s.candidate_id)} · ${esc(s.decision_id)}</p><p class="small">Revisione ${esc(s.candidate_payload.source_revision_id)}</p><pre>${esc(s.candidate_payload.evidence_text)}</pre>${button('Apri candidato','candidate-detail',`data-id="${s.candidate_id}"`)}</div>`).join('')}`);
        return
    }
    if (op === 'snapshot-profile') return action('snapshot', {
        schema_version: Number($('#schema-profile').value)
    });
    if (op === 'graph') {
        const r = await action('graph', {
            snapshot_id: id,
            dynamic: a.dataset.dynamic === 'true',
            mode: 'separate'
        });
        if (r) show('Grafo pronto', `<p>${r.files.map(f=>download(f,f.split('/').at(-1))).join('<br>')}</p><pre>${pretty(r)}</pre>`);
        return
    }
    if (op === 'diff') {
        const r = await action('diff', {
            before: $('#diff-before').value,
            after: $('#diff-after').value,
            cross_schema: $('#cross-schema').checked
        });
        if (r) show('Differenze fra snapshot', `<p>${r.count} cambiamenti. ${download(r.file,'Scarica il diff')}</p><pre>${pretty(r.changes)}</pre>`);
        return
    }
    if (op === 'profile') return action('config', {
        profile: a.dataset.profile,
        expected_hash: data.status.config_hash
    });
    if (op === 'save-actor') return action('config', {
        values: {
            actor_id: $('#actor-id').value
        },
        expected_hash: data.status.config_hash
    });
    if (op === 'save-config') return action('config', {
        values: {
            sql_dialect: $('#sql-dialect').value,
            ai_max_chars: Number($('#max-chars').value),
            ai_max_evidence: Number($('#max-evidence').value),
            exclude: $('#exclude').value.split('\n').map(x => x.trim()).filter(Boolean)
        },
        expected_hash: data.status.config_hash
    });
    if (op === 'logs') {
        const r = await api('log');
        show('Log applicazione', `<pre>${esc(r.text)}</pre>`);
        return
    }
    if (op === 'run-detail') {
        const r = data.runs.find(r => r.id === id);
        show('Report operazione', `<p>${badge(r.status)} ${esc(r.operation)}</p><pre>${pretty(JSON.parse(r.payload))}</pre>`);
        return
    }
}
document.addEventListener('click', e => {
    const a = e.target.closest('[data-action]');
    if (a) clickAction(a).catch(e => toast(errorText(e)))
});
$('#close-detail').onclick = () => $('#detail').close();
$('#refresh').onclick = () => refresh().catch(e => toast(errorText(e)));
addEventListener('hashchange', route);
try {
    const b = await api('bootstrap');
    token = b.token;
    $('#version').textContent = 'v' + b.version;
    $('#workspace-path').textContent = b.workspace;
    prepareNavigation();
    await refresh();
    route()
} catch (e) {
    $('#content').innerHTML = `<div class="hint warn">Connessione al server non riuscita: ${esc(errorText(e))}</div>`
}
