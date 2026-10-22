import { api } from './api.js?v=41';

// ─── Constants ───
const CATEGORY_LABELS = { opkald:'Opkald', tilbud:'Tilbud', moede:'Møde', opfølgning:'Opfølgning', demo:'Demo', kontrakt:'Kontrakt', implementering:'Implementering', support:'Support', faktura:'Fakturering', budget:'Budget', generelt:'Generelt' };
const AREA_LABELS = { salg:'Salg & marketing', leverance:'Leverance', oekonomi:'Økonomi' };
const AREA_INTRO = {
    salg: 'Relationer, tilbud, udbud og opfølgning på salg og marketing',
    leverance: 'Implementering, drift og opfølgning hos kunderne',
    oekonomi: 'Kontrakter, fakturering, budget og opfølgning på økonomi',
};
const PRIORITY_LABELS = { low:'Lav', normal:'Normal', high:'Høj', urgent:'Hastende' };
const STATUS_LABELS = { open:'Åben', in_progress:'I gang', done:'Færdig' };
const LI_ACTIVITY_LABELS = { post:'Opslag', comment:'Kommentar', like:'Like', share:'Deling', article:'Artikel' };
const LI_ENGAGE_LABELS = { like:'Like', comment:'Kommentar', share:'Deling', follow:'Følger' };
const TENDER_STATUS_LABELS = { draft:'Kladde', in_progress:'I gang', submitted:'Indsendt', won:'Vundet', lost:'Tabt', dropped:'Droppet' };
const TENDER_STATUS_COLORS = { draft:'bg-gray-100 text-gray-600', in_progress:'bg-blue-100 text-blue-700', submitted:'bg-yellow-100 text-yellow-700', won:'bg-green-100 text-green-700', lost:'bg-red-100 text-red-700', dropped:'bg-orange-100 text-orange-700' };
// Købsvej på et tilbud: direkte til kunden eller via et indkøbsfællesskab (fx Servia)
function routeBadge(t) {
    if (t.purchase_route !== 'faellesskab') return null;
    return h('span', { className: 'route-pill', title: 'Kunden køber via indkøbsfællesskab' }, `via ${t.via_group_name || 'fællesskab'}`);
}
const SECTION_STATUS_LABELS = { not_started:'Ikke startet', in_progress:'I gang', in_review:'Til review', approved:'Godkendt' };
const SECTION_STATUS_COLORS = { not_started:'bg-gray-100 text-gray-600', in_progress:'bg-blue-100 text-blue-700', in_review:'bg-yellow-100 text-yellow-700', approved:'bg-green-100 text-green-700' };

// ─── Router ───
function getRoute() {
    const hash = location.hash.slice(1) || '/';
    const parts = hash.split('/').filter(Boolean);
    return { path: hash, parts };
}

async function router() {
    const { path, parts } = getRoute();
    const content = document.getElementById('content');

    const navKey = parts[0] === 'area' ? parts.slice(0, 2).join('/') : (parts[0] || '');
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.getAttribute('data-page') === navKey);
    });

    try {
        if (parts[0] === 'companies' && parts[1]) {
            await renderCompanyDetail(content, parseInt(parts[1]));
        } else if (parts[0] === 'companies') {
            await renderCompanies(content);
        } else if (parts[0] === 'tenders' && parts[1]) {
            await renderTenderDetail(content, parseInt(parts[1]));
        } else if (parts[0] === 'tenders') {
            await renderTenders(content);
        } else if (parts[0] === 'tasks' && parts[1]) {
            await renderTaskDetail(content, parseInt(parts[1]));
        } else if (parts[0] === 'tasks') {
            await renderTasks(content);
        } else if (parts[0] === 'area' && AREA_LABELS[parts[1]]) {
            await renderTasks(content, parts[1]);
        } else if (parts[0] === 'goals' && parts[1]) {
            await renderGoalDetail(content, parseInt(parts[1]));
        } else if (parts[0] === 'goals') {
            await renderGoals(content);
        } else if (parts[0] === 'reports' && parts[1]) {
            await renderReportRound(content, parseInt(parts[1]));
        } else if (parts[0] === 'meetings' && parts[1]) {
            await renderMeetingDetail(content, parseInt(parts[1]));
        } else if (parts[0] === 'meetings') {
            await renderMeetings(content);
        } else if (parts[0] === 'users') {
            await renderUsers(content);
        } else if (parts[0] === 'settings') {
            await renderSettings(content);
        } else {
            await renderDashboard(content);
        }
    } catch (err) {
        content.innerHTML = `<div class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">Fejl: ${err.message}</div>`;
    }
}

window.addEventListener('hashchange', () => { window.scrollTo(0, 0); router(); });
window.addEventListener('load', () => {
    initUserSelector();
    initGlobalSearch();
    initNotifications();
    initAssistant();

    // Force re-render when clicking nav link for the current page (hash unchanged)
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            const target = link.getAttribute('href') || '#/';
            if (location.hash === target || (location.hash === '' && target === '#/')) {
                e.preventDefault();
                router();
            }
        });
    });

    router();
});

// ─── Helpers ───
function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
        else if (k === 'className') el.className = v;
        else if (k === 'innerHTML') el.innerHTML = v;
        else el.setAttribute(k, v);
    }
    for (const child of children.flat()) {
        if (child == null) continue;
        el.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return el;
}

function showModal(title, contentEl, widthClass) {
    const overlay = document.getElementById('modal-overlay');
    const modal = document.getElementById('modal-content');
    modal.className = `bg-white rounded-2xl shadow-xl w-full ${widthClass || 'max-w-lg'} max-h-[90vh] overflow-y-auto`;
    modal.innerHTML = '';
    modal.appendChild(h('div', { className: 'p-6' },
        h('div', { className: 'flex justify-between items-center mb-4' },
            h('h2', { className: 'text-lg font-semibold text-gray-900' }, title),
            h('button', { className: 'text-gray-400 hover:text-gray-600 text-2xl', onClick: closeModal }, '\u00d7')
        ),
        contentEl
    ));
    overlay.classList.remove('hidden');
    overlay.onclick = (e) => { if (e.target === overlay) closeModal(); };
}

function closeModal() { document.getElementById('modal-overlay').classList.add('hidden'); }

async function showScoreHistoryChart() {
    const container = h('div', { className: 'space-y-4' });
    container.innerHTML = '<div class="text-gray-400 text-sm text-center py-8">Indlæser historik...</div>';
    showModal('Historisk relationsscore — gennemsnit', container, 'max-w-2xl');
    let data;
    try { data = await api.getScoreHistoryAggregate(); } catch(e) {
        container.innerHTML = `<div class="text-red-500 text-sm">${e.message}</div>`; return;
    }
    if (!data || data.length === 0) {
        container.innerHTML = '<div class="text-gray-400 text-sm text-center py-8">Ingen historiske data endnu.</div>'; return;
    }
    container.innerHTML = '';

    // SVG line chart
    const W = 580, H = 220, PAD = { top: 16, right: 20, bottom: 40, left: 44 };
    const chartW = W - PAD.left - PAD.right, chartH = H - PAD.top - PAD.bottom;
    const maxScore = 100, minScore = 0;
    const MONTHS_DA = ['jan','feb','mar','apr','maj','jun','jul','aug','sep','okt','nov','dec'];

    function xPos(i) { return PAD.left + (data.length < 2 ? chartW / 2 : (i / (data.length - 1)) * chartW); }
    function yPos(v) { return PAD.top + chartH - ((v - minScore) / (maxScore - minScore)) * chartH; }

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('width', '100%');
    svg.style.overflow = 'visible';

    // Grid lines & Y labels
    for (const yVal of [0, 25, 50, 75, 100]) {
        const y = yPos(yVal);
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', PAD.left); line.setAttribute('x2', PAD.left + chartW);
        line.setAttribute('y1', y); line.setAttribute('y2', y);
        line.setAttribute('stroke', '#e5e7eb'); line.setAttribute('stroke-width', '1');
        svg.appendChild(line);
        const lbl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        lbl.setAttribute('x', PAD.left - 6); lbl.setAttribute('y', y + 4);
        lbl.setAttribute('text-anchor', 'end'); lbl.setAttribute('font-size', '10');
        lbl.setAttribute('fill', '#9ca3af'); lbl.textContent = yVal;
        svg.appendChild(lbl);
    }

    // Area fill
    const areaPoints = data.map((d, i) => `${xPos(i)},${yPos(d.avg_score)}`).join(' ');
    const area = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    area.setAttribute('points', `${PAD.left},${yPos(0)} ${areaPoints} ${PAD.left + chartW},${yPos(0)}`);
    area.setAttribute('fill', '#dbeafe'); area.setAttribute('opacity', '0.5');
    svg.appendChild(area);

    // Line
    const linePath = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
    linePath.setAttribute('points', areaPoints);
    linePath.setAttribute('fill', 'none'); linePath.setAttribute('stroke', '#3b82f6');
    linePath.setAttribute('stroke-width', '2'); linePath.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(linePath);

    // Data points + X labels
    const step = data.length <= 10 ? 1 : Math.ceil(data.length / 8);
    data.forEach((d, i) => {
        const x = xPos(i), y = yPos(d.avg_score);
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', x); circle.setAttribute('cy', y); circle.setAttribute('r', '4');
        circle.setAttribute('fill', '#3b82f6'); circle.setAttribute('stroke', 'white'); circle.setAttribute('stroke-width', '1.5');
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        title.textContent = `${d.date}: ${d.avg_score} (${d.total_companies} virksomheder)`;
        circle.appendChild(title); svg.appendChild(circle);

        if (i % step === 0 || i === data.length - 1) {
            const dt = new Date(d.date + 'T00:00:00');
            const xLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            xLabel.setAttribute('x', x); xLabel.setAttribute('y', PAD.top + chartH + 16);
            xLabel.setAttribute('text-anchor', 'middle'); xLabel.setAttribute('font-size', '10');
            xLabel.setAttribute('fill', '#9ca3af');
            xLabel.textContent = `${dt.getDate()}. ${MONTHS_DA[dt.getMonth()]}`;
            svg.appendChild(xLabel);
        }
    });

    // Latest value callout
    const last = data[data.length - 1];
    const lx = xPos(data.length - 1), ly = yPos(last.avg_score);
    const callout = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    callout.setAttribute('x', lx + 6); callout.setAttribute('y', ly - 8);
    callout.setAttribute('font-size', '11'); callout.setAttribute('font-weight', 'bold');
    callout.setAttribute('fill', '#1d4ed8'); callout.textContent = `${last.avg_score}`;
    svg.appendChild(callout);

    container.appendChild(svg);

    // Summary stats
    const first = data[0];
    const delta = (last.avg_score - first.avg_score).toFixed(1);
    const deltaColor = delta >= 0 ? 'text-green-600' : 'text-red-500';
    const deltaSign = delta >= 0 ? '+' : '';
    container.appendChild(h('div', { className: 'flex gap-6 text-sm border-t border-gray-100 pt-3 mt-1' },
        h('div', {},
            h('div', { className: 'text-gray-400 text-xs' }, 'Første måling'),
            h('div', { className: 'font-semibold text-gray-800' }, `${first.avg_score} / 100`),
            h('div', { className: 'text-xs text-gray-400' }, first.date)
        ),
        h('div', {},
            h('div', { className: 'text-gray-400 text-xs' }, 'Seneste måling'),
            h('div', { className: 'font-semibold text-gray-800' }, `${last.avg_score} / 100`),
            h('div', { className: 'text-xs text-gray-400' }, last.date)
        ),
        h('div', {},
            h('div', { className: 'text-gray-400 text-xs' }, 'Udvikling'),
            h('div', { className: `font-semibold ${deltaColor}` }, `${deltaSign}${delta} point`)
        ),
        h('div', {},
            h('div', { className: 'text-gray-400 text-xs' }, 'Målinger'),
            h('div', { className: 'font-semibold text-gray-800' }, `${data.length} dage`)
        )
    ));
}

function scoreColor(level) {
    return { 'staerk': '#059669', 'god': '#d97706', 'svag': '#ea580c', 'kold': '#dc2626' }[level] || '#6b7280';
}
function scoreBg(level) { return `badge-${level}`; }
function sectorLabel(s) { return { el:'El', vand:'Vand', varme:'Varme', multiforsyning:'Multiforsyning', 'e-mobilitet':'E-mobilitet', spildevand:'Spildevand', affald:'Affald', gas:'Gas' }[s] || s || 'Ukendt'; }
function tierLabel(t) { return { T1:'T1 - El+Multi', T2:'T2 - Primært El', T3:'T3 - Multi u/El', T4:'T4 - Enkelt forsyning', EM:'EM - E-mobilitet' }[t] || t || ''; }
function tierShort(t) { return t || ''; }
const TIER_COLORS = { T1:'bg-purple-100 text-purple-700', T2:'bg-blue-100 text-blue-700', T3:'bg-teal-100 text-teal-700', T4:'bg-gray-100 text-gray-600', EM:'bg-orange-100 text-orange-700' };
const SERVICE_LABELS = { has_el:'El', has_gas:'Gas', has_vand:'Vand', has_varme:'Varme', has_spildevand:'Spildevand', has_affald:'Affald' };

function interactionIcon(type) {
    const icons = {
        email: '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>',
        phone: '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"/></svg>',
        meeting: '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg>',
        meeting_task: '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>',
        meeting_event: '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>',
        campaign: '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z"/></svg>',
        linkedin: '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>',
    };
    return icons[type] || '';
}
function interactionLabel(type) {
    return { meeting_task:'Opgavemøde', meeting:'Møde', meeting_event:'Arrangement', phone:'Telefon', email:'Email', campaign:'Kampagne', linkedin:'LinkedIn' }[type] || type || '';
}

function formatDate(d) {
    if (!d) return '-';
    try { return new Date(d).toLocaleDateString('da-DK', { day:'numeric', month:'short', year:'numeric' }); }
    catch { return d; }
}

function formField(label, name, value = '', type = 'text', required = false) {
    return h('div', {},
        h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, label),
        h('input', { type, name, value, className: 'w-full border border-gray-300 rounded-lg px-3 py-2', ...(required ? { required:'' } : {}) })
    );
}

// ─── Tag Helpers ───
const TAG_COLORS = ['#3b82f6','#059669','#d97706','#dc2626','#7c3aed','#ec4899','#0891b2','#65a30d','#ea580c','#6366f1'];

function renderTagBar(currentTags, allTags, entityType, entityId) {
    const bar = h('div', { className: 'flex flex-wrap items-center gap-2 mb-4', style: 'position:relative' });

    for (const tag of currentTags) {
        const badge = h('span', { className: 'tag-badge', style: `background-color:${tag.color || '#6b7280'}` },
            tag.name,
            h('span', { className: 'tag-remove', style: 'margin-left:2px;font-size:0.7rem;opacity:0.7;cursor:pointer', title: 'Omdøb tag', onClick: async (e) => {
                e.stopPropagation();
                const newName = prompt(`Nyt navn for tag "${tag.name}":`, tag.name);
                if (newName && newName.trim() && newName.trim() !== tag.name) {
                    await api.updateTag(tag.id, { name: newName.trim(), color: tag.color || '#6b7280' });
                    router();
                }
            }}, '\u270f'),
            h('span', { className: 'tag-remove', onClick: async (e) => {
                e.stopPropagation();
                if (entityType === 'company') await api.removeCompanyTag(entityId, tag.id);
                else await api.removeContactTag(entityId, tag.id);
                router();
            }}, '\u00d7')
        );
        bar.appendChild(badge);
    }

    // Add tag button with dropdown
    const wrapper = h('div', { style: 'position:relative;display:inline-block' });
    const addBtn = h('button', { className: 'tag-add-btn', onClick: (e) => {
        e.stopPropagation();
        dropdown.classList.toggle('hidden');
        if (!dropdown.classList.contains('hidden')) input.focus();
    }}, '+ Tag');
    wrapper.appendChild(addBtn);

    const dropdown = h('div', { className: 'tag-dropdown hidden' });
    const input = h('input', {
        type: 'text', placeholder: 'Søg eller opret tag...',
        className: 'w-full px-3 py-2 border-b border-gray-200 text-sm outline-none',
    });
    input.addEventListener('input', () => {
        const q = input.value.toLowerCase().trim();
        const items = dropdown.querySelectorAll('.tag-dropdown-item');
        items.forEach(item => {
            item.style.display = item.dataset.name.toLowerCase().includes(q) ? '' : 'none';
        });
        createItem.style.display = q.length > 0 ? '' : 'none';
        createItem.textContent = `+ Opret "${q.startsWith('#') ? q : '#' + q}"`;
    });
    input.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter' && input.value.trim()) {
            e.preventDefault();
            await createAndAssignTag(input.value.trim(), entityType, entityId);
            dropdown.classList.add('hidden');
            router();
        }
        if (e.key === 'Escape') dropdown.classList.add('hidden');
    });
    dropdown.appendChild(input);

    const createItem = h('div', {
        className: 'tag-dropdown-item text-blue-600 font-medium',
        style: 'display:none',
        onClick: async () => {
            await createAndAssignTag(input.value.trim(), entityType, entityId);
            dropdown.classList.add('hidden');
            router();
        }
    }, '+ Opret tag');
    dropdown.appendChild(createItem);

    const existingIds = new Set(currentTags.map(t => t.id));
    for (const tag of allTags.filter(t => !existingIds.has(t.id))) {
        const item = h('div', {
            className: 'tag-dropdown-item',
            'data-name': tag.name,
            onClick: async () => {
                if (entityType === 'company') await api.addCompanyTag(entityId, tag.id);
                else await api.addContactTag(entityId, tag.id);
                dropdown.classList.add('hidden');
                router();
            }
        },
            h('span', { className: 'tag-color-dot', style: `background-color:${tag.color || '#6b7280'}` }),
            tag.name
        );
        dropdown.appendChild(item);
    }

    wrapper.appendChild(dropdown);
    bar.appendChild(wrapper);

    // Close dropdown on outside click
    document.addEventListener('click', (e) => {
        if (!wrapper.contains(e.target)) dropdown.classList.add('hidden');
    }, { once: true });

    return bar;
}

async function createAndAssignTag(name, entityType, entityId) {
    const color = TAG_COLORS[Math.floor(Math.random() * TAG_COLORS.length)];
    const result = await api.createTag({ name, color });
    if (entityType === 'company') await api.addCompanyTag(entityId, result.id);
    else await api.addContactTag(entityId, result.id);
}

function renderTagBadges(tags) {
    if (!tags || tags.length === 0) return h('span');
    return h('span', { className: 'inline-flex flex-wrap gap-1' },
        ...tags.map(t => h('span', {
            className: 'tag-badge',
            style: `background-color:${t.color || '#6b7280'};font-size:0.65rem;padding:1px 6px`
        }, t.name))
    );
}

// ─── User Selector ───
async function initUserSelector() {
    const sel = document.getElementById('user-selector');
    if (!sel) return;
    try {
        const users = await api.getUsers();
        sel.innerHTML = '<option value="">Vælg bruger...</option>';
        for (const u of users.filter(u => !u.deleted_at)) {
            const opt = document.createElement('option');
            opt.value = u.id;
            opt.textContent = u.name;
            sel.appendChild(opt);
        }
        const saved = localStorage.getItem('currentUserId');
        if (saved) sel.value = saved;
        sel.addEventListener('change', () => {
            localStorage.setItem('currentUserId', sel.value);
        });
    } catch (e) { /* users table might not exist yet */ }
}

// ─── Global Search ───
let searchTimeout = null;
function initGlobalSearch() {
    const input = document.getElementById('global-search');
    const results = document.getElementById('search-results');
    if (!input || !results) return;

    input.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        const q = input.value.trim();
        if (q.length < 2) { results.classList.add('hidden'); return; }
        searchTimeout = setTimeout(async () => {
            try {
                const data = await api.search(q);
                results.innerHTML = '';
                if (data.companies.length === 0 && data.contacts.length === 0) {
                    results.innerHTML = '<div class="p-3 text-sm text-gray-400">Ingen resultater</div>';
                    results.classList.remove('hidden');
                    return;
                }
                if (data.companies.length > 0) {
                    results.appendChild(h('div', { className: 'search-group' }, 'Virksomheder'));
                    for (const c of data.companies) {
                        results.appendChild(h('a', {
                            href: `#/companies/${c.id}`,
                            className: 'search-item block',
                            onClick: () => { results.classList.add('hidden'); input.value = ''; }
                        },
                            h('div', { className: 'font-medium text-sm' }, c.name),
                            h('div', { className: 'text-xs text-gray-500' },
                                [c.sector ? sectorLabel(c.sector) : null, c.city, c.rating ? `${c.rating}-kunde` : null].filter(Boolean).join(' \u2022 '))
                        ));
                    }
                }
                if (data.contacts.length > 0) {
                    results.appendChild(h('div', { className: 'search-group' }, 'Kontakter'));
                    for (const c of data.contacts) {
                        results.appendChild(h('a', {
                            href: `#/companies/${c.company_id}`,
                            className: 'search-item block',
                            onClick: () => { results.classList.add('hidden'); input.value = ''; }
                        },
                            h('div', { className: 'font-medium text-sm' }, `${c.first_name} ${c.last_name}`),
                            h('div', { className: 'text-xs text-gray-500' },
                                [c.title, c.company_name, c.email].filter(Boolean).join(' \u2022 '))
                        ));
                    }
                }
                results.classList.remove('hidden');
            } catch (e) { results.classList.add('hidden'); }
        }, 300);
    });

    input.addEventListener('keydown', (e) => { if (e.key === 'Escape') { results.classList.add('hidden'); input.value = ''; } });
    document.addEventListener('click', (e) => { if (!input.contains(e.target) && !results.contains(e.target)) results.classList.add('hidden'); });
}

// ─── Notifications ───
let notifInterval = null;
function initNotifications() {
    const bell = document.getElementById('notification-bell');
    const panel = document.getElementById('notification-panel');
    const closeBtn = document.getElementById('close-notifications');
    const markAllBtn = document.getElementById('mark-all-read');

    if (!bell) return;

    bell.addEventListener('click', async () => {
        panel.classList.toggle('hidden');
        if (!panel.classList.contains('hidden')) await loadNotifications();
    });
    closeBtn.addEventListener('click', () => panel.classList.add('hidden'));
    markAllBtn.addEventListener('click', async () => {
        await api.markAllNotificationsRead();
        await loadNotifications();
        updateNotifBadge();
    });

    // Check notifications in background after 3s (don't block page load)
    setTimeout(async () => {
        try { await api.checkNotifications(); updateNotifBadge(); } catch(e) {}
    }, 3000);
    notifInterval = setInterval(async () => {
        try { await api.checkNotifications(); updateNotifBadge(); } catch(e) {}
    }, 60000);
}

async function updateNotifBadge() {
    try {
        const data = await api.getNotificationCount();
        const badge = document.getElementById('notification-badge');
        if (data.unread > 0) {
            badge.textContent = data.unread > 99 ? '99+' : String(data.unread);
            badge.classList.remove('hidden');
        } else {
            badge.classList.add('hidden');
        }
    } catch(e) {}
}

async function loadNotifications() {
    const list = document.getElementById('notification-list');
    try {
        const notifs = await api.getNotifications();
        list.innerHTML = '';
        if (notifs.length === 0) {
            list.innerHTML = '<div class="text-center text-gray-400 text-sm py-8">Ingen notifikationer</div>';
            return;
        }
        for (const n of notifs) {
            const item = h('div', {
                className: `notif-item ${n.is_read ? '' : 'unread'}`,
                onClick: async () => {
                    if (!n.is_read) { await api.markNotificationRead(n.id); updateNotifBadge(); }
                    document.getElementById('notification-panel').classList.add('hidden');
                    location.hash = `#/companies/${n.company_id}`;
                }
            },
                h('div', { className: 'flex justify-between items-start' },
                    h('div', { className: 'font-medium text-sm text-gray-900' }, n.company_name || ''),
                    h('div', { className: 'text-xs text-gray-400' }, formatDate(n.created_at))
                ),
                h('div', { className: 'text-xs text-gray-600 mt-1' }, n.message)
            );
            list.appendChild(item);
        }
    } catch(e) { list.innerHTML = '<div class="text-sm text-red-500 p-4">Fejl ved indlaesning</div>'; }
}

// ─── Customer Matrix ───
function renderCustomerMatrix(scores) {
    const section = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8' });

    // T1-T4 filter state
    let selectedTier = null;
    const tiers = ['T1', 'T2', 'T3', 'T4'];

    const header = h('div', { className: 'flex items-center justify-between mb-3' },
        h('h2', { className: 'text-lg font-semibold text-gray-900' }, 'Kundematrix'),
        h('div', { className: 'flex items-center gap-4 text-xs' },
            h('span', { className: 'flex items-center gap-1' }, h('span', { className: 'w-3 h-3 rounded-full inline-block', style:'background:#dc2626' }), 'Kold (0\u201319)'),
            h('span', { className: 'flex items-center gap-1' }, h('span', { className: 'w-3 h-3 rounded-full inline-block', style:'background:#ea580c' }), 'Svag (20\u201349)'),
            h('span', { className: 'flex items-center gap-1' }, h('span', { className: 'w-3 h-3 rounded-full inline-block', style:'background:#d97706' }), 'God (50\u201379)'),
            h('span', { className: 'flex items-center gap-1' }, h('span', { className: 'w-3 h-3 rounded-full inline-block', style:'background:#059669' }), 'St\u00e6rk (80\u2013100)')
        )
    );
    section.appendChild(header);

    // Tier filter buttons
    const filterBar = h('div', { className: 'flex gap-2 mb-4' });
    const allBtn = h('button', {
        className: `px-3 py-1 rounded text-xs font-medium border ${selectedTier === null ? 'bg-gray-800 text-white border-gray-800' : 'bg-white text-gray-600 border-gray-300 hover:border-gray-500'}`,
        onClick: () => { selectedTier = null; rebuildGrid(); }
    }, 'Alle');
    filterBar.appendChild(allBtn);
    const tierBtns = {};
    for (const t of tiers) {
        const btn = h('button', {
            className: `px-3 py-1 rounded text-xs font-medium border ${selectedTier === t ? 'bg-gray-800 text-white border-gray-800' : 'bg-white text-gray-600 border-gray-300 hover:border-gray-500'}`,
            onClick: () => { selectedTier = t; rebuildGrid(); }
        }, t);
        tierBtns[t] = btn;
        filterBar.appendChild(btn);
    }
    section.appendChild(filterBar);

    const stages = ['tidlig_fase', 'aktiv_dialog', 'fremskreden'];
    const stageLabels = { tidlig_fase: 'Tidlig fase', aktiv_dialog: 'Aktiv dialog', fremskreden: 'Fremskreden' };
    const importances = ['meget_vigtig', 'middel_vigtig', 'lidt_vigtig'];
    const impLabels = { meget_vigtig: 'Meget vigtig', middel_vigtig: 'Middel vigtig', lidt_vigtig: 'Lidt vigtig' };

    const wrapper = h('div', { className: 'relative' });
    section.appendChild(wrapper);

    function rebuildGrid() {
        // Update button styles
        allBtn.className = `px-3 py-1 rounded text-xs font-medium border ${selectedTier === null ? 'bg-gray-800 text-white border-gray-800' : 'bg-white text-gray-600 border-gray-300 hover:border-gray-500'}`;
        for (const t of tiers) {
            tierBtns[t].className = `px-3 py-1 rounded text-xs font-medium border ${selectedTier === t ? 'bg-gray-800 text-white border-gray-800' : 'bg-white text-gray-600 border-gray-300 hover:border-gray-500'}`;
        }

        const filtered = selectedTier ? scores.filter(s => s.tier === selectedTier) : scores;

        // Remove old grid
        while (wrapper.firstChild) wrapper.removeChild(wrapper.firstChild);

        wrapper.appendChild(h('div', { className: 'matrix-y-label' }, '\u2191 Vigtighed'));

        const grid = h('div', { className: 'customer-matrix' });
        // Header row
        grid.appendChild(h('div', { className: 'matrix-corner' }));
        for (const st of stages) {
            grid.appendChild(h('div', { className: 'matrix-col-header' }, stageLabels[st]));
        }

        for (const imp of importances) {
            grid.appendChild(h('div', { className: 'matrix-row-header' }, impLabels[imp]));
            for (const st of stages) {
                const cell = h('div', { className: 'matrix-cell' });
                const cellInner = h('div', { className: 'matrix-cell-scroll' });
                const cellCompanies = filtered.filter(s =>
                    (s.importance || 'middel_vigtig') === imp && (s.sales_stage || 'tidlig_fase') === st
                );
                if (cellCompanies.length > 0) {
                    cellInner.appendChild(h('span', { className: 'text-xs text-gray-400 w-full block mb-1' }, `${cellCompanies.length} virksomheder`));
                }
                for (const c of cellCompanies) {
                    const s = Math.round(c.score ?? 0);
                    const color = s >= 70 ? '#059669' : s >= 40 ? '#d97706' : '#dc2626';
                    const bg = s >= 70 ? '#dcfce7' : s >= 40 ? '#fef9c3' : '#fee2e2';
                    const chip = h('a', {
                        href: `#/companies/${c.company_id}`,
                        className: 'matrix-chip',
                        style: `border-color:${color};background:${bg};color:${color};font-size:0.65rem;padding:1px 6px`,
                        title: `${c.company_name}${c.tier ? ' ('+c.tier+')' : ''}\nRelationsscore: ${s}/100`
                    },
                        h('span', { className: 'matrix-chip-dot', style: `background:${color};width:6px;height:6px` }),
                        h('span', { className: 'matrix-chip-name' }, c.company_name)
                    );
                    cellInner.appendChild(chip);
                }
                if (cellCompanies.length === 0) {
                    cellInner.appendChild(h('span', { className: 'text-gray-300 text-xs italic' }, 'Ingen'));
                }
                cell.appendChild(cellInner);
                grid.appendChild(cell);
            }
        }
        wrapper.appendChild(grid);
        wrapper.appendChild(h('div', { className: 'text-center text-xs text-gray-400 mt-2' }, 'Salgsproces \u2192'));
    }

    rebuildGrid();
    return section;
}

// ─── Dashboard ───
async function renderDashboard(container) {
    container.innerHTML = '<div class="text-gray-400">Indlæser dashboard...</div>';
    const [dashData, ceoData, assistant] = await Promise.all([api.getDashboardAll(), api.getCeoOverview().catch(() => null), api.getAssistant().catch(() => null)]);
    const scores = dashData.scores;
    const stats = dashData.stats;
    const allTags = dashData.all_tags || [];

    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';

    container.appendChild(renderCeoOverview(dashData, ceoData));
    if (assistant) container.firstChild.insertBefore(renderAssistantFocus(assistant), container.firstChild.children[1] || null);

    // ─── Active Tenders ───
    const activeTenders = dashData.active_tenders || [];
    if (activeTenders.length > 0) {
        const tenderSection = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8' },
            h('div', { className: 'flex items-center justify-between mb-4' },
                h('div', { className: 'flex items-center gap-3' },
                    h('h2', { className: 'text-lg font-bold text-gray-900' }, 'Igangværende tilbud & udbud'),
                    h('span', { className: 'text-sm text-gray-400' }, `${activeTenders.length} aktive`)
                ),
                h('a', { href: '#/tenders', className: 'text-sm text-blue-600 hover:underline' }, 'Se alle')
            )
        );
        const tenderScroll = h('div', { className: 'overflow-y-auto', style: 'max-height:320px' });
        const tenderGrid = h('div', { className: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3' });
        for (const t of activeTenders) {
            const progress = t.total_sections > 0 ? Math.round(t.approved_sections / t.total_sections * 100) : 0;
            const today = new Date().toISOString().split('T')[0];
            const isOverdue = t.deadline && t.deadline < today;
            const daysLeft = t.deadline ? Math.ceil((new Date(t.deadline) - new Date()) / 86400000) : null;

            tenderGrid.appendChild(h('a', { href: `#/tenders/${t.id}`, className: 'block border border-gray-200 rounded-lg p-4 hover:border-blue-300 hover:shadow-sm transition-all' },
                h('div', { className: 'flex items-start justify-between mb-2' },
                    h('div', { className: 'font-semibold text-gray-900 truncate flex-1' }, t.company_name || t.title),
                    routeBadge(t),
                    h('span', { className: `inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${TENDER_STATUS_COLORS[t.status] || ''}` }, TENDER_STATUS_LABELS[t.status] || t.status)
                ),
                t.company_name ? h('div', { className: 'text-xs text-gray-500 truncate mb-2' }, t.title) : null,
                h('div', { className: 'flex items-center gap-3 text-xs' },
                    h('div', { className: 'flex-1' },
                        h('div', { className: 'w-full h-1.5 rounded-full bg-gray-200 overflow-hidden' },
                            h('div', { className: 'h-full rounded-full bg-blue-500', style: `width:${progress}%` })
                        )
                    ),
                    h('span', { className: 'text-gray-500' }, `${progress}%`),
                    t.deadline ? h('span', { className: isOverdue ? 'text-red-500 font-medium' : daysLeft <= 7 ? 'text-orange-500' : 'text-gray-400' },
                        isOverdue ? `${Math.abs(daysLeft)}d overskredet` : `${daysLeft}d tilbage`
                    ) : null
                ),
                h('div', { className: 'flex items-center justify-between mt-2 text-xs text-gray-400' },
                    h('span', {}, t.responsible_name || '-'),
                    t.estimated_value ? h('span', {}, t.estimated_value) : null
                )
            ));
        }
        tenderScroll.appendChild(tenderGrid);
        tenderSection.appendChild(tenderScroll);
        container.appendChild(tenderSection);
    }

    // ─── Active Tasks ───
    const activeTasks = dashData.active_tasks || [];
    if (activeTasks.length > 0) {
        const PRIORITY_COLORS = { high: 'bg-red-100 text-red-700', normal: 'bg-blue-50 text-blue-700', low: 'bg-gray-100 text-gray-500' };
        const PRIORITY_LABELS = { high: 'Høj', normal: 'Normal', low: 'Lav' };
        const TASK_STATUS_COLORS = { open: 'bg-gray-100 text-gray-600', in_progress: 'bg-blue-100 text-blue-700' };

        const taskSection = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8' },
            h('div', { className: 'flex items-center justify-between mb-4' },
                h('div', { className: 'flex items-center gap-3' },
                    h('h2', { className: 'text-lg font-bold text-gray-900' }, 'Åbne sager pr. virksomhed'),
                    h('span', { className: 'text-sm text-gray-400' }, `${activeTasks.length} aktive`)
                ),
                h('a', { href: '#/tasks', className: 'text-sm text-blue-600 hover:underline' }, 'Se alle')
            )
        );
        const taskScroll = h('div', { className: 'overflow-y-auto', style: 'max-height:400px' });
        const taskGrid = h('div', { className: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3' });
        for (const t of activeTasks) {
            const today = new Date().toISOString().split('T')[0];
            const isOverdue = t.due_date && t.due_date < today;
            const daysLeft = t.due_date ? Math.ceil((new Date(t.due_date) - new Date()) / 86400000) : null;
            taskGrid.appendChild(h('a', { href: `#/tasks/${t.id}`, className: 'block border border-gray-200 rounded-lg p-4 hover:border-blue-300 hover:shadow-sm transition-all' },
                h('div', { className: 'flex items-start justify-between gap-2 mb-1' },
                    h('div', { className: 'font-semibold text-gray-900 flex-1 truncate' }, t.company_name),
                    t.priority === 'high' ? h('span', { className: 'inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 flex-shrink-0' }, '↑ Høj') : null
                ),
                h('div', { className: 'text-xs text-gray-500 truncate mb-2' }, t.title),
                h('div', { className: 'flex items-center justify-between text-xs' },
                    h('div', { className: 'flex items-center gap-2' },
                        h('span', { className: `area-pill area-${t.area || 'salg'}` }, AREA_LABELS[t.area || 'salg']),
                        h('span', { className: `inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${TASK_STATUS_COLORS[t.status] || 'bg-gray-100 text-gray-600'}` }, STATUS_LABELS[t.status] || t.status)
                    ),
                    t.due_date ? h('span', { className: isOverdue ? 'text-red-500 font-medium' : daysLeft <= 3 ? 'text-orange-500' : 'text-gray-400' },
                        isOverdue ? `${Math.abs(daysLeft)}d overskredet` : daysLeft === 0 ? 'I dag' : `${daysLeft}d`
                    ) : null
                ),
                t.assigned_to_name ? h('div', { className: 'text-xs text-gray-400 mt-2' }, t.assigned_to_name) : null
            ));
        }
        taskScroll.appendChild(taskGrid);
        taskSection.appendChild(taskScroll);
        container.appendChild(taskSection);
    }

    // Recent Activity Feed — interactive period selector
    let _activityDays = 14;
    let _activityFromDate = null;
    const activitySection = h('div', {});
    container.appendChild(activitySection);

    async function reloadActivityFeed() {
        const params = _activityFromDate ? { from_date: _activityFromDate } : { days: _activityDays };
        const data = await api.getDashboardAll(params);
        activitySection.innerHTML = '';
        activitySection.appendChild(renderActivityFeed(
            data.recent_activities || [],
            _activityDays,
            _activityFromDate,
            async (days, fromDate) => { _activityDays = days; _activityFromDate = fromDate; await reloadActivityFeed(); }
        ));
    }
    await reloadActivityFeed();

    // ─── Customer Matrix (2D scatter) ───
    container.appendChild(renderCustomerMatrix(scores));

    // Average score
    if (stats.total > 0) {
        const scoreColor = stats.avg_score >= 80 ? '#059669' : stats.avg_score >= 50 ? '#d97706' : stats.avg_score >= 20 ? '#ea580c' : '#dc2626';
        container.appendChild(h('div', {
            className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-8 flex items-center gap-4 cursor-pointer hover:shadow-md transition-shadow',
            title: 'Klik for at se historisk udvikling',
            onClick: () => showScoreHistoryChart()
        },
            h('div', {},
                h('div', { className: 'text-sm text-gray-500' }, 'Gennemsnitlig relations-score'),
                h('div', { className: 'flex items-baseline gap-2' },
                    h('div', { className: 'text-2xl font-bold text-gray-900' }, `${stats.avg_score} / 100`),
                    h('div', { className: 'text-xs text-blue-500' }, '📈 Se historik')
                )
            ),
            h('div', { className: 'flex-1' },
                h('div', { className: 'score-bar' },
                    h('div', { className: 'score-bar-fill', style: `width:${stats.avg_score}%;background-color:${scoreColor}` })
                )
            )
        ));
    }

    // ─── Declining scores table ───
    const IMPORTANCE_ORDER = { meget_vigtig: 0, middel_vigtig: 1, lidt_vigtig: 2 };
    const decliningScores = scores.filter(s => s.previous_score != null && s.score < s.previous_score);
    decliningScores.sort((a, b) => (IMPORTANCE_ORDER[a.importance] ?? 3) - (IMPORTANCE_ORDER[b.importance] ?? 3));

    if (decliningScores.length > 0) {
        container.appendChild(h('div', { className: 'flex items-center gap-3 mb-4' },
            h('h2', { className: 'text-lg font-bold text-gray-900' }, 'Faldende relationsscorer'),
            h('span', { className: 'text-sm text-gray-400' }, `${decliningScores.length} virksomheder med faldende score — sorteret efter vigtighed`)
        ));
        const tableContainer = h('div', {});
        container.appendChild(tableContainer);
        renderScoreTable(tableContainer, decliningScores);
    } else {
        container.appendChild(h('div', { className: 'bg-green-50 border border-green-200 rounded-xl p-5 mb-8 text-center' },
            h('div', { className: 'text-green-700 font-medium' }, 'Ingen virksomheder med faldende relationsscorer'),
            h('div', { className: 'text-green-600 text-sm mt-1' }, 'Alle scorer er stabile eller stigende')
        ));
    }
}

// ─── CEO-overblik: Salg & marketing, Leverance, Økonomi ───
function parseAmount(v) {
    if (v == null || v === '') return 0;
    const str = String(v).toLowerCase();
    const num = parseFloat(str.replace(/[^\d,.\-]/g, '').replace(/\.(?=\d{3}(\D|$))/g, '').replace(',', '.'));
    if (!isFinite(num)) return 0;
    return /mio/.test(str) ? num * 1e6 : /t\.?kr|tkr|\bk\b/.test(str) ? num * 1e3 : num;
}
function formatAmount(n) {
    if (!n) return '0';
    if (n >= 1e6) return `${(n / 1e6).toLocaleString('da-DK', { maximumFractionDigits: 1 })} mio.`;
    if (n >= 1e3) return `${Math.round(n / 1e3).toLocaleString('da-DK')} t.`;
    return Math.round(n).toLocaleString('da-DK');
}
const AREA_ICONS = {
    salg: 'M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z',
    leverance: 'M3 7h11v9H3zM14 10h4l3 3v3h-7M7.5 19a1.5 1.5 0 100-3 1.5 1.5 0 000 3zm10 0a1.5 1.5 0 100-3 1.5 1.5 0 000 3z',
    oekonomi: 'M12 21a9 9 0 100-18 9 9 0 000 18zm0-14v10m3-8.5c-.7-.9-1.8-1.5-3-1.5-1.7 0-3 1-3 2.3 0 3.2 6 1.6 6 4.7 0 1.3-1.3 2.5-3 2.5-1.3 0-2.4-.6-3-1.5',
};

function renderCeoOverview(d, ceo) {
    const wrap = h('div', {});
    const today = new Date().toISOString().split('T')[0];
    const tasks = d.active_tasks || [];
    const tenders = d.active_tenders || [];
    const summary = d.tender_summary || [];
    const done30 = Object.fromEntries((d.tasks_done_30d || []).map(r => [r.area, r.cnt]));
    const stats = d.stats || {};
    const areaOf = t => t.area || 'salg';
    const overdue = t => t.due_date && t.due_date < today;

    const byArea = {};
    for (const k of Object.keys(AREA_LABELS)) {
        const list = tasks.filter(t => areaOf(t) === k);
        byArea[k] = {
            open: list.length,
            overdue: list.filter(overdue).length,
            high: list.filter(t => t.priority === 'high' || t.priority === 'urgent').length,
            companies: new Set(list.map(t => t.company_id)).size,
            done30: done30[k] || 0,
        };
    }
    const overdueTenders = tenders.filter(t => t.deadline && t.deadline < today);
    const pipeline = tenders.reduce((sum, t) => sum + parseAmount(t.estimated_value), 0);
    const won = summary.filter(t => t.status === 'won');
    const lost = summary.filter(t => t.status === 'lost' || t.status === 'dropped');
    const wonValue = won.reduce((sum, t) => sum + parseAmount(t.estimated_value), 0);
    const decided = won.length + lost.length;
    const hitRate = decided ? Math.round(won.length / decided * 100) : null;

    // Header
    const now = new Date();
    const dateTxt = now.toLocaleDateString('da-DK', { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric' });
    wrap.appendChild(h('div', { className: 'ov-head' },
        h('h1', {}, 'Overblik'),
        h('div', { className: 'ov-meta' },
            `${dateTxt.charAt(0).toUpperCase()}${dateTxt.slice(1)}`, ' · ',
            h('span', { className: 'live-dot' }),
            `Opdateret ${now.toLocaleTimeString('da-DK', { hour: '2-digit', minute: '2-digit' })}`)
    ));

    const kpi = (v, l, sub, cls, href) => h('a', { className: `kpi ${cls || ''}`, href: href || '#/' },
        h('div', { className: 'kpi-v' }, v), h('div', { className: 'kpi-l' }, l), h('div', { className: 'kpi-s' }, sub));
    const areaCol = (key, label, tiles) => h('div', { className: 'ov-area' },
        h('a', { className: 'ov-area-head', href: `#/area/${key}` },
            h('span', { className: 'ov-ic', style: `background:var(--area-${key}-soft);color:var(--area-${key})`,
                innerHTML: `<svg fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${AREA_ICONS[key]}"/></svg>` }),
            AREA_LABELS[key],
            h('span', { className: 'ov-go' }, 'Åbn →')),
        h('div', { className: 'ov-label' }, label),
        h('div', { className: 'kpi-grid' }, ...tiles));

    const A = byArea;
    wrap.appendChild(h('div', { className: 'ov-areas' },
        areaCol('salg', 'Pipeline & opfølgning', [
            kpi(String(tenders.length), 'Aktive tilbud', overdueTenders.length ? `${overdueTenders.length} over deadline` : 'alle inden for deadline', overdueTenders.length ? 'warn' : '', '#/tenders'),
            kpi(formatAmount(pipeline), 'Pipeline', 'kr. i aktive tilbud', '', '#/tenders'),
            kpi(String(A.salg.open), 'Åbne sager', `${A.salg.companies} virksomheder`, '', '#/area/salg'),
            kpi(String(A.salg.overdue), 'Forfaldne', 'kræver opfølgning', A.salg.overdue ? 'bad' : 'good', '#/area/salg'),
        ]),
        areaCol('leverance', 'Kunder & drift', [
            kpi(String(won.length), 'Vundne aftaler', 'kunder i leverance', 'good', '#/tenders'),
            kpi(String(A.leverance.open), 'Åbne sager', `${A.leverance.companies} virksomheder`, '', '#/area/leverance'),
            kpi(String(A.leverance.overdue), 'Forfaldne', 'frist overskredet', A.leverance.overdue ? 'bad' : 'good', '#/area/leverance'),
            kpi(String(A.leverance.done30), 'Løst', 'seneste 30 dage', '', '#/area/leverance'),
        ]),
        areaCol('oekonomi', 'Resultat & opfølgning', [
            kpi(formatAmount(wonValue), 'Vundet værdi', 'kr. i vundne tilbud', 'good', '#/tenders'),
            kpi(hitRate == null ? '–' : `${hitRate}%`, 'Hitrate', `${won.length} vundet · ${lost.length} tabt`, '', '#/tenders'),
            kpi(String(A.oekonomi.open), 'Åbne sager', `${A.oekonomi.companies} virksomheder`, '', '#/area/oekonomi'),
            kpi(String(A.oekonomi.overdue), 'Forfaldne', 'frist overskredet', A.oekonomi.overdue ? 'bad' : 'good', '#/area/oekonomi'),
        ])
    ));

    if (ceo) wrap.appendChild(renderGoalsStrip(ceo));

    // Relations banner (keeps the old score filters one click away)
    const lvl = (n, label, level) => h('a', { href: '#/companies', className: 'hover:underline', onClick: () => { _companiesLevelFilter = level; } }, `${n} ${label}`);
    wrap.appendChild(h('div', { className: 'ov-banner' },
        h('span', { className: 'ov-ic', style: 'width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;background:var(--area-salg-soft);color:var(--area-salg)',
            innerHTML: '<svg width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg>' }),
        h('b', {}, 'Relationer:'),
        h('span', {}, `${stats.total || 0} virksomheder · `),
        h('span', { className: 'text-green-700' }, lvl(stats.strong || 0, 'stærke', 'staerk')), ' · ',
        h('span', { className: 'text-yellow-700' }, lvl(stats.good || 0, 'gode', 'god')), ' · ',
        h('span', { className: 'text-orange-700' }, lvl(stats.weak || 0, 'svage', 'svag')), ' · ',
        h('span', { className: 'text-red-600 font-semibold' }, lvl(stats.cold || 0, 'kolde', 'kold')),
        h('span', { className: 'text-gray-400 text-sm' }, `gns. score ${stats.avg_score || 0}/100`),
        h('a', { href: '#/companies', className: 'ov-go' }, 'Se virksomheder →')
    ));

    // Requires action + flow
    const actions = [
        ...tasks.filter(overdue).map(t => ({ days: Math.ceil((new Date(today) - new Date(t.due_date)) / 86400000), co: t.company_name, sub: t.title, area: areaOf(t), href: `#/tasks/${t.id}` })),
        ...overdueTenders.map(t => ({ days: Math.ceil((new Date(today) - new Date(t.deadline)) / 86400000), co: t.company_name, sub: `Tilbud: ${t.title}`, area: 'salg', href: `#/tenders/${t.id}` })),
    ].sort((a, b) => b.days - a.days);
    if (ceo) {
        for (const a of ceo.open_actions.filter(a => a.kind === 'aktion' && a.due_date && a.due_date < today)) {
            actions.push({ days: Math.ceil((new Date(today) - new Date(a.due_date)) / 86400000), co: `Aktion · ${a.owner || 'ingen ansvarlig'}`, sub: a.title, area: a.area === 'tvaers' ? 'salg' : a.area, href: a.goal_id ? `#/goals/${a.goal_id}` : '#/meetings' });
        }
        actions.sort((a, b) => b.days - a.days);
    }
    const highOpen = tasks.filter(t => !overdue(t) && (t.priority === 'high' || t.priority === 'urgent'))
        .map(t => ({ days: null, co: t.company_name, sub: t.title, area: areaOf(t), href: `#/tasks/${t.id}` }));
    const goalAlerts = ceo ? ceo.goals.filter(g => g.status === 'off_track').map(g => ({ days: null, goal: true, co: `Mål bagud · ${g.owner_role || ''}`, sub: g.title, area: g.area === 'tvaers' ? 'salg' : g.area, href: `#/goals/${g.id}` })) : [];
    const actionList = [...goalAlerts, ...actions, ...highOpen].slice(0, 10);

    const actPanel = h('div', { className: 'ov-panel' },
        h('h2', {}, h('span', { className: 'ov-dot' }), 'Kræver handling',
            h('span', { className: 'text-sm font-normal text-gray-400' }, `${goalAlerts.length} mål bagud · ${actions.length} over frist · ${highOpen.length} høj prioritet`)));
    if (actionList.length === 0) {
        actPanel.appendChild(h('div', { className: 'text-gray-400 text-sm py-6 text-center' }, 'Intet forfaldent — godt gået.'));
    }
    for (const a of actionList) {
        actPanel.appendChild(h('a', { className: 'act-row', href: a.href },
            h('span', { className: `area-pill area-${a.area}`, style: 'padding:2px 8px', title: AREA_LABELS[a.area] }, ''),
            h('div', { className: 'min-w-0' },
                h('div', { className: 'act-co truncate' }, a.co),
                h('div', { className: 'act-sub truncate' }, a.sub)),
            h('span', { className: 'act-tag', style: `color:${a.days || a.goal ? 'var(--bad)' : 'var(--warn)'}` }, a.days ? `${a.days}d over frist` : a.goal ? 'Bagud' : 'Høj prioritet')
        ));
    }

    const maxOpen = Math.max(1, ...Object.values(byArea).map(x => x.open));
    const flowPanel = h('div', { className: 'ov-panel' }, h('h2', {}, 'Åbne sager pr. område'),
        ...Object.keys(AREA_LABELS).map(k => h('a', { href: `#/area/${k}`, className: 'flow-row', style: `--fc:var(--area-${k})` },
            h('span', { className: 'text-gray-800' }, AREA_LABELS[k]),
            h('div', { className: 'flow-bar' }, h('i', { style: `width:${Math.max(2, byArea[k].open / maxOpen * 100)}%` })),
            h('span', { className: 'flow-n' }, String(byArea[k].open)))),
        h('div', { className: 'text-sm text-gray-500 mt-4' },
            `${tasks.length} åbne sager hos ${new Set(tasks.map(t => t.company_id)).size} virksomheder · `,
            `${Object.values(byArea).reduce((s2, x) => s2 + x.done30, 0)} løst de seneste 30 dage`)
    );
    wrap.appendChild(h('div', { className: 'grid grid-cols-1 lg:grid-cols-2 gap-5 mb-8' }, flowPanel, actPanel));
    return wrap;
}

function renderActivityFeed(activities, currentDays, currentFromDate, onPeriodChange) {
    const section = h('div', { className: 'mb-8' });

    const ACTIVITY_ICONS = {
        email: '\u{1F4E7}', phone: '\u{1F4DE}', meeting: '\u{1F91D}', meeting_task: '\u{1F4CB}', meeting_event: '\u{1F389}', campaign: '\u{1F4E2}', linkedin: '\u{1F4BC}',
        post: '\u{1F4DD}', comment: '\u{1F4AC}', like: '\u{1F44D}', share: '\u{1F501}', article: '\u{1F4F0}', follow: '\u{1F514}',
        opkald: '\u{1F4DE}', tilbud: '\u{1F4B0}', moede: '\u{1F91D}', opfølgning: '\u{1F504}', demo: '\u{1F4BB}', kontrakt: '\u{1F4C4}', generelt: '\u{2705}',
        note: '\u{1F4DD}',
        create: '\u{1F4C4}', update: '\u{1F504}',
        won: '\u{1F3C6}', lost: '\u{1F614}', dropped: '\u{274C}'
    };
    const ACTIVITY_LABELS = {
        email: 'Email', phone: 'Opkald', meeting: 'M\u00f8de', meeting_task: 'Opgavem\u00f8de', meeting_event: 'Arrangement', campaign: 'Kampagne', linkedin: 'LinkedIn',
        post: 'Opslag', comment: 'Kommentar', like: 'Like', share: 'Deling', article: 'Artikel', follow: 'F\u00f8lger',
        opkald: 'Opkald', tilbud: 'Tilbud', moede: 'M\u00f8de', opfølgning: 'Opf\u00f8lgning', demo: 'Demo', kontrakt: 'Kontrakt', generelt: 'Opgave', note: 'Note'
    };
    const SOURCE_COLORS = {
        interaction: 'bg-blue-100 text-blue-700',
        task: 'bg-green-100 text-green-700',
        task_note: 'bg-green-50 text-green-600',
        tender: 'bg-amber-100 text-amber-700',
        tender_note: 'bg-orange-50 text-orange-600',
        contact: 'bg-teal-100 text-teal-700',
        linkedin_activity: 'bg-purple-100 text-purple-700',
        linkedin_engagement: 'bg-indigo-100 text-indigo-700'
    };
    const TENDER_STATUS_DA = { draft: 'Kladde', in_progress: 'I gang', submitted: 'Indsendt', won: 'Vundet', lost: 'Tabt', dropped: 'Droppet' };
    const TENDER_STATUS_COLORS_BADGE = { won: 'bg-green-100 text-green-700', lost: 'bg-red-100 text-red-600', dropped: 'bg-orange-100 text-orange-600' };

    const periodLabel = currentFromDate ? `Fra ${currentFromDate}` :
        currentDays === 7 ? 'Seneste uge' :
        currentDays === 14 ? 'Seneste 14 dage' :
        currentDays === 30 ? 'Seneste m\u00e5ned' : `Seneste ${currentDays} dage`;

    // Header + period buttons
    const periodBtns = h('div', { className: 'flex gap-1 items-center flex-wrap' });
    for (const [label, days] of [['Uge', 7], ['14 dage', 14], ['M\u00e5ned', 30]]) {
        const active = !currentFromDate && currentDays === days;
        periodBtns.appendChild(h('button', {
            className: `px-2 py-1 rounded text-xs font-medium border ${active ? 'bg-gray-800 text-white border-gray-800' : 'bg-white text-gray-600 border-gray-300 hover:border-gray-500'}`,
            onClick: () => onPeriodChange && onPeriodChange(days, null)
        }, label));
    }
    // Custom date picker
    const fromInput = h('input', { type: 'date', className: 'border border-gray-300 rounded px-2 py-0.5 text-xs', value: currentFromDate || '' });
    fromInput.addEventListener('change', () => {
        if (fromInput.value) onPeriodChange && onPeriodChange(null, fromInput.value);
    });
    periodBtns.appendChild(h('span', { className: 'text-xs text-gray-400 ml-1' }, 'Fra:'));
    periodBtns.appendChild(fromInput);

    section.appendChild(h('div', { className: 'flex items-center justify-between mb-4 flex-wrap gap-2' },
        h('div', { className: 'flex items-center gap-3' },
            h('div', { className: 'text-xl' }, '\u{1F4CB}'),
            h('h2', { className: 'text-lg font-bold text-gray-900' }, `Aktiviteter \u2014 ${periodLabel}`),
            h('span', { className: 'text-sm text-gray-400' }, `${activities.length} aktiviteter`)
        ),
        periodBtns
    ));

    // Group by day
    const today = new Date(); today.setHours(0,0,0,0);
    const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
    const DAYS_DA = ['S\u00f8n', 'Man', 'Tir', 'Ons', 'Tor', 'Fre', 'L\u00f8r'];
    const MONTHS_DA = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

    function formatDayHeader(dateStr) {
        const d = new Date(dateStr + 'T00:00:00');
        if (d.getTime() === today.getTime()) return 'I dag';
        if (d.getTime() === yesterday.getTime()) return 'I g\u00e5r';
        return `${DAYS_DA[d.getDay()]} ${d.getDate()}. ${MONTHS_DA[d.getMonth()]}`;
    }

    const grouped = {};
    for (const a of activities) {
        const day = (a.activity_date || '').substring(0, 10);
        if (!grouped[day]) grouped[day] = [];
        grouped[day].push(a);
    }

    const sortedDays = Object.keys(grouped).sort((a, b) => b.localeCompare(a));
    const timeline = h('div', { className: 'activity-timeline' });

    if (activities.length === 0) {
        timeline.appendChild(h('div', { className: 'text-gray-400 text-sm italic p-4' }, 'Ingen aktiviteter i perioden.'));
    }

    for (const day of sortedDays) {
        const items = grouped[day];
        timeline.appendChild(h('div', { className: 'activity-day-header' },
            h('div', { className: 'activity-day-dot' }),
            h('span', { className: 'font-semibold text-sm text-gray-700' }, formatDayHeader(day))
        ));

        for (const item of items) {
            const icon = ACTIVITY_ICONS[item.sub_type] || '\u{1F4CC}';
            const label = ACTIVITY_LABELS[item.sub_type] || item.sub_type;

            const tenderStatus = item.source === 'tender' && item.sub_type === 'update' ? item.subject?.split(' → ')[1] : null;
            const sourceLabel = item.source === 'interaction' ? label
                : item.source === 'task' ? `Sag: ${label}`
                : item.source === 'task_note' ? 'Sag: Note'
                : item.source === 'tender' ? (
                    item.sub_type === 'create' ? 'Nyt tilbud' :
                    tenderStatus === 'won' ? '🏆 Vundet' :
                    tenderStatus === 'lost' ? 'Tabt' :
                    tenderStatus === 'dropped' ? 'Droppet' :
                    `Tilbud: ${TENDER_STATUS_DA[tenderStatus] || 'Opdateret'}`)
                : item.source === 'tender_note' ? 'Tilbud: Note'
                : item.source === 'contact' ? 'Ny kontakt'
                : item.source === 'linkedin_activity' ? `LinkedIn: ${label}`
                : `Engagement: ${label}`;
            const overrideColor = item.source === 'tender' && tenderStatus === 'won' ? 'bg-green-100 text-green-700'
                : item.source === 'tender' && tenderStatus === 'lost' ? 'bg-red-100 text-red-600'
                : item.source === 'tender' && tenderStatus === 'dropped' ? 'bg-orange-100 text-orange-600'
                : null;

            // Determine navigation target
            let navTarget;
            if (item.source === 'task' || item.source === 'task_note') {
                navTarget = `#/tasks/${item.entity_id}`;
            } else if (item.source === 'tender' || item.source === 'tender_note') {
                navTarget = `#/tenders/${item.entity_id}`;
            } else {
                navTarget = `#/companies/${item.company_id}`;
            }
            const badgeColor = overrideColor || SOURCE_COLORS[item.source] || 'bg-gray-100 text-gray-700';

            const detailLine = h('div', { className: 'text-xs text-gray-500 mt-0.5' });
            const parts = [];
            if (item.user_name) parts.push(item.user_name);
            if (item.contact_name) parts.push(item.contact_name);
            if (parts.length) detailLine.appendChild(document.createTextNode(parts.join(' \u2192 ')));
            if (item.subject) {
                if (parts.length) detailLine.appendChild(document.createTextNode(': '));
                let subjectText = item.subject.length > 80 ? item.subject.slice(0, 80) + '…' : item.subject;
                // Translate tender status keys in "Title → status" format
                if (item.source === 'tender' && item.sub_type === 'update') {
                    const arrowIdx = subjectText.lastIndexOf(' → ');
                    if (arrowIdx !== -1) {
                        const statusKey = subjectText.slice(arrowIdx + 3);
                        subjectText = subjectText.slice(0, arrowIdx + 3) + (TENDER_STATUS_DA[statusKey] || statusKey);
                    }
                }
                detailLine.appendChild(h('span', { className: 'text-gray-400' }, subjectText));
            }

            timeline.appendChild(h('div', {
                className: 'activity-item cursor-pointer',
                onClick: () => { location.hash = navTarget; }
            },
                h('div', { className: 'activity-item-icon' }, icon),
                h('div', { className: 'flex-1 min-w-0' },
                    h('div', { className: 'flex items-center gap-2' },
                        h('span', { className: 'font-semibold text-gray-900 text-sm' }, item.company_name),
                        h('span', { className: `activity-type-badge ${badgeColor}` }, sourceLabel)
                    ),
                    detailLine
                )
            ));
        }
    }

    section.appendChild(h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 activity-feed-scroll' }, timeline));
    return section;
}

let _companiesLevelFilter = null; // set by dashboard stat card clicks
let dashboardFilters = { sector: '', rating: '', tag: '', tier: '' };
let scoreTableSortKey = 'rating';
let scoreTableSortAsc = true;

function applyDashboardFilter(e, allScores, tableContainer) {
    const btn = e.target.closest('[data-filter]') || e.target;
    const filterType = btn.getAttribute('data-filter');
    const value = btn.getAttribute('data-value');
    dashboardFilters[filterType] = value;

    btn.parentElement.querySelectorAll(`[data-filter="${filterType}"]`).forEach(b => {
        b.className = 'px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-600 hover:bg-gray-200';
    });
    btn.className = `px-3 py-1 rounded-full text-sm font-medium ${filterType === 'sector' ? 'bg-gray-900' : filterType === 'tier' ? 'bg-purple-700' : 'bg-gray-700'} text-white`;

    let filtered = allScores;
    if (dashboardFilters.sector) filtered = filtered.filter(s => s.sector === dashboardFilters.sector);
    if (dashboardFilters.rating) filtered = filtered.filter(s => s.rating === dashboardFilters.rating);
    if (dashboardFilters.tier) filtered = filtered.filter(s => s.tier === dashboardFilters.tier);
    if (dashboardFilters.tag) filtered = filtered.filter(s => (s.tags || []).some(t => String(t.id) === dashboardFilters.tag));
    renderScoreTable(tableContainer, filtered);
}

function renderScoreTable(container, scores) {
    container.innerHTML = '';
    if (scores.length === 0) {
        container.appendChild(h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center text-gray-400' },
            'Ingen virksomheder fundet.'));
        return;
    }

    // Sort
    const ratingOrder = { A: 0, B: 1, C: 2 };
    const sorted = [...scores].sort((a, b) => {
        let cmp = 0;
        if (scoreTableSortKey === 'rating') {
            cmp = (ratingOrder[a.rating || 'C'] || 2) - (ratingOrder[b.rating || 'C'] || 2);
        } else if (scoreTableSortKey === 'name') {
            cmp = (a.company_name || '').localeCompare(b.company_name || '', 'da');
        } else if (scoreTableSortKey === 'score') {
            cmp = a.score - b.score;
        } else if (scoreTableSortKey === 'contacts') {
            cmp = a.total_contacts - b.total_contacts;
        } else if (scoreTableSortKey === 'last') {
            cmp = (a.days_since_last ?? 9999) - (b.days_since_last ?? 9999);
        }
        return scoreTableSortAsc ? cmp : -cmp;
    });

    const wrapper = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto' });
    const tbl = document.createElement('table');
    tbl.className = 'w-full text-sm';

    // Sortable header
    const si = (key) => scoreTableSortKey === key ? (scoreTableSortAsc ? ' \u25B2' : ' \u25BC') : '';
    const hdrClick = (key) => () => {
        if (scoreTableSortKey === key) scoreTableSortAsc = !scoreTableSortAsc;
        else { scoreTableSortKey = key; scoreTableSortAsc = true; }
        renderScoreTable(container, scores);
    };
    const thead = document.createElement('thead');
    const headerRow = h('tr', { className: 'bg-gray-50 border-b text-xs font-medium text-gray-500 uppercase tracking-wider' },
        h('th', { className: 'text-left px-4 py-3 cursor-pointer hover:text-gray-700 select-none', onClick: hdrClick('name') }, 'Virksomhed' + si('name')),
        h('th', { className: 'text-left px-2 py-3 cursor-pointer hover:text-gray-700 select-none', style: 'min-width:120px', onClick: hdrClick('score') }, 'Score' + si('score')),
        h('th', { className: 'text-center px-2 py-3 w-16' }, 'Status'),
        h('th', { className: 'text-center px-2 py-3 w-14 cursor-pointer hover:text-gray-700 select-none', onClick: hdrClick('contacts') }, 'Kont.' + si('contacts')),
        h('th', { className: 'text-center px-2 py-3 w-14 cursor-pointer hover:text-gray-700 select-none', onClick: hdrClick('last') }, 'Sidst' + si('last')),
        h('th', { className: 'text-left px-2 py-3' }, 'Ansvarlig')
    );
    thead.appendChild(headerRow);
    tbl.appendChild(thead);

    const tbody = document.createElement('tbody');
    for (const s of sorted) {
        const tr = document.createElement('tr');
        tr.className = 'border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors';
        tr.onclick = () => { location.hash = `#/companies/${s.company_id}`; };
        const tagsHtml = (s.tags || []).map(t => `<span class="tag-badge" style="background-color:${t.color || '#6b7280'};font-size:0.6rem;padding:1px 5px">${t.name}</span>`).join(' ');

        // Score delta indicator
        let deltaHtml = '';
        if (s.previous_score != null) {
            const delta = Math.round(s.score - s.previous_score);
            if (delta > 0) deltaHtml = `<span class="score-up">\u25B2 +${delta}</span>`;
            else if (delta < 0) deltaHtml = `<span class="score-down">\u25BC ${delta}</span>`;
        }

        tr.innerHTML = `
            <td class="px-4 py-3">
                <div class="font-medium text-gray-900">${s.company_name}</div>
                ${s.tier ? `<span class="text-xs px-1.5 py-0.5 rounded ${TIER_COLORS[s.tier] || 'bg-gray-100 text-gray-600'}">${s.tier}</span>` : ''}
                ${s.sector ? `<span class="badge badge-${s.sector} text-xs">${sectorLabel(s.sector)}</span>` : ''}
                ${tagsHtml}
            </td>
            <td class="px-2 py-3">
                <div class="flex items-center gap-2">
                    <div class="flex-1 score-bar"><div class="score-bar-fill" style="width:${s.score}%;background-color:${scoreColor(s.level)}"></div></div>
                    <span class="font-semibold" style="color:${scoreColor(s.level)}">${Math.round(s.score)}</span>
                    ${deltaHtml}
                </div>
            </td>
            <td class="text-center px-2 py-3"><span class="badge ${scoreBg(s.level)}">${s.level}</span></td>
            <td class="text-center px-2 py-3 text-gray-600">${s.contacted_count}/${s.total_contacts}</td>
            <td class="text-center px-2 py-3 ${s.days_since_last != null && s.days_since_last > 60 ? 'text-red-500 font-medium' : 'text-gray-500'}">${s.days_since_last != null ? s.days_since_last + 'd' : '-'}</td>
            <td class="px-2 py-3 text-gray-600 truncate max-w-[120px]">${s.account_manager_name || '-'}</td>
        `;
        tbody.appendChild(tr);
    }
    tbl.appendChild(tbody);
    wrapper.appendChild(tbl);
    container.appendChild(wrapper);
}

// ─── Companies ───
async function renderCompanies(container) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    // Consume level filter set by dashboard stat card click
    const initialLevelFilter = _companiesLevelFilter;
    _companiesLevelFilter = null;

    const fetchPromises = [api.getCompanies()];
    if (initialLevelFilter) fetchPromises.push(api.getDashboardAll());
    const [companies, dashData] = await Promise.all(fetchPromises);
    const levelScores = dashData ? dashData.scores : null;

    // Build set of company IDs matching the level filter
    let levelFilterIds = null;
    const LEVEL_LABELS = { staerk: 'Stærke', god: 'Gode', svag: 'Svage', kold: 'Kolde' };
    if (initialLevelFilter && levelScores) {
        levelFilterIds = new Set(levelScores.filter(s => s.level === initialLevelFilter).map(s => s.company_id));
    }

    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';

    container.appendChild(h('div', { className: 'flex justify-between items-center mb-6' },
        h('div', {},
            h('h1', { className: 'text-2xl font-bold text-gray-900' }, 'Virksomheder'),
            h('p', { className: 'text-gray-500 mt-1' }, `${companies.length} virksomheder registreret`)
        ),
        h('button', {
            className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors font-medium',
            onClick: () => showCompanyForm()
        }, '+ Tilføj virksomhed')
    ));

    if (companies.length === 0) {
        container.appendChild(h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center text-gray-400' }, 'Ingen virksomheder endnu.'));
        return;
    }

    // Collect all unique tags from companies
    const allTagsMap = {};
    for (const c of companies) {
        for (const t of (c.tags || [])) {
            allTagsMap[t.id] = t;
        }
    }
    const allCompanyTags = Object.values(allTagsMap).sort((a, b) => a.name.localeCompare(b.name));

    // Level filter banner (from dashboard click)
    let activeLevelFilterIds = levelFilterIds;
    if (activeLevelFilterIds) {
        const banner = h('div', { className: 'bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 mb-4 flex items-center justify-between' },
            h('span', { className: 'text-sm text-blue-700' }, `Filtreret: ${LEVEL_LABELS[initialLevelFilter] || initialLevelFilter} virksomheder (${activeLevelFilterIds.size})`),
            h('button', { className: 'text-blue-500 hover:text-blue-700 text-sm', onClick: () => {
                activeLevelFilterIds = null;
                banner.remove();
                renderGrid();
            }}, 'Ryd filter \u00d7')
        );
        container.appendChild(banner);
    }

    // Search + tier + tag filter
    let filterTier = '';
    let filterTagId = null;
    let searchQ = '';
    const countLabel = h('span', { className: 'text-sm text-gray-400' }, `Viser ${companies.length} af ${companies.length}`);
    const searchInput = h('input', {
        type: 'text', placeholder: 'Filtrer virksomheder...',
        className: 'border border-gray-300 rounded-lg px-3 py-2 text-sm w-64'
    });
    const tierBtns = h('div', { className: 'flex gap-1' });
    for (const t of ['Alle', 'T1', 'T2', 'T3', 'T4', 'EM']) {
        tierBtns.appendChild(h('button', {
            className: `px-2 py-1 rounded text-xs font-medium ${t === 'Alle' ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`,
            onClick: (e) => {
                filterTier = t === 'Alle' ? '' : t;
                tierBtns.querySelectorAll('button').forEach(b => b.className = 'px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-600 hover:bg-gray-200');
                e.target.className = 'px-2 py-1 rounded text-xs font-medium bg-gray-900 text-white';
                renderGrid();
            }
        }, t));
    }
    searchInput.addEventListener('input', () => { searchQ = searchInput.value.toLowerCase(); renderGrid(); });

    // Tag filter bar
    const tagBar = h('div', { className: 'flex flex-wrap gap-1' });
    if (allCompanyTags.length > 0) {
        const allBtn = h('button', {
            className: 'px-2 py-1 rounded text-xs font-medium bg-gray-900 text-white',
            onClick: () => {
                filterTagId = null;
                tagBar.querySelectorAll('button').forEach(b => {
                    b.className = 'px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-600 hover:bg-gray-200';
                    b.style.backgroundColor = '';
                    b.style.color = '';
                });
                allBtn.className = 'px-2 py-1 rounded text-xs font-medium bg-gray-900 text-white';
                renderGrid();
            }
        }, 'Alle tags');
        tagBar.appendChild(allBtn);
        for (const tag of allCompanyTags) {
            tagBar.appendChild(h('button', {
                className: 'px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-600 hover:bg-gray-200',
                onClick: (e) => {
                    filterTagId = tag.id;
                    tagBar.querySelectorAll('button').forEach(b => {
                        b.className = 'px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-600 hover:bg-gray-200';
                        b.style.backgroundColor = '';
                        b.style.color = '';
                    });
                    e.target.style.backgroundColor = tag.color || '#6b7280';
                    e.target.style.color = '#fff';
                    e.target.className = 'px-2 py-1 rounded text-xs font-medium';
                    renderGrid();
                }
            }, tag.name));
        }
    }

    container.appendChild(h('div', { className: 'flex flex-wrap items-center gap-3 mb-4' }, searchInput, tierBtns, countLabel));
    if (allCompanyTags.length > 0) {
        container.appendChild(h('div', { className: 'flex flex-wrap items-center gap-2 mb-4' },
            h('span', { className: 'text-xs text-gray-500' }, 'Tags:'), tagBar
        ));
    }

    const grid = h('div', { className: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4' });
    container.appendChild(grid);

    function renderGrid() {
        grid.innerHTML = '';
        const filtered = companies.filter(c => {
            if (activeLevelFilterIds && !activeLevelFilterIds.has(c.id)) return false;
            if (filterTier && c.tier !== filterTier) return false;
            if (filterTagId && !(c.tags || []).some(t => t.id === filterTagId)) return false;
            if (searchQ && !c.name.toLowerCase().includes(searchQ) && !(c.city || '').toLowerCase().includes(searchQ)
                && !(c.tags || []).some(t => t.name.toLowerCase().includes(searchQ))) return false;
            return true;
        });
        countLabel.textContent = `Viser ${filtered.length} af ${companies.length}`;
        for (const c of filtered) {
            const services = ['has_el','has_gas','has_vand','has_varme','has_spildevand','has_affald']
                .filter(k => c[k]).map(k => SERVICE_LABELS[k]);
            const cTags = c.tags || [];
            grid.appendChild(h('a', {
                href: `#/companies/${c.id}`,
                className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 hover:shadow-md transition-shadow cursor-pointer block'
            },
                h('div', { className: 'flex justify-between items-start mb-2' },
                    h('div', {},
                        h('h3', { className: 'font-semibold text-gray-900 text-sm' }, c.name),
                        c.is_purchasing_group ? h('span', { className: 'route-pill mt-1' }, 'Indkøbsfællesskab') : null,
                        ...(c.memberships || []).map(g => h('span', { className: 'route-pill mt-1 mr-1' }, `Medlem af ${g.name}`))),
                    h('div', { className: 'flex gap-1 flex-shrink-0' },
                        c.tier ? h('span', { className: `text-xs px-1.5 py-0.5 rounded ${TIER_COLORS[c.tier] || 'bg-gray-100 text-gray-600'}` }, c.tier) : null,
                        c.rating ? h('span', { className: `badge badge-${c.rating}` }, c.rating) : null
                    )
                ),
                cTags.length > 0 ? h('div', { className: 'flex flex-wrap gap-1 mb-1' },
                    ...cTags.map(t => h('span', {
                        className: 'tag-badge cursor-pointer',
                        style: `background-color:${t.color || '#6b7280'};font-size:0.65rem;padding:1px 6px`,
                        onClick: (e) => {
                            e.preventDefault(); e.stopPropagation();
                            filterTagId = t.id;
                            tagBar.querySelectorAll('button').forEach(b => {
                                b.className = 'px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-600 hover:bg-gray-200';
                                b.style.backgroundColor = ''; b.style.color = '';
                            });
                            const tagBtn = [...tagBar.querySelectorAll('button')].find(b => b.textContent === t.name);
                            if (tagBtn) { tagBtn.style.backgroundColor = t.color || '#6b7280'; tagBtn.style.color = '#fff'; tagBtn.className = 'px-2 py-1 rounded text-xs font-medium'; }
                            renderGrid();
                        }
                    }, t.name))
                ) : null,
                services.length > 0 ? h('div', { className: 'flex flex-wrap gap-1 mb-1' },
                    ...services.map(s => h('span', { className: 'text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded' }, s))
                ) : null,
                c.city ? h('p', { className: 'text-sm text-gray-500' }, `${c.zip_code || ''} ${c.city}`.trim()) : null,
                c.account_manager_name ? h('p', { className: 'text-xs text-gray-400 mt-1' }, `Ansvarlig: ${c.account_manager_name}`) : null
            ));
        }
    }
    renderGrid();
}

async function showCompanyForm(existing = null) {
    const isEdit = !!existing;
    let users = [];
    try { users = await api.getUsers(); } catch(e) {}

    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const data = Object.fromEntries(fd.entries());
        if (!data.sector) data.sector = null;
        data.account_manager_id = data.account_manager_id ? parseInt(data.account_manager_id) : null;
        for (const k of ['score_cxo','score_kontaktfrekvens','score_kontaktbredde','score_kendskab','score_historik']) {
            data[k] = parseInt(data[k]) || 0;
        }
        for (const k of ['has_el','has_gas','has_vand','has_varme','has_spildevand','has_affald']) {
            data[k] = e.target.querySelector(`[name="${k}"]`).checked ? 1 : 0;
        }
        if (!data.tier) data.tier = null;
        if (!data.ejerform) data.ejerform = null;
        try {
            if (isEdit) await api.updateCompany(existing.id, data);
            else await api.createCompany(data);
            closeModal();
            router();
        } catch (err) { alert(err.message); }
    }},
        formField('Virksomhedsnavn *', 'name', existing?.name || '', 'text', true),
        h('div', { className: 'grid grid-cols-2 gap-3' },
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Sektor'),
                h('select', { name: 'sector', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    h('option', { value: '' }, 'Vælg sektor...'),
                    ...['el', 'vand', 'varme', 'multiforsyning', 'gas', 'spildevand', 'affald', 'e-mobilitet'].map(s =>
                        h('option', { value: s, ...(existing?.sector === s ? { selected:'' } : {}) }, sectorLabel(s))
                    )
                )
            ),
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Rating'),
                h('select', { name: 'rating', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    ...['A', 'B', 'C'].map(r =>
                        h('option', { value: r, ...((existing?.rating || 'C') === r ? { selected:'' } : {}) },
                            `${r}${r === 'A' ? ' - Must win' : r === 'B' ? ' - Vigtig' : ' - Nice to have'}`)
                    )
                )
            )
        ),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Account Ansvarlig'),
            h('select', { name: 'account_manager_id', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value: '' }, 'Vælg ansvarlig...'),
                ...users.map(u => h('option', { value: u.id, ...(existing?.account_manager_id == u.id ? { selected:'' } : {}) }, u.name))
            )
        ),
        h('div', { className: 'grid grid-cols-2 gap-3' },
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Vigtighed'),
                h('select', { name: 'importance', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    ...['meget_vigtig', 'middel_vigtig', 'lidt_vigtig'].map(v =>
                        h('option', { value: v, ...((existing?.importance || 'middel_vigtig') === v ? { selected:'' } : {}) },
                            v === 'meget_vigtig' ? 'Meget vigtig' : v === 'middel_vigtig' ? 'Middel vigtig' : 'Lidt vigtig'))
                )
            ),
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Salgsstadie'),
                h('select', { name: 'sales_stage', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    ...['tidlig_fase', 'aktiv_dialog', 'fremskreden'].map(v =>
                        h('option', { value: v, ...((existing?.sales_stage || 'tidlig_fase') === v ? { selected:'' } : {}) },
                            v === 'tidlig_fase' ? 'Tidlig fase' : v === 'aktiv_dialog' ? 'Aktiv dialog' : 'Fremskreden'))
                )
            )
        ),
        h('div', { className: 'grid grid-cols-2 gap-3' },
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Tier'),
                h('select', { name: 'tier', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    h('option', { value: '' }, 'Vælg tier...'),
                    ...['T1', 'T2', 'T3', 'T4', 'EM'].map(t =>
                        h('option', { value: t, ...(existing?.tier === t ? { selected:'' } : {}) }, tierLabel(t))
                    )
                )
            ),
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Ejerform'),
                h('select', { name: 'ejerform', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    h('option', { value: '' }, 'Vælg ejerform...'),
                    ...['a.m.b.a.', 'A/S', 'I/S', 'Kommunalt', 'Andet'].map(e =>
                        h('option', { value: e, ...(existing?.ejerform === e ? { selected:'' } : {}) }, e)
                    )
                )
            )
        ),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-2' }, 'Forsyningsarter'),
            h('div', { className: 'grid grid-cols-3 gap-2' },
                ...Object.entries(SERVICE_LABELS).map(([key, label]) =>
                    h('label', { className: 'flex items-center gap-2 text-sm text-gray-600' },
                        h('input', { type: 'checkbox', name: key, ...(existing?.[key] ? { checked: '' } : {}), className: 'rounded border-gray-300' }),
                        label
                    )
                )
            )
        ),
        formField('Est. kunder', 'est_kunder', existing?.est_kunder || ''),
        formField('Adresse', 'address', existing?.address || ''),
        h('div', { className: 'grid grid-cols-2 gap-3' },
            formField('Postnummer', 'zip_code', existing?.zip_code || ''),
            formField('By', 'city', existing?.city || '')
        ),
        formField('Website', 'website', existing?.website || ''),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Notater'),
            h('textarea', { name: 'notes', rows: '3', className: 'w-full border border-gray-300 rounded-lg px-3 py-2', value: existing?.notes || '' })
        ),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type:'button', className:'px-4 py-2 text-gray-600 hover:text-gray-800', onClick: closeModal }, 'Annuller'),
            h('button', { type:'submit', className:'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, isEdit ? 'Gem' : 'Opret')
        )
    );
    showModal(isEdit ? 'Rediger virksomhed' : 'Ny virksomhed', form);
}

// ─── Relation Score Form ───
function showManualScoreForm(company, score, onDone) {
    const params = [
        { key: 'score_kendskab_behov', label: 'Kendskab til behov', weight: '15%',
          desc: ['0-2: Kender ikke behov', '3-5: Overordnet kendskab', '6-10: Dyb indsigt i strategi'] },
        { key: 'score_workshops', label: 'Deltagelse i workshops', weight: '10%',
          desc: ['0-2: Ingen deltagelse', '3-5: Deltaget 1-2 gange', '6-10: Aktiv deltager'] },
        { key: 'score_marketing', label: 'Kender de os (marketing)', weight: '15%',
          desc: ['0-2: Ingen kendskab', '3-5: Kender os lidt', '6-10: Reagerer paa vores marketing'] },
    ];

    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const data = {};
        for (const p of params) data[p.key] = parseInt(form.querySelector(`[name="${p.key}"]`).value) || 0;
        data.importance = form.querySelector('[name="importance"]').value;
        data.sales_stage = form.querySelector('[name="sales_stage"]').value;
        try {
            await api.updateCompany(company.id, data);
            closeModal();
            onDone();
        } catch (err) { alert(err.message); }
    }},
        h('div', { className: 'grid grid-cols-2 gap-3' },
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Vigtighed'),
                h('select', { name: 'importance', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    ...['meget_vigtig', 'middel_vigtig', 'lidt_vigtig'].map(v =>
                        h('option', { value: v, ...((company.importance || 'middel_vigtig') === v ? { selected:'' } : {}) },
                            v === 'meget_vigtig' ? 'Meget vigtig' : v === 'middel_vigtig' ? 'Middel vigtig' : 'Lidt vigtig'))
                )
            ),
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Salgsstadie'),
                h('select', { name: 'sales_stage', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    ...['tidlig_fase', 'aktiv_dialog', 'fremskreden'].map(v =>
                        h('option', { value: v, ...((company.sales_stage || 'tidlig_fase') === v ? { selected:'' } : {}) },
                            v === 'tidlig_fase' ? 'Tidlig fase' : v === 'aktiv_dialog' ? 'Aktiv dialog' : 'Fremskreden'))
                )
            )
        ),
        ...params.map(p => {
            const val = company[p.key] || 0;
            return h('div', { className: 'bg-gray-50 rounded-lg p-3' },
                h('div', { className: 'flex items-center justify-between mb-1' },
                    h('label', { className: 'text-sm font-medium text-gray-700' }, `${p.label} (${p.weight})`),
                    h('span', { className: 'text-sm font-bold text-gray-900 param-val' }, String(val))
                ),
                h('input', { type: 'range', name: p.key, min: '0', max: '10', value: String(val),
                    className: 'w-full accent-blue-600', onInput: (ev) => {
                        ev.target.closest('.bg-gray-50').querySelector('.param-val').textContent = ev.target.value;
                    }
                }),
                h('div', { className: 'flex justify-between text-xs text-gray-400 mt-1' },
                    ...p.desc.map(d => h('span', {}, d))
                )
            );
        }),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type:'button', className:'px-4 py-2 text-gray-600 hover:text-gray-800', onClick: closeModal }, 'Annuller'),
            h('button', { type:'submit', className:'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, 'Gem vurdering')
        )
    );

    showModal('Rediger manuelle vurderinger', form, 'max-w-2xl');
}

// ─── Company Detail ───
async function renderCompanyDetail(container, id) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    const data = await api.getCompanyFull(id);
    const company = data.company, contacts = data.contacts, score = data.score,
          interactions = data.interactions, emailsList = data.emails, users = data.users,
          tasks = data.tasks, auditLog = data.audit_log,
          liActivities = data.linkedin_activities, liEngagements = data.linkedin_engagements,
          companyTags = data.company_tags || [], allTags = data.all_tags || [],
          tenders = data.tenders || [];

    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';

    // Header
    container.appendChild(h('div', { className: 'flex items-center gap-4 mb-6' },
        h('a', { href: '#/', className: 'text-gray-400 hover:text-gray-600' },
            h('span', { innerHTML: '<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>' })
        ),
        h('div', { className: 'flex-1' },
            h('div', { className: 'flex items-center gap-3 flex-wrap' },
                h('h1', { className: 'text-2xl font-bold text-gray-900' }, company.name),
                company.tier ? h('span', { className: `text-xs px-2 py-0.5 rounded ${TIER_COLORS[company.tier] || 'bg-gray-100 text-gray-600'}` }, company.tier) : null,
                company.sector ? h('span', { className: `badge badge-${company.sector}` }, sectorLabel(company.sector)) : null
            ),
            h('div', { className: 'flex items-center gap-4 mt-1 flex-wrap' },
                company.city ? h('span', { className: 'text-gray-500 text-sm' }, `${company.zip_code || ''} ${company.city}`.trim()) : null,
                company.ejerform ? h('span', { className: 'text-gray-400 text-sm' }, company.ejerform) : null,
                company.est_kunder ? h('span', { className: 'text-gray-400 text-sm' }, `~${company.est_kunder} kunder`) : null,
                company.account_manager_name ? h('span', { className: 'text-sm text-blue-600' }, `Ansvarlig: ${company.account_manager_name}`) : null,
                ...['has_el','has_gas','has_vand','has_varme','has_spildevand','has_affald'].filter(k => company[k]).map(k =>
                    h('span', { className: 'text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded' }, SERVICE_LABELS[k])
                )
            )
        ),
        h('div', { className: 'flex gap-2' },
            h('button', { className: 'text-gray-400 hover:text-blue-600 px-3 py-1', onClick: () => showCompanyForm(company) }, 'Rediger'),
            h('button', { className: 'text-gray-400 hover:text-red-600 px-3 py-1 text-sm', onClick: async () => {
                if (confirm(`Slet virksomheden "${company.name}"? Dette kan ikke fortrydes.`)) {
                    await api.deleteCompany(id);
                    location.hash = '#/companies';
                }
            }}, 'Slet')
        )
    ));

    // Tags
    container.appendChild(renderTagBar(companyTags, allTags, 'company', id));

    // Indkøbsfællesskab: medlemskaber, eller medlemmer hvis virksomheden selv er et fællesskab
    container.appendChild(renderGroupBlock(company, data.memberships || [], data.members || []));

    // ─── Combined Relationsscore panel ───
    const sub = score.sub_scores || {};
    const scoreExpanded = { open: false };
    const channelList = (score.channel_types || []).length > 0 ? score.channel_types.map(t => interactionLabel(t) || t).join(', ') : 'Ingen';

    // Sub-score definitions: label, weight, auto/manual, detail text
    const subDefs = [
        { key: 'kontaktfrekvens', label: 'Kontaktfrekvens', weight: 20, auto: true,
          detail: () => `${score.total_interactions || 0} interaktioner. Point: ${score.interaction_points || 0}/60 → score ${sub.kontaktfrekvens || 0}/10` },
        { key: 'kontaktdaekning', label: 'Kontaktdækning & bredde', weight: 15, auto: true,
          detail: () => `${score.contacted_count || 0} af ${score.total_contacts || 0} kontakter. Kanaler: ${channelList}` },
        { key: 'tidsforfald', label: 'Tidsforfald', weight: 15, auto: true,
          detail: () => score.days_since_last != null ? `Seneste kontakt: ${score.days_since_last} dage siden (faktor x${score.decay_factor})` : 'Ingen interaktioner' },
        { key: 'linkedin', label: 'Følger os på LinkedIn', weight: 10, auto: true,
          detail: () => `${score.li_connected || 0} af ${score.total_contacts || 0} kontakter forbundet paa LinkedIn (Systemate / Settl)` },
        { key: 'kendskab_behov', label: 'Kendskab til behov', weight: 15, auto: false,
          detail: () => 'Manuel vurdering 0-10: kender vi deres strategi og tidsplan?' },
        { key: 'workshops', label: 'Deltagelse i workshops', weight: 10, auto: false,
          detail: () => 'Manuel vurdering 0-10: har de deltaget i vores arrangementer?' },
        { key: 'marketing', label: 'Kender de os (marketing)', weight: 15, auto: false,
          detail: () => 'Manuel vurdering 0-10: reagerer de på vores marketing?' },
    ];

    const scoreDetailPanel = h('div', { className: 'hidden mt-4 border-t border-gray-200 pt-4' });
    scoreDetailPanel.appendChild(h('div', { className: 'space-y-3 text-sm' },
        h('h3', { className: 'font-semibold text-gray-700 mb-3' }, 'Sådan beregnes Relationsscoren (7 delscorer):'),
        h('div', { className: 'space-y-2' },
            ...subDefs.map((d, i) => {
                const val = sub[d.key] ?? 0;
                const contrib = (val * d.weight / 100 * 10).toFixed(1);
                return h('div', { className: `flex justify-between items-start pb-2 ${i < subDefs.length-1 ? 'border-b border-gray-100' : ''}` },
                    h('div', { className: 'flex-1' },
                        h('div', { className: 'flex items-center gap-2' },
                            h('span', { className: 'font-medium text-gray-700 text-sm' }, d.label),
                            h('span', { className: `text-xs px-1.5 py-0.5 rounded ${d.auto ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'}` }, d.auto ? 'auto' : 'manuel')
                        ),
                        h('div', { className: 'text-xs text-gray-400 mt-0.5' }, d.detail())
                    ),
                    h('div', { className: 'text-right ml-4 flex-shrink-0' },
                        h('div', { className: 'font-bold text-gray-900' }, `${val}/10`),
                        h('div', { className: 'text-xs text-gray-400' }, `vaegt ${d.weight}%`)
                    )
                );
            })
        ),
        h('div', { className: 'mt-3 p-2 bg-gray-50 rounded text-xs text-gray-500' },
            h('span', { className: 'text-blue-600' }, 'Auto'), ': beregnes fra data. ',
            h('span', { className: 'text-purple-600' }, 'Manuel'), ': sættes af dig under "Rediger vurderinger".'
        )
    ));

    const importanceLabel = { meget_vigtig: 'Meget vigtig', middel_vigtig: 'Middel vigtig', lidt_vigtig: 'Lidt vigtig' };
    const stageLabel = { tidlig_fase: 'Tidlig fase', aktiv_dialog: 'Aktiv dialog', fremskreden: 'Fremskreden' };

    // Mini sub-score grid for top of card
    const subGrid = h('div', { className: 'grid grid-cols-4 md:grid-cols-7 gap-2 mt-3' });
    for (const d of subDefs) {
        const val = sub[d.key] ?? 0;
        const barColor = val >= 7 ? '#059669' : val >= 4 ? '#d97706' : '#dc2626';
        subGrid.appendChild(h('div', { className: 'text-center' },
            h('div', { className: 'text-xs text-gray-500 mb-0.5 leading-tight' }, d.label.split(' ')[0]),
            h('div', { className: 'text-sm font-bold', style: `color:${barColor}` }, String(val)),
            h('div', { className: 'w-full bg-gray-200 rounded-full h-1 mt-0.5' },
                h('div', { className: 'h-1 rounded-full', style: `width:${val*10}%;background-color:${barColor}` })
            )
        ));
    }

    const editManualBtn = h('button', {
        className: 'text-blue-600 hover:text-blue-800 text-sm font-medium',
        onClick: (e) => { e.stopPropagation(); showManualScoreForm(company, score, () => router()); }
    }, 'Rediger vurderinger');

    const scoreCard = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6 cursor-pointer hover:shadow-md transition-shadow',
        onClick: () => {
            scoreExpanded.open = !scoreExpanded.open;
            scoreDetailPanel.classList.toggle('hidden');
        }
    },
        h('div', { className: 'flex items-center justify-between mb-2' },
            h('div', { className: 'flex items-center gap-2' },
                h('h2', { className: 'text-lg font-semibold text-gray-900' }, 'Relationsscore'),
                h('span', { className: 'text-xs text-gray-400' }, '(klik for detaljer)')
            ),
            h('div', { className: 'flex items-center gap-3' },
                editManualBtn,
                h('span', { className: `badge ${scoreBg(score.level)} text-base px-4 py-1` }, `${Math.round(score.score)} / 100`)
            )
        ),
        h('div', { className: 'flex items-center gap-4 text-xs text-gray-500 mb-3' },
            h('span', {}, `Vigtighed: ${importanceLabel[company.importance] || 'Middel vigtig'}`),
            h('span', { className: 'text-gray-300' }, '|'),
            h('span', {}, `Salgsstadie: ${stageLabel[company.sales_stage] || 'Tidlig fase'}`)
        ),
        h('div', { className: 'score-bar mb-3', style: 'height:10px' },
            h('div', { className: 'score-bar-fill', style: `width:${score.score}%;background-color:${scoreColor(score.level)};height:100%` })
        ),
        subGrid,
        scoreDetailPanel
    );
    container.appendChild(scoreCard);

    // ─── Score recommendations ───
    if (Math.round(score.score) < 100) {
        const RECOMMENDATIONS = {
            tidsforfald: {
                icon: '⏰',
                label: 'Tag kontakt snart',
                detail: (s) => s.days_since_last != null
                    ? `Det er ${s.days_since_last} dage siden sidste kontakt. Ring eller skriv for at holde relationen varm.`
                    : 'Ingen interaktioner registreret endnu. Book et møde eller ring.',
                action: 'Log en interaktion',
                actionFn: () => showInteractionFormWithContactPicker(contacts, users, id)
            },
            kontaktfrekvens: {
                icon: '📞',
                label: 'Øg kontaktfrekvensen',
                detail: (s) => `Kun ${s.total_interactions || 0} interaktioner registreret. Hyppigere kontakt giver en stærkere relation.`,
                action: 'Log en interaktion',
                actionFn: () => showInteractionFormWithContactPicker(contacts, users, id)
            },
            kontaktdaekning: {
                icon: '👥',
                label: 'Nå flere kontakter',
                detail: (s) => `${s.contacted_count || 0} af ${s.total_contacts || 0} kontakter er blevet kontaktet. Bred relationen ud til flere beslutningstagere.`,
                action: contacts.length > 0 ? 'Tilføj interaktion' : 'Tilføj kontaktperson',
                actionFn: () => contacts.length > 0
                    ? showInteractionFormWithContactPicker(contacts, users, id)
                    : showContactForm(id)
            },
            linkedin: {
                icon: '💼',
                label: 'Styrk LinkedIn-forbindelser',
                detail: () => `Forbind med kontakterne på LinkedIn (Systemate/Settl) for at øge synlighed og engagement.`,
                action: null
            },
            kendskab_behov: {
                icon: '🎯',
                label: 'Kortlæg deres behov',
                detail: () => 'Vi kender ikke nok til deres strategi og tidsplan. Book et møde for at afdække behov.',
                action: 'Rediger vurderinger',
                actionFn: () => showManualScoreForm(company, score, () => router())
            },
            workshops: {
                icon: '🎓',
                label: 'Inviter til arrangement',
                detail: () => 'De har ikke deltaget i workshops eller arrangementer. Send en invitation til næste event.',
                action: 'Rediger vurderinger',
                actionFn: () => showManualScoreForm(company, score, () => router())
            },
            marketing: {
                icon: '📣',
                label: 'Øg marketingsynlighed',
                detail: () => 'De reagerer ikke på vores marketing. Tilføj dem til relevante kampagner.',
                action: 'Rediger vurderinger',
                actionFn: () => showManualScoreForm(company, score, () => router())
            }
        };

        // Score each area by potential gain: weight × (10 - current_score)
        const areas = Object.entries(RECOMMENDATIONS).map(([key, rec]) => ({
            key, rec,
            score: sub[key] ?? 0,
            weight: subDefs.find(d => d.key === key)?.weight || 10,
            gain: (subDefs.find(d => d.key === key)?.weight || 10) * (10 - (sub[key] ?? 0))
        })).filter(a => a.score < 8) // only show if not near perfect
          .sort((a, b) => b.gain - a.gain)
          .slice(0, 3); // top 3 recommendations

        if (areas.length > 0) {
            const recCard = h('div', { className: 'bg-blue-50 border border-blue-200 rounded-xl p-5 mb-6' });
            recCard.appendChild(h('div', { className: 'flex items-center gap-2 mb-3' },
                h('span', { className: 'text-lg' }, '💡'),
                h('h2', { className: 'text-base font-semibold text-blue-900' }, 'Anbefalinger for at løfte relationsscoren')
            ));
            const list = h('div', { className: 'space-y-3' });
            for (const a of areas) {
                const potentialPts = Math.round(a.gain / 10 * 0.7);
                const row = h('div', { className: 'bg-white rounded-lg p-4 flex items-start gap-3 border border-blue-100' },
                    h('div', { className: 'text-xl flex-shrink-0 mt-0.5' }, a.rec.icon),
                    h('div', { className: 'flex-1 min-w-0' },
                        h('div', { className: 'flex items-center gap-2 flex-wrap' },
                            h('span', { className: 'font-semibold text-gray-900 text-sm' }, a.rec.label),
                            h('span', { className: 'text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full' },
                                `Score ${a.score}/10 · Vægt ${a.weight}%`)
                        ),
                        h('p', { className: 'text-xs text-gray-600 mt-1' }, a.rec.detail(score))
                    ),
                    a.rec.action && a.rec.actionFn ? h('button', {
                        className: 'flex-shrink-0 text-xs bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-700 font-medium whitespace-nowrap',
                        onClick: a.rec.actionFn
                    }, a.rec.action) : null
                );
                list.appendChild(row);
            }
            recCard.appendChild(list);
            container.appendChild(recCard);
        }
    }

    // Tasks section
    const openTasks = tasks.filter(t => t.status !== 'done');
    const tasksSection = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6' },
        h('div', { className: 'flex justify-between items-center mb-4' },
            h('h2', { className: 'text-lg font-semibold text-gray-900' }, `Sager (${openTasks.length} aabne)`),
            h('button', { className: 'text-blue-600 hover:text-blue-800 text-sm font-medium', onClick: () => showTaskForm(id, contacts, users) }, '+ Ny sag')
        )
    );
    if (openTasks.length === 0) {
        tasksSection.appendChild(h('p', { className: 'text-gray-400 text-sm' }, 'Ingen åbne sager.'));
    } else {
        for (const t of openTasks) {
            const isOverdue = t.due_date && t.due_date < new Date().toISOString().split('T')[0] && t.status !== 'done';
            tasksSection.appendChild(h('div', { className: `flex items-center gap-3 py-3 border-b border-gray-100 last:border-0 ${isOverdue ? 'task-overdue pl-2' : ''}` },
                h('button', {
                    className: `w-5 h-5 rounded border-2 flex-shrink-0 flex items-center justify-center ${t.status === 'in_progress' ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-green-500'}`,
                    title: 'Marker som færdig',
                    onClick: async () => { await api.updateTask(t.id, { status: 'done' }); router(); }
                }, t.status === 'in_progress' ? h('span', { className: 'text-blue-500 text-xs' }, '\u25CF') : null),
                h('div', { className: 'flex-1' },
                    h('div', { className: 'font-medium text-sm text-gray-900' }, t.title),
                    h('div', { className: 'flex gap-2 mt-1' },
                        h('span', { className: `badge badge-${t.category}` }, CATEGORY_LABELS[t.category] || t.category),
                        t.assigned_to_name ? h('span', { className: 'text-xs text-gray-500' }, t.assigned_to_name) : null,
                        t.due_date ? h('span', { className: `text-xs ${isOverdue ? 'text-red-500 font-medium' : 'text-gray-400'}` }, formatDate(t.due_date)) : null
                    )
                ),
                h('select', {
                    className: 'text-xs border rounded px-1 py-0.5',
                    value: t.status,
                    onChange: async (e) => { await api.updateTask(t.id, { status: e.target.value }); router(); }
                },
                    ...['open', 'in_progress', 'done'].map(s =>
                        h('option', { value: s, ...(t.status === s ? { selected:'' } : {}) }, STATUS_LABELS[s])
                    )
                )
            ));
        }
    }
    container.appendChild(tasksSection);

    // Tenders section
    const activeTenders = tenders.filter(t => !['won','lost','dropped'].includes(t.status));
    const tendersSection = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6' },
        h('div', { className: 'flex justify-between items-center mb-4' },
            h('h2', { className: 'text-lg font-semibold text-gray-900' }, `Tilbud & Udbud (${activeTenders.length} aktive)`),
            h('button', { className: 'text-blue-600 hover:text-blue-800 text-sm font-medium',
                onClick: () => showTenderForm(users, null, id) }, '+ Nyt tilbud')
        )
    );
    if (tenders.length === 0) {
        tendersSection.appendChild(h('p', { className: 'text-gray-400 text-sm' }, 'Ingen tilbud.'));
    } else {
        for (const t of tenders) {
            const statusColors = { draft: 'bg-gray-100 text-gray-600', in_progress: 'bg-blue-100 text-blue-700',
                submitted: 'bg-yellow-100 text-yellow-700', won: 'bg-green-100 text-green-700',
                lost: 'bg-red-100 text-red-600', dropped: 'bg-gray-100 text-gray-400' };
            tendersSection.appendChild(h('a', { href: `#/tenders/${t.id}`, className: 'flex items-center gap-3 py-3 border-b border-gray-100 last:border-0 hover:bg-gray-50 -mx-2 px-2 rounded' },
                h('div', { className: 'flex-1' },
                    h('div', { className: 'font-medium text-sm text-gray-900' }, t.title),
                    h('div', { className: 'flex gap-2 mt-1 flex-wrap' },
                        h('span', { className: `text-xs px-2 py-0.5 rounded font-medium ${statusColors[t.status] || 'bg-gray-100 text-gray-600'}` }, TENDER_STATUS_LABELS[t.status] || t.status),
                        routeBadge(t),
                        t.deadline ? h('span', { className: 'text-xs text-gray-400' }, `Deadline: ${formatDate(t.deadline)}`) : null,
                        t.responsible_name ? h('span', { className: 'text-xs text-gray-500' }, t.responsible_name) : null,
                        t.estimated_value ? h('span', { className: 'text-xs text-gray-400' }, t.estimated_value) : null
                    )
                ),
                h('span', { className: 'text-gray-300 text-sm' }, '→')
            ));
        }
    }
    container.appendChild(tendersSection);

    // Two-column layout
    const columns = h('div', { className: 'grid grid-cols-1 lg:grid-cols-2 gap-6' });
    container.appendChild(columns);

    // Left: Contacts
    const contactsSection = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6' },
        h('div', { className: 'flex justify-between items-center mb-4' },
            h('h2', { className: 'text-lg font-semibold text-gray-900' }, `Kontaktpersoner (${contacts.length})`),
            h('button', { className: 'text-blue-600 hover:text-blue-800 text-sm font-medium', onClick: () => showContactForm(id) }, '+ Tilføj')
        )
    );
    if (contacts.length === 0) {
        contactsSection.appendChild(h('p', { className: 'text-gray-400 text-sm' }, 'Ingen kontaktpersoner.'));
    } else {
        for (const c of contacts) {
            const hasInteractions = interactions.some(i => i.contact_id === c.id);
            contactsSection.appendChild(h('div', { className: 'flex items-center gap-3 py-3 border-b border-gray-100 last:border-0' },
                h('div', { className: `w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold text-white ${hasInteractions ? 'bg-blue-500' : 'bg-gray-300'}` },
                    (c.first_name[0] + c.last_name[0]).toUpperCase()
                ),
                h('div', { className: 'flex-1' },
                    h('div', { className: 'font-medium text-gray-900' }, `${c.first_name} ${c.last_name}`),
                    h('div', { className: 'text-xs text-gray-500' }, c.title || 'Ingen titel'),
                    c.email ? h('div', { className: 'text-xs text-gray-400' }, c.email) : null,
                    c.tags && c.tags.length > 0 ? h('div', { className: 'mt-1' }, renderTagBadges(c.tags)) : null
                ),
                h('div', { className: 'flex gap-1 items-center' },
                    c.linkedin_connected_systemate ? h('span', { className: 'text-xs px-1.5 py-0.5 bg-green-100 text-green-700 rounded', title: 'Systemate' }, 'S') : null,
                    c.linkedin_connected_settl ? h('span', { className: 'text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded', title: 'Settl' }, 'Se') : null,
                    c.on_linkedin_list ? h('span', { className: 'interaction-linkedin', innerHTML: interactionIcon('linkedin'), title: 'På LinkedIn liste' }) : null
                ),
                h('div', { className: 'flex gap-1 items-center ml-2' },
                    h('button', {
                        className: 'text-gray-300 hover:text-blue-600', title: 'Registrer interaktion',
                        onClick: () => showInteractionForm(c.id, `${c.first_name} ${c.last_name}`, users)
                    }, h('span', { innerHTML: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>' })),
                    h('button', {
                        className: 'text-gray-300 hover:text-yellow-600', title: 'Rediger kontakt',
                        onClick: () => showContactForm(id, c)
                    }, h('span', { innerHTML: '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>' })),
                    h('button', {
                        className: 'text-gray-300 hover:text-red-500', title: 'Slet kontakt',
                        onClick: async () => {
                            if (confirm(`Slet kontaktperson "${c.first_name} ${c.last_name}"? Alle interaktioner for denne kontakt slettes ogsaa.`)) {
                                await api.deleteContact(c.id);
                                router();
                            }
                        }
                    }, h('span', { innerHTML: '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>' }))
                )
            ));
        }
    }
    columns.appendChild(contactsSection);

    // Right column
    const rightCol = h('div', { className: 'space-y-6' });

    // Interactions
    const timelineSection = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6' },
        h('div', { className: 'flex justify-between items-center mb-4' },
            h('h2', { className: 'text-lg font-semibold text-gray-900' }, `Interaktioner (${interactions.length})`),
            h('button', {
                className: 'bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-700 text-sm font-medium',
                onClick: () => showInteractionFormWithContactPicker(contacts, users, id)
            }, '+ Ny interaktion')
        )
    );
    if (interactions.length === 0) {
        timelineSection.appendChild(h('p', { className: 'text-gray-400 text-sm' }, 'Ingen interaktioner.'));
    } else {
        for (const i of interactions.slice(0, 10)) {
            timelineSection.appendChild(h('div', { className: 'flex gap-3 py-3 border-b border-gray-100 last:border-0' },
                h('div', { className: `mt-1 interaction-${i.type}`, innerHTML: interactionIcon(i.type) }),
                h('div', { className: 'flex-1' },
                    h('div', { className: 'flex justify-between' },
                        h('span', { className: 'font-medium text-gray-900 text-sm' }, i.subject || interactionLabel(i.type)),
                        h('span', { className: 'text-xs text-gray-400' }, formatDate(i.date))
                    ),
                    h('div', { className: 'text-xs text-gray-500' }, `${i.contact_name || 'Ingen kontakt'}${i.user_name ? ' \u2022 ' + i.user_name : ''}`),
                    i.notes ? h('div', { className: 'text-xs text-gray-400 mt-1' }, i.notes) : null
                ),
                h('button', {
                    className: 'text-gray-300 hover:text-red-500 flex-shrink-0 mt-1',
                    title: 'Slet interaktion',
                    onClick: async () => {
                        if (confirm(`Slet interaktion "${i.subject || interactionLabel(i.type)}"?`)) {
                            await api.deleteInteraction(i.id);
                            router();
                        }
                    }
                }, h('span', { innerHTML: '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>' }))
            ));
        }
    }
    rightCol.appendChild(timelineSection);

    // LinkedIn section
    if (liActivities.length > 0 || liEngagements.length > 0) {
        const liSection = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6' },
            h('h2', { className: 'text-lg font-semibold text-gray-900 mb-4' }, 'LinkedIn Aktivitet')
        );
        for (const a of liActivities.slice(0, 5)) {
            liSection.appendChild(h('div', { className: 'flex gap-3 py-2 border-b border-gray-100 last:border-0' },
                h('span', { className: 'interaction-linkedin mt-1', innerHTML: interactionIcon('linkedin') }),
                h('div', { className: 'flex-1' },
                    h('div', { className: 'text-sm' },
                        h('strong', {}, a.contact_name), ` - ${LI_ACTIVITY_LABELS[a.activity_type] || a.activity_type}`
                    ),
                    a.content_summary ? h('div', { className: 'text-xs text-gray-500 mt-0.5' }, a.content_summary) : null,
                    h('div', { className: 'text-xs text-gray-400' }, formatDate(a.activity_date))
                )
            ));
        }
        for (const e of liEngagements.slice(0, 5)) {
            liSection.appendChild(h('div', { className: 'flex gap-3 py-2 border-b border-gray-100 last:border-0' },
                h('span', { className: 'text-green-600 mt-1', innerHTML: '\u2764' }),
                h('div', { className: 'flex-1' },
                    h('div', { className: 'text-sm' },
                        h('strong', {}, e.contact_name), ` ${LI_ENGAGE_LABELS[e.engagement_type] || e.engagement_type} paa `,
                        h('strong', {}, e.company_page === 'systemate' ? 'Systemate' : 'Settl')
                    ),
                    h('div', { className: 'text-xs text-gray-400' }, formatDate(e.observed_date))
                )
            ));
        }
        rightCol.appendChild(liSection);
    }

    // LinkedIn log buttons
    const liButtons = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6' },
        h('h2', { className: 'text-lg font-semibold text-gray-900 mb-4' }, 'Log LinkedIn'),
        h('div', { className: 'flex gap-2' },
            h('button', {
                className: 'bg-blue-50 text-blue-700 px-3 py-2 rounded-lg text-sm hover:bg-blue-100',
                onClick: () => showLinkedInActivityForm(contacts)
            }, '+ LinkedIn aktivitet'),
            h('button', {
                className: 'bg-green-50 text-green-700 px-3 py-2 rounded-lg text-sm hover:bg-green-100',
                onClick: () => showLinkedInEngagementForm(contacts)
            }, '+ Engagement (like/kommentar)')
        )
    );
    rightCol.appendChild(liButtons);

    // Email dropzone
    rightCol.appendChild(h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6' },
        h('h2', { className: 'text-lg font-semibold text-gray-900 mb-4' }, 'Email Import'),
        createEmailDropzone(contacts, users, id)
    ));

    // Email list
    if (emailsList.length > 0) {
        const emailListSection = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6' },
            h('h2', { className: 'text-lg font-semibold text-gray-900 mb-4' }, `Importerede emails (${emailsList.length})`)
        );
        for (const em of emailsList) {
            emailListSection.appendChild(h('div', { className: 'py-3 border-b border-gray-100 last:border-0 cursor-pointer hover:bg-gray-50 -mx-6 px-6', onClick: () => showEmailDetail(em) },
                h('div', { className: 'flex justify-between' },
                    h('span', { className: 'font-medium text-gray-900 text-sm' }, em.subject || '(Intet emne)'),
                    h('span', { className: 'text-xs text-gray-400' }, formatDate(em.date_sent))
                ),
                h('div', { className: 'text-xs text-gray-500 mt-1' }, `Fra: ${em.from_email || '?'}`)
            ));
        }
        rightCol.appendChild(emailListSection);
    }

    // Audit log
    if (auditLog.length > 0) {
        const auditSection = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6' },
            h('h2', { className: 'text-lg font-semibold text-gray-900 mb-4' }, 'Aktivitetslog')
        );
        for (const a of auditLog) {
            auditSection.appendChild(h('div', { className: 'audit-item' },
                h('div', { className: `audit-dot ${a.action}` }),
                h('div', { className: 'flex-1' },
                    h('div', {}, h('strong', {}, a.user_name || 'System'), ` ${a.action === 'create' ? 'oprettede' : a.action === 'update' ? 'opdaterede' : a.action === 'delete' ? 'slettede' : 'importerede'} ${a.entity_type} `, h('em', {}, a.entity_name || '')),
                    h('div', { className: 'text-xs text-gray-400' }, formatDate(a.created_at))
                )
            ));
        }
        rightCol.appendChild(auditSection);
    }

    columns.appendChild(rightCol);

    // ─── Company Notes ───
    const companyNotes = data.company_notes || [];
    renderActivityLog(container, companyNotes, [],
        async (content) => { await api.createCompanyNote(id, { content }); router(); },
        async (noteId, content) => { await api.updateCompanyNote(noteId, { content }); router(); }
    );
}

function scoreDetail(label, value, sub) {
    return h('div', { className: 'bg-gray-50 rounded-lg p-3' },
        h('div', { className: 'text-xs text-gray-500' }, label),
        h('div', { className: 'font-semibold text-gray-900' }, value),
        h('div', { className: 'text-xs text-gray-400' }, sub)
    );
}

// ─── Contact Form ───
function showContactForm(companyId, existing = null) {
    const isEdit = !!existing;
    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const data = Object.fromEntries(fd.entries());
        data.company_id = companyId;
        data.on_linkedin_list = !!fd.get('on_linkedin_list');
        data.linkedin_connected_systemate = !!fd.get('linkedin_connected_systemate');
        data.linkedin_connected_settl = !!fd.get('linkedin_connected_settl');
        try {
            if (isEdit) await api.updateContact(existing.id, data);
            else await api.createContact(data);
            closeModal();
            router();
        } catch (err) { alert(err.message); }
    }},
        h('div', { className: 'grid grid-cols-2 gap-3' },
            formField('Fornavn *', 'first_name', existing?.first_name || '', 'text', true),
            formField('Efternavn *', 'last_name', existing?.last_name || '', 'text', true),
        ),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Titel/Rolle'),
            h('select', { name: 'title', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value: '' }, 'Vælg...'),
                ...['CEO', 'COO', 'CFO', 'CCO', 'Afregningschef', 'Kundechef', 'IT-chef', 'Driftschef', 'Anden'].map(t =>
                    h('option', { value: t, ...(existing?.title === t ? { selected:'' } : {}) }, t)
                )
            )
        ),
        formField('Email', 'email', existing?.email || '', 'email'),
        formField('Telefon', 'phone', existing?.phone || '', 'tel'),
        formField('LinkedIn URL', 'linkedin_url', existing?.linkedin_url || ''),
        h('div', { className: 'space-y-2 bg-gray-50 rounded-lg p-3' },
            h('div', { className: 'text-sm font-medium text-gray-700 mb-1' }, 'LinkedIn status'),
            h('div', { className: 'flex items-center gap-2' },
                h('input', { type: 'checkbox', name: 'on_linkedin_list', id: 'li_list', className: 'rounded', ...(existing?.on_linkedin_list ? { checked: '' } : {}) }),
                h('label', { for: 'li_list', className: 'text-sm text-gray-700' }, 'Paa vores LinkedIn liste')
            ),
            h('div', { className: 'flex items-center gap-2' },
                h('input', { type: 'checkbox', name: 'linkedin_connected_systemate', id: 'li_sys', className: 'rounded', ...(existing?.linkedin_connected_systemate ? { checked: '' } : {}) }),
                h('label', { for: 'li_sys', className: 'text-sm text-gray-700' }, 'Forbundet med Systemate')
            ),
            h('div', { className: 'flex items-center gap-2' },
                h('input', { type: 'checkbox', name: 'linkedin_connected_settl', id: 'li_settl', className: 'rounded', ...(existing?.linkedin_connected_settl ? { checked: '' } : {}) }),
                h('label', { for: 'li_settl', className: 'text-sm text-gray-700' }, 'Forbundet med Settl')
            ),
        ),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type:'button', className:'px-4 py-2 text-gray-600 hover:text-gray-800', onClick: closeModal }, 'Annuller'),
            h('button', { type:'submit', className:'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, isEdit ? 'Gem' : 'Tilføj kontakt')
        )
    );
    showModal(isEdit ? 'Rediger kontakt' : 'Tilføj kontaktperson', form);
}

// ─── Interaction Form ───
function showInteractionForm(contactId, contactName, users) {
    const today = new Date().toISOString().split('T')[0];
    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const data = {
            contact_id: contactId,
            type: fd.get('type'),
            date: fd.get('date'),
            subject: fd.get('subject') || null,
            notes: fd.get('notes') || null,
            user_id: fd.get('user_id') ? parseInt(fd.get('user_id')) : null,
        };
        try { await api.createInteraction(data); closeModal(); router(); }
        catch (err) { alert(err.message); }
    }},
        h('p', { className: 'text-sm text-gray-500 mb-2' }, `Kontakt: ${contactName}`),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-2' }, 'Type *'),
            h('div', { className: 'space-y-2' },
                h('div', { className: 'text-xs text-gray-400 uppercase tracking-wider' }, 'Møder'),
                h('div', { className: 'grid grid-cols-3 gap-2 mb-3' },
                    ...['meeting_task', 'meeting', 'meeting_event'].map(t =>
                        h('label', { className: 'flex flex-col items-center gap-1 p-3 border rounded-lg cursor-pointer hover:border-blue-400 has-[:checked]:border-blue-500 has-[:checked]:bg-blue-50' },
                            h('input', { type:'radio', name:'type', value:t, className:'sr-only', required:'' }),
                            h('span', { innerHTML: interactionIcon(t) }),
                            h('span', { className: 'text-xs text-center' }, interactionLabel(t))
                        )
                    )
                ),
                h('div', { className: 'text-xs text-gray-400 uppercase tracking-wider' }, 'Andet'),
                h('div', { className: 'grid grid-cols-4 gap-2' },
                    ...['phone', 'email', 'campaign', 'linkedin'].map(t =>
                        h('label', { className: 'flex flex-col items-center gap-1 p-3 border rounded-lg cursor-pointer hover:border-blue-400 has-[:checked]:border-blue-500 has-[:checked]:bg-blue-50' },
                            h('input', { type:'radio', name:'type', value:t, className:'sr-only', required:'' }),
                            h('span', { innerHTML: interactionIcon(t) }),
                            h('span', { className: 'text-xs text-center' }, interactionLabel(t))
                        )
                    )
                )
            )
        ),
        formField('Dato *', 'date', today, 'date', true),
        formField('Emne', 'subject', ''),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Sælger'),
            h('select', { name: 'user_id', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value: '' }, 'Vælg sælger...'),
                ...users.map(u => h('option', { value: u.id }, u.name))
            )
        ),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Notater'),
            h('textarea', { name:'notes', rows:'3', className:'w-full border border-gray-300 rounded-lg px-3 py-2' })
        ),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type:'button', className:'px-4 py-2 text-gray-600 hover:text-gray-800', onClick: closeModal }, 'Annuller'),
            h('button', { type:'submit', className:'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, 'Registrer')
        )
    );
    showModal('Ny interaktion', form);
}

function showInteractionFormWithContactPicker(contacts, users, companyId = null) {
    const today = new Date().toISOString().split('T')[0];
    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const rawContact = fd.get('contact_id');
        const data = {
            contact_id: rawContact ? parseInt(rawContact) : null,
            company_id: companyId,
            type: fd.get('type'),
            date: fd.get('date'),
            subject: fd.get('subject') || null,
            notes: fd.get('notes') || null,
            user_id: fd.get('user_id') ? parseInt(fd.get('user_id')) : null,
        };
        try { await api.createInteraction(data); closeModal(); router(); }
        catch (err) { alert(err.message); }
    }},
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Kontakt'),
            h('select', { name: 'contact_id', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value: '' }, 'Ingen specifik kontakt'),
                ...contacts.map(c => h('option', { value: c.id }, `${c.first_name} ${c.last_name}${c.title ? ' — ' + c.title : ''}`))
            )
        ),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-2' }, 'Type *'),
            h('div', { className: 'space-y-2' },
                h('div', { className: 'text-xs text-gray-400 uppercase tracking-wider' }, 'Møder'),
                h('div', { className: 'grid grid-cols-3 gap-2 mb-3' },
                    ...['meeting_task', 'meeting', 'meeting_event'].map(t =>
                        h('label', { className: 'flex flex-col items-center gap-1 p-3 border rounded-lg cursor-pointer hover:border-blue-400 has-[:checked]:border-blue-500 has-[:checked]:bg-blue-50' },
                            h('input', { type:'radio', name:'type', value:t, className:'sr-only', required:'' }),
                            h('span', { innerHTML: interactionIcon(t) }),
                            h('span', { className: 'text-xs text-center' }, interactionLabel(t))
                        )
                    )
                ),
                h('div', { className: 'text-xs text-gray-400 uppercase tracking-wider' }, 'Andet'),
                h('div', { className: 'grid grid-cols-4 gap-2' },
                    ...['phone', 'email', 'campaign', 'linkedin'].map(t =>
                        h('label', { className: 'flex flex-col items-center gap-1 p-3 border rounded-lg cursor-pointer hover:border-blue-400 has-[:checked]:border-blue-500 has-[:checked]:bg-blue-50' },
                            h('input', { type:'radio', name:'type', value:t, className:'sr-only', required:'' }),
                            h('span', { innerHTML: interactionIcon(t) }),
                            h('span', { className: 'text-xs text-center' }, interactionLabel(t))
                        )
                    )
                )
            )
        ),
        formField('Dato *', 'date', today, 'date', true),
        formField('Emne', 'subject', ''),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Sælger'),
            h('select', { name: 'user_id', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value: '' }, 'Vælg sælger...'),
                ...users.map(u => h('option', { value: u.id }, u.name))
            )
        ),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Notater'),
            h('textarea', { name:'notes', rows:'3', className:'w-full border border-gray-300 rounded-lg px-3 py-2' })
        ),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type:'button', className:'px-4 py-2 text-gray-600 hover:text-gray-800', onClick: closeModal }, 'Annuller'),
            h('button', { type:'submit', className:'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, 'Registrer')
        )
    );
    showModal('Ny interaktion', form);
}

// ─── Task Form ───
let _newTaskArea = null; // preselected area when creating a sag from an area page
async function showTaskForm(companyId, contacts, users, existing = null) {
    const isEdit = !!existing;
    let allCompanies = [];
    if (!companyId) {
        try { allCompanies = await api.getCompanies(); } catch(e) {}
    }

    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const data = {
            company_id: companyId || parseInt(fd.get('company_id')),
            title: fd.get('title'),
            category: fd.get('category'),
            area: fd.get('area'),
            description: fd.get('description') || null,
            priority: fd.get('priority'),
            due_date: fd.get('due_date') || null,
            assigned_to: fd.get('assigned_to') ? parseInt(fd.get('assigned_to')) : null,
            contact_id: fd.get('contact_id') ? parseInt(fd.get('contact_id')) : null,
        };
        try {
            if (isEdit) await api.updateTask(existing.id, data);
            else await api.createTask(data);
            closeModal(); router();
        } catch (err) { alert(err.message); }
    }},
        formField('Titel *', 'title', existing?.title || '', 'text', true),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Område *'),
            h('select', { name:'area', className:'w-full border border-gray-300 rounded-lg px-3 py-2', required:'' },
                ...Object.entries(AREA_LABELS).map(([k, v]) =>
                    h('option', { value: k, ...((existing?.area || _newTaskArea || 'salg') === k ? { selected:'' } : {}) }, v)
                )
            )
        ),
        h('div', { className: 'grid grid-cols-2 gap-3' },
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Kategori *'),
                h('select', { name:'category', className:'w-full border border-gray-300 rounded-lg px-3 py-2', required:'' },
                    ...Object.entries(CATEGORY_LABELS).map(([k, v]) =>
                        h('option', { value: k, ...(existing?.category === k ? { selected:'' } : {}) }, v)
                    )
                )
            ),
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Prioritet'),
                h('select', { name:'priority', className:'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    ...Object.entries(PRIORITY_LABELS).map(([k, v]) =>
                        h('option', { value: k, ...((existing?.priority || 'normal') === k ? { selected:'' } : {}) }, v)
                    )
                )
            ),
        ),
        !companyId ? h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Virksomhed *'),
            h('select', { name:'company_id', className:'w-full border border-gray-300 rounded-lg px-3 py-2', required:'' },
                h('option', { value:'' }, 'Vælg...'),
                ...allCompanies.map(c => h('option', { value: c.id }, c.name))
            )
        ) : null,
        contacts && contacts.length > 0 ? h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Kontaktperson'),
            h('select', { name:'contact_id', className:'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value:'' }, 'Vælg...'),
                ...contacts.map(c => h('option', { value: c.id, ...(existing?.contact_id == c.id ? { selected:'' } : {}) }, `${c.first_name} ${c.last_name}`))
            )
        ) : null,
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Ansvarlig'),
            h('select', { name:'assigned_to', className:'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value:'' }, 'Vælg...'),
                ...users.map(u => h('option', { value: u.id, ...(existing?.assigned_to == u.id ? { selected:'' } : {}) }, u.name))
            )
        ),
        formField('Forfaldsdato', 'due_date', existing?.due_date || '', 'date'),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Beskrivelse'),
            h('textarea', { name:'description', rows:'3', className:'w-full border border-gray-300 rounded-lg px-3 py-2', value: existing?.description || '' })
        ),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type:'button', className:'px-4 py-2 text-gray-600 hover:text-gray-800', onClick: closeModal }, 'Annuller'),
            h('button', { type:'submit', className:'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, isEdit ? 'Gem' : 'Opret sag')
        )
    );
    showModal(isEdit ? 'Rediger sag' : 'Ny sag', form);
}

// ─── Tilbud & Udbud ───
async function renderTenders(container) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    const [tenders, users] = await Promise.all([api.getTenders(), api.getUsers()]);
    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';

    container.appendChild(h('div', { className: 'flex justify-between items-center mb-6' },
        h('div', {},
            h('h1', { className: 'text-2xl font-bold text-gray-900' }, 'Tilbud & Udbud'),
            h('p', { className: 'text-gray-500 mt-1' }, `${tenders.length} tilbud`)
        ),
        h('button', {
            className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors font-medium',
            onClick: () => showTenderForm(users)
        }, '+ Nyt tilbud')
    ));

    // Summary stats
    const byStatus = { draft:0, in_progress:0, submitted:0, won:0, lost:0 };
    for (const t of tenders) byStatus[t.status] = (byStatus[t.status] || 0) + 1;
    const statData = [
        { label:'Kladde', value: byStatus.draft, color:'text-gray-600' },
        { label:'I gang', value: byStatus.in_progress, color:'text-blue-600' },
        { label:'Indsendt', value: byStatus.submitted, color:'text-yellow-600' },
        { label:'Vundet', value: byStatus.won, color:'text-green-600' },
        { label:'Tabt', value: byStatus.lost, color:'text-red-600' },
    ];
    const statCards = h('div', { className: 'grid grid-cols-2 md:grid-cols-5 gap-4 mb-6' });
    for (const s of statData) {
        statCards.appendChild(h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-4' },
            h('div', { className: `text-2xl font-bold ${s.color}` }, String(s.value)),
            h('div', { className: 'text-sm text-gray-500' }, s.label)
        ));
    }
    container.appendChild(statCards);

    // Status filter
    const filterBar = h('div', { className: 'flex flex-wrap items-center gap-3 mb-4' });
    filterBar.appendChild(h('span', { className: 'text-sm text-gray-500' }, 'Status:'));
    const filterEntries = [['', 'Alle'], ...Object.entries(TENDER_STATUS_LABELS)];
    const listContainer = h('div', {});
    for (const [key, label] of filterEntries) {
        filterBar.appendChild(h('button', {
            className: `px-3 py-1 rounded-full text-sm font-medium ${key === '' ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`,
            onClick: (e) => {
                e.target.parentElement.querySelectorAll('button').forEach(b =>
                    b.className = 'px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-600 hover:bg-gray-200');
                e.target.className = 'px-3 py-1 rounded-full text-sm font-medium bg-gray-900 text-white';
                renderTenderList(listContainer, tenders, key);
            }
        }, label));
    }
    container.appendChild(filterBar);
    container.appendChild(listContainer);
    renderTenderList(listContainer, tenders, '');
}

function renderTenderList(container, tenders, statusFilter) {
    container.innerHTML = '';
    const filtered = statusFilter ? tenders.filter(t => t.status === statusFilter) : tenders;
    if (filtered.length === 0) {
        container.appendChild(h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center text-gray-400' },
            'Ingen tilbud fundet.'));
        return;
    }
    const list = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden' });
    for (const t of filtered) {
        const today = new Date().toISOString().split('T')[0];
        const isOverdue = t.deadline && t.deadline < today && !['won', 'lost', 'submitted'].includes(t.status);
        list.appendChild(h('div', {
            className: `flex items-center gap-4 px-6 py-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors ${isOverdue ? 'border-l-4 border-l-red-500 bg-red-50' : ''}`,
            onClick: () => { location.hash = `#/tenders/${t.id}`; }
        },
            h('div', { className: 'flex-1 min-w-0' },
                t.company_name
                    ? h('a', { href: `#/companies/${t.company_id}`, className: 'font-semibold text-gray-900 hover:underline', onClick: (e) => e.stopPropagation() }, t.company_name)
                    : h('div', { className: 'font-semibold text-gray-900' }, t.title),
                t.company_name ? h('div', { className: 'text-sm text-gray-500 truncate' }, t.title) : null,
                h('div', { className: 'flex flex-wrap gap-2 mt-1' },
                    h('span', { className: `inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${TENDER_STATUS_COLORS[t.status] || ''}` }, TENDER_STATUS_LABELS[t.status] || t.status),
                    routeBadge(t),
                    t.responsible_name ? h('span', { className: 'text-xs text-gray-500' }, t.responsible_name) : null,
                    t.estimated_value ? h('span', { className: 'text-xs text-gray-400' }, t.estimated_value) : null
                )
            ),
            h('div', { className: 'text-right flex-shrink-0' },
                h('div', { className: 'flex items-center gap-2 mb-1' },
                    h('div', { className: 'w-24 h-2 rounded-full bg-gray-200 overflow-hidden' },
                        h('div', { className: 'h-full rounded-full bg-blue-500 transition-all', style: `width:${t.progress || 0}%` })
                    ),
                    h('span', { className: 'text-xs font-medium text-gray-600 w-8' }, `${t.progress || 0}%`)
                ),
                t.deadline ? h('div', { className: `text-sm ${isOverdue ? 'text-red-500 font-medium' : 'text-gray-400'}` }, formatDate(t.deadline)) : null,
                h('div', { className: 'text-xs text-gray-400' }, `${t.sections_approved || 0}/${t.section_count || 0} sektioner`)
            )
        ));
    }
    container.appendChild(list);
}

async function renderTenderDetail(container, id) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    const [data, tenderNotes, tenderHistory] = await Promise.all([
        api.getTenderFull(id),
        api.getTenderNotes(id),
        api.getTenderHistory(id)
    ]);
    const { tender, sections, users } = data;
    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';

    // Back + header
    container.appendChild(h('div', { className: 'mb-6' },
        h('a', { href: '#/tenders', className: 'text-sm text-blue-600 hover:underline mb-2 inline-block' }, '\u2190 Alle tilbud'),
        h('div', { className: 'flex justify-between items-start' },
            h('div', {},
                tender.company_name
                    ? h('h1', { className: 'text-2xl font-bold text-gray-900' },
                        h('a', { href: `#/companies/${tender.company_id}`, className: 'hover:underline' }, tender.company_name))
                    : h('h1', { className: 'text-2xl font-bold text-gray-900' }, tender.title),
                tender.company_name ? h('div', { className: 'text-base text-gray-500 mt-1' }, tender.title) : null,
                h('div', { className: 'flex flex-wrap gap-2 mt-2' },
                    h('span', { className: `inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${TENDER_STATUS_COLORS[tender.status] || ''}` }, TENDER_STATUS_LABELS[tender.status] || tender.status),
                    tender.purchase_route === 'faellesskab'
                        ? h('a', { href: `#/companies/${tender.via_group_id}`, className: 'route-pill' }, `Køber via ${tender.via_group_name || 'fællesskab'}`)
                        : h('span', { className: 'text-sm text-gray-500' }, 'Kunden køber selv'),
                    tender.deadline ? h('span', { className: 'text-sm text-gray-500' }, `Deadline: ${formatDate(tender.deadline)}`) : null,
                    tender.estimated_value ? h('span', { className: 'text-sm text-gray-400' }, tender.estimated_value) : null
                )
            ),
            h('div', { className: 'flex gap-2 flex-wrap' },
                !['won','lost','dropped'].includes(tender.status) ? h('div', { className: 'flex gap-1 border border-gray-200 rounded-lg p-1' },
                    h('button', {
                        className: 'bg-green-50 text-green-700 px-3 py-1.5 rounded hover:bg-green-100 text-sm font-medium',
                        onClick: async () => {
                            if (confirm('Marker tilbud som VUNDET?')) { await api.updateTender(id, { status: 'won' }); router(); }
                        }
                    }, 'Vundet'),
                    h('button', {
                        className: 'bg-red-50 text-red-600 px-3 py-1.5 rounded hover:bg-red-100 text-sm font-medium',
                        onClick: async () => {
                            if (confirm('Marker tilbud som TABT?')) { await api.updateTender(id, { status: 'lost' }); router(); }
                        }
                    }, 'Tabt'),
                    h('button', {
                        className: 'bg-orange-50 text-orange-600 px-3 py-1.5 rounded hover:bg-orange-100 text-sm font-medium',
                        onClick: async () => {
                            if (confirm('Marker tilbud som DROPPET?')) { await api.updateTender(id, { status: 'dropped' }); router(); }
                        }
                    }, 'Droppet')
                ) : null,
                h('button', {
                    className: 'bg-gray-100 text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-200 text-sm',
                    onClick: () => showTenderForm(users, tender)
                }, 'Rediger'),
                h('button', {
                    className: 'bg-red-50 text-red-600 px-3 py-2 rounded-lg hover:bg-red-100 text-sm',
                    onClick: async () => {
                        if (confirm('Slet dette tilbud?')) { await api.deleteTender(id); location.hash = '#/tenders'; }
                    }
                }, 'Slet')
            )
        )
    ));

    // Info cards
    const totalSections = sections.length;
    const approvedSections = sections.filter(s => s.status === 'approved').length;
    const progress = totalSections > 0 ? Math.round(approvedSections / totalSections * 100) : 0;

    container.appendChild(h('div', { className: 'grid grid-cols-2 md:grid-cols-4 gap-4 mb-6' },
        h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-4' },
            h('div', { className: 'text-2xl font-bold text-blue-600' }, `${progress}%`),
            h('div', { className: 'text-sm text-gray-500' }, 'Fremgang'),
            h('div', { className: 'w-full h-2 rounded-full bg-gray-200 mt-2 overflow-hidden' },
                h('div', { className: 'h-full rounded-full bg-blue-500', style: `width:${progress}%` }))
        ),
        h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-4' },
            h('div', { className: 'text-2xl font-bold text-gray-900' }, `${approvedSections}/${totalSections}`),
            h('div', { className: 'text-sm text-gray-500' }, 'Sektioner godkendt')
        ),
        h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-4' },
            h('div', { className: 'text-2xl font-bold text-gray-900' }, tender.responsible_name || '-'),
            h('div', { className: 'text-sm text-gray-500' }, 'Ansvarlig')
        ),
        h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-4' },
            h('div', { className: `text-2xl font-bold ${tender.deadline && tender.deadline < new Date().toISOString().split('T')[0] ? 'text-red-600' : 'text-gray-900'}` },
                tender.deadline ? formatDate(tender.deadline) : '-'),
            h('div', { className: 'text-sm text-gray-500' }, 'Deadline')
        )
    ));

    // Description / notes
    if (tender.description || tender.notes || tender.portal_link) {
        const infoCard = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6' });
        if (tender.description) infoCard.appendChild(h('p', { className: 'text-gray-700 mb-2' }, tender.description));
        if (tender.portal_link) infoCard.appendChild(h('a', { href: tender.portal_link, target: '_blank', className: 'text-blue-600 hover:underline text-sm' }, 'Åben udbudsportal'));
        if (tender.notes) infoCard.appendChild(h('p', { className: 'text-sm text-gray-500 mt-2' }, tender.notes));
        container.appendChild(infoCard);
    }

    // Gantt timeline — always show if tender has a deadline
    if (tender.deadline || sections.length > 0) {
        container.appendChild(renderGanttTimeline(tender, sections, users));
    }

    // Activity log (notes + history) — after Gantt, before sections
    renderActivityLog(container, tenderNotes, tenderHistory,
        async (content) => { await api.createTenderNote(id, { content }); router(); },
        async (noteId, content) => { await api.updateTenderNote(noteId, { content }); router(); }
    );

    // Sections header
    container.appendChild(h('div', { className: 'flex justify-between items-center mb-4' },
        h('h2', { className: 'text-lg font-bold text-gray-900' }, `Sektioner (${totalSections})`),
        h('button', {
            className: 'bg-blue-600 text-white px-3 py-2 rounded-lg hover:bg-blue-700 text-sm font-medium',
            onClick: () => showSectionForm(id, users, sections.length)
        }, '+ Tilføj sektion')
    ));

    // Sections list
    const sectionList = h('div', { className: 'space-y-3' });
    if (sections.length === 0) {
        sectionList.appendChild(h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center text-gray-400' },
            'Ingen sektioner. Tilføj sektioner manuelt eller vaelg en skabelon ved oprettelse.'));
    }
    for (const sec of sections) {
        const today = new Date().toISOString().split('T')[0];
        const isOverdue = sec.deadline && sec.deadline < today && sec.status !== 'approved';
        sectionList.appendChild(h('div', {
            className: `bg-white rounded-xl shadow-sm border border-gray-200 p-5 cursor-pointer ${isOverdue ? 'border-l-4 border-l-red-500' : ''}`,
            onDblClick: () => showSectionNotes(sec, users)
        },
            h('div', { className: 'flex justify-between items-start' },
                h('div', { className: 'flex-1' },
                    h('div', { className: 'flex items-center gap-3 flex-wrap' },
                        h('span', { className: 'text-xs text-gray-400 font-mono' }, `#${sec.sort_order + 1}`),
                        h('h3', { className: 'font-semibold text-gray-900 cursor-pointer hover:text-blue-600 transition-colors', onClick: (e) => { e.stopPropagation(); showSectionNotes(sec, users); } }, sec.title),
                        h('span', { className: `inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${SECTION_STATUS_COLORS[sec.status] || ''}` }, SECTION_STATUS_LABELS[sec.status] || sec.status)
                    ),
                    sec.description ? h('p', { className: 'text-sm text-gray-500 mt-1' }, sec.description) : null,
                    h('div', { className: 'flex flex-wrap gap-4 mt-2 text-xs text-gray-500' },
                        h('span', {}, `Ansvarlig: ${sec.responsible_name || '-'}`),
                        h('span', {}, `Reviewer: ${sec.reviewer_name || '-'}`),
                        sec.deadline ? h('span', { className: isOverdue ? 'text-red-500 font-medium' : '' }, `Deadline: ${formatDate(sec.deadline)}`) : null
                    )
                ),
                h('div', { className: 'flex gap-1 items-start flex-shrink-0' },
                    h('select', {
                        className: 'text-xs border rounded px-2 py-1',
                        onChange: async (e) => {
                            await api.updateTenderSection(sec.id, { status: e.target.value });
                            router();
                        }
                    },
                        ...Object.entries(SECTION_STATUS_LABELS).map(([k, v]) =>
                            h('option', Object.assign({ value: k }, sec.status === k ? { selected: '' } : {}), v))
                    ),
                    h('button', {
                        className: 'text-gray-400 hover:text-blue-600 px-2 py-1 text-sm',
                        onClick: () => showSectionForm(id, users, sections.length, sec)
                    }, 'Rediger'),
                    h('button', {
                        className: 'text-gray-400 hover:text-red-600 px-2 py-1 text-sm',
                        onClick: async () => {
                            if (confirm(`Slet sektion "${sec.title}"?`)) { await api.deleteTenderSection(sec.id); router(); }
                        }
                    }, 'Slet')
                )
            )
        ));
    }
    container.appendChild(sectionList);
}

// ─── Gantt Timeline ───
const GANTT_BAR_COLORS = {
    not_started: '#e5e7eb', in_progress: '#93c5fd',
    in_review: '#fde68a', approved: '#86efac'
};
const GANTT_BAR_BORDERS = {
    not_started: '#d1d5db', in_progress: '#60a5fa',
    in_review: '#fbbf24', approved: '#4ade80'
};

function renderGanttTimeline(tender, sections, users) {
    const sorted = [...sections].sort((a, b) => a.sort_order - b.sort_order);
    const tenderStart = new Date(tender.created_at);
    const tenderEnd = tender.deadline ? new Date(tender.deadline + 'T23:59:59') : new Date();
    // Extend range to include all section dates
    for (const s of sorted) {
        if (s.deadline) {
            const d = new Date(s.deadline + 'T23:59:59');
            if (d > tenderEnd) tenderEnd.setTime(d.getTime());
        }
        if (s.end_date) {
            const d = new Date(s.end_date + 'T23:59:59');
            if (d > tenderEnd) tenderEnd.setTime(d.getTime());
        }
        if (s.start_date) {
            const d = new Date(s.start_date + 'T00:00:00');
            if (d < tenderStart) tenderStart.setTime(d.getTime());
        }
    }
    const totalMs = Math.max(1, tenderEnd - tenderStart);
    const today = new Date();
    const MONTHS_DA = ['jan','feb','mar','apr','maj','jun','jul','aug','sep','okt','nov','dec'];

    const container = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6' });
    container.appendChild(h('h2', { className: 'text-lg font-bold text-gray-900 mb-4' }, 'Tidsplan'));

    const scrollOuter = h('div', { style: 'overflow-x:auto;' });
    const chartWrapper = h('div', { className: 'flex', style: 'min-width:700px;' });

    // Y-axis labels
    const yAxis = h('div', { className: 'flex-shrink-0', style: 'width:160px; padding-top:24px;' });
    for (const sec of sorted) {
        yAxis.appendChild(h('div', {
            className: 'gantt-label',
            style: 'height:36px; display:flex; align-items:center;',
            title: sec.title,
            onClick: () => showSectionNotes(sec, users)
        }, `#${sec.sort_order + 1} ${sec.title}`));
    }
    chartWrapper.appendChild(yAxis);

    // Chart body
    const chartBody = h('div', { className: 'flex-1 relative' });

    // X-axis ticks
    const tickRow = h('div', { className: 'relative', style: 'height:24px;' });
    const totalDays = Math.ceil(totalMs / (1000 * 60 * 60 * 24));
    const tickInterval = totalDays > 120 ? 30 : totalDays > 60 ? 14 : 7;
    const tickDate = new Date(tenderStart);
    tickDate.setDate(tickDate.getDate() + tickInterval);
    while (tickDate < tenderEnd) {
        const pct = ((tickDate - tenderStart) / totalMs) * 100;
        tickRow.appendChild(h('div', { className: 'gantt-tick', style: `left:${pct}%` },
            `${tickDate.getDate()}. ${MONTHS_DA[tickDate.getMonth()]}`));
        tickDate.setDate(tickDate.getDate() + tickInterval);
    }
    chartBody.appendChild(tickRow);

    // Rows with bars
    const rowsContainer = h('div', { className: 'relative' });
    for (let i = 0; i < sorted.length; i++) {
        const sec = sorted[i];
        const row = h('div', { className: 'gantt-row' });

        // Tick grid lines
        const gridDate = new Date(tenderStart);
        gridDate.setDate(gridDate.getDate() + tickInterval);
        while (gridDate < tenderEnd) {
            const pct = ((gridDate - tenderStart) / totalMs) * 100;
            row.appendChild(h('div', { className: 'gantt-tick-line', style: `left:${pct}%; top:0; bottom:0;` }));
            gridDate.setDate(gridDate.getDate() + tickInterval);
        }

        // Bar — use start_date/end_date if available, fallback to old logic
        const barStart = sec.start_date
            ? new Date(sec.start_date + 'T00:00:00')
            : (i > 0 && (sorted[i - 1].end_date || sorted[i - 1].deadline)
                ? new Date((sorted[i - 1].end_date || sorted[i - 1].deadline) + 'T00:00:00')
                : tenderStart);
        const barEnd = sec.end_date
            ? new Date(sec.end_date + 'T23:59:59')
            : (sec.deadline ? new Date(sec.deadline + 'T23:59:59') : tenderEnd);
        const leftPct = Math.max(0, ((barStart - tenderStart) / totalMs) * 100);
        const widthPct = Math.max(2, ((barEnd - barStart) / totalMs) * 100);
        const barColor = GANTT_BAR_COLORS[sec.status] || '#e5e7eb';
        const barBorder = GANTT_BAR_BORDERS[sec.status] || '#d1d5db';

        const bar = h('div', {
            className: 'gantt-bar',
            style: `left:${leftPct}%; width:${widthPct}%; background-color:${barColor}; border:1px solid ${barBorder};`,
            title: `${sec.title}\n${SECTION_STATUS_LABELS[sec.status] || sec.status}${sec.deadline ? '\nDeadline: ' + formatDate(sec.deadline) : ''}${sec.responsible_name ? '\nAnsvarlig: ' + sec.responsible_name : ''}`,
            onClick: () => showSectionNotes(sec, users)
        }, widthPct > 10 ? sec.title : '');
        row.appendChild(bar);
        rowsContainer.appendChild(row);
    }

    // Today line
    if (today >= tenderStart && today <= tenderEnd) {
        const todayPct = ((today - tenderStart) / totalMs) * 100;
        rowsContainer.appendChild(h('div', { className: 'gantt-today-line', style: `left:${todayPct}%` }));
        tickRow.appendChild(h('div', {
            className: 'gantt-today-label',
            style: `left:${todayPct}%`
        }, 'I dag'));
    }

    chartBody.appendChild(rowsContainer);
    chartWrapper.appendChild(chartBody);
    scrollOuter.appendChild(chartWrapper);

    // Legend
    const legend = h('div', { className: 'flex flex-wrap gap-4 mt-3 text-xs text-gray-500' });
    for (const [status, label] of Object.entries(SECTION_STATUS_LABELS)) {
        legend.appendChild(h('div', { className: 'flex items-center gap-1' },
            h('div', { style: `width:12px; height:12px; border-radius:3px; background-color:${GANTT_BAR_COLORS[status]};border:1px solid ${GANTT_BAR_BORDERS[status]}` }),
            label
        ));
    }
    legend.appendChild(h('div', { className: 'flex items-center gap-1' },
        h('div', { style: 'width:12px; height:2px; background-color:#dc2626;' }),
        'I dag'
    ));

    container.appendChild(scrollOuter);
    container.appendChild(legend);
    return container;
}

// ─── Section Notes & Audit Trail ───
async function showSectionNotes(section, users) {
    const auditEntries = await api.getSectionAudit(section.id);
    const container = h('div', { className: 'space-y-5' });

    // ─── Editable fields section ───
    const editSection = h('div', { className: 'bg-gray-50 rounded-lg p-4 space-y-3' });

    // Status + Deadline row
    const statusSelect = h('select', { className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm' },
        ...Object.entries(SECTION_STATUS_LABELS).map(([k, v]) =>
            h('option', Object.assign({ value: k }, section.status === k ? { selected: '' } : {}), v))
    );
    const deadlineInput = h('input', { type: 'date', value: section.deadline || '', className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm' });

    editSection.appendChild(h('div', { className: 'grid grid-cols-2 gap-3' },
        h('div', {},
            h('label', { className: 'block text-xs font-medium text-gray-600 mb-1' }, 'Status'),
            statusSelect
        ),
        h('div', {},
            h('label', { className: 'block text-xs font-medium text-gray-600 mb-1' }, 'Deadline'),
            deadlineInput
        )
    ));

    // Start + End date row
    const startDateInput = h('input', { type: 'date', value: section.start_date || '', className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm' });
    const endDateInput = h('input', { type: 'date', value: section.end_date || '', className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm' });

    editSection.appendChild(h('div', { className: 'grid grid-cols-2 gap-3' },
        h('div', {},
            h('label', { className: 'block text-xs font-medium text-gray-600 mb-1' }, 'Startdato'),
            startDateInput
        ),
        h('div', {},
            h('label', { className: 'block text-xs font-medium text-gray-600 mb-1' }, 'Slutdato'),
            endDateInput
        )
    ));

    // Responsible + Reviewer row
    const responsibleSelect = h('select', { className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm' },
        h('option', { value: '' }, 'Ingen'),
        ...users.map(u => h('option', Object.assign({ value: String(u.id) }, section.responsible_id == u.id ? { selected: '' } : {}), u.name))
    );
    const reviewerSelect = h('select', { className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm' },
        h('option', { value: '' }, 'Ingen'),
        ...users.map(u => h('option', Object.assign({ value: String(u.id) }, section.reviewer_id == u.id ? { selected: '' } : {}), u.name))
    );

    editSection.appendChild(h('div', { className: 'grid grid-cols-2 gap-3' },
        h('div', {},
            h('label', { className: 'block text-xs font-medium text-gray-600 mb-1' }, 'Ansvarlig'),
            responsibleSelect
        ),
        h('div', {},
            h('label', { className: 'block text-xs font-medium text-gray-600 mb-1' }, 'Reviewer'),
            reviewerSelect
        )
    ));

    // Save changes button
    const saveFieldsBtn = h('button', {
        className: 'bg-blue-600 text-white px-4 py-1.5 rounded-lg hover:bg-blue-700 text-sm font-medium',
        onClick: async () => {
            try {
                await api.updateTenderSection(section.id, {
                    status: statusSelect.value,
                    deadline: deadlineInput.value || null,
                    start_date: startDateInput.value || null,
                    end_date: endDateInput.value || null,
                    responsible_id: responsibleSelect.value ? parseInt(responsibleSelect.value) : null,
                    reviewer_id: reviewerSelect.value ? parseInt(reviewerSelect.value) : null,
                });
                closeModal();
                router();
            } catch (err) { alert(err.message); }
        }
    }, 'Gem ændringer');
    editSection.appendChild(h('div', { className: 'flex justify-end' }, saveFieldsBtn));
    container.appendChild(editSection);

    // ─── New note input ───
    const noteInput = h('textarea', {
        rows: '2', placeholder: 'Skriv en note...',
        className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-blue-500 focus:outline-none'
    });
    const addNoteBtn = h('button', {
        className: 'bg-gray-700 text-white px-4 py-1.5 rounded-lg hover:bg-gray-800 text-sm font-medium',
        onClick: async () => {
            const text = noteInput.value.trim();
            if (!text) return;
            try {
                await api.addSectionComment(section.id, text);
                closeModal();
                const updated = await api.getTenderFull(section.tender_id);
                const updatedSec = updated.sections.find(s => s.id === section.id);
                if (updatedSec) showSectionNotes(updatedSec, updated.users);
            } catch (err) { alert(err.message); }
        }
    }, 'Tilføj note');
    container.appendChild(h('div', { className: 'border-t pt-4' },
        h('h3', { className: 'text-sm font-semibold text-gray-700 mb-2' }, 'Tidslinje'),
        noteInput,
        h('div', { className: 'flex justify-end mt-1 mb-3' }, addNoteBtn)
    ));

    // ─── Unified Timeline ───
    const AUDIT_ICONS = { created: '\u2795', status_change: '\uD83D\uDD04', field_change: '\u270F\uFE0F', note: '\uD83D\uDCDD', comment: '\uD83D\uDCDD' };
    const DOT_CLASS = { created: 'created', status_change: 'status', field_change: 'field', note: 'note', comment: 'note' };
    const FIELD_LABELS = { status: 'Status', responsible: 'Ansvarlig', reviewer: 'Reviewer', notes: 'Noter' };

    if (auditEntries.length === 0) {
        container.appendChild(h('div', { className: 'text-sm text-gray-400 italic py-2' }, 'Ingen aktivitet endnu.'));
    } else {
        const timeline = h('div', { className: 'section-timeline max-h-64 overflow-y-auto' });

        for (const entry of auditEntries) {
            const isContentEntry = entry.note_type === 'comment' && entry.content;
            const dotClass = DOT_CLASS[entry.note_type] || 'note';

            const entryEl = h('div', { className: 'section-tl-entry' });
            entryEl.appendChild(h('div', { className: `section-tl-dot ${dotClass}` }));

            if (isContentEntry) {
                // ─ Note/comment card with expandable content ─
                const firstLine = entry.content.split('\n')[0];
                const preview = firstLine.length > 80 ? firstLine.substring(0, 80) + '\u2026' : firstLine;
                const hasMore = entry.content.length > preview.length || entry.content.includes('\n');

                const card = h('div', { className: 'section-tl-card' });
                const headerRow = h('div', { className: 'flex items-center gap-2' },
                    h('span', { className: 'text-xs font-semibold text-gray-600' }, entry.user_name || 'System'),
                    h('span', { className: 'text-xs text-gray-400' }, formatDate(entry.created_at)),
                    hasMore ? h('span', { className: 'section-tl-expand-hint' }, 'klik for at åbne') : null
                );
                card.appendChild(headerRow);

                const previewEl = h('div', { className: 'tl-preview text-sm text-gray-700 mt-0.5' }, preview);
                card.appendChild(previewEl);

                if (hasMore) {
                    const fullEl = h('div', { className: 'tl-full text-sm text-gray-700 mt-1 whitespace-pre-wrap' }, entry.content);
                    card.appendChild(fullEl);

                    card.addEventListener('click', () => {
                        card.classList.toggle('expanded');
                    });
                }

                entryEl.appendChild(card);
            } else {
                // ─ System entry (status change, field change, etc.) ─
                let detail = '';
                const icon = AUDIT_ICONS[entry.note_type] || '\uD83D\uDCCC';
                if (entry.note_type === 'status_change') {
                    const oldL = SECTION_STATUS_LABELS[entry.old_value] || entry.old_value;
                    const newL = SECTION_STATUS_LABELS[entry.new_value] || entry.new_value;
                    detail = `${oldL} \u2192 ${newL}`;
                } else if (entry.note_type === 'field_change') {
                    const fl = FIELD_LABELS[entry.field_name] || entry.field_name || '';
                    detail = `${fl}: ${entry.old_value || '-'} \u2192 ${entry.new_value || '-'}`;
                } else if (entry.note_type === 'note') {
                    detail = 'Noter opdateret';
                } else if (entry.note_type === 'created') {
                    detail = entry.content || 'Sektion oprettet';
                } else {
                    detail = entry.content || '';
                }

                entryEl.appendChild(h('div', { className: 'section-tl-system' },
                    h('span', { className: 'mr-1' }, icon),
                    h('span', {}, detail),
                    h('span', { className: 'text-xs text-gray-400 ml-2' },
                        `${entry.user_name || 'System'} \u00B7 ${formatDate(entry.created_at)}`)
                ));
            }

            timeline.appendChild(entryEl);
        }

        container.appendChild(timeline);
    }

    showModal(`${section.title}`, container);
}

async function showTenderForm(users, existing = null, prefillCompanyId = null) {
    const isEdit = !!existing;
    let companies = [], templates = [], groups = [];
    try { [companies, templates, groups] = await Promise.all([api.getCompanies(), api.getTenderTemplates(), api.getPurchasingGroups()]); } catch(e) {}

    // Købsvej: kunden selv eller via et indkøbsfællesskab. Kundens egne fællesskaber står først.
    const routeField = h('div', { className: 'route-field' });
    const drawRoute = (companyId) => {
        const company = companies.find(c => String(c.id) === String(companyId));
        const mine = (company?.memberships || []);
        const others = groups.filter(g => !mine.some(m => m.id === g.id));
        const route = routeField.querySelector('input[name=purchase_route]:checked')?.value || existing?.purchase_route || (mine.length ? '' : 'selv');
        const chosen = routeField.querySelector('select[name=via_group_id]')?.value || existing?.via_group_id || (mine[0]?.id ?? '');
        routeField.innerHTML = '';
        routeField.append(
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Købsvej'),
            mine.length ? h('div', { className: 'text-xs text-gray-500 mb-2' }, `${company.name} er medlem af ${mine.map(m => m.name).join(' og ')}. Går de selv, eller med fællesskabet?`) : null,
            h('div', { className: 'flex gap-4 items-center flex-wrap' },
                h('label', { className: 'flex items-center gap-2 text-sm' }, h('input', { type: 'radio', name: 'purchase_route', value: 'selv', ...(route === 'selv' ? { checked: '' } : {}) }), 'Kunden selv'),
                h('label', { className: 'flex items-center gap-2 text-sm' }, h('input', { type: 'radio', name: 'purchase_route', value: 'faellesskab', ...(route === 'faellesskab' ? { checked: '' } : {}) }), 'Via fællesskab'),
                h('select', { name: 'via_group_id', className: 'border border-gray-300 rounded-lg px-2 py-1.5 text-sm' },
                    h('option', { value: '' }, 'Vælg fællesskab…'),
                    ...mine.map(g => h('option', { value: g.id, ...(String(chosen) === String(g.id) ? { selected: '' } : {}) }, `${g.name} (medlem)`)),
                    ...others.map(g => h('option', { value: g.id, ...(String(chosen) === String(g.id) ? { selected: '' } : {}) }, g.name)))));
    };
    drawRoute(existing?.company_id || prefillCompanyId);

    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const data = {
            company_id: parseInt(fd.get('company_id')),
            title: fd.get('title'),
            template_id: fd.get('template_id') ? parseInt(fd.get('template_id')) : null,
            description: fd.get('description') || null,
            status: fd.get('status') || 'draft',
            deadline: fd.get('deadline') || null,
            responsible_id: fd.get('responsible_id') ? parseInt(fd.get('responsible_id')) : null,
            estimated_value: fd.get('estimated_value') || null,
            portal_link: fd.get('portal_link') || null,
            notes: fd.get('notes') || null,
            purchase_route: fd.get('purchase_route') || 'selv',
            via_group_id: fd.get('purchase_route') === 'faellesskab' && fd.get('via_group_id') ? parseInt(fd.get('via_group_id')) : null,
        };
        const memberOf = companies.find(c => c.id === data.company_id)?.memberships || [];
        if (memberOf.length && !fd.get('purchase_route')) { alert('Kunden er medlem af et indkøbsfællesskab. Vælg om de køber selv eller via fællesskabet.'); return; }
        if (data.purchase_route === 'faellesskab' && !data.via_group_id) { alert('Vælg hvilket fællesskab kunden køber via.'); return; }
        try {
            if (isEdit) await api.updateTender(existing.id, data);
            else { const created = await api.createTender(data); location.hash = `#/tenders/${created.id}`; closeModal(); return; }
            closeModal(); router();
        } catch (err) { alert(err.message); }
    }},
        formField('Titel *', 'title', existing?.title || '', 'text', true),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Virksomhed *'),
            h('select', { name:'company_id', className:'w-full border border-gray-300 rounded-lg px-3 py-2', required:'', onChange: (e) => drawRoute(e.target.value) },
                h('option', { value:'' }, 'Vælg...'),
                ...companies.map(c => h('option', Object.assign({ value: String(c.id) }, (existing?.company_id == c.id || (!existing && prefillCompanyId == c.id)) ? { selected:'' } : {}), c.name))
            )
        ),
        routeField,
        !isEdit ? h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Skabelon'),
            h('select', { name:'template_id', className:'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value:'' }, 'Ingen skabelon'),
                ...templates.map(t => h('option', { value: String(t.id) }, `${t.name} (${t.section_count} sektioner)`))
            )
        ) : null,
        h('div', { className: 'grid grid-cols-2 gap-3' },
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Status'),
                h('select', { name:'status', className:'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    ...Object.entries(TENDER_STATUS_LABELS).map(([k, v]) =>
                        h('option', Object.assign({ value: k }, (existing?.status || 'draft') === k ? { selected:'' } : {}), v))
                )
            ),
            formField('Deadline', 'deadline', existing?.deadline || '', 'date')
        ),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Ansvarlig'),
            h('select', { name:'responsible_id', className:'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value:'' }, 'Vælg...'),
                ...users.map(u => h('option', Object.assign({ value: String(u.id) }, existing?.responsible_id == u.id ? { selected:'' } : {}), u.name))
            )
        ),
        h('div', { className: 'grid grid-cols-2 gap-3' },
            formField('Estimeret værdi', 'estimated_value', existing?.estimated_value || ''),
            formField('Portallink', 'portal_link', existing?.portal_link || '', 'url')
        ),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Beskrivelse'),
            h('textarea', { name:'description', rows:'2', className:'w-full border border-gray-300 rounded-lg px-3 py-2' }, existing?.description || '')
        ),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type:'button', className:'px-4 py-2 text-gray-600 hover:text-gray-800', onClick: closeModal }, 'Annuller'),
            h('button', { type:'submit', className:'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, isEdit ? 'Gem' : 'Opret tilbud')
        )
    );
    showModal(isEdit ? 'Rediger tilbud' : 'Nyt tilbud', form);
}

function showSectionForm(tenderId, users, sectionCount, existing = null) {
    const isEdit = !!existing;
    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const data = {
            tender_id: tenderId,
            title: fd.get('title'),
            description: fd.get('description') || null,
            responsible_id: fd.get('responsible_id') ? parseInt(fd.get('responsible_id')) : null,
            reviewer_id: fd.get('reviewer_id') ? parseInt(fd.get('reviewer_id')) : null,
            status: fd.get('status') || 'not_started',
            deadline: fd.get('deadline') || null,
            start_date: fd.get('start_date') || null,
            end_date: fd.get('end_date') || null,
            sort_order: parseInt(fd.get('sort_order') || sectionCount),
            notes: fd.get('notes') || null,
        };
        try {
            if (isEdit) await api.updateTenderSection(existing.id, data);
            else await api.createTenderSection(data);
            closeModal(); router();
        } catch (err) { alert(err.message); }
    }},
        formField('Titel *', 'title', existing?.title || '', 'text', true),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Beskrivelse'),
            h('textarea', { name:'description', rows:'2', className:'w-full border border-gray-300 rounded-lg px-3 py-2' }, existing?.description || '')
        ),
        h('div', { className: 'grid grid-cols-2 gap-3' },
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Ansvarlig'),
                h('select', { name:'responsible_id', className:'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    h('option', { value:'' }, 'Vælg...'),
                    ...users.map(u => h('option', Object.assign({ value: String(u.id) }, existing?.responsible_id == u.id ? { selected:'' } : {}), u.name))
                )
            ),
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Reviewer'),
                h('select', { name:'reviewer_id', className:'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    h('option', { value:'' }, 'Vælg...'),
                    ...users.map(u => h('option', Object.assign({ value: String(u.id) }, existing?.reviewer_id == u.id ? { selected:'' } : {}), u.name))
                )
            )
        ),
        h('div', { className: 'grid grid-cols-2 gap-3' },
            formField('Startdato', 'start_date', existing?.start_date || '', 'date'),
            formField('Slutdato', 'end_date', existing?.end_date || '', 'date')
        ),
        h('div', { className: 'grid grid-cols-2 gap-3' },
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Status'),
                h('select', { name:'status', className:'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    ...Object.entries(SECTION_STATUS_LABELS).map(([k, v]) =>
                        h('option', Object.assign({ value: k }, (existing?.status || 'not_started') === k ? { selected:'' } : {}), v))
                )
            ),
            formField('Deadline', 'deadline', existing?.deadline || '', 'date')
        ),
        formField('Rækkefølge', 'sort_order', String(existing?.sort_order ?? sectionCount), 'number'),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type:'button', className:'px-4 py-2 text-gray-600 hover:text-gray-800', onClick: closeModal }, 'Annuller'),
            h('button', { type:'submit', className:'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, isEdit ? 'Gem' : 'Tilføj sektion')
        )
    );
    showModal(isEdit ? 'Rediger sektion' : 'Ny sektion', form);
}

// ─── Tasks Page ───
// ─── Shared Activity Log (notes + history merged) ───
const AUDIT_ACTION_LABELS = {
    create: 'Oprettet', update: 'Opdateret', add_note: 'Note tilf\u00f8jet',
    delete: 'Slettet', status_change: 'Status \u00e6ndret', 'upload-email': 'E-mail vedhæftet'
};

function renderActivityLog(container, notes, history, onAddNote, onEditNote) {
    const panel = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mt-6' });
    panel.appendChild(h('h2', { className: 'text-base font-semibold text-gray-900 mb-4' }, 'Aktivitetslog'));

    // Add note form
    const noteTextarea = h('textarea', { rows: '3', className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-blue-500 focus:outline-none mb-2', placeholder: 'Tilf\u00f8j en note...' });
    panel.appendChild(h('div', { className: 'mb-5 pb-5 border-b border-gray-100' },
        noteTextarea,
        h('div', { className: 'flex justify-end mt-2' },
            h('button', {
                className: 'bg-blue-600 text-white px-4 py-1.5 rounded-lg hover:bg-blue-700 text-sm font-medium',
                onClick: async () => {
                    const content = noteTextarea.value.trim();
                    if (!content) return;
                    await onAddNote(content);
                }
            }, 'Gem note')
        )
    ));

    // Merge notes and history, sort newest first
    const noteEntries = notes.map(n => ({ ...n, _type: 'note' }));
    const histEntries = history
        .filter(h_ => h_.action !== 'add_note') // skip "note added" audit duplicates
        .map(h_ => ({ ...h_, _type: 'history' }));
    const all = [...noteEntries, ...histEntries].sort((a, b) =>
        (b.created_at || '').localeCompare(a.created_at || '')
    );

    if (all.length === 0) {
        panel.appendChild(h('div', { className: 'text-sm text-gray-400 italic' }, 'Ingen aktivitet endnu.'));
    }

    // Scrollable container (max ~10 items visible)
    const scrollBox = h('div', { style: 'max-height:480px;overflow-y:auto' });
    panel.appendChild(scrollBox);

    for (const entry of all) {
        const ts = entry.created_at ? entry.created_at.replace('T', ' ').slice(0, 16) : '';

        if (entry._type === 'note') {
            const entryDiv = h('div', { className: 'flex items-start gap-3 py-3 border-b border-gray-50' });
            const dot = h('div', { className: 'w-2 h-2 rounded-full bg-blue-500 mt-1.5 flex-shrink-0' });
            const body_ = h('div', { className: 'flex-1 min-w-0' });

            const meta = h('div', { className: 'flex items-center gap-2 mb-0.5' },
                h('span', { className: 'text-xs font-medium text-gray-800' }, entry.user_name || 'System'),
                h('span', { className: 'text-xs text-gray-400' }, ts)
            );

            const contentDiv = h('p', { className: 'text-sm text-gray-700 whitespace-pre-wrap' }, entry.content);

            // Edit button
            const editBtn = h('button', {
                className: 'text-gray-300 hover:text-blue-500 text-xs ml-1 transition-colors',
                title: 'Rediger note',
                onClick: () => {
                    // Swap content for textarea
                    const editArea = h('textarea', { rows: '3', className: 'w-full border border-blue-300 rounded px-2 py-1 text-sm focus:outline-none mt-1' });
                    editArea.value = entry.content;
                    const actions = h('div', { className: 'flex gap-2 mt-1' },
                        h('button', {
                            className: 'bg-blue-600 text-white px-3 py-1 rounded text-xs hover:bg-blue-700',
                            onClick: async () => {
                                const newContent = editArea.value.trim();
                                if (!newContent) return;
                                await onEditNote(entry.id, newContent);
                            }
                        }, 'Gem'),
                        h('button', {
                            className: 'text-gray-500 px-3 py-1 rounded text-xs hover:text-gray-700',
                            onClick: () => {
                                body_.replaceChild(contentDiv, editArea);
                                actions.remove();
                                editBtn.style.display = '';
                            }
                        }, 'Annuller')
                    );
                    body_.replaceChild(editArea, contentDiv);
                    body_.appendChild(actions);
                    editBtn.style.display = 'none';
                    editArea.focus();
                }
            }, '\u270f');

            body_.appendChild(meta);
            body_.appendChild(contentDiv);
            const metaRow = meta;
            metaRow.appendChild(editBtn);
            entryDiv.appendChild(dot);
            entryDiv.appendChild(body_);
            scrollBox.appendChild(entryDiv);

        } else {
            // History entry
            const action = AUDIT_ACTION_LABELS[entry.action] || entry.action;
            let detail = '';
            if (entry.details && typeof entry.details === 'string') {
                try { const d = JSON.parse(entry.details); detail = Object.entries(d).map(([k,v]) => `${k}: ${typeof v === 'object' ? (v.old + ' \u2192 ' + v.new) : v}`).join(', '); }
                catch { detail = entry.details; }
            }
            scrollBox.appendChild(h('div', { className: 'flex items-start gap-3 py-2 border-b border-gray-50' },
                h('div', { className: 'w-2 h-2 rounded-full bg-gray-300 mt-1.5 flex-shrink-0' }),
                h('div', { className: 'flex-1' },
                    h('span', { className: 'text-xs text-gray-500' }, action),
                    entry.user_name ? h('span', { className: 'text-xs text-gray-400 ml-1' }, `\u2014 ${entry.user_name}`) : null,
                    h('span', { className: 'text-xs text-gray-400 ml-2' }, ts),
                    detail ? h('div', { className: 'text-xs text-gray-400 mt-0.5' }, detail) : null
                )
            ));
        }
    }
    container.appendChild(panel);
}

// ─── Task Detail ───
async function renderTaskDetail(container, id) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    const [task, notes, history, users] = await Promise.all([
        api.getTask(id),
        api.getTaskNotes(id),
        api.getTaskHistory(id),
        api.getUsers()
    ]);
    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';

    const iCls = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:border-blue-500 focus:outline-none';

    function renderView() {
        container.innerHTML = '';
        container.appendChild(h('div', { className: 'mb-6' },
            h('a', { href: `#/area/${task.area || 'salg'}`, className: 'text-sm text-blue-600 hover:underline mb-2 inline-block' }, `\u2190 ${AREA_LABELS[task.area || 'salg']}`),
            h('div', { className: 'flex justify-between items-start' },
                h('div', {},
                    h('h1', { className: 'text-2xl font-bold text-gray-900' },
                        h('a', { href: `#/companies/${task.company_id}`, className: 'hover:underline' }, task.company_name)),
                    h('div', { className: 'text-base text-gray-500 mt-1' }, task.title),
                    h('div', { className: 'flex flex-wrap gap-2 mt-2' },
                        h('span', { className: `area-pill area-${task.area || 'salg'}` }, AREA_LABELS[task.area || 'salg']),
                        h('span', { className: `badge badge-${task.category}` }, CATEGORY_LABELS[task.category] || task.category),
                        h('span', { className: `text-xs priority-${task.priority}` }, PRIORITY_LABELS[task.priority] || task.priority),
                        h('span', { className: `text-xs px-2 py-0.5 rounded-full font-medium ${task.status === 'done' ? 'bg-green-100 text-green-700' : task.status === 'in_progress' ? 'bg-yellow-100 text-yellow-700' : 'bg-blue-100 text-blue-700'}` }, STATUS_LABELS[task.status] || task.status),
                        task.due_date ? h('span', { className: 'text-sm text-gray-500' }, `Frist: ${formatDate(task.due_date)}`) : null
                    )
                ),
                h('div', { className: 'flex gap-2' },
                    h('button', {
                        className: 'bg-white border border-gray-300 text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-50 text-sm',
                        onClick: () => renderEdit()
                    }, 'Rediger'),
                    h('button', {
                        className: 'bg-gray-100 text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-200 text-sm',
                        onClick: async () => {
                            const newStatus = task.status === 'done' ? 'open' : 'done';
                            await api.updateTask(id, { status: newStatus }); router();
                        }
                    }, task.status === 'done' ? 'Genåbn' : 'Marker færdig')
                )
            )
        ));

        if (task.description) {
            container.appendChild(h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6' },
                h('p', { className: 'text-gray-700' }, task.description)
            ));
        }

        const isOverdue = task.due_date && task.due_date < new Date().toISOString().split('T')[0] && task.status !== 'done';
        container.appendChild(h('div', { className: 'grid grid-cols-2 md:grid-cols-4 gap-4 mb-6' },
            h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-4' },
                h('div', { className: 'text-sm font-medium text-gray-500 mb-1' }, 'Ansvarlig'),
                h('div', { className: 'font-semibold text-gray-900' }, task.assigned_to_name || '-')
            ),
            h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-4' },
                h('div', { className: 'text-sm font-medium text-gray-500 mb-1' }, 'Oprettet af'),
                h('div', { className: 'font-semibold text-gray-900' }, task.created_by_name || '-')
            ),
            h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-4' },
                h('div', { className: 'text-sm font-medium text-gray-500 mb-1' }, 'Oprettet'),
                h('div', { className: 'font-semibold text-gray-900' }, task.created_at ? formatDate(task.created_at.split('T')[0]) : '-')
            ),
            h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-4' },
                h('div', { className: 'text-sm font-medium text-gray-500 mb-1' }, 'Frist'),
                h('div', { className: `font-semibold ${isOverdue ? 'text-red-600' : 'text-gray-900'}` }, task.due_date ? formatDate(task.due_date) : '-')
            )
        ));

        renderActivityLog(container, notes, history,
            async (content) => { await api.createTaskNote(id, { content }); router(); },
            async (noteId, content) => { await api.updateTaskNote(noteId, { content }); router(); }
        );
    }

    function renderEdit() {
        container.innerHTML = '';
        container.appendChild(h('a', { href: '#/tasks', className: 'text-sm text-blue-600 hover:underline mb-4 inline-block' }, '\u2190 Alle sager'));

        const fld = (label, el) => h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, label), el);

        const form = h('form', {
            className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6',
            onSubmit: async (e) => {
                e.preventDefault();
                const fd = new FormData(form);
                await api.updateTask(id, {
                    title: fd.get('title'),
                    area: fd.get('area'),
                    category: fd.get('category'),
                    priority: fd.get('priority'),
                    status: fd.get('status'),
                    description: fd.get('description') || null,
                    assigned_to: fd.get('assigned_to') ? parseInt(fd.get('assigned_to')) : null,
                    due_date: fd.get('due_date') || null,
                });
                router();
            }
        },
            h('h2', { className: 'text-base font-semibold text-gray-900 mb-5' }, 'Rediger sag'),
            h('div', { className: 'space-y-4' },
                fld('Titel', h('input', { type: 'text', name: 'title', value: task.title || '', required: true, className: iCls })),
                fld('Område', h('select', { name: 'area', className: iCls },
                    ...Object.entries(AREA_LABELS).map(([k, v]) => h('option', { value: k, ...((task.area || 'salg') === k ? { selected: '' } : {}) }, v))
                )),
                h('div', { className: 'grid grid-cols-2 md:grid-cols-4 gap-4' },
                    fld('Kategori', h('select', { name: 'category', className: iCls },
                        ...Object.entries(CATEGORY_LABELS).map(([k, v]) => h('option', { value: k, ...(task.category === k ? { selected: '' } : {}) }, v))
                    )),
                    fld('Prioritet', h('select', { name: 'priority', className: iCls },
                        ...Object.entries(PRIORITY_LABELS).map(([k, v]) => h('option', { value: k, ...(task.priority === k ? { selected: '' } : {}) }, v))
                    )),
                    fld('Status', h('select', { name: 'status', className: iCls },
                        ...Object.entries(STATUS_LABELS).map(([k, v]) => h('option', { value: k, ...(task.status === k ? { selected: '' } : {}) }, v))
                    )),
                    fld('Frist', h('input', { type: 'date', name: 'due_date', value: task.due_date || '', className: iCls }))
                ),
                fld('Ansvarlig', h('select', { name: 'assigned_to', className: iCls },
                    h('option', { value: '' }, '\u2014 Ingen \u2014'),
                    ...users.map(u => h('option', { value: String(u.id), ...(task.assigned_to == u.id ? { selected: '' } : {}) }, u.name))
                )),
                fld('Beskrivelse', h('textarea', { name: 'description', rows: '3', className: iCls + ' resize-y' }, task.description || ''))
            ),
            h('div', { className: 'flex gap-2 mt-5' },
                h('button', { type: 'submit', className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm font-medium' }, 'Gem \u00e6ndringer'),
                h('button', { type: 'button', className: 'bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50 text-sm', onClick: () => renderView() }, 'Annuller')
            )
        );
        container.appendChild(form);

        renderActivityLog(container, notes, history,
            async (content) => { await api.createTaskNote(id, { content }); router(); },
            async (noteId, content) => { await api.updateTaskNote(noteId, { content }); router(); }
        );
    }

    renderView();
}

async function renderTasks(container, area = null) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    const [allTasks, users, areaGoals] = await Promise.all([api.getTasks(), api.getUsers(),
        area ? api.getGoals({ area }).catch(() => []) : Promise.resolve([])]);
    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';

    const today = new Date().toISOString().split('T')[0];
    const areaOf = t => t.area || 'salg';
    const tasks = area ? allTasks.filter(t => areaOf(t) === area) : allTasks;
    const isOverdue = t => t.due_date && t.due_date < today && t.status !== 'done';
    const showDone = sessionStorage.getItem('tasksShowDone') === '1';

    container.appendChild(h('div', { className: 'flex justify-between items-center mb-6' },
        h('div', {},
            h('h1', { className: 'text-2xl font-bold text-gray-900 flex items-center gap-3' },
                area ? h('span', { className: `area-pill area-${area}`, style: 'font-size:.8rem' }, 'Område') : null,
                area ? AREA_LABELS[area] : 'Alle sager'),
            h('p', { className: 'text-gray-500 mt-1' }, area ? AREA_INTRO[area] : 'Opfølgning pr. virksomhed på tværs af salg, leverance og økonomi')
        ),
        h('button', {
            className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors font-medium',
            onClick: () => { _newTaskArea = area; showTaskForm(null, [], users); }
        }, '+ Ny sag')
    ));

    // Area tabs
    const tabs = h('div', { className: 'area-tabs' },
        ...[[null, 'Alle'], ...Object.entries(AREA_LABELS)].map(([k, v]) => {
            const n = k ? allTasks.filter(t => areaOf(t) === k && t.status !== 'done').length : allTasks.filter(t => t.status !== 'done').length;
            return h('button', { className: (k || null) === area ? 'on' : '', onClick: () => { location.hash = k ? `#/area/${k}` : '#/tasks'; } }, `${v} · ${n}`);
        })
    );
    const doneToggle = h('label', { className: 'flex items-center gap-2 text-sm text-gray-600 cursor-pointer' },
        h('input', { type: 'checkbox', ...(showDone ? { checked: '' } : {}), onChange: (e) => { sessionStorage.setItem('tasksShowDone', e.target.checked ? '1' : '0'); router(); } }),
        'Vis færdige sager');
    container.appendChild(h('div', { className: 'flex flex-wrap items-center justify-between gap-3 mb-5' }, tabs, doneToggle));

    if (area) {
        container.appendChild(h('div', { className: 'flex items-baseline justify-between mb-3' },
            h('h2', { className: 'text-lg font-bold text-gray-900' }, `Mål · ${AREA_ROLE[area]}`),
            h('div', { className: 'flex gap-4 text-sm' },
                h('button', { className: 'font-semibold text-blue-600 hover:underline', onClick: () => showGoalForm(null, { area }) }, '+ Nyt mål'),
                h('a', { href: '#/meetings', className: 'font-semibold text-blue-600 hover:underline' }, 'Ledermøder →'))));
        container.appendChild(areaGoals.length
            ? h('div', { className: 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 mb-6' }, ...areaGoals.map(g => goalCard(g, { compact: true })))
            : h('div', { className: 'empty-box mb-6' }, 'Ingen mål for området endnu.'));
        container.appendChild(h('h2', { className: 'text-lg font-bold text-gray-900 mb-3' }, 'Sager'));
    }

    // KPI tiles
    const open = tasks.filter(t => t.status !== 'done');
    const companiesWithOpen = new Set(open.map(t => t.company_id)).size;
    const kpis = [
        { v: companiesWithOpen, l: 'Virksomheder', s: 'med åbne sager', cls: '' },
        { v: open.filter(t => t.status === 'open').length, l: 'Åbne', s: 'ikke startet', cls: '' },
        { v: open.filter(t => t.status === 'in_progress').length, l: 'I gang', s: 'under behandling', cls: 'warn' },
        { v: open.filter(isOverdue).length, l: 'Forfaldne', s: 'frist overskredet', cls: 'bad' },
        { v: tasks.filter(t => t.status === 'done').length, l: 'Færdige', s: 'i alt', cls: 'good' },
    ];
    container.appendChild(h('div', { className: 'grid grid-cols-2 md:grid-cols-5 gap-3 mb-6' },
        ...kpis.map(k => h('div', { className: `kpi ${k.cls}`, style: 'cursor:default;background:#fff;box-shadow:var(--shadow)' },
            h('div', { className: 'kpi-v' }, String(k.v)),
            h('div', { className: 'kpi-l' }, k.l),
            h('div', { className: 'kpi-s' }, k.s)))
    ));

    // Group by company — the company is the unit we follow up on
    const visible = showDone ? tasks : open;
    const groups = new Map();
    for (const t of visible) {
        if (!groups.has(t.company_id)) groups.set(t.company_id, { id: t.company_id, name: t.company_name, tasks: [] });
        groups.get(t.company_id).tasks.push(t);
    }
    const STATUS_ORDER = { in_progress: 0, open: 1, done: 2 };
    const groupList = [...groups.values()].map(g => {
        g.tasks.sort((a, b) => (STATUS_ORDER[a.status] - STATUS_ORDER[b.status]) || String(a.due_date || '9999').localeCompare(String(b.due_date || '9999')));
        g.overdue = g.tasks.filter(isOverdue).length;
        g.open = g.tasks.filter(t => t.status !== 'done').length;
        g.nextDue = g.tasks.filter(t => t.status !== 'done' && t.due_date).map(t => t.due_date).sort()[0] || '9999';
        return g;
    }).sort((a, b) => (b.overdue - a.overdue) || a.nextDue.localeCompare(b.nextDue) || String(a.name).localeCompare(String(b.name), 'da'));

    const taskList = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden' });
    if (groupList.length === 0) {
        taskList.appendChild(h('div', { className: 'p-8 text-center text-gray-400' }, area ? `Ingen åbne sager inden for ${AREA_LABELS[area].toLowerCase()}.` : 'Ingen åbne sager.'));
    }
    for (const g of groupList) {
        const areas = [...new Set(g.tasks.map(areaOf))];
        taskList.appendChild(h('div', { className: 'co-group-head' },
            h('a', { href: `#/companies/${g.id}` }, g.name),
            h('span', { className: 'text-sm text-gray-500' }, `${g.open} ${g.open === 1 ? 'åben sag' : 'åbne sager'}`),
            g.overdue ? h('span', { className: 'text-sm font-semibold text-red-600' }, `${g.overdue} forfalden${g.overdue === 1 ? '' : 'e'}`) : null,
            !area ? h('span', { className: 'ml-auto flex gap-1' }, ...areas.map(a => h('span', { className: `area-pill area-${a}` }, AREA_LABELS[a]))) : null
        ));
        for (const t of g.tasks) {
            const overdue = isOverdue(t);
            taskList.appendChild(h('div', {
                className: `flex items-center gap-4 pl-10 pr-6 py-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer ${overdue ? 'task-overdue' : ''}`,
                onClick: () => { location.hash = `#/tasks/${t.id}`; }
            },
                h('button', {
                    className: `w-5 h-5 rounded border-2 flex-shrink-0 ${t.status === 'done' ? 'bg-green-500 border-green-500' : 'border-gray-300 hover:border-green-500'}`,
                    onClick: async (e) => {
                        e.stopPropagation();
                        await api.updateTask(t.id, { status: t.status === 'done' ? 'open' : 'done' }); router();
                    }
                }, t.status === 'done' ? h('span', { className: 'text-white text-xs flex items-center justify-center', innerHTML: '✓' }) : null),
                h('div', { className: 'flex-1 min-w-0' },
                    h('div', { className: `${t.status === 'done' ? 'text-gray-400 line-through' : 'text-gray-800'}` }, t.title),
                    h('div', { className: 'flex flex-wrap items-center gap-2 mt-1' },
                        !area ? h('span', { className: `area-pill area-${areaOf(t)}` }, AREA_LABELS[areaOf(t)]) : null,
                        h('span', { className: `badge badge-${t.category}` }, CATEGORY_LABELS[t.category] || t.category),
                        t.status === 'in_progress' ? h('span', { className: 'text-xs px-2 py-0.5 rounded-full font-medium bg-yellow-100 text-yellow-700' }, STATUS_LABELS[t.status]) : null,
                        h('span', { className: `text-xs ${PRIORITY_LABELS[t.priority] ? 'priority-' + t.priority : ''}` }, PRIORITY_LABELS[t.priority] || t.priority),
                        t.assigned_to_name ? h('span', { className: 'text-xs text-gray-500' }, t.assigned_to_name) : null,
                    )
                ),
                t.due_date ? h('div', { className: `text-sm ${overdue ? 'text-red-600 font-medium' : 'text-gray-400'}` }, formatDate(t.due_date)) : null
            ));
        }
    }
    container.appendChild(taskList);
}

// ─── LinkedIn Forms ───
function showLinkedInActivityForm(contacts) {
    const today = new Date().toISOString().split('T')[0];
    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const data = {
            contact_id: parseInt(fd.get('contact_id')),
            activity_type: fd.get('activity_type'),
            content_summary: fd.get('content_summary') || null,
            linkedin_post_url: fd.get('linkedin_post_url') || null,
            activity_date: fd.get('activity_date'),
        };
        try { await api.createLinkedInActivity(data); closeModal(); router(); }
        catch (err) { alert(err.message); }
    }},
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Kontaktperson *'),
            h('select', { name:'contact_id', className:'w-full border border-gray-300 rounded-lg px-3 py-2', required:'' },
                h('option', { value:'' }, 'Vælg...'),
                ...contacts.map(c => h('option', { value: c.id }, `${c.first_name} ${c.last_name}`))
            )
        ),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Aktivitetstype *'),
            h('select', { name:'activity_type', className:'w-full border border-gray-300 rounded-lg px-3 py-2', required:'' },
                ...Object.entries(LI_ACTIVITY_LABELS).map(([k, v]) => h('option', { value: k }, v))
            )
        ),
        formField('Dato *', 'activity_date', today, 'date', true),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Resume'),
            h('textarea', { name:'content_summary', rows:'3', className:'w-full border border-gray-300 rounded-lg px-3 py-2', placeholder:'Hvad handlede opslaget om...' })
        ),
        formField('LinkedIn URL', 'linkedin_post_url', ''),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type:'button', className:'px-4 py-2 text-gray-600', onClick: closeModal }, 'Annuller'),
            h('button', { type:'submit', className:'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, 'Log aktivitet')
        )
    );
    showModal('Log LinkedIn Aktivitet', form);
}

function showLinkedInEngagementForm(contacts) {
    const today = new Date().toISOString().split('T')[0];
    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const data = {
            contact_id: parseInt(fd.get('contact_id')),
            engagement_type: fd.get('engagement_type'),
            company_page: fd.get('company_page'),
            post_url: fd.get('post_url') || null,
            observed_date: fd.get('observed_date'),
            notes: fd.get('notes') || null,
        };
        try { await api.createLinkedInEngagement(data); closeModal(); router(); }
        catch (err) { alert(err.message); }
    }},
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Kontaktperson *'),
            h('select', { name:'contact_id', className:'w-full border border-gray-300 rounded-lg px-3 py-2', required:'' },
                h('option', { value:'' }, 'Vælg...'),
                ...contacts.map(c => h('option', { value: c.id }, `${c.first_name} ${c.last_name}`))
            )
        ),
        h('div', { className: 'grid grid-cols-2 gap-3' },
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Type *'),
                h('select', { name:'engagement_type', className:'w-full border border-gray-300 rounded-lg px-3 py-2', required:'' },
                    ...Object.entries(LI_ENGAGE_LABELS).map(([k, v]) => h('option', { value: k }, v))
                )
            ),
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Virksomhedsside *'),
                h('select', { name:'company_page', className:'w-full border border-gray-300 rounded-lg px-3 py-2', required:'' },
                    h('option', { value:'systemate' }, 'Systemate'),
                    h('option', { value:'settl' }, 'Settl'),
                )
            ),
        ),
        formField('Dato *', 'observed_date', today, 'date', true),
        formField('Post URL', 'post_url', ''),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Noter'),
            h('textarea', { name:'notes', rows:'2', className:'w-full border border-gray-300 rounded-lg px-3 py-2' })
        ),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type:'button', className:'px-4 py-2 text-gray-600', onClick: closeModal }, 'Annuller'),
            h('button', { type:'submit', className:'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, 'Log engagement')
        )
    );
    showModal('Log LinkedIn Engagement', form);
}

// ─── Email Dropzone ───
function createEmailDropzone(contacts, users, companyId) {
    const statusEl = h('div', { className: 'mt-3 text-sm hidden' });
    const dropzone = h('div', { className: 'dropzone rounded-lg p-8 text-center cursor-pointer' },
        h('div', { innerHTML: '<svg class="w-12 h-12 mx-auto text-gray-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>' }),
        h('p', { className: 'text-gray-500 font-medium' }, 'Træk email-filer hertil (.eml)'),
        h('p', { className: 'text-gray-400 text-sm mt-1' }, 'Tip: Træk email fra Outlook til Skrivebordet først'),
        h('input', { type:'file', accept:'.eml,.msg', multiple:'', className:'hidden', id:'eml-input' })
    );
    const selectsRow = h('div', { className: 'grid grid-cols-2 gap-3 mt-3' },
        h('div', {},
            h('label', { className: 'block text-xs font-medium text-gray-500 mb-1' }, 'Tilknyt kontakt *'),
            h('select', { id:'dropzone-contact', className:'w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm' },
                h('option', { value:'' }, 'Vælg kontakt...'),
                ...contacts.map(c => h('option', { value: c.id }, `${c.first_name} ${c.last_name}`))
            )
        ),
        h('div', {},
            h('label', { className: 'block text-xs font-medium text-gray-500 mb-1' }, 'Sælger'),
            h('select', { id:'dropzone-user', className:'w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm' },
                h('option', { value:'' }, 'Vælg...'),
                ...users.map(u => h('option', { value: u.id }, u.name))
            )
        )
    );

    async function handleFiles(files) {
        const contactId = document.getElementById('dropzone-contact').value;
        if (!contactId) {
            statusEl.className = 'mt-3 text-sm text-red-500';
            statusEl.textContent = 'Vælg en kontaktperson først';
            statusEl.classList.remove('hidden');
            return;
        }
        const userId = document.getElementById('dropzone-user').value || null;
        statusEl.className = 'mt-3 text-sm text-blue-500';
        statusEl.classList.remove('hidden');
        let uploaded = 0;
        for (const file of files) {
            const name = file.name.toLowerCase();
            if (!name.endsWith('.eml') && !name.endsWith('.msg')) continue;
            statusEl.textContent = `Uploader ${file.name}...`;
            try { await api.uploadEmail(file, contactId, userId); uploaded++; }
            catch (err) { statusEl.className = 'mt-3 text-sm text-red-500'; statusEl.textContent = `Fejl: ${err.message}`; return; }
        }
        if (uploaded === 0) {
            statusEl.className = 'mt-3 text-sm text-orange-500';
            statusEl.textContent = 'Ingen email-filer fundet. Outlook tip: Træk emailen til Skrivebordet først, og træk .eml filen hertil.';
            statusEl.classList.remove('hidden');
            return;
        }
        statusEl.className = 'mt-3 text-sm text-green-600';
        statusEl.textContent = `${uploaded} email(s) importeret!`;
        setTimeout(() => router(), 1500);
    }

    async function handleDrop(e) {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        const dt = e.dataTransfer;

        // 1. Try .eml/.msg files first (dragged from Finder/desktop)
        if (dt.files && dt.files.length > 0) {
            const hasEmailFile = Array.from(dt.files).some(f => {
                const n = f.name.toLowerCase();
                return n.endsWith('.eml') || n.endsWith('.msg');
            });
            if (hasEmailFile) { handleFiles(dt.files); return; }
        }

        // 2. Try items API for file drops
        if (dt.items && dt.items.length > 0) {
            for (const item of dt.items) {
                if (item.kind === 'file') {
                    const file = item.getAsFile();
                    if (file) { handleFiles([file]); return; }
                }
            }
        }

        // 3. Outlook drag: read text data (subject/content) — settcare approach
        let txt = dt.getData('text/plain')
            || dt.getData('text/html')
            || dt.getData('text/uri-list')
            || dt.getData('text')
            || '';
        // Strip HTML tags if we got HTML
        if (txt.includes('<')) txt = txt.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
        // If we got .msg file, use filename as subject
        if (!txt && dt.files && dt.files.length > 0) {
            txt = dt.files[0].name.replace(/\.\w+$/, '');
        }

        if (txt) {
            // Create interaction from Outlook drag text
            const contactId = document.getElementById('dropzone-contact').value;
            if (!contactId) {
                statusEl.className = 'mt-3 text-sm text-red-500';
                statusEl.textContent = 'Vælg en kontaktperson først';
                statusEl.classList.remove('hidden');
                return;
            }
            const userId = document.getElementById('dropzone-user').value || null;
            statusEl.className = 'mt-3 text-sm text-blue-500';
            statusEl.textContent = 'Importerer email fra Outlook...';
            statusEl.classList.remove('hidden');
            try {
                const subject = txt.slice(0, 120);
                await api.createInteraction({
                    contact_id: parseInt(contactId),
                    user_id: userId ? parseInt(userId) : null,
                    type: 'email',
                    date: new Date().toISOString().slice(0, 10),
                    subject: subject,
                    notes: 'Importeret via drag-drop fra Outlook.\n\n' + txt
                });
                statusEl.className = 'mt-3 text-sm text-green-600';
                statusEl.textContent = 'Email registreret fra Outlook!';
                setTimeout(() => router(), 1500);
            } catch (err) {
                statusEl.className = 'mt-3 text-sm text-red-500';
                statusEl.textContent = `Fejl: ${err.message}`;
            }
            return;
        }

        // 4. Nothing worked
        statusEl.className = 'mt-3 text-sm text-orange-500';
        statusEl.textContent = 'Kunne ikke læse email-data. Prøv at trække emailen direkte fra Outlook.';
        statusEl.classList.remove('hidden');
    }

    dropzone.addEventListener('click', () => document.getElementById('eml-input').click());
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', handleDrop);
    document.addEventListener('change', (e) => { if (e.target.id === 'eml-input') handleFiles(e.target.files); });

    return h('div', {}, dropzone, selectsRow, statusEl);
}

// ─── Email Detail ───
function showEmailDetail(em) {
    showModal(em.subject || '(Intet emne)', h('div', { className: 'space-y-3' },
        h('div', { className: 'bg-gray-50 rounded-lg p-3 text-sm space-y-1' },
            h('div', {}, h('strong', {}, 'Fra: '), em.from_email || '?'),
            h('div', {}, h('strong', {}, 'Til: '), em.to_email || '?'),
            em.cc ? h('div', {}, h('strong', {}, 'CC: '), em.cc) : null,
            h('div', {}, h('strong', {}, 'Dato: '), formatDate(em.date_sent)),
        ),
        h('div', { className: 'border rounded-lg p-4 text-sm whitespace-pre-wrap max-h-96 overflow-y-auto' }, em.body_text || em.body_html || '(Tom)')
    ));
}

// ─── Users ───
async function renderUsers(container) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    const allUsers = await api.getUsers();
    const activeUsers = allUsers.filter(u => !u.deleted_at);
    const deletedUsers = allUsers.filter(u => u.deleted_at);
    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';

    container.appendChild(h('div', { className: 'flex justify-between items-center mb-6' },
        h('div', {},
            h('h1', { className: 'text-2xl font-bold text-gray-900' }, 'Brugere / Sælgere'),
            h('p', { className: 'text-gray-500 mt-1' }, `${activeUsers.length} aktive brugere`)
        ),
        h('button', {
            className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors font-medium',
            onClick: () => showUserForm()
        }, '+ Tilføj bruger')
    ));

    if (activeUsers.length === 0) {
        container.appendChild(h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center text-gray-400' }, 'Ingen aktive brugere.'));
    } else {
        const table = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden mb-6' });
        for (const u of activeUsers) {
            table.appendChild(h('div', { className: 'flex items-center justify-between px-6 py-4 border-b border-gray-100' },
                h('div', { className: 'flex items-center gap-3' },
                    h('div', { className: 'w-10 h-10 rounded-full bg-blue-500 flex items-center justify-center text-sm font-bold text-white' },
                        u.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
                    ),
                    h('div', {},
                        h('div', { className: 'font-medium text-gray-900' }, u.name),
                        h('div', { className: 'text-sm text-gray-500' }, u.email)
                    )
                ),
                h('div', { className: 'flex items-center gap-3' },
                    h('span', { className: `badge ${u.role === 'admin' ? 'bg-purple-100 text-purple-800' : 'bg-gray-100 text-gray-600'}` }, u.role),
                    h('button', {
                        className: 'text-gray-300 hover:text-red-500', title: 'Deaktiver bruger',
                        onClick: async () => {
                            if (confirm(`Deaktiver bruger "${u.name}"? Brugeren fjernes fra aktive brugere men beholdes i systemet.`)) {
                                await api.deleteUser(u.id);
                                router();
                            }
                        }
                    }, h('span', { innerHTML: '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"/></svg>' }))
                )
            ));
        }
        container.appendChild(table);
    }

    // Deleted users section
    if (deletedUsers.length > 0) {
        container.appendChild(h('div', { className: 'flex items-center gap-3 mb-4' },
            h('h2', { className: 'text-lg font-semibold text-gray-500' }, 'Deaktiverede brugere'),
            h('span', { className: 'text-sm text-gray-400' }, `${deletedUsers.length} brugere`)
        ));
        const delTable = h('div', { className: 'bg-gray-50 rounded-xl border border-gray-200 overflow-hidden' });
        for (const u of deletedUsers) {
            delTable.appendChild(h('div', { className: 'flex items-center justify-between px-6 py-3 border-b border-gray-200' },
                h('div', { className: 'flex items-center gap-3' },
                    h('div', { className: 'w-10 h-10 rounded-full bg-gray-300 flex items-center justify-center text-sm font-bold text-white' },
                        u.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
                    ),
                    h('div', {},
                        h('div', { className: 'font-medium text-gray-500' }, u.name),
                        h('div', { className: 'text-xs text-gray-400' }, `${u.email} — deaktiveret ${formatDate(u.deleted_at)}`)
                    )
                ),
                h('button', {
                    className: 'text-sm text-blue-600 hover:text-blue-800',
                    onClick: async () => {
                        if (confirm(`Genaktiver bruger "${u.name}"?`)) {
                            await api.restoreUser(u.id);
                            router();
                        }
                    }
                }, 'Genaktiver')
            ));
        }
        container.appendChild(delTable);
    }
}

function showUserForm() {
    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try { await api.createUser(Object.fromEntries(fd.entries())); closeModal(); router(); initUserSelector(); }
        catch (err) { alert(err.message); }
    }},
        formField('Navn *', 'name', '', 'text', true),
        formField('Email *', 'email', '', 'email', true),
        h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Rolle'),
            h('select', { name:'role', className:'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value:'user' }, 'Bruger'),
                h('option', { value:'admin' }, 'Administrator'),
            )
        ),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type:'button', className:'px-4 py-2 text-gray-600', onClick: closeModal }, 'Annuller'),
            h('button', { type:'submit', className:'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, 'Opret')
        )
    );
    showModal('Ny bruger', form);
}

// ─── Settings Page ───
async function renderSettings(container) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    const [thresholds, decayRules] = await Promise.all([
        api.getScoreThresholds(),
        api.getDecayRules()
    ]);
    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';

    container.appendChild(h('div', { className: 'mb-6' },
        h('h1', { className: 'text-2xl font-bold text-gray-900' }, 'Indstillinger'),
        h('p', { className: 'text-gray-500 mt-1' }, 'Konfigurer dashboard og scoreregler')
    ));

    // ─── Score Thresholds Section ───
    const thresholdCard = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6' });
    thresholdCard.appendChild(h('h2', { className: 'text-lg font-semibold text-gray-900 mb-4' }, 'Score Grænseværdier'));
    thresholdCard.appendChild(h('p', { className: 'text-sm text-gray-500 mb-4' }, 'Bestemmer hvornår en virksomhed får en notifikation, hvis scoren falder under grænsen for deres rating.'));

    const thresholdInputs = {};
    const thresholdGrid = h('div', { className: 'grid grid-cols-3 gap-4' });
    for (const rating of ['A', 'B', 'C']) {
        const inp = h('input', {
            type: 'number', min: '0', max: '100', value: String(thresholds[rating] || 50),
            className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm'
        });
        thresholdInputs[rating] = inp;
        thresholdGrid.appendChild(h('div', {},
            h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, `${rating}-kunde`),
            inp
        ));
    }
    thresholdCard.appendChild(thresholdGrid);

    const saveThresholdsBtn = h('button', {
        className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm font-medium mt-4',
        onClick: async () => {
            try {
                const data = {};
                for (const [r, inp] of Object.entries(thresholdInputs)) data[r] = parseInt(inp.value);
                await api.updateScoreThresholds(data);
                saveThresholdsBtn.textContent = 'Gemt!';
                setTimeout(() => { saveThresholdsBtn.textContent = 'Gem grænseværdier'; }, 2000);
            } catch (err) { alert(err.message); }
        }
    }, 'Gem grænseværdier');
    thresholdCard.appendChild(saveThresholdsBtn);
    container.appendChild(thresholdCard);

    // ─── Decay Rules Section ───
    const decayCard = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6' });
    decayCard.appendChild(h('h2', { className: 'text-lg font-semibold text-gray-900 mb-4' }, 'Inaktivitets-straf'));
    decayCard.appendChild(h('p', { className: 'text-sm text-gray-500 mb-4' },
        'Konfigurer point-fald når en virksomhed ikke har haft aktivitet i et bestemt antal dage. Reglerne er kumulative - den højeste matchende straf anvendes.'));

    let rules = decayRules.map(r => ({ ...r }));

    function renderRulesTable() {
        const existingTable = decayCard.querySelector('.decay-rules-wrapper');
        if (existingTable) existingTable.remove();

        const wrapper = h('div', { className: 'decay-rules-wrapper' });

        if (rules.length === 0) {
            wrapper.appendChild(h('div', { className: 'text-sm text-gray-400 italic py-4' }, 'Ingen regler defineret. Tilføj en regel for at komme i gang.'));
        } else {
            // Table header
            const thead = h('div', { className: 'grid grid-cols-12 gap-2 px-3 py-2 bg-gray-50 rounded-t-lg text-xs font-semibold text-gray-500 uppercase' },
                h('div', { className: 'col-span-2' }, 'Dage'),
                h('div', { className: 'col-span-2' }, 'Point'),
                h('div', { className: 'col-span-4' }, 'Beskrivelse'),
                h('div', { className: 'col-span-2' }, 'Aktiv'),
                h('div', { className: 'col-span-2' }, '')
            );
            wrapper.appendChild(thead);

            for (let i = 0; i < rules.length; i++) {
                const rule = rules[i];
                const row = h('div', { className: 'grid grid-cols-12 gap-2 px-3 py-2 border-b border-gray-100 items-center' },
                    h('div', { className: 'col-span-2' },
                        h('input', {
                            type: 'number', min: '1', value: String(rule.inactivity_days),
                            className: 'w-full border border-gray-300 rounded px-2 py-1 text-sm',
                            onInput: (e) => { rule.inactivity_days = parseInt(e.target.value) || 1; }
                        })
                    ),
                    h('div', { className: 'col-span-2' },
                        h('input', {
                            type: 'number', min: '0', value: String(rule.penalty_points),
                            className: 'w-full border border-gray-300 rounded px-2 py-1 text-sm',
                            onInput: (e) => { rule.penalty_points = parseInt(e.target.value) || 0; }
                        })
                    ),
                    h('div', { className: 'col-span-4' },
                        h('input', {
                            type: 'text', value: rule.description || '',
                            className: 'w-full border border-gray-300 rounded px-2 py-1 text-sm',
                            onInput: (e) => { rule.description = e.target.value; }
                        })
                    ),
                    h('div', { className: 'col-span-2 flex items-center' },
                        h('input', {
                            type: 'checkbox',
                            className: 'w-4 h-4 rounded border-gray-300 text-blue-600',
                            ...(rule.is_active ? { checked: '' } : {}),
                            onChange: (e) => { rule.is_active = e.target.checked; }
                        })
                    ),
                    h('div', { className: 'col-span-2 flex justify-end' },
                        h('button', {
                            className: 'text-red-400 hover:text-red-600 text-sm',
                            onClick: () => { rules.splice(i, 1); renderRulesTable(); }
                        }, 'Slet')
                    )
                );
                wrapper.appendChild(row);
            }
        }

        // Add rule button
        wrapper.appendChild(h('button', {
            className: 'text-blue-600 hover:text-blue-800 text-sm font-medium mt-3',
            onClick: () => {
                rules.push({ inactivity_days: 30, penalty_points: 10, description: '', is_active: true });
                renderRulesTable();
            }
        }, '+ Tilføj regel'));

        decayCard.appendChild(wrapper);
    }

    renderRulesTable();

    const saveDecayBtn = h('button', {
        className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm font-medium mt-4',
        onClick: async () => {
            try {
                await api.updateDecayRules({ rules });
                saveDecayBtn.textContent = 'Gemt!';
                setTimeout(() => { saveDecayBtn.textContent = 'Gem regler'; }, 2000);
            } catch (err) { alert(err.message); }
        }
    }, 'Gem regler');
    decayCard.appendChild(saveDecayBtn);
    container.appendChild(decayCard);

    // ─── Tender Templates Section ───
    const tmplCard = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6 mt-6' });
    tmplCard.appendChild(h('h2', { className: 'text-lg font-semibold text-gray-900 mb-1' }, 'Tilbudsskabeloner'));
    tmplCard.appendChild(h('p', { className: 'text-sm text-gray-500 mb-4' },
        'Opret og rediger skabeloner der bruges til at oprette nye tilbud med foruddefinerede sektioner.'));

    const tmplListWrapper = h('div', { className: 'space-y-4' });

    async function loadTemplates() {
        tmplListWrapper.innerHTML = '<div class="text-sm text-gray-400">Indlæser...</div>';
        const templates = await api.getTenderTemplates();
        tmplListWrapper.innerHTML = '';

        if (templates.length === 0) {
            tmplListWrapper.appendChild(h('div', { className: 'text-sm text-gray-400 italic py-4' },
                'Ingen skabeloner endnu. Opret en for at komme i gang.'));
        }

        for (const tmpl of templates) {
            const detail = await api.getTenderTemplate(tmpl.id);
            const sections = detail.sections || [];
            const tmplEl = h('div', { className: 'border border-gray-200 rounded-lg p-4' });

            // Template header with inline editing
            const nameDisplay = h('div', { className: 'flex items-center justify-between mb-3' });
            const nameSpan = h('div', { className: 'flex items-center gap-2' },
                h('span', { className: 'font-semibold text-gray-800' }, tmpl.name),
                tmpl.is_default ? h('span', { className: 'badge badge-god text-xs' }, 'Standard') : null,
                h('span', { className: 'text-xs text-gray-400' }, `${tmpl.section_count} sektioner`)
            );
            const editTmplBtn = h('button', {
                className: 'text-blue-600 hover:text-blue-800 text-sm',
                onClick: () => showTemplateForm(tmpl)
            }, 'Rediger');
            const deleteTmplBtn = h('button', {
                className: 'text-red-400 hover:text-red-600 text-sm ml-2',
                onClick: async () => {
                    if (!confirm(`Slet skabelon "${tmpl.name}"?`)) return;
                    await api.deleteTenderTemplate(tmpl.id);
                    loadTemplates();
                }
            }, 'Slet');
            nameDisplay.appendChild(nameSpan);
            nameDisplay.appendChild(h('div', {}, editTmplBtn, deleteTmplBtn));
            tmplEl.appendChild(nameDisplay);

            if (tmpl.description) {
                tmplEl.appendChild(h('p', { className: 'text-sm text-gray-500 mb-3' }, tmpl.description));
            }

            // Sections list
            const secList = h('div', { className: 'space-y-1' });
            for (const sec of sections) {
                const secRow = h('div', { className: 'flex items-center justify-between px-3 py-2 bg-gray-50 rounded-lg text-sm' });
                secRow.appendChild(h('div', { className: 'flex items-center gap-3' },
                    h('span', { className: 'text-gray-400 text-xs font-mono w-5' }, `${sec.sort_order + 1}.`),
                    h('span', { className: 'text-gray-700' }, sec.title),
                    h('span', { className: 'text-xs text-gray-400' }, `${sec.default_days_before_deadline}d før deadline`)
                ));
                secRow.appendChild(h('div', { className: 'flex gap-1' },
                    h('button', {
                        className: 'text-gray-400 hover:text-blue-600 text-xs px-1',
                        onClick: () => showTemplateSectionForm(tmpl.id, sec, () => loadTemplates())
                    }, 'Rediger'),
                    h('button', {
                        className: 'text-gray-400 hover:text-red-600 text-xs px-1',
                        onClick: async () => {
                            await api.deleteTemplateSection(sec.id);
                            loadTemplates();
                        }
                    }, 'Slet')
                ));
                secList.appendChild(secRow);
            }
            tmplEl.appendChild(secList);

            // Add section button
            tmplEl.appendChild(h('button', {
                className: 'text-blue-600 hover:text-blue-800 text-sm font-medium mt-2',
                onClick: () => showTemplateSectionForm(tmpl.id, null, () => loadTemplates())
            }, '+ Tilføj sektion'));

            tmplListWrapper.appendChild(tmplEl);
        }
    }

    // Show template create/edit modal
    function showTemplateForm(existing = null) {
        const isEdit = !!existing;
        const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
            e.preventDefault();
            const fd = new FormData(e.target);
            const data = { name: fd.get('name'), description: fd.get('description') || null };
            try {
                if (isEdit) await api.updateTenderTemplate(existing.id, data);
                else await api.createTenderTemplate(data);
                closeModal();
                loadTemplates();
            } catch (err) { alert(err.message); }
        }},
            formField('Navn *', 'name', existing?.name || '', 'text', true),
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Beskrivelse'),
                h('textarea', { name: 'description', rows: '2', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' }, existing?.description || '')
            ),
            h('div', { className: 'flex justify-end gap-3 pt-2' },
                h('button', { type: 'button', className: 'px-4 py-2 text-gray-600', onClick: closeModal }, 'Annuller'),
                h('button', { type: 'submit', className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' },
                    isEdit ? 'Gem' : 'Opret skabelon')
            )
        );
        showModal(isEdit ? 'Rediger skabelon' : 'Ny skabelon', form);
    }

    // Show template section create/edit modal
    function showTemplateSectionForm(templateId, existing = null, onDone) {
        const isEdit = !!existing;
        const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
            e.preventDefault();
            const fd = new FormData(e.target);
            const data = {
                title: fd.get('title'),
                description: fd.get('description') || null,
                default_days_before_deadline: parseInt(fd.get('default_days_before_deadline') || '7'),
                sort_order: parseInt(fd.get('sort_order') || '0'),
            };
            try {
                if (isEdit) await api.updateTemplateSection(existing.id, data);
                else await api.addTemplateSection(templateId, data);
                closeModal();
                if (onDone) onDone();
            } catch (err) { alert(err.message); }
        }},
            formField('Titel *', 'title', existing?.title || '', 'text', true),
            h('div', {},
                h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Beskrivelse'),
                h('textarea', { name: 'description', rows: '2', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' }, existing?.description || '')
            ),
            h('div', { className: 'grid grid-cols-2 gap-3' },
                formField('Dage før deadline', 'default_days_before_deadline', String(existing?.default_days_before_deadline ?? 7), 'number'),
                formField('Rækkefølge', 'sort_order', String(existing?.sort_order ?? 0), 'number')
            ),
            h('div', { className: 'flex justify-end gap-3 pt-2' },
                h('button', { type: 'button', className: 'px-4 py-2 text-gray-600', onClick: closeModal }, 'Annuller'),
                h('button', { type: 'submit', className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' },
                    isEdit ? 'Gem' : 'Tilføj sektion')
            )
        );
        showModal(isEdit ? 'Rediger sektion' : 'Ny sektion', form);
    }

    // New template button
    tmplCard.appendChild(h('div', { className: 'flex justify-end mb-4' },
        h('button', {
            className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm font-medium',
            onClick: () => showTemplateForm()
        }, '+ Ny skabelon')
    ));

    tmplCard.appendChild(tmplListWrapper);
    container.appendChild(tmplCard);

    // Load templates
    loadTemplates();
}

// ════════════════════════════════════════════════════════════════════
// SystemateCEO — mål, statusopdateringer og strukturerede ledermøder
// ════════════════════════════════════════════════════════════════════
const GOAL_AREAS = { ...AREA_LABELS, tvaers: 'Tværgående' };
const AREA_ROLE = { salg: 'CCO', leverance: 'COO', oekonomi: 'CFO', tvaers: 'CEO' };
const ROLE_LABELS = { CEO: 'CEO', CCO: 'CCO · salg & marketing', COO: 'COO · leverance', CFO: 'CFO · økonomi' };
const MEETING_TITLES = {
    salg: 'Salg & marketing med CCO',
    leverance: 'Leverance med COO',
    oekonomi: 'Økonomi med CFO',
    tvaers: 'Ledelsesmøde · strategi',
};
const GOAL_KIND_LABELS = { drift: 'Driftsmål', strategisk: 'Strategisk mål' };
const GOAL_STATUS = {
    not_started: { label: 'Ikke vurderet', cls: 'gs-none' },
    on_track: { label: 'På sporet', cls: 'gs-good' },
    at_risk: { label: 'I risiko', cls: 'gs-warn' },
    off_track: { label: 'Bagud', cls: 'gs-bad' },
    done: { label: 'Nået', cls: 'gs-done' },
};
const STALE_DAYS = 30; // et mål uden statusopdatering i så mange dage markeres som "ikke fulgt op"

function todayIso() { return new Date().toISOString().split('T')[0]; }
function addDaysIso(days, from = todayIso()) {
    const d = new Date(from + 'T00:00:00'); d.setDate(d.getDate() + days);
    return d.toISOString().split('T')[0];
}
function daysBetween(a, b) { return Math.round((new Date(b + 'T00:00:00') - new Date(String(a).slice(0, 10) + 'T00:00:00')) / 86400000); }
function fmtNum(n) {
    if (n == null || n === '') return '–';
    return Number(n).toLocaleString('da-DK', { maximumFractionDigits: 1 });
}
function fmtGoalValue(n, unit) {
    if (n == null || n === '') return '–';
    return unit === '%' ? `${fmtNum(n)} %` : `${fmtNum(n)}${unit ? ' ' + unit : ''}`;
}

// Fremdrift 0–1 mod målværdien (virker også for mål, der skal ned, fx omkostninger)
function goalProgress(g) {
    if (g.target_value == null) return null;
    const start = Number(g.start_value || 0), target = Number(g.target_value), cur = Number(g.current_value ?? start);
    if (target === start) return cur === target ? 1 : 0;
    return Math.max(0, Math.min(1, (cur - start) / (target - start)));
}
// Hvor langt vi burde være nået, hvis fremdriften var lineær fra start til deadline
function goalExpected(g) {
    if (!g.due_date) return null;
    const start = (g.start_date || g.created_at || todayIso()).slice(0, 10);
    const total = daysBetween(start, g.due_date);
    if (total <= 0) return 1;
    return Math.max(0, Math.min(1, daysBetween(start, todayIso()) / total));
}
function suggestGoalStatus(g, value) {
    const probe = { ...g, current_value: value === '' || value == null ? g.current_value : value };
    const p = goalProgress(probe), e = goalExpected(probe);
    if (p == null) return null;
    if (p >= 1) return 'done';
    if (e == null || e === 0) return 'on_track';
    if (p >= e - 0.05) return 'on_track';
    if (p >= e - 0.2) return 'at_risk';
    return 'off_track';
}
function goalIsStale(g) {
    if (g.status === 'done') return false;
    const ref = g.last_checkin || (g.created_at || '').slice(0, 10);
    return !ref || daysBetween(ref, todayIso()) > STALE_DAYS;
}
function goalStatusPill(status) {
    const s = GOAL_STATUS[status] || GOAL_STATUS.not_started;
    return h('span', { className: `gs-pill ${s.cls}` }, s.label);
}
function goalProgressBar(g) {
    const p = goalProgress(g), e = goalExpected(g);
    const st = GOAL_STATUS[g.status] || GOAL_STATUS.not_started;
    return h('div', { className: 'gp' },
        h('div', { className: 'gp-track' },
            h('i', { className: `gp-fill ${st.cls}`, style: `width:${p == null ? 0 : Math.round(p * 100)}%` }),
            e != null && g.status !== 'done' ? h('b', { className: 'gp-mark', style: `left:${Math.round(e * 100)}%`, title: 'Forventet fremdrift i dag' }) : null
        ),
        h('span', { className: 'gp-pct' }, p == null ? '' : `${Math.round(p * 100)}%`)
    );
}
function lastUpdateText(g) {
    if (!g.last_checkin) return 'Aldrig opdateret';
    const d = daysBetween(g.last_checkin, todayIso());
    return d === 0 ? 'Opdateret i dag' : `Opdateret for ${d} dage siden`;
}

function goalCard(g, opts = {}) {
    const stale = goalIsStale(g);
    return h('a', { href: `#/goals/${g.id}`, className: `goal-card ${opts.compact ? 'compact' : ''}` },
        h('div', { className: 'flex items-center gap-2 mb-2 flex-wrap' },
            h('span', { className: `area-pill area-${g.area}` }, GOAL_AREAS[g.area] || g.area),
            h('span', { className: 'goal-kind' }, GOAL_KIND_LABELS[g.kind] || g.kind),
            g.owner_role ? h('span', { className: 'goal-owner' }, g.owner_role) : null,
            h('span', { className: 'ml-auto' }, goalStatusPill(g.status))
        ),
        h('div', { className: 'goal-title' }, g.title),
        g.company_name ? h('div', { className: 'text-sm text-gray-500' }, g.company_name) : null,
        g.target_value != null ? h('div', { className: 'mt-3' },
            goalProgressBar(g),
            h('div', { className: 'flex justify-between text-xs text-gray-500 mt-1' },
                h('span', {}, `${fmtGoalValue(g.current_value ?? g.start_value, g.unit)} af ${fmtGoalValue(g.target_value, g.unit)}`),
                g.due_date ? h('span', {}, `Deadline ${formatDate(g.due_date)}`) : null)
        ) : (g.milestones_total ? h('div', { className: 'text-xs text-gray-500 mt-3' }, `${g.milestones_done}/${g.milestones_total} milepæle nået`) : null),
        opts.compact ? null : h('div', { className: `goal-foot ${stale ? 'stale' : ''}` },
            h('span', {}, stale ? `⚠ ${lastUpdateText(g)}` : lastUpdateText(g)),
            g.open_actions ? h('span', {}, `${g.open_actions} åbne aktioner`) : null),
        !opts.compact && g.last_comment ? h('div', { className: 'goal-comment' }, `“${g.last_comment}”`) : null
    );
}

// ─── Mål: liste ───
async function renderGoals(container) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    const goals = await api.getGoals();
    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';
    const areaFilter = sessionStorage.getItem('goalsArea') || '';

    container.appendChild(h('div', { className: 'flex justify-between items-center mb-6' },
        h('div', {},
            h('h1', { className: 'text-2xl font-bold text-gray-900' }, 'Mål'),
            h('p', { className: 'text-gray-500 mt-1' }, 'Driftsmål og strategiske mål for salg & marketing, leverance og økonomi')),
        h('button', { className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium',
            onClick: () => showGoalForm(null, { area: areaFilter || 'salg' }) }, '+ Nyt mål')
    ));

    container.appendChild(h('div', { className: 'mb-5' }, h('div', { className: 'area-tabs' },
        ...[['', 'Alle'], ...Object.entries(GOAL_AREAS)].map(([k, v]) => h('button', {
            className: k === areaFilter ? 'on' : '',
            onClick: () => { sessionStorage.setItem('goalsArea', k); router(); }
        }, `${v} · ${goals.filter(g => !k || g.area === k).length}`))
    )));

    const list = goals.filter(g => !areaFilter || g.area === areaFilter);
    const count = st => list.filter(g => g.status === st).length;
    const stale = list.filter(goalIsStale).length;
    container.appendChild(h('div', { className: 'grid grid-cols-2 md:grid-cols-5 gap-3 mb-6' },
        ...[
            [count('on_track'), 'På sporet', 'good'], [count('at_risk'), 'I risiko', 'warn'], [count('off_track'), 'Bagud', 'bad'],
            [stale, 'Ikke fulgt op', stale ? 'warn' : ''], [count('done'), 'Nået', 'good'],
        ].map(([v, l, cls]) => h('div', { className: `kpi ${cls}`, style: 'cursor:default;background:#fff;box-shadow:var(--shadow)' },
            h('div', { className: 'kpi-v' }, String(v)), h('div', { className: 'kpi-l' }, l),
            h('div', { className: 'kpi-s' }, l === 'Ikke fulgt op' ? `> ${STALE_DAYS} dage uden status` : 'mål')))
    ));

    for (const kind of ['drift', 'strategisk']) {
        const ks = list.filter(g => g.kind === kind);
        container.appendChild(h('div', { className: 'flex items-baseline gap-3 mb-3 mt-2' },
            h('h2', { className: 'text-lg font-bold text-gray-900' }, kind === 'drift' ? 'Driftsmål' : 'Strategiske mål'),
            h('span', { className: 'text-sm text-gray-400' }, kind === 'drift'
                ? 'Kortsigtede mål: salgstal, leveranceplaner, budgetter'
                : 'Langsigtede retninger: position, kompetencer, måden vi arbejder på')));
        if (ks.length === 0) {
            container.appendChild(h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6 text-gray-400 text-sm' },
                kind === 'drift' ? 'Ingen driftsmål endnu, fx en leveranceplan til en kunde eller et salgsmål for året.'
                    : 'Ingen strategiske mål endnu.'));
            continue;
        }
        container.appendChild(h('div', { className: 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-8' }, ...ks.map(g => goalCard(g))));
    }
}

// ─── Mål: formular ───
async function showGoalForm(existing, defaults = {}) {
    let companies = [];
    try { companies = await api.getCompanies(); } catch (e) {}
    const g = existing || { kind: 'drift', area: 'salg', start_value: 0, start_date: todayIso(), ...defaults };
    const sel = (name, options, value) => h('select', { name, className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
        ...Object.entries(options).map(([k, v]) => h('option', { value: k, ...(String(value ?? '') === k ? { selected: '' } : {}) }, v)));
    const lbl = (text, el, hint) => h('div', {}, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, text), el,
        hint ? h('div', { className: 'text-xs text-gray-400 mt-1' }, hint) : null);
    const roleSel = sel('owner_role', { '': 'Vælg...', ...ROLE_LABELS }, g.owner_role || AREA_ROLE[g.area]);

    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const num = k => fd.get(k) === '' ? null : Number(String(fd.get(k)).replace(/\./g, '').replace(',', '.'));
        const data = {
            title: fd.get('title'), area: fd.get('area'), kind: fd.get('kind'), owner_role: fd.get('owner_role') || null,
            description: fd.get('description') || null, unit: fd.get('unit') || null,
            start_value: num('start_value'), target_value: num('target_value'),
            start_date: fd.get('start_date') || null, due_date: fd.get('due_date') || null,
            company_id: fd.get('company_id') ? parseInt(fd.get('company_id')) : null,
        };
        if (!existing) data.current_value = data.start_value;
        try {
            const saved = existing ? await api.updateGoal(existing.id, data) : await api.createGoal(data);
            closeModal();
            if (existing) router(); else location.hash = `#/goals/${saved.id}`;
        } catch (err) { alert(err.message); }
    }},
        lbl('Mål *', h('input', { name: 'title', required: '', value: g.title || '', className: 'w-full border border-gray-300 rounded-lg px-3 py-2', placeholder: 'Fx Sælge 150.000 målepunkter i 2027' })),
        h('div', { className: 'grid grid-cols-3 gap-3' },
            lbl('Type *', sel('kind', GOAL_KIND_LABELS, g.kind)),
            lbl('Område *', (() => {
                const s = sel('area', GOAL_AREAS, g.area);
                s.addEventListener('change', () => { roleSel.value = AREA_ROLE[s.value]; });
                return s;
            })()),
            lbl('Ansvarlig', roleSel)),
        lbl('Hvordan måles det?', h('textarea', { name: 'description', rows: '2', className: 'w-full border border-gray-300 rounded-lg px-3 py-2',
            placeholder: 'Fx antal målepunkter i underskrevne kontrakter' }, g.description || '')),
        h('div', { className: 'grid grid-cols-3 gap-3' },
            lbl('Startværdi', h('input', { name: 'start_value', value: g.start_value ?? '', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' })),
            lbl('Målværdi', h('input', { name: 'target_value', value: g.target_value ?? '', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' })),
            lbl('Enhed', h('input', { name: 'unit', value: g.unit || '', className: 'w-full border border-gray-300 rounded-lg px-3 py-2', placeholder: 'målepunkter, %, kr.' }))),
        h('div', { className: 'grid grid-cols-2 gap-3' },
            lbl('Start', h('input', { type: 'date', name: 'start_date', value: (g.start_date || '').slice(0, 10), className: 'w-full border border-gray-300 rounded-lg px-3 py-2' })),
            lbl('Deadline', h('input', { type: 'date', name: 'due_date', value: (g.due_date || '').slice(0, 10), className: 'w-full border border-gray-300 rounded-lg px-3 py-2' }))),
        lbl('Kunde (valgfri)', h('select', { name: 'company_id', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
            h('option', { value: '' }, 'Ingen bestemt kunde'),
            ...companies.map(c => h('option', { value: c.id, ...(g.company_id == c.id ? { selected: '' } : {}) }, c.name))),
            'Bruges fx til en leveranceplan for en bestemt kunde. Milepæle tilføjer du på målets side.'),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type: 'button', className: 'px-4 py-2 text-gray-600', onClick: closeModal }, 'Annuller'),
            h('button', { type: 'submit', className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, existing ? 'Gem' : 'Opret mål'))
    );
    showModal(existing ? 'Rediger mål' : 'Nyt mål', form, 'max-w-2xl');
}

// ─── Statusopdatering (check-in) — bruges både på målsiden og i møder ───
function showCheckinForm(goal, meetingId, onDone) {
    const hasTarget = goal.target_value != null;
    const statusSel = h('select', { name: 'status', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
        ...Object.entries(GOAL_STATUS).filter(([k]) => k !== 'not_started').map(([k, v]) => h('option', { value: k }, v.label)));
    const hint = h('div', { className: 'text-xs mt-1 text-gray-500' });
    const commentBox = h('textarea', { name: 'comment', rows: '3', className: 'w-full border border-gray-300 rounded-lg px-3 py-2',
        placeholder: 'Hvad er status, og hvad gør vi nu?' });
    const commentHint = h('div', { className: 'text-xs mt-1 text-gray-400' });

    function refresh(valueStr) {
        const suggestion = suggestGoalStatus(goal, valueStr === '' ? null : Number(String(valueStr).replace(/\./g, '').replace(',', '.')));
        if (suggestion) {
            statusSel.value = suggestion;
            const exp = goalExpected(goal);
            hint.textContent = `Forslag ud fra fremdrift: ${GOAL_STATUS[suggestion].label}` + (exp != null ? ` (forventet ${Math.round(exp * 100)}% i dag)` : '');
        } else {
            statusSel.value = goal.status && goal.status !== 'not_started' ? goal.status : 'on_track';
            hint.textContent = 'Vurdér selv status — målet har ingen målværdi.';
        }
        updateCommentHint();
    }
    function updateCommentHint() {
        const needs = statusSel.value === 'at_risk' || statusSel.value === 'off_track';
        commentHint.textContent = needs ? 'Påkrævet: beskriv hvad der skal ske for at komme på sporet.' : '';
        if (needs) commentBox.setAttribute('required', ''); else commentBox.removeAttribute('required');
    }
    statusSel.addEventListener('change', updateCommentHint);

    const valueInput = hasTarget ? h('input', { name: 'value', value: goal.current_value ?? '', className: 'w-full border border-gray-300 rounded-lg px-3 py-2',
        onInput: (e) => refresh(e.target.value) }) : null;

    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const raw = fd.get('value');
        try {
            await api.createGoalCheckin(goal.id, {
                meeting_id: meetingId || null,
                value: hasTarget && raw !== '' && raw != null ? Number(String(raw).replace(/\./g, '').replace(',', '.')) : null,
                status: fd.get('status'),
                comment: fd.get('comment') || null,
            });
            closeModal();
            if (onDone) onDone(); else router();
        } catch (err) { alert(err.message); }
    }},
        h('div', { className: 'bg-gray-50 rounded-lg p-3 text-sm' },
            h('div', { className: 'font-semibold text-gray-900' }, goal.title),
            hasTarget ? h('div', { className: 'text-gray-500 mt-1' },
                `Sidst: ${fmtGoalValue(goal.current_value ?? goal.start_value, goal.unit)} af ${fmtGoalValue(goal.target_value, goal.unit)}` +
                (goal.due_date ? ` · deadline ${formatDate(goal.due_date)}` : '')) : null),
        hasTarget ? h('div', {}, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, `Ny værdi${goal.unit ? ' (' + goal.unit + ')' : ''}`), valueInput) : null,
        h('div', {}, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Status'), statusSel, hint),
        h('div', {}, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Kommentar'), commentBox, commentHint),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type: 'button', className: 'px-4 py-2 text-gray-600', onClick: closeModal }, 'Annuller'),
            h('button', { type: 'submit', className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, 'Gem status'))
    );
    showModal('Opdater status', form);
    refresh(goal.current_value ?? '');
}

// ─── Mål: detalje ───
function goalHistoryChart(g) {
    const pts = [...(g.checkins || [])].filter(c => c.value != null).reverse();
    if (g.target_value == null || pts.length === 0) return null;
    const W = 1100, H = 230, P = { t: 14, r: 16, b: 28, l: 64 };
    const start = (g.start_date || g.created_at || pts[0].checkin_date).slice(0, 10);
    const end = (g.due_date || pts[pts.length - 1].checkin_date).slice(0, 10);
    const span = Math.max(1, daysBetween(start, end));
    const maxV = Math.max(Number(g.target_value), ...pts.map(p => Number(p.value)), Number(g.start_value || 0)) || 1;
    const minV = Math.min(0, Number(g.start_value || 0), ...pts.map(p => Number(p.value)));
    const x = d => P.l + Math.max(0, Math.min(1, daysBetween(start, d.slice(0, 10)) / span)) * (W - P.l - P.r);
    const y = v => P.t + (1 - (v - minV) / (maxV - minV || 1)) * (H - P.t - P.b);
    const line = pts.map(p => `${x(p.checkin_date)},${y(Number(p.value))}`).join(' ');
    const dots = pts.map(p => `<circle cx="${x(p.checkin_date)}" cy="${y(Number(p.value))}" r="4" fill="#194b66" stroke="#fff" stroke-width="1.5"><title>${formatDate(p.checkin_date)}: ${fmtNum(p.value)}</title></circle>`).join('');
    const svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="overflow:visible">
        <line x1="${P.l}" x2="${W - P.r}" y1="${y(Number(g.target_value))}" y2="${y(Number(g.target_value))}" stroke="#2c7a4b" stroke-dasharray="4 4"/>
        <text x="${P.l - 6}" y="${y(Number(g.target_value)) + 4}" text-anchor="end" font-size="11" fill="#2c7a4b">${fmtNum(g.target_value)}</text>
        <line x1="${x(start)}" y1="${y(Number(g.start_value || 0))}" x2="${x(end)}" y2="${y(Number(g.target_value))}" stroke="#c3cfd8" stroke-width="1.5"/>
        <line x1="${P.l}" x2="${W - P.r}" y1="${H - P.b}" y2="${H - P.b}" stroke="#d9e2e9"/>
        <text x="${P.l}" y="${H - 8}" font-size="11" fill="#788a96">${formatDate(start)}</text>
        <text x="${W - P.r}" y="${H - 8}" font-size="11" fill="#788a96" text-anchor="end">${formatDate(end)}</text>
        <polyline points="${line}" fill="none" stroke="#194b66" stroke-width="2.5" stroke-linejoin="round"/>${dots}</svg>`;
    return h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6' },
        h('div', { className: 'flex items-center justify-between mb-2' },
            h('h2', { className: 'font-semibold text-gray-900' }, 'Udvikling'),
            h('span', { className: 'text-xs text-gray-400' }, 'Grå linje = lineær plan · stiplet = målværdi')),
        h('div', { innerHTML: svg }));
}

async function renderGoalDetail(container, id) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    const g = await api.getGoal(id);
    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';
    const p = goalProgress(g), e = goalExpected(g);

    container.appendChild(h('div', { className: 'mb-6' },
        h('a', { href: '#/goals', className: 'text-sm text-blue-600 hover:underline mb-2 inline-block' }, '← Alle mål'),
        h('div', { className: 'flex justify-between items-start gap-4' },
            h('div', {},
                h('div', { className: 'flex items-center gap-2 mb-2 flex-wrap' },
                    h('span', { className: `area-pill area-${g.area}` }, GOAL_AREAS[g.area]),
                    h('span', { className: 'goal-kind' }, GOAL_KIND_LABELS[g.kind]),
                    g.owner_role ? h('span', { className: 'goal-owner' }, `Ansvarlig: ${g.owner_role}`) : null,
                    goalStatusPill(g.status),
                    g.archived ? h('span', { className: 'gs-pill gs-none' }, 'Arkiveret') : null),
                h('h1', { className: 'text-2xl font-bold text-gray-900' }, g.title),
                g.company_name ? h('a', { href: `#/companies/${g.company_id}`, className: 'text-blue-600 hover:underline' }, g.company_name) : null,
                g.description ? h('p', { className: 'text-gray-500 mt-1 max-w-3xl' }, g.description) : null),
            h('div', { className: 'flex gap-2 flex-shrink-0' },
                h('button', { className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium', onClick: () => showCheckinForm(g) }, 'Opdater status'),
                h('button', { className: 'bg-white border border-gray-300 text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-50', onClick: () => showGoalForm(g) }, 'Rediger'),
                h('button', { className: 'bg-white border border-gray-300 text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-50',
                    onClick: async () => { await api.updateGoal(g.id, { archived: !g.archived }); router(); } }, g.archived ? 'Genåbn' : 'Arkivér'),
                h('button', { className: 'text-red-600 px-3 py-2 rounded-lg hover:bg-red-50',
                    onClick: async () => { if (confirm(`Slet målet "${g.title}" og al dets historik?`)) { await api.deleteGoal(g.id); location.hash = '#/goals'; } } }, 'Slet'))
        )));

    const tile = (v, l, s, cls) => h('div', { className: `kpi ${cls || ''}`, style: 'cursor:default;background:#fff;box-shadow:var(--shadow)' },
        h('div', { className: 'kpi-v' }, v), h('div', { className: 'kpi-l' }, l), h('div', { className: 'kpi-s' }, s));
    // Tallet stort, enheden lille, så lange enheder som "målepunkter" ikke fylder hele feltet
    const valueEl = (n, unit) => n == null ? '–' : h('span', {}, unit === '%' ? `${fmtNum(n)}%` : fmtNum(n),
        unit && unit !== '%' ? h('small', {}, ` ${unit}`) : null);
    const behind = p != null && e != null && p < e - 0.05;
    container.appendChild(h('div', { className: 'grid grid-cols-2 md:grid-cols-5 gap-3 mb-6' },
        tile(valueEl(g.current_value ?? g.start_value, g.unit), 'Nu', lastUpdateText(g), goalIsStale(g) ? 'warn' : ''),
        tile(valueEl(g.target_value, g.unit), 'Mål', g.start_value != null ? `fra ${fmtGoalValue(g.start_value, g.unit)}` : ''),
        tile(p == null ? '–' : `${Math.round(p * 100)}%`, 'Fremdrift', 'af målet', behind ? 'bad' : (p != null ? 'good' : '')),
        tile(e == null ? '–' : `${Math.round(e * 100)}%`, 'Forventet', 'ved lineær plan'),
        tile(g.due_date ? formatDate(g.due_date) : '–', 'Deadline', g.due_date ? `${Math.max(0, daysBetween(todayIso(), g.due_date))} dage tilbage` : 'ingen deadline')
    ));

    const chart = goalHistoryChart(g);
    if (chart) container.appendChild(chart);

    // Milepæle
    const ms = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6' },
        h('h2', { className: 'font-semibold text-gray-900 mb-3' }, `Milepæle${g.milestones.length ? ` · ${g.milestones.filter(m => m.done).length}/${g.milestones.length}` : ''}`));
    for (const m of g.milestones) {
        const late = !m.done && m.due_date && m.due_date < todayIso();
        ms.appendChild(h('div', { className: 'flex items-center gap-3 py-2 border-b border-gray-100' },
            h('input', { type: 'checkbox', ...(m.done ? { checked: '' } : {}), className: 'w-4 h-4',
                onChange: async (ev) => { await api.updateMilestone(m.id, { done: ev.target.checked }); router(); } }),
            h('span', { className: `flex-1 ${m.done ? 'line-through text-gray-400' : 'text-gray-800'}` }, m.title),
            m.due_date ? h('span', { className: `text-sm ${late ? 'text-red-600 font-medium' : 'text-gray-400'}` }, formatDate(m.due_date)) : null,
            h('button', { className: 'text-gray-300 hover:text-red-500 text-lg', title: 'Slet milepæl',
                onClick: async () => { if (confirm('Slet milepæl?')) { await api.deleteMilestone(m.id); router(); } } }, '×')));
    }
    const msForm = h('form', { className: 'flex gap-2 mt-3', onSubmit: async (ev) => {
        ev.preventDefault();
        const fd = new FormData(ev.target);
        await api.createMilestone(g.id, { title: fd.get('title'), due_date: fd.get('due_date') || null });
        router();
    }},
        h('input', { name: 'title', required: '', placeholder: 'Ny milepæl, fx "Go-live hos kunden"', className: 'flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm' }),
        h('input', { type: 'date', name: 'due_date', className: 'border border-gray-300 rounded-lg px-3 py-2 text-sm' }),
        h('button', { type: 'submit', className: 'bg-white border border-gray-300 px-3 py-2 rounded-lg text-sm hover:bg-gray-50' }, 'Tilføj'));
    ms.appendChild(msForm);

    // Aktioner knyttet til målet
    const acts = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6' },
        h('h2', { className: 'font-semibold text-gray-900 mb-3' }, 'Aktioner & beslutninger'));
    if (g.actions.length === 0) acts.appendChild(h('div', { className: 'text-sm text-gray-400' }, 'Ingen endnu. Aktioner oprettes typisk på ledermødet.'));
    for (const a of g.actions) acts.appendChild(actionRow(a, { onChange: () => router() }));

    container.appendChild(h('div', { className: 'grid grid-cols-1 lg:grid-cols-2 gap-6' }, ms, acts));

    // Historik
    const hist = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6' },
        h('h2', { className: 'font-semibold text-gray-900 mb-3' }, 'Statushistorik'));
    if (g.checkins.length === 0) hist.appendChild(h('div', { className: 'text-sm text-gray-400' }, 'Ingen statusopdateringer endnu.'));
    for (const c of g.checkins) {
        hist.appendChild(h('div', { className: 'flex gap-4 py-3 border-b border-gray-100' },
            h('div', { className: 'w-28 flex-shrink-0 text-sm text-gray-500' }, formatDate(c.checkin_date)),
            h('div', { className: 'w-28 flex-shrink-0' }, goalStatusPill(c.status)),
            h('div', { className: 'w-32 flex-shrink-0 text-sm font-semibold text-gray-800' }, c.value != null ? fmtGoalValue(c.value, g.unit) : ''),
            h('div', { className: 'flex-1 text-sm text-gray-700' }, c.comment || '',
                h('div', { className: 'text-xs text-gray-400 mt-0.5' }, [c.user_name, c.meeting_title ? `på mødet "${c.meeting_title}"` : null].filter(Boolean).join(' · ')))));
    }
    container.appendChild(hist);
}

// ─── Aktioner ───
function actionRow(a, { meetingId = null, onChange, showCarry = false, carried = false, onCarry } = {}) {
    const late = a.status === 'open' && a.due_date && a.due_date < todayIso();
    const row = h('div', { className: `action-row ${a.status === 'done' ? 'done' : ''} ${late ? 'late' : ''}` },
        h('span', { className: `act-kind ${a.kind}` }, a.kind === 'beslutning' ? 'Beslutning' : 'Aktion'),
        h('div', { className: 'flex-1 min-w-0' },
            h('div', { className: 'act-title' }, a.title),
            h('div', { className: 'text-xs text-gray-500 mt-0.5' }, [
                a.owner ? `Ansvarlig: ${a.owner}` : (a.kind === 'aktion' ? '⚠ Ingen ansvarlig' : null),
                a.due_date ? `Frist ${formatDate(a.due_date)}` : (a.kind === 'aktion' ? '⚠ Ingen frist' : null),
                a.goal_title ? `Mål: ${a.goal_title}` : null,
                a.company_name ? a.company_name : null,
                a.meeting_date ? `fra møde ${formatDate(a.meeting_date)}` : null,
            ].filter(Boolean).join(' · '))),
        a.kind === 'aktion' ? h('div', { className: 'flex gap-2 flex-shrink-0 items-center' },
            showCarry && a.status === 'open' ? (carried
                ? h('span', { className: 'text-xs text-gray-500' }, '↻ Fortsætter')
                : h('button', { className: 'act-btn', onClick: onCarry }, 'Fortsætter')) : null,
            showCarry && a.status === 'open' ? h('button', { className: 'act-btn', onClick: async () => {
                const d = prompt('Ny frist (ÅÅÅÅ-MM-DD):', a.due_date || addDaysIso(14));
                if (d) { await api.updateAction(a.id, { due_date: d }); if (onCarry) onCarry(); else if (onChange) onChange(); }
            } }, 'Ny frist') : null,
            h('button', { className: `act-btn ${a.status === 'done' ? '' : 'primary'}`, onClick: async () => {
                await api.updateAction(a.id, { status: a.status === 'done' ? 'open' : 'done', closed_in_meeting_id: meetingId });
                onChange && onChange();
            } }, a.status === 'done' ? 'Genåbn' : 'Udført')
        ) : null
    );
    return row;
}

// ─── Ledermøder: oversigt ───
async function renderMeetings(container) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    const [ov, meetings] = await Promise.all([api.getCeoOverview(), api.getMeetings()]);
    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';

    const cfg = await api.getReportConfig().catch(() => null);
    container.appendChild(h('div', { className: 'mb-6' },
        h('h1', { className: 'text-2xl font-bold text-gray-900' }, 'Ledermøder'),
        h('p', { className: 'text-gray-500 mt-1' }, 'Faste opfølgningsmøder med CCO, COO og CFO, med samme dagsorden hver gang, så intet bliver glemt')));

    if (cfg) container.appendChild(aiContextCard(cfg));
    const grid = h('div', { className: 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-8' });
    for (const area of Object.keys(GOAL_AREAS)) {
        const goals = ov.goals.filter(g => area === 'tvaers' ? (g.area === 'tvaers' || g.kind === 'strategisk') : g.area === area);
        const acts = ov.open_actions.filter(a => area === 'tvaers' || a.area === area);
        const last = ov.last_meetings.find(m => m.area === area && m.status === 'done') || null;
        const planned = ov.planned_meetings.find(m => m.area === area) || null;
        const red = goals.filter(g => g.status === 'off_track').length, amber = goals.filter(g => g.status === 'at_risk').length;
        const stale = goals.filter(goalIsStale).length;
        const lateActs = acts.filter(a => a.due_date && a.due_date < todayIso()).length;
        const sinceLast = last ? daysBetween(last.meeting_date, todayIso()) : null;

        grid.appendChild(h('div', { className: 'meet-card' },
            h('div', { className: 'meet-card-head', style: `--ac:var(--area-${area}, var(--accent))` },
                h('span', { className: 'meet-role' }, AREA_ROLE[area]),
                h('div', {}, h('div', { className: 'font-bold text-gray-900' }, MEETING_TITLES[area]),
                    h('div', { className: 'text-xs text-gray-500' }, last ? `Sidst holdt ${formatDate(last.meeting_date)} (${sinceLast === 0 ? 'i dag' : sinceLast + ' dage siden'})` : 'Ikke holdt endnu'))),
            h('div', { className: 'meet-stats' },
                h('div', {}, h('b', {}, String(goals.length)), 'mål'),
                h('div', { className: red ? 'bad' : amber ? 'warn' : '' }, h('b', {}, String(red + amber)), 'i risiko/bagud'),
                h('div', { className: stale ? 'warn' : '' }, h('b', {}, String(stale)), 'ikke fulgt op'),
                h('div', { className: lateActs ? 'bad' : '' }, h('b', {}, String(acts.length)), `åbne aktioner${lateActs ? ` (${lateActs} over frist)` : ''}`)),
            planned
                ? h('a', { href: `#/meetings/${planned.id}`, className: 'meet-btn primary' }, planned.status === 'in_progress' ? 'Fortsæt mødet' : `Planlagt ${formatDate(planned.meeting_date)} · Åbn`)
                : h('button', { className: 'meet-btn primary', onClick: async () => {
                    const m = await api.createMeeting({ area, title: MEETING_TITLES[area], meeting_date: todayIso(),
                        participants: area === 'tvaers' ? 'CEO, CCO, COO, CFO' : `CEO, ${AREA_ROLE[area]}` });
                    location.hash = `#/meetings/${m.id}`;
                } }, 'Start møde nu'),
            !planned ? h('button', { className: 'meet-btn', onClick: async () => {
                const d = prompt('Dato for mødet (ÅÅÅÅ-MM-DD):', addDaysIso(7));
                if (!d) return;
                await api.createMeeting({ area, title: MEETING_TITLES[area], meeting_date: d,
                    participants: area === 'tvaers' ? 'CEO, CCO, COO, CFO' : `CEO, ${AREA_ROLE[area]}` });
                router();
            } }, 'Planlæg møde') : null
        ));
    }
    container.appendChild(grid);

    container.appendChild(h('h2', { className: 'text-lg font-bold text-gray-900 mb-3' }, 'Alle møder'));
    const list = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden' });
    if (meetings.length === 0) list.appendChild(h('div', { className: 'p-8 text-center text-gray-400' }, 'Ingen møder endnu. Start det første ovenfor.'));
    const MS = { planned: ['Planlagt', 'gs-none'], in_progress: ['I gang', 'gs-warn'], done: ['Afholdt', 'gs-good'] };
    for (const m of meetings) {
        list.appendChild(h('a', { href: `#/meetings/${m.id}`, className: 'flex items-center gap-4 px-6 py-3 border-b border-gray-100 hover:bg-gray-50' },
            h('div', { className: 'w-28 text-sm text-gray-500' }, formatDate(m.meeting_date)),
            h('span', { className: `area-pill area-${m.area}` }, GOAL_AREAS[m.area]),
            h('div', { className: 'flex-1 font-medium text-gray-900' }, m.title),
            h('div', { className: 'text-xs text-gray-500' }, `${m.checkins_count} mål opdateret · ${m.decisions_count} beslutninger · ${m.actions_count} aktioner`),
            h('span', { className: `gs-pill ${MS[m.status][1]}` }, MS[m.status][0])));
    }
    container.appendChild(list);
}

// ─── Ledermøde: guidet gennemgang ───
const MEETING_STEPS = [
    { key: 'prep', label: 'Forberedelse', hint: 'Deltagere, dagsorden og referat fra sidst' },
    { key: 'actions', label: 'Aktioner fra sidst', hint: 'Er det, vi aftalte, blevet gjort?' },
    { key: 'drift', label: 'Driftsmål', hint: 'Status og tal på de kortsigtede mål' },
    { key: 'strategi', label: 'Strategiske mål', hint: 'Bevæger vi os i den retning, vi har valgt?' },
    { key: 'risks', label: 'Sager & risici', hint: 'Forfaldne sager, deadlines og bekymringer' },
    { key: 'decisions', label: 'Beslutninger & aktioner', hint: 'Hvad besluttede vi, og hvem gør hvad hvornår?' },
    { key: 'close', label: 'Afslut & referat', hint: 'Tjek at alt er dækket, og planlæg næste møde' },
];

async function renderMeetingDetail(container, id) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    let m = await api.getMeeting(id);
    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';
    const notes = Object.assign({ step_notes: {}, carried: [], visited: [] }, m.notes || {});
    const stepKey = `meetingStep_${id}`;
    let step = parseInt(sessionStorage.getItem(stepKey) || (m.status === 'done' ? '6' : '0'));

    async function saveNotes() { await api.updateMeeting(id, { notes }); }
    async function reload() { m = await api.getMeeting(id); draw(); }

    const goalsOf = kind => m.goals.filter(g => g.kind === kind);
    function progress() {
        const fu = m.followup_actions.filter(a => a.kind === 'aktion');
        const fuDone = fu.filter(a => a.status === 'done' || notes.carried.includes(a.id)).length;
        const d = goalsOf('drift'), s = goalsOf('strategisk');
        return {
            actions: [fuDone, fu.length],
            drift: [d.filter(g => g.meeting_checkin).length, d.length],
            strategi: [s.filter(g => g.meeting_checkin).length, s.length],
            risks: [notes.visited.includes('risks') ? 1 : 0, 1],
            decisions: [m.new_items.length ? 1 : 0, 1],
        };
    }
    function stepDone(key) {
        const pr = progress();
        if (key === 'prep') return m.status !== 'planned';
        if (key === 'close') return m.status === 'done';
        const [a, b] = pr[key];
        return b === 0 ? notes.visited.includes(key) : a >= b;
    }

    function draw() {
        container.innerHTML = '';
        const isDone = m.status === 'done';
        container.appendChild(h('div', { className: 'mb-5' },
            h('a', { href: '#/meetings', className: 'text-sm text-blue-600 hover:underline mb-2 inline-block' }, '← Ledermøder'),
            h('div', { className: 'flex items-center gap-3 flex-wrap' },
                h('span', { className: `area-pill area-${m.area}` }, GOAL_AREAS[m.area]),
                h('h1', { className: 'text-2xl font-bold text-gray-900' }, m.title),
                h('span', { className: 'text-gray-500' }, formatDate(m.meeting_date)),
                h('span', { className: `gs-pill ${isDone ? 'gs-good' : m.status === 'in_progress' ? 'gs-warn' : 'gs-none'}` },
                    isDone ? 'Afholdt' : m.status === 'in_progress' ? 'I gang' : 'Planlagt'),
                h('button', { className: 'ml-auto text-sm text-red-600 hover:underline', onClick: async () => {
                    if (confirm('Slet mødet? Statusopdateringer og aktioner bevares, men mister koblingen til mødet.')) { await api.deleteMeeting(id); location.hash = '#/meetings'; }
                } }, 'Slet møde'))));

        const layout = h('div', { className: 'meeting-layout' });
        const stepper = h('div', { className: 'meeting-steps' });
        const pr = progress();
        MEETING_STEPS.forEach((s, i) => {
            const counts = pr[s.key];
            stepper.appendChild(h('button', { className: `mstep ${i === step ? 'on' : ''} ${stepDone(s.key) ? 'ok' : ''}`,
                onClick: () => go(i) },
                h('span', { className: 'mstep-n' }, stepDone(s.key) ? '✓' : String(i + 1)),
                h('span', { className: 'mstep-txt' }, h('b', {}, s.label),
                    h('small', {}, counts && counts[1] > 1 ? `${counts[0]} af ${counts[1]}` : s.hint))));
        });
        layout.appendChild(stepper);

        const body = h('div', { className: 'meeting-body' });
        const S = MEETING_STEPS[step];
        body.appendChild(h('div', { className: 'mb-4' },
            h('div', { className: 'text-xs font-bold uppercase tracking-wider text-gray-400' }, `Punkt ${step + 1} af ${MEETING_STEPS.length}`),
            h('h2', { className: 'text-xl font-bold text-gray-900' }, S.label),
            h('p', { className: 'text-gray-500' }, S.hint)));
        body.appendChild(STEP_RENDER[S.key]());

        if (!['prep', 'close'].includes(S.key)) {
            const ta = h('textarea', { rows: '3', className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm', placeholder: 'Noter til dette punkt (kommer med i referatet)' },
                notes.step_notes[S.key] || '');
            ta.addEventListener('blur', async () => { notes.step_notes[S.key] = ta.value; await saveNotes(); });
            body.appendChild(h('div', { className: 'mt-6' }, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Noter'), ta));
        }
        body.appendChild(h('div', { className: 'flex justify-between mt-6 pt-4 border-t border-gray-100' },
            step > 0 ? h('button', { className: 'px-4 py-2 text-gray-600 hover:text-gray-900', onClick: () => go(step - 1) }, '← Forrige') : h('span', {}),
            step < MEETING_STEPS.length - 1 ? h('button', { className: 'bg-blue-600 text-white px-5 py-2 rounded-lg hover:bg-blue-700 font-medium',
                onClick: () => go(step + 1) }, `Næste: ${MEETING_STEPS[step + 1].label} →`) : h('span', {})));
        layout.appendChild(body);
        container.appendChild(layout);
    }

    async function go(i) {
        const key = MEETING_STEPS[step].key;
        if (!notes.visited.includes(key)) { notes.visited.push(key); await saveNotes(); }
        if (m.status === 'planned' && i > 0) { await api.updateMeeting(id, { status: 'in_progress' }); m.status = 'in_progress'; }
        step = i; sessionStorage.setItem(stepKey, String(i));
        window.scrollTo(0, 0);
        draw();
    }

    function goalReviewList(kind) {
        const list = goalsOf(kind);
        const wrap = h('div', { className: 'space-y-3' });
        if (list.length === 0) {
            wrap.appendChild(h('div', { className: 'empty-box' },
                kind === 'drift' ? 'Der er ingen driftsmål for området endnu.' : 'Der er ingen strategiske mål for området endnu.',
                h('button', { className: 'act-btn primary ml-3', onClick: () => showGoalForm(null, { area: m.area === 'tvaers' ? 'tvaers' : m.area, kind }) }, '+ Opret mål')));
            return wrap;
        }
        for (const g of list) {
            const ci = g.meeting_checkin;
            wrap.appendChild(h('div', { className: `review-goal ${ci ? 'ok' : ''}` },
                h('div', { className: 'flex-1 min-w-0' },
                    h('div', { className: 'flex items-center gap-2 flex-wrap mb-1' },
                        m.area === 'tvaers' ? h('span', { className: `area-pill area-${g.area}` }, GOAL_AREAS[g.area]) : null,
                        g.owner_role ? h('span', { className: 'goal-owner' }, g.owner_role) : null,
                        goalStatusPill(g.status),
                        goalIsStale(g) && !ci ? h('span', { className: 'text-xs text-yellow-700' }, `⚠ ${lastUpdateText(g)}`) : null),
                    h('a', { href: `#/goals/${g.id}`, className: 'font-semibold text-gray-900 hover:underline' }, g.title),
                    g.company_name ? h('div', { className: 'text-sm text-gray-500' }, g.company_name) : null,
                    g.target_value != null ? h('div', { className: 'mt-2 max-w-md' }, goalProgressBar(g),
                        h('div', { className: 'text-xs text-gray-500 mt-1' }, `${fmtGoalValue(g.current_value ?? g.start_value, g.unit)} af ${fmtGoalValue(g.target_value, g.unit)}${g.due_date ? ' · deadline ' + formatDate(g.due_date) : ''}`)) : null,
                    g.milestones_total ? h('div', { className: 'text-xs text-gray-500 mt-1' }, `Milepæle: ${g.milestones_done}/${g.milestones_total}`) : null,
                    ci ? h('div', { className: 'text-sm text-gray-700 mt-2' }, `✓ Opdateret på mødet${ci.comment ? ': ' + ci.comment : ''}`)
                       : (g.last_comment ? h('div', { className: 'goal-comment' }, `Sidst: “${g.last_comment}”`) : null)),
                h('div', { className: 'flex flex-col gap-2 flex-shrink-0' },
                    h('button', { className: `act-btn ${ci ? '' : 'primary'}`, onClick: () => showCheckinForm(g, id, reload) }, ci ? 'Opdater igen' : 'Opdater status'),
                    h('button', { className: 'act-btn', onClick: () => showActionForm({ area: g.area, goal_id: g.id, owner: g.owner_role }, reload) }, '+ Aktion'))));
        }
        return wrap;
    }

    function showActionForm(defaults, after) {
        const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
            e.preventDefault();
            const fd = new FormData(e.target);
            await api.createAction({
                meeting_id: id, area: defaults.area || (m.area === 'tvaers' ? 'tvaers' : m.area), kind: fd.get('kind'),
                title: fd.get('title'), owner: fd.get('owner') || null, due_date: fd.get('due_date') || null,
                goal_id: fd.get('goal_id') ? parseInt(fd.get('goal_id')) : null, company_id: defaults.company_id || null,
            });
            closeModal(); after && after();
        }},
            h('div', { className: 'flex gap-4' }, ...[['aktion', 'Aktion (nogen skal gøre noget)'], ['beslutning', 'Beslutning']].map(([k, v]) =>
                h('label', { className: 'flex items-center gap-2 text-sm' }, h('input', { type: 'radio', name: 'kind', value: k, ...((defaults.kind || 'aktion') === k ? { checked: '' } : {}) }), v))),
            formField('Hvad *', 'title', defaults.title || '', 'text', true),
            h('div', { className: 'grid grid-cols-2 gap-3' },
                h('div', {}, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Ansvarlig'),
                    h('input', { name: 'owner', value: defaults.owner || AREA_ROLE[m.area] || '', list: 'owner-options', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' }),
                    h('datalist', { id: 'owner-options' }, ...['CEO', 'CCO', 'COO', 'CFO'].map(r => h('option', { value: r })))),
                formField('Frist', 'due_date', defaults.due_date || addDaysIso(14), 'date')),
            h('div', {}, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Knyt til mål'),
                h('select', { name: 'goal_id', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                    h('option', { value: '' }, 'Intet mål'),
                    ...m.goals.map(g => h('option', { value: g.id, ...(defaults.goal_id == g.id ? { selected: '' } : {}) }, g.title)))),
            h('div', { className: 'flex justify-end gap-3 pt-2' },
                h('button', { type: 'button', className: 'px-4 py-2 text-gray-600', onClick: closeModal }, 'Annuller'),
                h('button', { type: 'submit', className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, 'Tilføj'))
        );
        showModal('Ny aktion eller beslutning', form);
    }

    function buildMinutes() {
        const L = [];
        L.push(`REFERAT · ${m.title}`, `Dato: ${formatDate(m.meeting_date)}`, `Deltagere: ${m.participants || '-'}`, '');
        const fu = m.followup_actions.filter(a => a.kind === 'aktion');
        if (fu.length) {
            L.push('1. AKTIONER FRA SIDST');
            for (const a of fu) L.push(`   [${a.status === 'done' ? 'Udført' : notes.carried.includes(a.id) ? 'Fortsætter' : 'Åben'}] ${a.title}${a.owner ? ' – ' + a.owner : ''}${a.due_date ? ' (frist ' + formatDate(a.due_date) + ')' : ''}`);
            if (notes.step_notes.actions) L.push(`   Noter: ${notes.step_notes.actions}`);
            L.push('');
        }
        for (const [kind, title, key] of [['drift', '2. DRIFTSMÅL', 'drift'], ['strategisk', '3. STRATEGISKE MÅL', 'strategi']]) {
            const gs = goalsOf(kind);
            if (!gs.length) continue;
            L.push(title);
            for (const g of gs) {
                const st = GOAL_STATUS[g.status]?.label || '';
                const val = g.target_value != null ? ` – ${fmtGoalValue(g.current_value ?? g.start_value, g.unit)} af ${fmtGoalValue(g.target_value, g.unit)}` : '';
                L.push(`   [${st}] ${g.title}${val}${g.owner_role ? ' (' + g.owner_role + ')' : ''}`);
                if (g.meeting_checkin?.comment) L.push(`      ${g.meeting_checkin.comment}`);
                if (!g.meeting_checkin) L.push('      (ikke opdateret på mødet)');
            }
            if (notes.step_notes[key]) L.push(`   Noter: ${notes.step_notes[key]}`);
            L.push('');
        }
        if (notes.step_notes.risks) L.push('4. SAGER & RISICI', `   ${notes.step_notes.risks}`, '');
        const dec = m.new_items.filter(a => a.kind === 'beslutning'), act = m.new_items.filter(a => a.kind === 'aktion');
        L.push('5. BESLUTNINGER');
        L.push(...(dec.length ? dec.map(a => `   • ${a.title}`) : ['   Ingen']));
        L.push('', 'NYE AKTIONER');
        L.push(...(act.length ? act.map(a => `   • ${a.title} – ${a.owner || 'ingen ansvarlig'}, frist ${a.due_date ? formatDate(a.due_date) : 'ingen'}`) : ['   Ingen']));
        if (notes.step_notes.decisions) L.push(`   Noter: ${notes.step_notes.decisions}`);
        if (m.summary) L.push('', 'OPSUMMERING', m.summary);
        if (m.next_meeting_date) L.push('', `Næste møde: ${formatDate(m.next_meeting_date)}`);
        return L.join('\n');
    }

    const STEP_RENDER = {
        prep: () => {
            const w = h('div', { className: 'space-y-4' });
            const partInput = h('input', { value: m.participants || '', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' });
            partInput.addEventListener('blur', async () => { await api.updateMeeting(id, { participants: partInput.value }); m.participants = partInput.value; });
            const dateInput = h('input', { type: 'date', value: (m.meeting_date || '').slice(0, 10), className: 'border border-gray-300 rounded-lg px-3 py-2' });
            dateInput.addEventListener('change', async () => { await api.updateMeeting(id, { meeting_date: dateInput.value }); m.meeting_date = dateInput.value; });
            w.appendChild(h('div', { className: 'grid grid-cols-3 gap-3' },
                h('div', { className: 'col-span-2' }, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Deltagere'), partInput),
                h('div', {}, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Dato'), dateInput)));
            const pr = progress();
            w.appendChild(h('div', { className: 'prep-agenda' },
                h('div', { className: 'font-semibold text-gray-900 mb-2' }, 'Dagsorden'),
                ...MEETING_STEPS.slice(1).map((s, i) => h('div', { className: 'flex justify-between py-1.5 border-b border-gray-100 text-sm' },
                    h('span', {}, `${i + 1}. ${s.label}`),
                    h('span', { className: 'text-gray-500' }, {
                        actions: `${pr.actions[1]} åbne aktioner`, drift: `${pr.drift[1]} driftsmål`, strategi: `${pr.strategi[1]} strategiske mål`,
                        risks: `${m.risk_tasks.length} sager · ${m.risk_tenders.length} tilbud`, decisions: '', close: '' }[s.key] || '')))));
            if (m.area !== 'tvaers') w.appendChild(reportPanel(m));
            if (m.previous) {
                w.appendChild(h('div', { className: 'prep-prev' },
                    h('div', { className: 'flex justify-between mb-1' }, h('b', {}, `Sidste møde: ${formatDate(m.previous.meeting_date)}`),
                        h('a', { href: `#/meetings/${m.previous.id}`, className: 'text-sm text-blue-600 hover:underline' }, 'Åbn referat')),
                    h('div', { className: 'text-sm text-gray-600 whitespace-pre-wrap' }, m.previous.summary || 'Ingen opsummering skrevet.')));
            }
            if (m.status === 'planned') {
                w.appendChild(h('button', { className: 'bg-blue-600 text-white px-5 py-2.5 rounded-lg hover:bg-blue-700 font-semibold',
                    onClick: () => go(1) }, 'Start mødet →'));
            }
            return w;
        },
        actions: () => {
            const fu = m.followup_actions;
            const w = h('div', { className: 'space-y-2' });
            if (fu.length === 0) w.appendChild(h('div', { className: 'empty-box' }, 'Ingen åbne aktioner fra tidligere møder.'));
            for (const a of fu) w.appendChild(actionRow(a, { meetingId: id, onChange: reload, showCarry: true, carried: notes.carried.includes(a.id),
                onCarry: async () => { if (!notes.carried.includes(a.id)) notes.carried.push(a.id); await saveNotes(); await reload(); } }));
            return w;
        },
        drift: () => goalReviewList('drift'),
        strategi: () => goalReviewList('strategisk'),
        risks: () => {
            if (!notes.visited.includes('risks')) { notes.visited.push('risks'); saveNotes(); }
            const w = h('div', { className: 'space-y-5' });
            const tl = h('div', {}, h('div', { className: 'font-semibold text-gray-900 mb-2' }, `Sager over frist eller med høj prioritet (${m.risk_tasks.length})`));
            if (!m.risk_tasks.length) tl.appendChild(h('div', { className: 'empty-box' }, 'Ingen. Godt.'));
            for (const t of m.risk_tasks) {
                const late = t.due_date && t.due_date < todayIso();
                tl.appendChild(h('div', { className: 'risk-row' },
                    h('div', { className: 'flex-1 min-w-0' },
                        h('a', { href: `#/companies/${t.company_id}`, className: 'font-semibold text-gray-900 hover:underline' }, t.company_name),
                        h('div', { className: 'text-sm text-gray-600' }, h('a', { href: `#/tasks/${t.id}`, className: 'hover:underline' }, t.title),
                            t.assigned_to_name ? ` · ${t.assigned_to_name}` : '')),
                    h('span', { className: `text-sm ${late ? 'text-red-600 font-medium' : 'text-yellow-700'}` }, late ? `${daysBetween(t.due_date, todayIso())}d over frist` : 'Høj prioritet'),
                    h('button', { className: 'act-btn', onClick: () => showActionForm({ area: t.area, company_id: t.company_id, title: `${t.company_name}: ${t.title}` }, reload) }, '+ Aktion')));
            }
            w.appendChild(tl);
            if (m.risk_tenders.length) {
                const tt = h('div', {}, h('div', { className: 'font-semibold text-gray-900 mb-2' }, `Tilbud med deadline inden for 14 dage (${m.risk_tenders.length})`));
                for (const t of m.risk_tenders) {
                    const late = t.deadline < todayIso();
                    tt.appendChild(h('div', { className: 'risk-row' },
                        h('div', { className: 'flex-1 min-w-0' },
                            h('a', { href: `#/tenders/${t.id}`, className: 'font-semibold text-gray-900 hover:underline' }, t.company_name),
                            h('div', { className: 'text-sm text-gray-600' }, t.title)),
                        h('span', { className: `text-sm ${late ? 'text-red-600 font-medium' : 'text-gray-500'}` }, late ? `${daysBetween(t.deadline, todayIso())}d over deadline` : formatDate(t.deadline)),
                        h('button', { className: 'act-btn', onClick: () => showActionForm({ area: 'salg', company_id: t.company_id, title: `${t.company_name}: ${t.title}` }, reload) }, '+ Aktion')));
                }
                w.appendChild(tt);
            }
            return w;
        },
        decisions: () => {
            const w = h('div', { className: 'space-y-2' });
            w.appendChild(h('div', { className: 'flex gap-2 mb-2' },
                h('button', { className: 'act-btn primary', onClick: () => showActionForm({ kind: 'beslutning' }, reload) }, '+ Beslutning'),
                h('button', { className: 'act-btn primary', onClick: () => showActionForm({ kind: 'aktion' }, reload) }, '+ Aktion')));
            if (!m.new_items.length) w.appendChild(h('div', { className: 'empty-box' }, 'Ingen beslutninger eller aktioner fra dette møde endnu.'));
            for (const a of m.new_items) {
                const row = actionRow(a, { meetingId: id, onChange: reload });
                row.appendChild(h('button', { className: 'text-gray-300 hover:text-red-500 text-lg ml-2', title: 'Slet',
                    onClick: async () => { await api.deleteAction(a.id); reload(); } }, '×'));
                w.appendChild(row);
            }
            return w;
        },
        close: () => {
            const pr = progress();
            const fuOpen = m.followup_actions.filter(a => a.kind === 'aktion' && a.status === 'open' && !notes.carried.includes(a.id));
            const missingOwner = m.new_items.filter(a => a.kind === 'aktion' && (!a.owner || !a.due_date));
            const notChecked = m.goals.filter(g => !g.meeting_checkin);
            const checks = [
                [pr.actions[0] >= pr.actions[1], `Aktioner fra sidst gennemgået (${pr.actions[0]}/${pr.actions[1]})`, fuOpen.map(a => a.title), 1],
                [pr.drift[0] >= pr.drift[1], `Driftsmål opdateret (${pr.drift[0]}/${pr.drift[1]})`, notChecked.filter(g => g.kind === 'drift').map(g => g.title), 2],
                [pr.strategi[0] >= pr.strategi[1], `Strategiske mål opdateret (${pr.strategi[0]}/${pr.strategi[1]})`, notChecked.filter(g => g.kind === 'strategisk').map(g => g.title), 3],
                [notes.visited.includes('risks'), 'Sager & risici gennemgået', [], 4],
                [missingOwner.length === 0, 'Alle nye aktioner har ansvarlig og frist', missingOwner.map(a => a.title), 5],
            ];
            const w = h('div', { className: 'space-y-5' });
            w.appendChild(h('div', { className: 'checklist' }, ...checks.map(([ok, label, items, stepIdx]) => h('div', { className: `check ${ok ? 'ok' : ''}` },
                h('span', { className: 'check-ic' }, ok ? '✓' : '!'),
                h('div', { className: 'flex-1' }, h('div', {}, label),
                    !ok && items.length ? h('div', { className: 'text-xs text-gray-500 mt-0.5' }, items.slice(0, 4).join(' · ') + (items.length > 4 ? ' …' : '')) : null),
                !ok ? h('button', { className: 'act-btn', onClick: () => go(stepIdx) }, 'Gå til') : null))));

            const summary = h('textarea', { rows: '3', className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm', placeholder: 'De vigtigste pointer fra mødet' }, m.summary || '');
            summary.addEventListener('blur', async () => { await api.updateMeeting(id, { summary: summary.value }); m.summary = summary.value; });
            const nextDate = h('input', { type: 'date', value: (m.next_meeting_date || addDaysIso(14, (m.meeting_date || todayIso()).slice(0, 10))).slice(0, 10), className: 'border border-gray-300 rounded-lg px-3 py-2' });
            w.appendChild(h('div', { className: 'grid grid-cols-1 md:grid-cols-3 gap-4' },
                h('div', { className: 'md:col-span-2' }, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Opsummering'), summary),
                h('div', {}, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Næste møde'), nextDate,
                    h('div', { className: 'text-xs text-gray-400 mt-1' }, 'Mødet bliver planlagt automatisk'))));

            const allOk = checks.every(c => c[0]);
            if (m.status !== 'done') {
                w.appendChild(h('div', { className: 'flex items-center gap-3' },
                    h('button', { className: 'bg-blue-600 text-white px-5 py-2.5 rounded-lg hover:bg-blue-700 font-semibold', onClick: async () => {
                        if (!allOk && !confirm('Ikke alle punkter er dækket. Vil du afslutte mødet alligevel?')) return;
                        await api.updateMeeting(id, { status: 'done', summary: summary.value, next_meeting_date: nextDate.value || null });
                        if (nextDate.value) {
                            const existing = (await api.getMeetings({ area: m.area })).find(x => x.status !== 'done' && x.id !== id);
                            if (!existing) await api.createMeeting({ area: m.area, title: m.title, meeting_date: nextDate.value, participants: m.participants });
                        }
                        await reload();
                    } }, 'Afslut møde'),
                    !allOk ? h('span', { className: 'text-sm text-yellow-700' }, 'Der mangler stadig punkter. Se tjeklisten.') : null));
            }
            const minutes = buildMinutes();
            w.appendChild(h('div', { className: 'minutes' },
                h('div', { className: 'flex items-center justify-between mb-2' }, h('b', {}, 'Referat'),
                    h('div', { className: 'flex gap-2' },
                        h('button', { className: 'act-btn', onClick: async (e) => { await navigator.clipboard.writeText(buildMinutes()); e.target.textContent = 'Kopieret ✓'; } }, 'Kopiér'),
                        h('button', { className: 'act-btn', onClick: () => {
                            const win = window.open('', '_blank');
                            if (!win) return;
                            win.document.write(`<title>${m.title} ${m.meeting_date}</title><pre style="font:14px/1.5 'Schibsted Grotesk',system-ui,sans-serif;white-space:pre-wrap;padding:32px">${buildMinutes().replace(/</g, '&lt;')}</pre>`);
                            win.document.close(); win.print();
                        } }, 'Print'))),
                h('pre', {}, minutes)));
            return w;
        },
    };

    draw();
}


// Overblik: mål og ledermøder pr. område
function renderGoalsStrip(ceo) {
    const wrap = h('div', { className: 'ov-panel mb-5' });
    wrap.appendChild(h('div', { className: 'flex items-center justify-between mb-4' },
        h('h2', { style: 'margin:0' }, 'Mål & ledermøder'),
        h('div', { className: 'flex gap-4 text-sm' },
            h('a', { href: '#/goals', className: 'font-semibold text-blue-600 hover:underline' }, 'Alle mål →'),
            h('a', { href: '#/meetings', className: 'font-semibold text-blue-600 hover:underline' }, 'Ledermøder →'))));
    const grid = h('div', { className: 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3' });
    for (const area of Object.keys(GOAL_AREAS)) {
        const goals = ceo.goals.filter(g => g.area === area);
        const by = st => goals.filter(g => g.status === st).length;
        const stale = goals.filter(goalIsStale).length;
        const acts = ceo.open_actions.filter(a => a.area === area && a.kind === 'aktion');
        const late = acts.filter(a => a.due_date && a.due_date < todayIso()).length;
        const last = ceo.last_meetings.find(m => m.area === area && m.status === 'done');
        const next = ceo.planned_meetings.find(m => m.area === area);
        const seg = (n, cls) => n ? h('i', { className: cls, style: `flex:${n}` }) : null;
        grid.appendChild(h('a', { href: `#/goals`, className: 'strip-card', onClick: () => sessionStorage.setItem('goalsArea', area) },
            h('div', { className: 'flex items-center gap-2 mb-2' },
                h('span', { className: 'meet-role' }, AREA_ROLE[area]),
                h('b', { className: 'text-gray-900' }, GOAL_AREAS[area]),
                h('span', { className: 'ml-auto text-sm text-gray-500' }, `${goals.length} mål`)),
            h('div', { className: 'rag-bar' }, goals.length ? [seg(by('on_track') + by('done'), 'gs-good'), seg(by('at_risk'), 'gs-warn'), seg(by('off_track'), 'gs-bad'), seg(by('not_started'), 'gs-none')] : h('i', { className: 'gs-none', style: 'flex:1' })),
            h('div', { className: 'strip-facts' },
                h('span', {}, `${by('on_track') + by('done')} på sporet`),
                h('span', { className: by('at_risk') ? 'warn' : '' }, `${by('at_risk')} i risiko`),
                h('span', { className: by('off_track') ? 'bad' : '' }, `${by('off_track')} bagud`)),
            h('div', { className: 'strip-facts' },
                h('span', { className: stale ? 'warn' : '' }, `${stale} ikke fulgt op`),
                h('span', { className: late ? 'bad' : '' }, `${acts.length} aktioner${late ? ` (${late} over frist)` : ''}`)),
            h('div', { className: 'text-xs text-gray-500 mt-2' },
                next ? `Næste møde ${formatDate(next.meeting_date)}` : last ? `Sidste møde ${formatDate(last.meeting_date)} · intet planlagt` : 'Intet møde planlagt')));
    }
    wrap.appendChild(grid);

    const strategic = ceo.goals.filter(g => g.kind === 'strategisk');
    if (strategic.length) {
        wrap.appendChild(h('div', { className: 'ov-label', style: 'margin:18px 0 8px' }, 'Strategiske mål'));
        wrap.appendChild(h('div', { className: 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3' }, ...strategic.map(g => goalCard(g, { compact: true }))));
    }
    return wrap;
}


// ─── Indrapportering før ledermøder ───
const REPORT_CUSTOMER_STATUS = { som_planlagt: 'Som planlagt', venter: 'Venter på kunden', udfordret: 'Udfordret', vundet: 'Vundet', tabt: 'Tabt / droppet', forsinket: 'Forsinket', leveret: 'Leveret' };
const REPORT_GOAL_STATUS = { on_track: 'På sporet', at_risk: 'I risiko', off_track: 'Bagud', done: 'Nået' };
const reportLink = r => `${location.origin}/r/${r.token}`;

function reportStatusText(r) {
    if (r.status === 'answered' || r.status === 'closed') return `Indsendt ${formatDate(r.submitted_at)}`;
    if (r.sent_at) return `Sendt ${formatDate(r.sent_at)} · ${r.items_answered ?? 0} af ${r.items_total ?? r.items?.length ?? 0} besvaret`;
    return 'Oprettet, ikke sendt endnu';
}

// Panel i mødets forberedelse: bed om, send og følg indrapporteringen
function reportPanel(m) {
    const box = h('div', { className: 'prep-agenda' }, h('div', { className: 'text-sm text-gray-400' }, 'Indlæser indrapportering…'));
    (async () => {
        const [rounds, cfg] = await Promise.all([api.getReportRounds({ meeting_id: m.id }), api.getReportConfig().catch(() => ({}))]);
        box.innerHTML = '';
        box.appendChild(h('div', { className: 'flex items-center justify-between mb-2' },
            h('div', { className: 'font-semibold text-gray-900' }, `Indrapportering fra ${AREA_ROLE[m.area]}`),
            h('span', { className: 'text-xs text-gray-500' }, 'Spørgsmålene laves ud fra kunder, sager og mål')));
        if (rounds.length === 0) {
            box.appendChild(h('p', { className: 'text-sm text-gray-600 mb-3' },
                m.area === 'salg'
                    ? 'Bed CCO om at indrapportere status på hver kunde i proces, marketing de sidste 14 dage og salgsmålene, inden mødet.'
                    : `Bed ${AREA_ROLE[m.area]} om at indrapportere status på områdets mål og de faste spørgsmål, inden mødet.`));
            box.appendChild(h('button', { className: 'act-btn primary', onClick: () => showReportRequestForm(m) }, 'Bed om indrapportering'));
            return;
        }
        for (const r of rounds) {
            const link = reportLink(r);
            if (r.status === 'draft') {
                box.appendChild(h('div', { className: 'report-row' },
                    h('div', { className: 'flex items-center gap-2 flex-wrap' },
                        h('b', {}, r.respondent_name), h('span', { className: 'gs-pill gs-none' }, 'Kladde'),
                        r.practice ? h('span', { className: 'gs-pill gs-none' }, 'Øvelse') : null,
                        h('span', { className: 'text-sm text-gray-500' }, 'Spørgsmålene skal godkendes, før linket virker')),
                    h('div', { className: 'flex gap-3 mt-2 text-sm' },
                        h('a', { href: `#/reports/${r.id}`, className: 'font-semibold text-blue-600 hover:underline' }, 'Gennemse og godkend spørgsmål \u2192'),
                        h('button', { className: 'text-red-600 hover:underline', onClick: async () => {
                            if (confirm('Slet kladden?')) { await api.deleteReportRound(r.id); router(); }
                        } }, 'Slet'))));
                continue;
            }
            const answered = r.status !== 'open';
            box.appendChild(h('div', { className: 'report-row' },
                h('div', { className: 'flex items-center gap-2 flex-wrap' },
                    h('b', {}, r.respondent_name),
                    h('span', { className: `gs-pill ${answered ? 'gs-good' : r.sent_at ? 'gs-warn' : 'gs-none'}` }, answered ? 'Indsendt' : r.sent_at ? 'Afventer svar' : 'Ikke sendt'),
                    h('span', { className: 'text-sm text-gray-500' }, reportStatusText(r)),
                    r.due_date ? h('span', { className: 'text-sm text-gray-500' }, `· frist ${formatDate(r.due_date)}`) : null),
                !answered ? h('div', { className: 'flex gap-2 mt-2 flex-wrap items-center' },
                    h('input', { value: link, readonly: '', className: 'flex-1 min-w-0 border border-gray-300 rounded-lg px-3 py-1.5 text-sm bg-white', onClick: e => e.target.select() }),
                    h('button', { className: 'act-btn', onClick: async (e) => {
                        await navigator.clipboard.writeText(link); e.target.textContent = 'Kopieret ✓';
                        if (!r.sent_at) { await api.markReportSent(r.id); }
                    } }, 'Kopiér link'),
                    h('button', { className: 'act-btn', ...(cfg.slack ? {} : { disabled: '' }),
                        onClick: async (e) => {
                            if (!cfg.slack) return;
                            if (!confirm(`Send linket til ${r.respondent_name} i Slack nu?`)) return;
                            try { await api.sendReportSlack(r.id, link); e.target.textContent = 'Sendt ✓'; }
                            catch (err) { alert(err.message); }
                        } }, cfg.slack ? 'Send i Slack' : 'Slack (ikke sat op)'),
                    h('a', { href: link, target: '_blank', className: 'act-btn' }, 'Se som modtager')) : null,
                h('div', { className: 'flex gap-3 mt-2 text-sm' },
                    h('a', { href: `#/reports/${r.id}`, className: 'font-semibold text-blue-600 hover:underline' }, answered ? 'Se svar & vurdering →' : 'Se svar indtil nu →'),
                    h('button', { className: 'text-red-600 hover:underline', onClick: async () => {
                        if (confirm('Slet indrapporteringen? Linket holder op med at virke.')) { await api.deleteReportRound(r.id); router(); }
                    } }, 'Slet'))));
        }
    })();
    return box;
}

async function showReportRequestForm(m) {
    const [allUsers, cfg] = await Promise.all([api.getUsers(), api.getReportConfig().catch(() => ({}))]);
    const users = allUsers.filter(u => !u.deleted_at);
    const remembered = localStorage.getItem(`reportRespondent_${m.area}`);
    const due = addDaysIso(-1, (m.meeting_date || todayIso()).slice(0, 10));
    const form = h('form', { className: 'space-y-4', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        localStorage.setItem(`reportRespondent_${m.area}`, fd.get('respondent_user_id'));
        const useAi = !!fd.get('ai_questions');
        try {
            const r = await api.createReportRound({ area: m.area, meeting_id: m.id, respondent_user_id: parseInt(fd.get('respondent_user_id')),
                due_date: fd.get('due_date') || null, ai_questions: useAi, practice: !!fd.get('practice') });
            if (useAi) await runAiQuestionGeneration(r.id);
            else { closeModal(); router(); }
        } catch (err) { alert(err.message); }
    }},
        h('p', { className: 'text-sm text-gray-600' }, 'Der laves et personligt link med spørgsmål til modtageren. Intet bliver sendt, før du selv kopierer linket eller trykker "Send i Slack".'),
        h('div', {}, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, `Hvem er ${AREA_ROLE[m.area]}?`),
            h('select', { name: 'respondent_user_id', required: '', className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value: '' }, 'Vælg...'),
                ...users.map(u => h('option', { value: u.id, ...(String(u.id) === remembered ? { selected: '' } : {}) }, u.name)))),
        formField('Svarfrist', 'due_date', due < todayIso() ? todayIso() : due, 'date'),
        h('label', { className: `flex items-start gap-2 text-sm ${cfg.ai ? '' : 'opacity-60'}` },
            h('input', { type: 'checkbox', name: 'ai_questions', className: 'mt-1', ...(cfg.ai ? { checked: '' } : { disabled: '' }) }),
            h('span', {}, h('b', {}, 'Lad AI formulere spørgsmålene'), h('br', {}),
                cfg.ai ? 'Claude læser kunder, sager, mål og din beskrivelse af salgsprocessen og laver skarpe spørgsmål. Du gennemser og godkender dem, før linket virker.'
                       : 'Kræver ANTHROPIC_API_KEY i Vercel. Ellers bruges de faste spørgsmål.')),
        h('label', { className: 'flex items-start gap-2 text-sm' },
            h('input', { type: 'checkbox', name: 'practice', className: 'mt-1' }),
            h('span', {}, h('b', {}, 'Øvelse'), h('br', {}), 'Svarene bliver ikke overført til mål eller kunder. Godt til at prøve løsningen af.')),
        h('div', { className: 'flex justify-end gap-3 pt-2' },
            h('button', { type: 'button', className: 'px-4 py-2 text-gray-600', onClick: closeModal }, 'Annuller'),
            h('button', { type: 'submit', className: 'bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-medium' }, 'Opret indrapportering')));
    showModal(`Indrapportering · ${AREA_LABELS[m.area]}`, form);
}

// Minimal markdown (overskrifter, punktlister, fed) til AI-vurderingen — teksten escapes først
function miniMarkdown(text) {
    const esc = String(text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const out = []; let inList = false;
    for (const raw of esc.split('\n')) {
        const line = raw.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        if (/^\s*[-*•]\s+/.test(line)) { if (!inList) { out.push('<ul>'); inList = true; } out.push(`<li>${line.replace(/^\s*[-*•]\s+/, '')}</li>`); continue; }
        if (inList) { out.push('</ul>'); inList = false; }
        if (/^#{1,3}\s+/.test(line)) out.push(`<h3>${line.replace(/^#{1,3}\s+/, '')}</h3>`);
        else if (line.trim()) out.push(`<p>${line}</p>`);
    }
    if (inList) out.push('</ul>');
    return out.join('');
}

async function renderReportRound(container, id) {
    container.innerHTML = '<div class="text-gray-400">Indlæser...</div>';
    const [r, cfg] = await Promise.all([api.getReportRound(id), api.getReportConfig().catch(() => ({}))]);
    container.innerHTML = '';
    container.className = 'ml-64 p-8 fade-in';
    if (r.status === 'draft') {
        container.appendChild(h('div', { className: 'mb-4' },
            r.meeting_id ? h('a', { href: `#/meetings/${r.meeting_id}`, className: 'text-sm text-blue-600 hover:underline mb-2 inline-block' }, `\u2190 ${r.meeting_title || 'Mødet'}`) : null,
            h('div', { className: 'flex items-center gap-3 flex-wrap' },
                h('span', { className: `area-pill area-${r.area}` }, AREA_LABELS[r.area]),
                h('h1', { className: 'text-2xl font-bold text-gray-900' }, `Spørgsmål til ${r.respondent_name}`),
                r.practice ? h('span', { className: 'gs-pill gs-none' }, 'Øvelse') : null)));
        renderReportDraft(container, r);
        return;
    }
    const answered = r.status !== 'open';
    const allFlags = r.items.flatMap(it => (it.flags || []).filter(f => f !== 'Ikke besvaret').map(f => ({ f, it })));
    const unanswered = r.items.filter(it => !it.answer);

    container.appendChild(h('div', { className: 'mb-6' },
        r.meeting_id ? h('a', { href: `#/meetings/${r.meeting_id}`, className: 'text-sm text-blue-600 hover:underline mb-2 inline-block' }, `← ${r.meeting_title || 'Mødet'}`) : null,
        h('div', { className: 'flex items-center gap-3 flex-wrap' },
            h('span', { className: `area-pill area-${r.area}` }, AREA_LABELS[r.area]),
            h('h1', { className: 'text-2xl font-bold text-gray-900' }, `Indrapportering fra ${r.respondent_name}`),
            h('span', { className: `gs-pill ${answered ? 'gs-good' : 'gs-warn'}` }, answered ? 'Indsendt' : 'Afventer'),
            r.practice ? h('span', { className: 'gs-pill gs-none' }, 'Øvelse') : null),
        h('p', { className: 'text-gray-500 mt-1' }, `${reportStatusText({ ...r, items_answered: r.items.filter(i => i.answer).length, items_total: r.items.length })}` +
            (answered && !r.practice ? ' · målstatus er overført til målene, og kundestatus er gemt som noter på virksomhederne' : '') +
            (r.practice ? ' · øvelse: svarene er ikke overført til mål eller kunder' : ''))));

    // AI-vurdering
    const ai = h('div', { className: 'ai-box mb-6' });
    const drawAi = (rr) => {
        ai.innerHTML = '';
        ai.appendChild(h('div', { className: 'flex items-center justify-between mb-3 gap-3' },
            h('h2', { className: 'font-bold text-gray-900 text-lg' }, 'Vurdering til dig'),
            h('div', { className: 'flex items-center gap-3' },
                rr.ai_generated_at ? h('span', { className: 'text-xs text-gray-400' }, `Lavet ${new Date(rr.ai_generated_at).toLocaleString('da-DK', { dateStyle: 'short', timeStyle: 'short' })} af AI (${rr.ai_model || 'Claude'})`) : null,
                h('button', { className: 'act-btn primary', ...(cfg.ai ? {} : { disabled: '' }), onClick: async (e) => {
                    e.target.disabled = true; e.target.textContent = 'Vurderer… (op til et minut)';
                    try { drawAi(await api.assessReportRound(id)); }
                    catch (err) { alert(err.message); e.target.disabled = false; e.target.textContent = 'Prøv igen'; }
                } }, rr.ai_assessment ? 'Lav ny vurdering' : 'Lav AI-vurdering'))));
        if (!cfg.ai) ai.appendChild(h('p', { className: 'text-sm text-yellow-700 mb-2' }, 'AI-vurdering er ikke sat op endnu: der mangler en ANTHROPIC_API_KEY i Vercel. Advarslerne herunder virker uden.'));
        if (rr.ai_assessment) ai.appendChild(h('div', { className: 'md', innerHTML: miniMarkdown(rr.ai_assessment) }));
        else if (cfg.ai) ai.appendChild(h('p', { className: 'text-sm text-gray-500' }, answered ? 'Klik for at få en vurdering af indrapporteringen holdt op mod data i systemet.' : 'Kan laves, når der er svar.'));
        ai.appendChild(h('div', { className: 'text-xs text-gray-400 mt-3' }, 'Vurderingen er AI-genereret og bygger kun på svarene og data i SystemateCEO. Tjek den før du handler på den.'));
    };
    drawAi(r);
    container.appendChild(ai);

    // Advarsler
    const fl = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6' },
        h('h2', { className: 'font-semibold text-gray-900 mb-3' }, `Advarsler (${allFlags.length})${unanswered.length ? ` · ${unanswered.length} ikke besvaret` : ''}`));
    if (!allFlags.length) fl.appendChild(h('div', { className: 'text-sm text-gray-400' }, answered ? 'Ingen automatiske advarsler.' : 'Advarsler vises, når der er svar.'));
    for (const { f, it } of allFlags) fl.appendChild(h('div', { className: 'flex gap-3 py-1.5 text-sm border-b border-gray-100' },
        h('span', { className: 'text-yellow-700' }, '⚠'), h('b', { className: 'w-56 flex-shrink-0 truncate' }, it.title), h('span', { className: 'text-gray-700' }, f)));
    container.appendChild(fl);

    // Svar
    // Forslag til oprydning (tabt/vundet/ikke i proces/afleveret → ét klik)
    if ((r.suggestions || []).length) {
        const sbox = h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6' },
            h('h2', { className: 'font-semibold text-gray-900 mb-1' }, `Forslag til oprydning (${r.suggestions.length})`),
            h('p', { className: 'text-sm text-gray-500 mb-3' }, r.practice ? 'Øvelse: forslagene vises, men kan ikke udføres på rigtige data.' : 'Ud fra svarene. Gennemse og udfør med ét klik.'));
        for (const sg of r.suggestions) {
            sbox.appendChild(h('div', { className: 'sug-row' },
                h('div', { className: 'flex-1 min-w-0' },
                    h('a', { href: `#/companies/${sg.company_id}`, className: 'font-semibold text-gray-900 hover:underline' }, sg.company_name),
                    h('span', { className: 'text-xs text-gray-500 ml-2' }, sg.source),
                    h('ul', { className: 'text-sm text-gray-700 mt-1 list-disc ml-5' }, ...sg.actions.map(a => h('li', {}, a.label)))),
                h('button', { className: 'act-btn primary', ...(r.practice ? { disabled: '' } : {}), onClick: async (e) => {
                    e.target.disabled = true;
                    try { await api.applyReportSuggestion(r.id, sg.id); router(); } catch (err) { alert(err.message); e.target.disabled = false; }
                } }, 'Udfør')));
        }
        container.appendChild(sbox);
    }

    const kinds = [['matrix', 'Hurtige afklaringer'], ['topic', 'Emner'], ['customer', 'Kunder'], ['marketing', 'Marketing'], ['goal', 'Mål'], ['question', 'Spørgsmål']];
    for (const [kind, label] of kinds) {
        const its = r.items.filter(i => i.kind === kind);
        if (!its.length) continue;
        container.appendChild(h('h2', { className: 'text-lg font-bold text-gray-900 mb-3 mt-2' }, `${label} (${its.length})`));
        const grid = h('div', { className: 'grid grid-cols-1 xl:grid-cols-2 gap-3 mb-6' });
        for (const it of its) {
            const a = it.answer || {};
            const rows = [];
            const row = (k, v) => v || v === 0 ? rows.push(h('div', { className: 'ans-row' }, h('span', {}, k), h('div', {}, String(v)))) : null;
            if (a.later) row('Status', 'Svarer senere. Kommer med i næste indrapportering.');
            else if (kind === 'matrix') {
                const opt = Object.fromEntries(it.context?.options || []);
                for (const rr of it.context?.rows || []) {
                    const v = (a.rows || {})[rr.company_id];
                    const note = (a.notes || {})[rr.company_id];
                    row(rr.name, v ? `${opt[v] || v}${note ? ': ' + note : ''}${rr.current && rr.current !== v && it.context?.target === 'sales_phase' ? ` (før: ${opt[rr.current] || rr.current})` : ''}` : '(ikke besvaret)');
                }
            } else if (kind === 'customer') {
                if (a.not_relevant) row('Status', 'Ikke længere i proces');
                else { row('Status', REPORT_CUSTOMER_STATUS[a.status]); row('Siden sidst', a.since_last); row('Næste skridt', a.next_step ? `${a.next_step}${a.next_date ? ' (' + formatDate(a.next_date) + ')' : ''}` : ''); row('Sandsynlighed', a.probability ? `${a.probability} %` : ''); row('Brug for hjælp', a.help); }
            } else if (kind === 'marketing') {
                row('Aktiviteter', a.activities); row('Resultat', a.results); row('Leads / møder', a.leads || a.meetings ? `${a.leads || 0} leads · ${a.meetings || 0} møder` : ''); row('Næste 14 dage', a.next); row('Læring', a.learnings);
            } else if (kind === 'goal') {
                row('Status', REPORT_GOAL_STATUS[a.status]); row('Værdi', a.value); row('Kommentar', a.comment);
            } else if (kind === 'topic') {
                row('Vurdering', { paa_sporet: 'På sporet', risiko: 'Risiko', kritisk: 'Kritisk' }[a.status]);
                if (a.goal_status) row('Målstatus', REPORT_GOAL_STATUS[a.goal_status]);
                if (a.value) row('Værdi', a.value);
                (it.context?.questions || []).forEach((q, i) => row(String.fromCharCode(97 + i), `${typeof q === 'string' ? q : q.text}\n→ ${a[`q${i}`] || '(ikke besvaret)'}`));
                if (a.next_step) row('Næste skridt', `${a.next_step}${a.next_date ? ' (' + formatDate(a.next_date) + ')' : ''}`);
                if (a.probability) row('Sandsynlighed', `${a.probability} %`);
                if (a.followup?.question) row('Opfølgning', `${a.followup.question}\n→ ${a.followup.answer || (a.followup.skipped ? '(sprunget over)' : '(ikke besvaret)')}`);
            } else row('Svar', a.answer);
            grid.appendChild(h('div', { className: `ans-card ${(it.flags || []).length ? 'flagged' : ''} ${kind === 'matrix' ? 'xl:col-span-2' : ''}` },
                h('div', { className: 'flex items-center gap-2 mb-2' },
                    it.company_id && kind === 'customer' ? h('a', { href: `#/companies/${it.company_id}`, className: 'font-bold text-gray-900 hover:underline' }, it.title) :
                        it.ref_type === 'goal' ? h('a', { href: `#/goals/${it.ref_id}`, className: 'font-bold text-gray-900 hover:underline' }, it.title) :
                        h('b', { className: 'text-gray-900' }, it.title)),
                rows.length ? rows : h('div', { className: 'text-sm text-gray-400' }, 'Ikke besvaret'),
                ...(it.flags || []).filter(f => f !== 'Ikke besvaret').map(f => h('div', { className: 'ans-flag' }, `⚠ ${f}`))));
        }
        container.appendChild(grid);
    }
}


// Lader Claude lave spørgsmålene i små portioner (hvert kald under Vercels tidsgrænse) og viser fremdriften
async function runAiQuestionGeneration(id) {
    const status = h('div', { className: 'text-sm text-gray-600' }, 'Starter…');
    const bar = h('i', { style: 'width:4%' });
    showModal('AI laver spørgsmålene', h('div', { className: 'space-y-3' },
        h('p', { className: 'text-sm text-gray-600' }, 'Claude gennemgår kunder, sager og mål og formulerer spørgsmål ud fra salgsprocessen. Det tager typisk 1–3 minutter.'),
        h('div', { className: 'gen-bar' }, bar), status));
    try {
        let res = { remaining: 1 }, total = null;
        while (res.remaining > 0) {
            res = await api.aiGenerateReport(id, 4);
            total = total ?? (res.remaining + res.done);
            const done = total - res.remaining;
            bar.style.width = `${Math.max(4, Math.round(done / (total + 1) * 100))}%`;
            status.textContent = `${done} af ${total} emner har fået spørgsmål…`;
        }
        status.textContent = 'Leder efter mønstre på tværs (dubletter, klynger, partnere)…';
        try { await api.aiReportPatterns(id); } catch (e) { console.warn(e); }
        bar.style.width = '100%';
        closeModal();
        location.hash = `#/reports/${id}`;
    } catch (err) {
        status.innerHTML = '';
        status.append(h('div', { className: 'text-red-600 mb-2' }, err.message),
            h('div', { className: 'flex gap-2' },
                h('button', { className: 'act-btn primary', onClick: () => runAiQuestionGeneration(id) }, 'Prøv igen'),
                h('a', { href: `#/reports/${id}`, className: 'act-btn', onClick: closeModal }, 'Gennemse det, der er lavet')));
    }
}

// Kladde: CEO'en gennemser, retter og godkender spørgsmålene, før linket virker
function renderReportDraft(container, r) {
    const pending = r.items.filter(it => !['topic', 'matrix'].includes(it.kind)).length;
    container.appendChild(h('div', { className: 'draft-bar' },
        h('div', {}, h('b', {}, 'Kladde. '), `Gennemse spørgsmålene til ${r.respondent_name}. Ret, slet eller tilføj, og godkend, når du er tilfreds. Først derefter virker linket.`),
        h('div', { className: 'flex gap-2 flex-shrink-0' },
            pending ? h('button', { className: 'act-btn', onClick: () => runAiQuestionGeneration(r.id) }, `Lav de sidste ${pending} med AI`) : null,
            h('button', { className: 'act-btn', onClick: async () => { await api.addReportItem(r.id, { title: 'Nyt emne', context: { questions: ['Nyt spørgsmål'], facts: [], ask_status: false, source_kind: 'manual' } }); router(); } }, '+ Emne'),
            h('button', { className: 'act-btn primary', onClick: async () => {
                await api.updateReportRound(r.id, { status: 'open' });
                if (r.meeting_id) location.hash = `#/meetings/${r.meeting_id}`; else router();
            } }, 'Godkend spørgsmål'))));

    const SRC = { customer: 'Kunde', goal: 'Mål', marketing: 'Marketing', question: 'Fast spørgsmål', pattern: 'Mønster', manual: 'Eget emne' };
    const srcLabel = it => it.kind === 'matrix' ? 'Klik-liste' : it.context?.carried ? 'Fra sidst' : (SRC[it.context?.source_kind] || (it.kind === 'topic' ? 'Emne' : 'Skabelon'));
    for (const it of r.items) {
        const c = it.context || {};
        const save = async (patch) => { await api.updateReportItem(r.id, it.id, patch); };
        const titleIn = h('input', { value: it.title, className: 'draft-title' });
        titleIn.addEventListener('change', () => save({ title: titleIn.value }));
        const factsIn = h('textarea', { rows: String(Math.max(2, (c.facts || []).length)), className: 'draft-facts', placeholder: 'Fakta, én pr. linje' }, (c.facts || []).join('\n'));
        factsIn.addEventListener('change', () => { c.facts = factsIn.value.split('\n').map(x => x.trim()).filter(Boolean); save({ context: c }); });
        const qList = h('div', { className: 'space-y-3' });
        const TYPES = { text: 'Tekst', choice: 'Klik-valg', date: 'Dato', number: 'Tal' };
        const drawQs = () => {
            qList.innerHTML = '';
            c.questions = (c.questions || []).map(q => typeof q === 'string' ? { text: q, answer_type: 'text', options: [] } : q);
            c.questions.forEach((q, i) => {
                const qi = h('textarea', { rows: '2', className: 'draft-q' }, q.text);
                qi.addEventListener('change', () => { q.text = qi.value; save({ context: c }); });
                const ty = h('select', { className: 'draft-type' }, ...Object.entries(TYPES).map(([k, v]) => h('option', { value: k, ...(q.answer_type === k ? { selected: '' } : {}) }, v)));
                const opts = h('input', { className: 'draft-opts', value: (q.options || []).join(', '), placeholder: 'Valgmuligheder, adskilt med komma' });
                opts.style.display = q.answer_type === 'choice' ? '' : 'none';
                ty.addEventListener('change', () => { q.answer_type = ty.value; opts.style.display = ty.value === 'choice' ? '' : 'none'; save({ context: c }); });
                opts.addEventListener('change', () => { q.options = opts.value.split(',').map(x => x.trim()).filter(Boolean); save({ context: c }); });
                qList.appendChild(h('div', { className: 'flex gap-2 items-start' },
                    h('span', { className: 'draft-qn' }, String.fromCharCode(97 + i)),
                    h('div', { className: 'flex-1 space-y-1' }, qi, h('div', { className: 'flex gap-2 items-center' }, h('span', { className: 'text-xs text-gray-500' }, 'Svarform'), ty, opts)),
                    h('button', { className: 'text-gray-300 hover:text-red-500 text-xl', title: 'Fjern spørgsmål',
                        onClick: async () => { c.questions.splice(i, 1); await save({ context: c }); drawQs(); } }, '\u00d7')));
            });
            qList.appendChild(h('button', { className: 'text-sm text-blue-600 hover:underline', onClick: async () => {
                c.questions = [...c.questions, { text: '', answer_type: 'text', options: [] }]; await save({ context: c }); drawQs();
            } }, '+ Spørgsmål'));
        };
        const rowList = h('div', { className: 'flex flex-wrap gap-1 mt-2' });
        const drawRows = () => {
            rowList.innerHTML = '';
            for (const [ri, row] of (c.rows || []).entries()) rowList.appendChild(h('span', { className: 'route-pill' }, row.name,
                h('button', { className: 'ml-1 opacity-60 hover:opacity-100', title: 'Fjern fra listen', onClick: async () => { c.rows.splice(ri, 1); await save({ context: c }); drawRows(); } }, '\u00d7')));
        };
        if (it.kind === 'matrix') drawRows();
        if (it.kind === 'topic') drawQs();
        container.appendChild(h('div', { className: 'draft-card' },
            h('div', { className: 'flex items-center gap-2 mb-2' },
                h('span', { className: 'gs-pill gs-none' }, srcLabel(it)),
                c.related?.length ? h('span', { className: 'text-xs text-gray-500' }, `Bygger på: ${c.related.join(', ')}`) : null,
                h('button', { className: 'ml-auto text-sm text-red-600 hover:underline', onClick: async () => {
                    if (confirm(`Fjern emnet "${it.title}"?`)) { await api.deleteReportItem(r.id, it.id); router(); }
                } }, 'Fjern emne')),
            titleIn,
            it.kind === 'topic' ? factsIn
                : it.kind === 'matrix' ? h('div', { className: 'text-sm text-gray-500 mt-1' }, `Klik-liste til ${(c.rows || []).length} kunder: ${(c.options || []).map(o => o[1]).join(' · ')}`)
                : h('div', { className: 'text-sm text-gray-500 mt-2' }, 'Endnu ikke formuleret af AI. Bruger de faste spørgsmål.'),
            c.why ? h('div', { className: 'text-sm text-gray-500 italic mt-1' }, c.why) : null,
            it.kind === 'topic' ? h('div', { className: 'mt-3' }, qList) : null,
            it.kind === 'matrix' ? rowList : null));
    }
}

// AI-kontekst: CEO'ens beskrivelse af salgsprocessen og hvad CEO'en altid vil vide
function aiContextCard(cfg) {
    const sp = h('textarea', { rows: '7', className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm' }, cfg.sales_process || '');
    const focus = h('textarea', { rows: '3', className: 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm',
        placeholder: 'Fx: vores partnere (Servia), konkurrenter (EG), hvad der er vigtigst i år, ting jeg altid spørger om' }, cfg.ceo_focus || '');
    const msg = h('span', { className: 'text-sm text-gray-500' });
    const body = h('div', { className: 'mt-3 space-y-3', style: 'display:none' },
        h('div', {}, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Salgsprocessen'), sp),
        h('div', {}, h('label', { className: 'block text-sm font-medium text-gray-700 mb-1' }, 'Hvad jeg ellers lægger vægt på'), focus),
        h('div', { className: 'flex items-center gap-3' },
            h('button', { className: 'act-btn primary', onClick: async () => {
                await api.saveReportConfig({ sales_process: sp.value, ceo_focus: focus.value }); msg.textContent = 'Gemt ✓';
            } }, 'Gem'), msg));
    return h('div', { className: 'bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6' },
        h('div', { className: 'flex items-center justify-between cursor-pointer', onClick: () => { body.style.display = body.style.display === 'none' ? '' : 'none'; } },
            h('div', {}, h('div', { className: 'font-semibold text-gray-900' }, 'Kontekst til AI-spørgsmål'),
                h('div', { className: 'text-sm text-gray-500' }, `Claude bruger din beskrivelse af salgsprocessen, når spørgsmål og vurderinger laves${cfg.ai ? '' : ' (AI er ikke sat op endnu)'}.`)),
            h('span', { className: 'text-sm font-semibold text-blue-600' }, 'Vis / ret')),
        body);
}


// Virksomhedsside: medlemskab af indkøbsfællesskaber, eller medlemslisten hvis virksomheden selv er et fællesskab
function renderGroupBlock(company, memberships, members) {
    const box = h('div', { className: 'group-block mb-6' });
    if (company.is_purchasing_group) {
        const add = async () => {
            const all = (await api.getCompanies()).filter(c => c.id !== company.id && !members.some(m => m.id === c.id));
            const sel = h('select', { className: 'w-full border border-gray-300 rounded-lg px-3 py-2', size: '10', multiple: '' },
                ...all.map(c => h('option', { value: c.id }, c.name)));
            showModal(`Tilføj medlemmer til ${company.name}`, h('div', { className: 'space-y-3' },
                h('p', { className: 'text-sm text-gray-500' }, 'Hold Cmd nede for at vælge flere.'), sel,
                h('div', { className: 'flex justify-end gap-3' },
                    h('button', { className: 'px-4 py-2 text-gray-600', onClick: closeModal }, 'Annuller'),
                    h('button', { className: 'bg-blue-600 text-white px-4 py-2 rounded-lg font-medium', onClick: async () => {
                        for (const o of [...sel.selectedOptions]) await api.addMembership(parseInt(o.value), company.id);
                        closeModal(); router();
                    } }, 'Tilføj'))));
        };
        box.appendChild(h('div', { className: 'flex items-center justify-between mb-3' },
            h('div', { className: 'flex items-center gap-2' }, h('span', { className: 'route-pill' }, 'Indkøbsfællesskab'),
                h('b', { className: 'text-gray-900' }, `${members.length} medlemmer`)),
            h('div', { className: 'flex gap-3 text-sm' },
                h('button', { className: 'font-semibold text-blue-600 hover:underline', onClick: add }, '+ Tilføj medlemmer'),
                h('button', { className: 'text-gray-400 hover:underline', onClick: async () => {
                    if (confirm(`Er ${company.name} ikke et indkøbsfællesskab?`)) { await api.setPurchasingGroup(company.id, false); router(); }
                } }, 'Ikke et fællesskab'))));
        if (!members.length) box.appendChild(h('div', { className: 'text-sm text-gray-400' }, 'Ingen medlemmer registreret endnu.'));
        const grid = h('div', { className: 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2' });
        for (const m of members) {
            grid.appendChild(h('div', { className: 'member-row' },
                h('a', { href: `#/companies/${m.id}`, className: 'font-medium text-gray-900 hover:underline flex-1 truncate' }, m.name),
                m.active_tenders ? h('span', { className: 'text-xs text-gray-500' }, `${m.active_tenders} tilbud${m.via_group_tenders ? `, ${m.via_group_tenders} via ${company.name}` : ''}`) : null,
                h('button', { className: 'text-gray-300 hover:text-red-500 text-lg', title: 'Fjern medlem', onClick: async () => {
                    await api.removeMembership(m.id, company.id); router();
                } }, '×')));
        }
        box.appendChild(grid);
        return box;
    }
    const chips = h('div', { className: 'flex items-center gap-2 flex-wrap' },
        h('span', { className: 'text-sm text-gray-500' }, memberships.length ? 'Medlem af indkøbsfællesskab:' : 'Ikke medlem af et indkøbsfællesskab.'),
        ...memberships.map(g => h('span', { className: 'route-pill' },
            h('a', { href: `#/companies/${g.id}`, className: 'hover:underline' }, g.name),
            h('button', { className: 'ml-1 opacity-60 hover:opacity-100', title: 'Fjern medlemskab', onClick: async () => {
                if (confirm(`Fjern ${company.name} fra ${g.name}?`)) { await api.removeMembership(company.id, g.id); router(); }
            } }, '×'))),
        h('button', { className: 'text-sm font-semibold text-blue-600 hover:underline', onClick: async () => {
            const [groups, all] = await Promise.all([api.getPurchasingGroups(), api.getCompanies()]);
            const sel = h('select', { className: 'w-full border border-gray-300 rounded-lg px-3 py-2' },
                h('option', { value: '' }, 'Vælg…'),
                groups.length ? h('optgroup', { label: 'Indkøbsfællesskaber' }, ...groups.filter(g => g.id !== company.id).map(g => h('option', { value: g.id }, `${g.name} (${g.member_count} medlemmer)`))) : null,
                h('optgroup', { label: 'Gør en anden virksomhed til fællesskab' }, ...all.filter(c => c.id !== company.id && !c.is_purchasing_group).map(c => h('option', { value: c.id }, c.name))));
            showModal(`${company.name} er medlem af…`, h('div', { className: 'space-y-3' }, sel,
                h('div', { className: 'flex justify-end gap-3' },
                    h('button', { className: 'px-4 py-2 text-gray-600', onClick: closeModal }, 'Annuller'),
                    h('button', { className: 'bg-blue-600 text-white px-4 py-2 rounded-lg font-medium', onClick: async () => {
                        if (!sel.value) return;
                        await api.addMembership(company.id, parseInt(sel.value)); closeModal(); router();
                    } }, 'Tilføj'))));
        } }, '+ Tilføj til fællesskab'),
        h('button', { className: 'text-sm text-gray-400 hover:underline ml-auto', onClick: async () => {
            if (confirm(`Markér ${company.name} som indkøbsfællesskab (fx en sammenslutning af forsyninger)?`)) { await api.setPurchasingGroup(company.id, true); router(); }
        } }, 'Er selv et indkøbsfællesskab?'));
    box.appendChild(chips);
    return box;
}


// ─── CEO-assistent: hvad mangler, hvad er over frist, og hvad bør jeg gøre? ───
const SEVERITY = { kritisk: ['Kritisk', 'gs-bad'], vigtig: ['Vigtigt', 'gs-warn'], tips: ['Tips', 'gs-none'] };
let _assistantChat = [];

function assistantItem(it, onChange, compact = false) {
    const [label, cls] = SEVERITY[it.severity];
    return h('div', { className: `as-item sev-${it.severity}` },
        h('div', { className: 'flex items-center gap-2 mb-1 flex-wrap' },
            h('span', { className: `gs-pill ${cls}` }, label),
            it.area && GOAL_AREAS[it.area] ? h('span', { className: `area-pill area-${it.area}` }, GOAL_AREAS[it.area]) : null),
        h('div', { className: 'as-title' }, it.title),
        it.detail ? h('div', { className: 'as-detail' }, it.detail) : null,
        !compact && it.why ? h('div', { className: 'as-why' }, it.why) : null,
        h('div', { className: 'flex items-center gap-3 mt-2' },
            h('a', { href: it.href, className: 'act-btn primary', onClick: () => closeAssistant() }, `${it.action} →`),
            h('button', { className: 'text-xs text-gray-400 hover:underline', onClick: async () => { await api.snoozeAssistant(it.id, 7); onChange && onChange(); updateAssistantBadge(); } }, 'Udsæt en uge')));
}

function renderAssistantFocus(a) {
    const top = a.items.slice(0, 3);
    const box = h('div', { className: 'as-focus mb-5' },
        h('div', { className: 'flex items-center justify-between mb-3' },
            h('div', { className: 'flex items-center gap-2' },
                h('span', { className: 'as-spark' }, '✦'),
                h('b', { className: 'text-gray-900' }, 'Assistenten: dagens fokus'),
                h('span', { className: 'text-sm text-gray-500' }, `${a.counts.kritisk} kritiske · ${a.counts.vigtig} vigtige · ${a.counts.tips} tips`)),
            h('button', { className: 'text-sm font-semibold text-blue-600 hover:underline', onClick: () => openAssistant() }, `Se alle ${a.items.length} →`)));
    if (!top.length) box.appendChild(h('div', { className: 'text-sm text-gray-500' }, 'Intet at gøre lige nu. Alt er fulgt op.'));
    box.appendChild(h('div', { className: 'grid grid-cols-1 lg:grid-cols-3 gap-3' }, ...top.map(it => assistantItem(it, () => router(), true))));
    return box;
}

async function updateAssistantBadge() {
    try {
        const a = await api.getAssistant();
        const n = a.counts.kritisk + a.counts.vigtig;
        const b = document.getElementById('assistant-badge');
        b.textContent = String(n);
        b.classList.toggle('hidden', n === 0);
        b.classList.toggle('crit', a.counts.kritisk > 0);
        return a;
    } catch (e) { return null; }
}

function initAssistant() {
    document.getElementById('assistant-btn')?.addEventListener('click', () => {
        const p = document.getElementById('assistant-panel');
        if (p.classList.contains('hidden')) openAssistant(); else closeAssistant();
    });
    setTimeout(updateAssistantBadge, 1500);
}
function closeAssistant() { document.getElementById('assistant-panel')?.classList.add('hidden'); }

async function openAssistant() {
    const panel = document.getElementById('assistant-panel');
    panel.classList.remove('hidden');
    panel.innerHTML = '<div class="p-6 text-gray-400">Gennemgår mål, møder, aktioner og tilbud…</div>';
    const a = await updateAssistantBadge();
    if (!a) { panel.innerHTML = '<div class="p-6 text-red-600">Assistenten kunne ikke hentes.</div>'; return; }
    panel.innerHTML = '';
    const list = h('div', { className: 'as-list' });
    const drawList = (data) => {
        list.innerHTML = '';
        for (const sev of ['kritisk', 'vigtig', 'tips']) {
            const items = data.items.filter(i => i.severity === sev);
            if (!items.length) continue;
            list.appendChild(h('div', { className: 'as-sec' }, `${SEVERITY[sev][0]} (${items.length})`));
            for (const it of items) list.appendChild(assistantItem(it, async () => drawList(await api.getAssistant())));
        }
        if (!data.items.length) list.appendChild(h('div', { className: 'text-sm text-gray-500 p-4' }, 'Intet at gøre lige nu. Alt er fulgt op.'));
        if (data.snoozed) list.appendChild(h('button', { className: 'text-xs text-gray-400 hover:underline mt-3', onClick: async () => { await api.clearAssistantSnoozes(); drawList(await api.getAssistant()); updateAssistantBadge(); } }, `Vis ${data.snoozed} udsatte punkter igen`));
    };
    drawList(a);

    // AI-rådgivning: plan og spørgsmål
    const chat = h('div', { className: 'as-chat' });
    const drawChat = () => {
        chat.innerHTML = '';
        for (const m of _assistantChat) chat.appendChild(m.role === 'user'
            ? h('div', { className: 'as-q' }, m.content)
            : h('div', { className: 'as-a md', innerHTML: miniMarkdown(m.content) }));
    };
    const input = h('input', { className: 'as-input', placeholder: a.ai ? 'Spørg assistenten…' : 'AI er ikke slået til endnu', ...(a.ai ? {} : { disabled: '' }) });
    const ask = async (q) => {
        if (!q.trim()) return;
        _assistantChat.push({ role: 'user', content: q }); drawChat();
        const wait = h('div', { className: 'as-a text-gray-400' }, 'Tænker…'); chat.appendChild(wait); chat.scrollTop = chat.scrollHeight;
        try {
            const res = await api.askAssistant(q, _assistantChat.slice(0, -1));
            _assistantChat.push({ role: 'assistant', content: res.answer });
        } catch (e) { _assistantChat.push({ role: 'assistant', content: `Fejl: ${e.message}` }); }
        drawChat(); chat.scrollTop = chat.scrollHeight;
    };
    input.addEventListener('keydown', e => { if (e.key === 'Enter') { const q = input.value; input.value = ''; ask(q); } });
    const quick = ['Lav min plan for ugen', 'Hvad skal jeg tage op med CCO?', 'Hvad skal jeg tage op med COO?', 'Hvad skal jeg tage op med CFO?', 'Hvilke mål er i fare, og hvad gør jeg?'];
    drawChat();

    panel.append(
        h('div', { className: 'as-head' },
            h('div', {}, h('div', { className: 'font-bold text-gray-900 text-lg' }, '✦ CEO-assistent'),
                h('div', { className: 'text-xs text-gray-500' }, `${a.counts.kritisk} kritiske · ${a.counts.vigtig} vigtige · ${a.counts.tips} tips`)),
            h('button', { className: 'text-gray-400 hover:text-gray-700 text-2xl', onClick: closeAssistant }, '×')),
        h('div', { className: 'as-body' },
            h('div', { className: 'as-ai' },
                h('div', { className: 'font-semibold text-gray-900 mb-2' }, 'Spørg assistenten'),
                a.ai ? h('div', { className: 'flex flex-wrap gap-1 mb-2' }, ...quick.map(q => h('button', { className: 'as-chip', onClick: () => ask(q) }, q)))
                     : h('div', { className: 'text-xs text-yellow-700 mb-2' }, 'Kræver ANTHROPIC_API_KEY i Vercel. Tjeklisten herunder virker uden.'),
                chat, input),
            list));
}
