// Indrapportering: siden modtageren (fx CCO) åbner via sit personlige link /r/<token>
const token = location.pathname.split('/').filter(Boolean)[1] || '';
const app = document.getElementById('app');
const savedEl = document.getElementById('saved');
const barEl = document.getElementById('bar');
const foot = document.getElementById('foot');
const countEl = document.getElementById('count');
const submitBtn = document.getElementById('submit');

const AREA = { salg: 'Salg & marketing', leverance: 'Leverance', oekonomi: 'Økonomi' };
const CUSTOMER_STATUS = [['som_planlagt', 'Som planlagt', 'good'], ['venter', 'Venter på kunden', ''], ['udfordret', 'Udfordret', 'bad'], ['vundet', 'Vundet', 'good'], ['tabt', 'Tabt / droppet', 'bad']];
const GOAL_STATUS = [['on_track', 'På sporet', 'good'], ['at_risk', 'I risiko', 'warn'], ['off_track', 'Bagud', 'bad'], ['done', 'Nået', 'good']];
const DELIVERY_STATUS = [['som_planlagt', 'Som planlagt', 'good'], ['forsinket', 'Forsinket', 'warn'], ['udfordret', 'Udfordret', 'bad'], ['leveret', 'Leveret', 'good']];
const PROBS = ['10', '25', '50', '75', '90'];
const TOPIC_STATUS = [['paa_sporet', 'På sporet', 'good'], ['risiko', 'Risiko', 'warn'], ['kritisk', 'Kritisk', 'bad']];

