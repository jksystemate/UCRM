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
    getCompany: (id) => request(`/companies/${id}`),
    createCompany: (data) => request('/companies', { method: 'POST', body: JSON.stringify(data) }),
    updateCompany: (id, data) => request(`/companies/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteCompany: (id) => request(`/companies/${id}`, { method: 'DELETE' }),

    // Contacts
    getContacts: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/contacts${qs ? '?' + qs : ''}`);
    },
    getContact: (id) => request(`/contacts/${id}`),
    createContact: (data) => request('/contacts', { method: 'POST', body: JSON.stringify(data) }),
    updateContact: (id, data) => request(`/contacts/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteContact: (id) => request(`/contacts/${id}`, { method: 'DELETE' }),

    // Interactions
    getInteractions: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/interactions${qs ? '?' + qs : ''}`);
    },
    createInteraction: (data) => request('/interactions', { method: 'POST', body: JSON.stringify(data) }),
    deleteInteraction: (id) => request(`/interactions/${id}`, { method: 'DELETE' }),

    // Emails
    getEmails: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/emails${qs ? '?' + qs : ''}`);
    },
    getEmail: (id) => request(`/emails/${id}`),
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
    createUser: (data) => request('/users', { method: 'POST', body: JSON.stringify(data) }),
    deleteUser: (id) => request(`/users/${id}`, { method: 'DELETE' }),

    // Combined endpoints (fewer requests = faster)
    getCompanyFull: (id) => request(`/companies/${id}/full`),
    getDashboardAll: () => request('/dashboard/all'),

    // Dashboard
    getScores: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/dashboard/scores${qs ? '?' + qs : ''}`);
    },
    getCompanyScore: (id) => request(`/dashboard/scores/${id}`),
    getStats: () => request('/dashboard/stats'),

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
    deleteTask: (id) => request(`/tasks/${id}`, { method: 'DELETE' }),
    getTaskSummary: () => request('/tasks/summary'),

    // Audit log
    getAuditLog: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/audit-log${qs ? '?' + qs : ''}`);
    },

    // Notifications
    getNotifications: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/notifications${qs ? '?' + qs : ''}`);
    },
    getNotificationCount: () => request('/notifications/count'),
    markNotificationRead: (id) => request(`/notifications/${id}/read`, { method: 'PUT' }),
    markAllNotificationsRead: () => request('/notifications/read-all', { method: 'PUT' }),
    checkNotifications: () => request('/notifications/check'),

    // Score settings
    getScoreThresholds: () => request('/settings/score-thresholds'),
    updateScoreThresholds: (data) => request('/settings/score-thresholds', { method: 'PUT', body: JSON.stringify(data) }),

    // LinkedIn activities
    getLinkedInActivities: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/linkedin-activities${qs ? '?' + qs : ''}`);
    },
    createLinkedInActivity: (data) => request('/linkedin-activities', { method: 'POST', body: JSON.stringify(data) }),
    deleteLinkedInActivity: (id) => request(`/linkedin-activities/${id}`, { method: 'DELETE' }),

    // LinkedIn engagements
    getLinkedInEngagements: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return request(`/linkedin-engagements${qs ? '?' + qs : ''}`);
    },
    createLinkedInEngagement: (data) => request('/linkedin-engagements', { method: 'POST', body: JSON.stringify(data) }),
    deleteLinkedInEngagement: (id) => request(`/linkedin-engagements/${id}`, { method: 'DELETE' }),

    // Tags
    getTags: () => request('/tags'),
    createTag: (data) => request('/tags', { method: 'POST', body: JSON.stringify(data) }),
    deleteTag: (id) => request(`/tags/${id}`, { method: 'DELETE' }),
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

    // Tender Sections
    createTenderSection: (data) => request('/tender-sections', { method: 'POST', body: JSON.stringify(data) }),
    updateTenderSection: (id, data) => request(`/tender-sections/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteTenderSection: (id) => request(`/tender-sections/${id}`, { method: 'DELETE' }),
    getSectionAudit: (sectionId) => request(`/tender-sections/${sectionId}/audit`),
    addSectionComment: (sectionId, content) => request(`/tender-sections/${sectionId}/comments`,
        { method: 'POST', body: JSON.stringify({ content }) }),

    // Decay rules
    getDecayRules: () => request('/settings/decay-rules'),
    updateDecayRules: (data) => request('/settings/decay-rules', { method: 'PUT', body: JSON.stringify(data) }),

    // Tender Templates
    getTenderTemplates: () => request('/tender-templates'),
    getTenderTemplate: (id) => request(`/tender-templates/${id}`),
    createTenderTemplate: (data) => request('/tender-templates', { method: 'POST', body: JSON.stringify(data) }),
    updateTenderTemplate: (id, data) => request(`/tender-templates/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteTenderTemplate: (id) => request(`/tender-templates/${id}`, { method: 'DELETE' }),
    addTemplateSection: (templateId, data) => request(`/tender-templates/${templateId}/sections`, { method: 'POST', body: JSON.stringify(data) }),
    updateTemplateSection: (id, data) => request(`/tender-template-sections/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteTemplateSection: (id) => request(`/tender-template-sections/${id}`, { method: 'DELETE' }),
};

window.api = api;
