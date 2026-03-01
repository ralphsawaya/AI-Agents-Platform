/* ── API helpers ── */
async function api(method, url, body) {
    const opts = {method, headers: {}};
    if (body instanceof FormData) {
        opts.body = body;
    } else if (body) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    return res.json();
}

const API = {
    get:    (url) => api('GET', url),
    post:   (url, body) => api('POST', url, body),
    put:    (url, body) => api('PUT', url, body),
    del:    (url) => api('DELETE', url),
    upload: (url, formData) => api('POST', url, formData),
};

/* ── Toast notifications ── */
function toast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

/* ── WebSocket helper ── */
function connectWS(path, onMessage) {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${protocol}://${location.host}${path}`);
    ws.onmessage = (e) => {
        try {
            onMessage(JSON.parse(e.data));
        } catch {
            onMessage(e.data);
        }
    };
    ws.onerror = () => toast('WebSocket error', 'error');
    ws.onclose = () => {};
    // Keep alive
    const ping = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        else clearInterval(ping);
    }, 30000);
    return ws;
}

/* ── Tab switching ── */
function initTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const group = tab.closest('.tabs');
            group.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const target = tab.dataset.tab;
            const parent = group.parentElement;
            parent.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            const content = parent.querySelector(`#tab-${target}`);
            if (content) content.classList.add('active');
        });
    });
}

/* ── Modal ── */
function openModal(id) {
    document.getElementById(id).classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

/* ── Badge HTML ── */
function statusBadge(status) {
    return `<span class="badge badge-${status || 'idle'}">${status || 'idle'}</span>`;
}

/* ── Date formatting ── */
function fmtDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
}

function fmtDuration(seconds) {
    if (!seconds && seconds !== 0) return '—';
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const m = Math.floor(seconds / 60);
    const s = (seconds % 60).toFixed(0);
    return `${m}m ${s}s`;
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded', () => {
    initTabs();

    // Highlight active sidebar link
    const path = location.pathname;
    document.querySelectorAll('.sidebar a').forEach(a => {
        if (a.getAttribute('href') === path ||
            (path.startsWith('/agents/') && a.getAttribute('href') === '/')) {
            a.classList.add('active');
        }
    });
});