function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
        else if (k === 'className') el.className = v;
        else if (k === 'value') el.value = v;
        else el.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) if (c != null) el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    return el;
}
const fmtDate = d => d ? new Date(String(d).slice(0, 10) + 'T00:00:00').toLocaleDateString('da-DK', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
const fmtNum = n => n == null || n === '' ? '–' : Number(n).toLocaleString('da-DK', { maximumFractionDigits: 1 });
const today = new Date().toISOString().slice(0, 10);
const daysAgo = d => Math.round((new Date(today) - new Date(String(d).slice(0, 10))) / 86400000);

async function api(path, opts = {}) {
    const res = await fetch(`/api/r/${token}${path}`, { headers: { 'Content-Type': 'application/json' }, ...opts });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    return res.json();
}

let round = null;
const timers = {};     // ventende (debouncede) gemninger pr. punkt
async function push(item) {
    delete timers[item.id];
    try { await api(`/items/${item.id}`, { method: 'PUT', body: JSON.stringify({ answer: item.answer }) }); savedEl.textContent = 'Gemt ✓'; }
    catch (e) { savedEl.textContent = `Ikke gemt: ${e.message}`; throw e; }
}
function save(item) {
    savedEl.textContent = 'Gemmer…';
    clearTimeout(timers[item.id]);
    timers[item.id] = setTimeout(() => push(item).catch(() => {}), 500);
    refresh();
}
async function flush() {
    const ids = Object.keys(timers);
    for (const id of ids) clearTimeout(timers[id]);
    await Promise.all(ids.map(id => push(round.items.find(i => String(i.id) === id))));
}

// Spørgsmål kan være ren tekst (ældre runder) eller {text, answer_type, options}
const normQ = q => typeof q === 'string' ? { text: q, answer_type: 'text', options: [] } : { options: [], answer_type: 'text', ...q };

function isComplete(it) {
    const a = it.answer || {};
    if (a.later) return true;
    if (it.kind === 'matrix') return (it.context?.rows || []).every(r => (a.rows || {})[r.company_id]);
    if (it.kind === 'customer') return !!(a.not_relevant || (a.status && (a.next_step || ['vundet', 'tabt', 'leveret'].includes(a.status))));
    if (it.kind === 'marketing') return !!a.activities;
    if (it.kind === 'goal') return !!a.status && (!['at_risk', 'off_track'].includes(a.status) || !!a.comment);
    if (it.kind === 'topic') {
        const c = it.context || {};
        const fu = a.followup || {};
        const asksGoal = c.source_kind === 'goal';
        return (c.questions || []).every((_, i) => (a[`q${i}`] || '').trim())
            && (asksGoal ? !!a.goal_status : (!c.ask_status || !!a.status))
            && (!fu.question || !!(fu.answer || '').trim() || !!fu.skipped);
    }
    return !!a.answer;
}
function refresh() {
    const n = round.items.length, done = round.items.filter(isComplete).length;
    barEl.style.width = `${n ? Math.round(done / n * 100) : 0}%`;
    countEl.textContent = `${done} af ${n} besvaret`;
    for (const it of round.items) it._card && it._card.classList.toggle('done', isComplete(it));
}

function chips(options, value, onPick) {
    const wrap = h('div', { className: 'chips' });
    for (const [k, label, tone] of options) {
        const b = h('button', { type: 'button', className: `chip ${tone || ''} ${value === k ? 'on' : ''}` }, label);
        b.addEventListener('click', () => { [...wrap.children].forEach(c => c.classList.remove('on')); b.classList.add('on'); onPick(k); });
        wrap.appendChild(b);
    }
    return wrap;
}
function field(label, el) { return h('div', {}, h('label', { className: 'l' }, label), el); }
function text(item, key, placeholder, multi = true) {
    const el = multi ? h('textarea', { placeholder }) : h('input', { type: 'text', placeholder });
    el.value = (item.answer || {})[key] || '';
    el.addEventListener('input', () => { item.answer = { ...(item.answer || {}), [key]: el.value }; save(item); });
    return el;
}
function input(item, key, type, placeholder) {
    const el = h('input', { type, placeholder });
    el.value = (item.answer || {})[key] ?? '';
    el.addEventListener('input', () => { item.answer = { ...(item.answer || {}), [key]: el.value }; save(item); });
    return el;
}

function customerCard(it) {
    const c = it.context || {};
    const prev = c.previous_answer;
    const facts = h('div', { className: 'facts' });
    for (const t of c.tenders || []) {
        const late = t.deadline && String(t.deadline).slice(0, 10) < today;
        facts.appendChild(h('div', { className: late ? 'late' : '' }, `Tilbud: ${t.title}` + (t.deadline ? ` · deadline ${fmtDate(t.deadline)}${late ? ' (overskredet)' : ''}` : '') + (t.estimated_value ? ` · ${fmtNum(Number(String(t.estimated_value).replace(/\D/g, '')) || t.estimated_value)} kr.` : '')));
    }
    for (const t of c.tasks || []) facts.appendChild(h('div', {}, `Sag: ${t.title}` + (t.due_date ? ` · frist ${fmtDate(t.due_date)}` : '')));
    facts.appendChild(h('div', {}, c.last_contact ? `Sidste registrerede kontakt: ${daysAgo(c.last_contact)} dage siden` : 'Ingen registreret kontakt'));

    const body = h('div', { className: 'body' });
    const draw = () => {
        body.innerHTML = '';
        const a = it.answer || {};
        const nr = h('input', { type: 'checkbox', ...(a.not_relevant ? { checked: true } : {}) });
        nr.addEventListener('change', () => { it.answer = { ...(it.answer || {}), not_relevant: nr.checked }; save(it); draw(); });
        const delivery = round.area === 'leverance';
        if (!a.not_relevant) {
            body.append(
                field(delivery ? 'Status på leverancen' : 'Status', chips(delivery ? DELIVERY_STATUS : CUSTOMER_STATUS, a.status, k => { it.answer = { ...(it.answer || {}), status: k }; save(it); })),
                field('Hvad er sket siden sidst?', text(it, 'since_last', 'Møder, svar fra kunden, nye oplysninger…')),
                h('div', { className: 'row2b' },
                    field('Næste skridt', text(it, 'next_step', 'Hvad skal der ske nu?', false)),
                    field('Hvornår', input(it, 'next_date', 'date'))),
                delivery ? null : field('Sandsynlighed for at lukke', chips(PROBS.map(p => [p, `${p} %`, '']), a.probability, k => { it.answer = { ...(it.answer || {}), probability: k }; save(it); })),
                field('Brug for hjælp? (valgfrit)', text(it, 'help', 'Fx fra CEO, leverance eller økonomi')));
        }
        body.appendChild(h('label', { className: 'nr' }, nr, delivery ? 'Intet aktivt hos kunden lige nu' : 'Kunden er ikke længere i proces'));
    };
    draw();
    const card = h('div', { className: 'card' },
        h('div', { className: 'card-h' }, h('span', { className: 'check' }, '✓'), h('div', { className: 'card-t' }, it.title),
            prev ? h('button', { type: 'button', className: 'ghost', onClick: () => {
                it.answer = { ...prev, since_last: 'Intet nyt siden sidst' };
                save(it); draw();
            } }, 'Uændret siden sidst') : null),
        facts,
        prev ? h('div', { className: 'prev' }, `Sidst (${fmtDate(c.previous_date)}): ${[prev.next_step && `næste skridt "${prev.next_step}"`, prev.probability && `${prev.probability} %`].filter(Boolean).join(' · ') || 'besvaret'}`) : null,
        body);
    return card;
}

function goalCard(it) {
    const c = it.context || {};
    const hasTarget = c.target_value != null;
    const body = h('div', { className: 'body' });
    const commentLabel = h('label', { className: 'l' }, 'Kommentar');
    const a = it.answer || {};
    body.append(
        hasTarget ? field(`Ny værdi${c.unit ? ` (${c.unit})` : ''}`, input(it, 'value', 'number', String(c.current_value ?? ''))) : null,
        field('Status', chips(GOAL_STATUS, a.status, k => {
            it.answer = { ...(it.answer || {}), status: k };
            commentLabel.textContent = ['at_risk', 'off_track'].includes(k) ? 'Hvad gør vi for at komme på sporet? (påkrævet)' : 'Kommentar';
            save(it);
        })),
        h('div', {}, commentLabel, text(it, 'comment', 'Status med dine egne ord')));
    return h('div', { className: 'card' },
        h('div', { className: 'card-h' }, h('span', { className: 'check' }, '✓'), h('div', { className: 'card-t' }, it.title)),
        h('div', { className: 'facts' },
            h('div', {}, c.kind === 'strategisk' ? 'Strategisk mål' : 'Driftsmål'),
            hasTarget ? h('div', {}, `Nu: ${fmtNum(c.current_value ?? c.start_value)} af ${fmtNum(c.target_value)}${c.unit ? ' ' + c.unit : ''}` + (c.due_date ? ` · deadline ${fmtDate(c.due_date)}` : '')) : null,
            c.milestones_total ? h('div', {}, `Milepæle: ${c.milestones_done} af ${c.milestones_total} nået`) : null),
        c.last_comment ? h('div', { className: 'prev' }, `Sidst: "${c.last_comment}"`) : null,
        body);
}

function marketingCard(it) {
    return h('div', { className: 'card' },
        h('div', { className: 'card-h' }, h('span', { className: 'check' }, '✓'), h('div', { className: 'card-t' }, it.title)),
        h('div', { className: 'hint' }, (it.context || {}).hint || ''),
        h('div', { className: 'body' },
            field('Aktiviteter de sidste 14 dage', text(it, 'activities', 'Kampagner, opslag, events, webinarer, nyhedsbreve…')),
            field('Hvad kom der ud af det?', text(it, 'results', 'Respons, henvendelser, synlighed…')),
            h('div', { className: 'row2' }, field('Nye leads', input(it, 'leads', 'number', '0')), field('Bookede møder', input(it, 'meetings', 'number', '0'))),
            field('Plan for de næste 14 dage', text(it, 'next', 'Hvad sker der nu?')),
            field('Hvad virker, og hvad virker ikke? (valgfrit)', text(it, 'learnings', ''))));
}

// Emne med fakta og konkrete spørgsmål (formuleret af AI eller CEO'en ud fra data)
function topicCard(it) {
    const c = it.context || {};
    const src = c.source || {};
    const body = h('div', { className: 'body' });
    const a0 = it.answer || {};
    if (c.source_kind === 'goal') {
        body.append(
            src.target_value != null ? field(`Ny værdi${src.unit ? ` (${src.unit})` : ''}`, input(it, 'value', 'number', String(src.current_value ?? ''))) : null,
            field('Status på målet', chips(GOAL_STATUS, a0.goal_status, k => { it.answer = { ...(it.answer || {}), goal_status: k }; save(it); })));
    } else if (c.ask_status) {
        body.appendChild(field('Din samlede vurdering', chips(TOPIC_STATUS, a0.status, k => { it.answer = { ...(it.answer || {}), status: k }; save(it); })));
    }
    (c.questions || []).map(normQ).forEach((q, i) => body.appendChild(h('div', {},
        h('label', { className: 'l q' }, h('span', { className: 'qn' }, String.fromCharCode(97 + i)), q.text),
        answerInput(it, `q${i}`, q))));
    if (c.source_kind === 'customer') {
        body.append(
            h('div', { className: 'row2b' },
                field('Næste skridt', text(it, 'next_step', 'Hvad skal der ske nu?', false)),
                field('Hvornår', input(it, 'next_date', 'date'))),
            round.area === 'salg' ? field('Sandsynlighed for at lukke', chips(PROBS.map(p => [p, `${p} %`, '']), a0.probability, k => { it.answer = { ...(it.answer || {}), probability: k }; save(it); })) : null);
    }
    const fuBox = h('div', {});
    body.appendChild(fuBox);
    it._drawFollowup = () => {
        fuBox.innerHTML = '';
        const fu = (it.answer || {}).followup;
        if (it._checking) { fuBox.appendChild(h('div', { className: 'fu-wait' }, 'Tjekker dit svar…')); return; }
        if (!fu || !fu.question) return;
        const ta = h('textarea', { placeholder: 'Dit svar' });
        ta.value = fu.answer || '';
        ta.addEventListener('input', () => { it.answer = { ...it.answer, followup: { ...fu, answer: ta.value, skipped: false } }; save(it); });
        fuBox.appendChild(h('div', { className: 'fu' },
            h('div', { className: 'fu-h' }, 'Opfølgende spørgsmål'),
            h('div', { className: 'fu-q' }, fu.question), ta,
            fu.answer ? null : h('button', { type: 'button', className: 'fu-skip', onClick: () => {
                it.answer = { ...it.answer, followup: { ...fu, skipped: true } }; save(it); it._drawFollowup();
            } }, fu.skipped ? 'Sprunget over' : 'Spring over')));
    };
    it._drawFollowup();
    const card = h('div', { className: 'card' },
        h('div', { className: 'card-h' }, h('span', { className: 'check' }, '✓'), h('div', { className: 'card-t' }, it.title)),
        (c.facts || []).length ? h('div', { className: 'facts' }, ...c.facts.map(f => h('div', {}, f))) : null,
        c.why ? h('div', { className: 'prev' }, c.why) : null,
        body);
    // Når et færdigt kort forlades, tjekkes svaret, og der kommer evt. ét opfølgende spørgsmål
    card.addEventListener('focusout', (e) => {
        if (card.contains(e.relatedTarget)) return;
        setTimeout(() => checkFollowup(it), 50);
    });
    return card;
}

// Bedste svarform: klik for kendte udfald, dato- og talfelter, fritekst kun når der skal forklares
function answerInput(it, key, q) {
    const a = it.answer || {};
    if (q.answer_type === 'choice' && q.options.length) {
        const tone = o => /tabt|kritisk|bagud|nej/i.test(o) ? 'bad' : /ved ikke|udskudt|risiko/i.test(o) ? 'warn' : /vundet|ja|afleveret|på sporet/i.test(o) ? 'good' : '';
        return chips(q.options.map(o => [o, o, tone(o)]), a[key], k => { it.answer = { ...(it.answer || {}), [key]: k }; save(it); });
    }
    if (q.answer_type === 'date') return h('div', { style: 'max-width:200px' }, input(it, key, 'date'));
    if (q.answer_type === 'number') return h('div', { style: 'max-width:200px' }, input(it, key, 'number'));
    return text(it, key, '');
}

// Én liste med ét klik pr. kunde (fx "Direkte salg eller udbud?")
function matrixCard(it) {
    const c = it.context || {};
    const a = () => it.answer || {};
    const setRow = (cid, v) => { it.answer = { ...a(), rows: { ...(a().rows || {}), [cid]: v } }; save(it); };
    const list = h('div', { className: 'mx' });
    const draw = () => {
        list.innerHTML = '';
        for (const r of c.rows || []) {
            const val = (a().rows || {})[r.company_id];
            let control;
            if (c.input === 'select') {
                control = h('select', { className: `mx-sel ${val ? 'set' : ''}` },
                    h('option', { value: '' }, 'Vælg fase…'),
                    ...c.options.map(([k, l]) => h('option', { value: k, ...(val === k ? { selected: true } : {}) }, l)));
                control.addEventListener('change', () => { setRow(r.company_id, control.value); control.classList.toggle('set', !!control.value); });
            } else {
                control = chips(c.options.map(([k, l]) => [k, l, k === 'ved_ikke' ? 'warn' : '']), val, k => { setRow(r.company_id, k); if (c.target === 'news') draw(); });
            }
            const row = h('div', { className: 'mx-row' },
                h('div', { className: 'mx-name' }, h('b', {}, r.name), r.hint ? h('small', {}, r.hint) : null,
                    r.current && c.target === 'sales_phase' ? h('small', { className: 'mx-cur' }, `Sidst: ${(c.options.find(o => o[0] === r.current) || [])[1] || r.current}`) : null),
                control);
            list.appendChild(row);
            if (c.target === 'news' && val === 'ja') {
                const t = h('input', { type: 'text', placeholder: `Hvad er sket hos ${r.name}?`, className: 'mx-note' });
                t.value = (a().notes || {})[r.company_id] || '';
                t.addEventListener('input', () => { it.answer = { ...a(), notes: { ...(a().notes || {}), [r.company_id]: t.value } }; save(it); });
                list.appendChild(t);
            }
        }
    };
    draw();
    const withCurrent = (c.rows || []).filter(r => r.current);
    return h('div', { className: 'card' },
        h('div', { className: 'card-h' }, h('span', { className: 'check' }, '✓'), h('div', { className: 'card-t' }, it.title)),
        c.hint ? h('div', { className: 'hint' }, c.hint) : null,
        c.target === 'sales_phase' && withCurrent.length ? h('button', { type: 'button', className: 'ghost', style: 'margin-top:8px', onClick: () => {
            const rows = { ...(a().rows || {}) };
            for (const r of withCurrent) if (!rows[r.company_id]) rows[r.company_id] = r.current;
            it.answer = { ...a(), rows }; save(it); draw();
        } }, 'Alle uændrede') : null,
        c.target === 'news' ? h('button', { type: 'button', className: 'ghost', style: 'margin-top:8px', onClick: () => {
            const rows = { ...(a().rows || {}) };
            for (const r of c.rows) if (!rows[r.company_id]) rows[r.company_id] = 'nej';
            it.answer = { ...a(), rows }; save(it); draw();
        } }, 'Intet nyt hos resten') : null,
        list);
}

// "Svarer senere": emnet tæller som håndteret og kommer automatisk med i næste indrapportering
function addLaterToggle(it, card) {
    const head = card.querySelector('.card-h');
    const btn = h('button', { type: 'button', className: 'later-btn' });
    const sync = () => {
        const later = !!(it.answer || {}).later;
        btn.textContent = later ? 'Svar nu' : 'Svarer senere';
        card.classList.toggle('later', later);
    };
    btn.addEventListener('click', () => { it.answer = { ...(it.answer || {}), later: !(it.answer || {}).later }; save(it); sync(); });
    head.appendChild(btn);
    card.appendChild(h('div', { className: 'later-note' }, 'Du svarer på dette senere. Det kommer med i næste indrapportering.'));
    sync();
}

async function checkFollowup(it) {
    const a = it.answer || {};
    if (it.kind !== 'topic' || a.later || a.checked || it._checking || (a.followup || {}).question) return false;
    const c = it.context || {};
    const baseDone = (c.questions || []).every((_, i) => (a[`q${i}`] || '').trim());
    if (!baseDone) return false;
    it._checking = true; it._drawFollowup();
    try {
        clearTimeout(timers[it.id]); await push(it);
        const res = await api(`/items/${it.id}/followup`, { method: 'POST' });
        it.answer = { ...it.answer, checked: true, ...(res.followup ? { followup: res.followup } : {}) };
    } catch (e) { /* tjekket mislykkedes: lad modtageren fortsætte */ }
    it._checking = false; it._drawFollowup(); refresh();
    return !!(it.answer.followup && it.answer.followup.question && !it.answer.followup.answer);
}

function questionCard(it) {
    return h('div', { className: 'card' },
        h('div', { className: 'card-h' }, h('span', { className: 'check' }, '✓'), h('div', { className: 'card-t' }, it.title)),
        h('div', { className: 'hint' }, (it.context || {}).hint || ''),
        h('div', { className: 'body' }, field('Svar', text(it, 'answer', ''))));
}

function render() {
    app.innerHTML = '';
    const first = (round.respondent_name || '').split(' ')[0];
    if (round.status === 'draft') {
        app.appendChild(h('div', { className: 'msg' }, h('h1', {}, 'Ikke klar endnu'),
            h('p', { className: 'intro' }, 'Spørgsmålene er ved at blive gjort klar. Prøv igen lidt senere.')));
        foot.hidden = true; return;
    }
    if (round.status !== 'open') {
        app.appendChild(h('div', { className: 'msg' }, h('h1', {}, 'Tak, din indrapportering er sendt ✓'),
            h('p', { className: 'intro' }, 'Den indgår i forberedelsen af næste opfølgningsmøde.')));
        foot.hidden = true; barEl.style.width = '100%'; return;
    }
    app.append(
        h('div', { className: 'sec', style: 'margin-top:0' }, `Indrapportering · ${AREA[round.area] || round.area}`),
        round.practice ? h('div', { className: 'practice' }, 'Øvelse: dine svar bliver ikke gemt på mål eller kunder.') : null,
        h('h1', {}, `Hej ${first}`),
        h('p', { className: 'intro' }, `Her er spørgsmålene til næste opfølgningsmøde${round.due_date ? `. Svar gerne senest ${fmtDate(round.due_date)}` : ''}. Dine svar gemmes løbende, så du kan holde pause og fortsætte senere. Korte, konkrete svar er fine. Skriv hellere "ved ikke" end ingenting.`));
    const groups = [
        ['matrix', 'Hurtige afklaringer'], ['carried', 'Fra sidst: svarer senere'], ['topic', 'Emner'], ['customer', 'Kunder i proces'],
        ['marketing', 'Marketing'], ['goal', 'Mål'], ['question', 'Spørgsmål'],
    ];
    const groupOf = i => i.context?.carried ? 'carried' : i.kind;
    for (const [kind, label] of groups) {
        const its = round.items.filter(i => groupOf(i) === kind);
        if (!its.length) continue;
        app.appendChild(h('div', { className: 'sec' }, `${label} (${its.length})`));
        for (const it of its) {
            it._card = { matrix: matrixCard, topic: topicCard, customer: customerCard, goal: goalCard, marketing: marketingCard, question: questionCard }[it.kind](it);
            if (it.kind !== 'matrix') addLaterToggle(it, it._card);
            app.appendChild(it._card);
        }
    }
    foot.hidden = false;
    refresh();
}

submitBtn.addEventListener('click', async () => {
    // Tjek de emner, der ikke er tjekket endnu, før indsendelse
    const toCheck = round.items.filter(i => i.kind === 'topic' && !(i.answer || {}).later && !(i.answer || {}).checked && !((i.answer || {}).followup || {}).question);
    if (toCheck.length) {
        submitBtn.disabled = true; submitBtn.textContent = 'Tjekker dine svar…';
        const results = [];
        for (let k = 0; k < toCheck.length; k += 3) results.push(...await Promise.all(toCheck.slice(k, k + 3).map(checkFollowup)));
        submitBtn.disabled = false; submitBtn.textContent = 'Indsend';
        const n = results.filter(Boolean).length;
        if (n) {
            const first = round.items.find(i => i.answer?.followup?.question && !i.answer.followup.answer && !i.answer.followup.skipped);
            first?._card?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            alert(`Der er ${n} opfølgende spørgsmål til dine svar. Svar på dem (eller spring over), og tryk Indsend igen.`);
            return;
        }
    }
    const missing = round.items.filter(i => !isComplete(i));
    if (missing.length && !confirm(`${missing.length} punkter er ikke besvaret helt:\n\n${missing.slice(0, 8).map(m => '• ' + m.title).join('\n')}\n\nVil du indsende alligevel?`)) return;
    submitBtn.disabled = true; submitBtn.textContent = 'Sender…';
    try {
        await flush();
        await api('/submit', { method: 'POST' });
        round.status = 'answered'; render(); window.scrollTo(0, 0);
    } catch (e) { alert(e.message); submitBtn.disabled = false; submitBtn.textContent = 'Indsend'; }
});

(async () => {
    try { round = await api(''); render(); }
    catch (e) { app.innerHTML = ''; app.appendChild(h('div', { className: 'msg' }, h('h1', {}, 'Linket virker ikke'), h('p', { className: 'intro' }, 'Det er udløbet eller forkert. Bed om et nyt link.'))); }
})();
