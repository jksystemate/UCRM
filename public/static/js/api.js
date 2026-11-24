const BASE = '/api';

function getCurrentUserId() {
    return localStorage.getItem('currentUserId') || null;
}

async function request(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    const userId = getCurrentUserId();
    if (userId) headers['X-User-Id'] = userId;
    const res = await fetch(`${BASE}${path}`, { headers, ...options });
    if (res.status === 204) return null;
    // Session udløbet eller ikke logget ind: appen viser login-skærmen
    if (res.status === 401 && !path.startsWith('/login')) window.dispatchEvent(new CustomEvent('ucrm-login-required'));
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Ukendt fejl' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

export const api = {
    // Companies
    getCompanies: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/companies${qs ? '?' + qs : ''}`);
    },
    createCompany: (data) => request('/companies', { method: 'POST', body: JSON.stringify(data) }),
    updateCompany: (id, data) => request(`/companies/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteCompany: (id) => request(`/companies/${id}`, { method: 'DELETE' }),

    // Contacts
    createContact: (data) => request('/contacts', { method: 'POST', body: JSON.stringify(data) }),
    updateContact: (id, data) => request(`/contacts/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteContact: (id) => request(`/contacts/${id}`, { method: 'DELETE' }),

    // Interactions
    createInteraction: (data) => request('/interactions', { method: 'POST', body: JSON.stringify(data) }),
    deleteInteraction: (id) => request(`/interactions/${id}`, { method: 'DELETE' }),

    // Emails
    uploadEmail: async (file, contactId, userId) => {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('contact_id', contactId);
        if (userId) formData.append('user_id', userId);
        const headers = {};
        const uid = getCurrentUserId();
        if (uid) headers['X-User-Id'] = uid;
        const res = await fetch(`${BASE}/emails/upload`, { method: 'POST', body: formData, headers });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Upload fejlede' }));
            throw new Error(err.detail);
        }
        return res.json();
    },

    // Users
    getUsers: () => request('/users'),
    updateUser: (id, data) => request(`/users/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    createUser: (data) => request('/users', { method: 'POST', body: JSON.stringify(data) }),
    deleteUser: (id) => request(`/users/${id}`, { method: 'DELETE' }),
    restoreUser: (id) => request(`/users/${id}/restore`, { method: 'POST' }),

    // Combined endpoints (fewer requests = faster)
    getCompanyFull: (id) => request(`/companies/${id}/full`),
    getDashboardAll: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/dashboard/all${qs ? '?' + qs : ''}`);
    },
    getScoreHistoryAggregate: () => request('/score-history/aggregate'),

    // Dashboard

    // Search
    search: (q) => request(`/search?q=${encodeURIComponent(q)}`),

    // Tasks
    getTasks: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/tasks${qs ? '?' + qs : ''}`);
    },
    getTask: (id) => request(`/tasks/${id}`),
    createTask: (data) => request('/tasks', { method: 'POST', body: JSON.stringify(data) }),
    updateTask: (id, data) => request(`/tasks/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    getTaskNotes: (id) => request(`/tasks/${id}/notes`),
    createTaskNote: (id, data) => request(`/tasks/${id}/notes`, { method: 'POST', body: JSON.stringify(data) }),
    updateTaskNote: (id, data) => request(`/task-notes/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    getTaskHistory: (id) => request(`/tasks/${id}/history`),
    uploadTaskEmail: async (taskId, file) => {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('task_id', taskId);
        const headers = {};
        const uid = getCurrentUserId();
        if (uid) headers['X-User-Id'] = uid;
        const res = await fetch(`${BASE}/tasks/upload-email`, { method: 'POST', body: formData, headers });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Upload fejlede' }));
            throw new Error(err.detail);
        }
        return res.json();
    },

    // Tags
    updateTag: (id, data) => request(`/tags/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

    // Company notes
    createCompanyNote: (id, data) => request(`/companies/${id}/notes`, { method: 'POST', body: JSON.stringify(data) }),
    updateCompanyNote: (id, data) => request(`/company-notes/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

    // Tender notes
    getTenderNotes: (id) => request(`/tenders/${id}/notes`),
    createTenderNote: (id, data) => request(`/tenders/${id}/notes`, { method: 'POST', body: JSON.stringify(data) }),
    updateTenderNote: (id, data) => request(`/tender-notes/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    getTenderHistory: (id) => request(`/tenders/${id}/history`),
    getTenderPhases: (id) => request(`/tenders/${id}/phases`),

    // Audit log

    // Notifications
    getNotifications: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/notifications${qs ? '?' + qs : ''}`);
    },
    getNotificationCount: () => request('/notifications/count'),
    markNotificationRead: (id) => request(`/notifications/${id}/read`, { method: 'PUT' }),
    clearReadNotifications: () => request('/notifications/read', { method: 'DELETE' }),
    markAllNotificationsRead: () => request('/notifications/read-all', { method: 'PUT' }),
    checkNotifications: () => request('/notifications/check'),

    // Score settings
    getScoreThresholds: () => request('/settings/score-thresholds'),
    updateScoreThresholds: (data) => request('/settings/score-thresholds', { method: 'PUT', body: JSON.stringify(data) }),

    // LinkedIn activities
    createLinkedInActivity: (data) => request('/linkedin-activities', { method: 'POST', body: JSON.stringify(data) }),

    // LinkedIn engagements
    createLinkedInEngagement: (data) => request('/linkedin-engagements', { method: 'POST', body: JSON.stringify(data) }),

    // Tags
    createTag: (data) => request('/tags', { method: 'POST', body: JSON.stringify(data) }),
    addCompanyTag: (companyId, tagId) => request(`/companies/${companyId}/tags`, { method: 'POST', body: JSON.stringify({ tag_id: tagId }) }),
    removeCompanyTag: (companyId, tagId) => request(`/companies/${companyId}/tags/${tagId}`, { method: 'DELETE' }),
    addContactTag: (contactId, tagId) => request(`/contacts/${contactId}/tags`, { method: 'POST', body: JSON.stringify({ tag_id: tagId }) }),
    removeContactTag: (contactId, tagId) => request(`/contacts/${contactId}/tags/${tagId}`, { method: 'DELETE' }),

    // Tenders
    getTenders: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/tenders${qs ? '?' + qs : ''}`);
    },
    getTenderFull: (id) => request(`/tenders/${id}/full`),
    createTender: (data) => request('/tenders', { method: 'POST', body: JSON.stringify(data) }),
    updateTender: (id, data) => request(`/tenders/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteTender: (id) => request(`/tenders/${id}`, { method: 'DELETE' }),

    // Decay rules
    getDecayRules: () => request('/settings/decay-rules'),
    updateDecayRules: (data) => request('/settings/decay-rules', { method: 'PUT', body: JSON.stringify(data) }),

    // SystemateCEO: mål, ledermøder og aktioner
    // Login
    getSession: () => request('/session'),
    login: (username, password) => request('/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
    logout: () => request('/logout', { method: 'POST' }),
    getCeoOverview: () => request('/ceo/overview'),
    // Økonomi: budget og saldobalance
    getFinanceBudget: () => request('/finance/budget'),
    uploadFinanceBudget: (data) => request('/finance/budget', { method: 'POST', body: JSON.stringify(data) }),
    getFinanceBalances: () => request('/finance/balances'),
    getFinanceBalance: (id) => request(`/finance/balances/${id}`),
    uploadFinanceBalance: (data) => request('/finance/balances', { method: 'POST', body: JSON.stringify(data) }),
    analyzeFinanceBalance: (id) => request(`/finance/balances/${id}/analyze`, { method: 'POST' }),
    deleteFinanceBalance: (id) => request(`/finance/balances/${id}`, { method: 'DELETE' }),
    getGoals: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/goals${qs ? '?' + qs : ''}`);
    },
    getGoal: (id) => request(`/goals/${id}`),
    createGoal: (data) => request('/goals', { method: 'POST', body: JSON.stringify(data) }),
    updateGoal: (id, data) => request(`/goals/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteGoal: (id) => request(`/goals/${id}`, { method: 'DELETE' }),
    createGoalCheckin: (id, data) => request(`/goals/${id}/checkins`, { method: 'POST', body: JSON.stringify(data) }),
    goalFollowupSuggestions: (goalId, notes) => request(`/goals/${goalId}/followup-suggestions`, { method: 'POST', body: JSON.stringify({ notes }) }),
    goalBreakdown: (goalId, data) => request(`/goals/${goalId}/breakdown`, { method: 'POST', body: JSON.stringify(data) }),
    createMilestone: (goalId, data) => request(`/goals/${goalId}/milestones`, { method: 'POST', body: JSON.stringify(data) }),
    updateMilestone: (id, data) => request(`/milestones/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteMilestone: (id) => request(`/milestones/${id}`, { method: 'DELETE' }),
    getMeetings: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/meetings${qs ? '?' + qs : ''}`);
    },
    getMeeting: (id) => request(`/meetings/${id}`),
    createMeeting: (data) => request('/meetings', { method: 'POST', body: JSON.stringify(data) }),
    updateMeeting: (id, data) => request(`/meetings/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteMeeting: (id) => request(`/meetings/${id}`, { method: 'DELETE' }),
    getActions: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/actions${qs ? '?' + qs : ''}`);
    },
    getFollowupSettings: () => request('/ceo/followup-settings'),
    saveFollowupSettings: (data) => request('/ceo/followup-settings', { method: 'PUT', body: JSON.stringify(data) }),
    requestTaskStatus: (role, sendSlack = false, taskIds = null) => request('/ceo/followup', { method: 'POST', body: JSON.stringify({ role, send_slack: sendSlack, origin: location.origin, task_ids: taskIds }) }),
    breakdownTask: (data) => request('/actions/breakdown', { method: 'POST', body: JSON.stringify(data) }),
    createAction: (data) => request('/actions', { method: 'POST', body: JSON.stringify(data) }),
    updateAction: (id, data) => request(`/actions/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteAction: (id) => request(`/actions/${id}`, { method: 'DELETE' }),

    // Indrapportering før ledermøder
    getReportConfig: () => request('/report-config'),
    getReportRounds: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/report-rounds${qs ? '?' + qs : ''}`);
    },
    getReportRound: (id) => request(`/report-rounds/${id}`),
    createReportRound: (data) => request('/report-rounds', { method: 'POST', body: JSON.stringify(data) }),
    markReportSent: (id) => request(`/report-rounds/${id}/sent`, { method: 'POST' }),
    sendReportSlack: (id, link, text = null) => request(`/report-rounds/${id}/slack`, { method: 'POST', body: JSON.stringify({ link, text }) }),
    assessReportRound: (id) => request(`/report-rounds/${id}/assess`, { method: 'POST' }),
    updateReportRound: (id, data) => request(`/report-rounds/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteReportRound: (id) => request(`/report-rounds/${id}`, { method: 'DELETE' }),
    rebuildReportRound: (id) => request(`/report-rounds/${id}/rebuild`, { method: 'POST' }),
    // CEO-assistent
    getAssistant: () => request('/ceo/assistant'),
    snoozeAssistant: (id, days = 7) => request('/ceo/assistant/snooze', { method: 'POST', body: JSON.stringify({ id, days }) }),
    clearAssistantSnoozes: () => request('/ceo/assistant/snooze', { method: 'POST', body: JSON.stringify({ clear: true }) }),
    askAssistant: (question, history = [], mode = null) => request('/ceo/assistant/ask', { method: 'POST', body: JSON.stringify({ question, history, mode }) }),
    getLeadershipMirror: () => request('/ceo/assistant/mirror'),
    // Indkøbsfællesskaber
    getPurchasingGroups: () => request('/purchasing-groups'),
    setPurchasingGroup: (companyId, isGroup) => request(`/companies/${companyId}/group`, { method: 'PUT', body: JSON.stringify({ is_purchasing_group: isGroup }) }),
    addMembership: (companyId, groupId) => request(`/companies/${companyId}/memberships`, { method: 'POST', body: JSON.stringify({ group_id: groupId }) }),
    removeMembership: (companyId, groupId) => request(`/companies/${companyId}/memberships/${groupId}`, { method: 'DELETE' }),
    saveReportConfig: (data) => request('/report-config', { method: 'PUT', body: JSON.stringify(data) }),
    aiGenerateReport: (id, limit = 4) => request(`/report-rounds/${id}/ai-generate`, { method: 'POST', body: JSON.stringify({ limit }) }),
    aiReportPatterns: (id) => request(`/report-rounds/${id}/ai-patterns`, { method: 'POST' }),
    addReportItem: (id, data) => request(`/report-rounds/${id}/items`, { method: 'POST', body: JSON.stringify(data) }),
    updateReportItem: (id, itemId, data) => request(`/report-rounds/${id}/items/${itemId}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteReportItem: (id, itemId) => request(`/report-rounds/${id}/items/${itemId}`, { method: 'DELETE' }),
    suggestReportQuestions: (id) => request(`/report-rounds/${id}/suggest-questions`, { method: 'POST' }),
    createFollowupRound: (id, data) => request(`/report-rounds/${id}/followup-round`, { method: 'POST', body: JSON.stringify(data) }),
    applyReportSuggestion: (id, suggestionId) => request(`/report-rounds/${id}/apply-suggestion`, { method: 'POST', body: JSON.stringify({ id: suggestionId }) }),
};

window.api = api;
