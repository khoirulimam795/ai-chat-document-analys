// ============================================================
// CONFIGURATION
// ============================================================
const API_URL = 'http://localhost:8000';
let token = localStorage.getItem('token');
let currentDocId = null;
let currentDocName = null;
let allDocuments = [];

// ============================================================
// THEME
// ============================================================
function toggleTheme() {
    const html = document.documentElement;
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    document.getElementById('themeToggle').textContent = next === 'dark' ? '☀️' : '🌙';
    localStorage.setItem('docuchat-theme', next);
}

(function () {
    let saved = localStorage.getItem('docuchat-theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    const btn = document.getElementById('themeToggle');
    if (btn) btn.textContent = saved === 'dark' ? '☀️' : '🌙';
})();

// ============================================================
// AUTHENTICATION
// ============================================================
async function login() {
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    const errorDiv = document.getElementById('loginError');

    errorDiv.style.display = 'none';

    try {
        const response = await fetch(`${API_URL}/api/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (response.ok) {
            token = data.access_token;
            localStorage.setItem('token', token);
            document.getElementById('loginScreen').style.display = 'none';
            document.getElementById('appContainer').style.display = 'flex';
            await loadDocuments();
            showAlert('success', '✅ Login berhasil! Selamat datang, ' + username);
        } else {
            errorDiv.textContent = data.detail || 'Login gagal. Cek username/password!';
            errorDiv.style.display = 'block';
        }
    } catch (error) {
        errorDiv.textContent = 'Koneksi ke server gagal. Pastikan backend berjalan di ' + API_URL;
        errorDiv.style.display = 'block';
    }
}

function logout() {
    localStorage.removeItem('token');
    token = null;
    document.getElementById('appContainer').style.display = 'none';
    document.getElementById('loginScreen').style.display = 'flex';
    document.getElementById('loginUsername').value = 'admin';
    document.getElementById('loginPassword').value = 'admin123';
}

// ============================================================
// API CALLS WITH AUTH
// ============================================================
async function authenticatedFetch(url, options = {}) {
    if (!token) throw new Error('No token');
    return fetch(url, {
        ...options,
        headers: {
            ...options.headers,
            'Authorization': `Bearer ${token}`
        }
    });
}

async function loadDocuments() {
    try {
        const response = await authenticatedFetch(`${API_URL}/api/documents`);
        const data = await response.json();

        allDocuments = data.documents || [];
        renderDocList();

        if (allDocuments.length > 0) {
            selectDocument(allDocuments[0].id, allDocuments[0].name);
        } else {
            document.getElementById('activeDocTitle').textContent = 'Belum ada dokumen';
            document.getElementById('tipText').innerHTML = 'Upload PDF di atas untuk mulai bertanya!';
        }
    } catch (error) {
        console.error('Load documents error:', error);
        renderDocList([]);
    }
}

function renderDocList() {
    const container = document.getElementById('docList');
    if (!allDocuments.length) {
        container.innerHTML = '<div class="doc-item" style="justify-content:center;color:var(--ink-muted);">Belum ada dokumen</div>';
        return;
    }

    container.innerHTML = allDocuments.map(doc => `
      <div class="doc-item ${currentDocId === doc.id ? 'active' : ''}" onclick="selectDocument('${doc.id}', '${doc.name.replace(/'/g, "\\'")}')">
        <span class="doc-icon">📄</span>
        <div class="doc-info">
          <div class="doc-name">${doc.name}</div>
          <div class="doc-meta">${doc.pages || '?'} halaman</div>
        </div>
        <span class="badge badge-green">Siap</span>
      </div>
    `).join('');
}

function selectDocument(docId, docName) {
    currentDocId = docId;
    currentDocName = docName;
    document.getElementById('activeDocTitle').textContent = docName;
    document.getElementById('tipText').innerHTML = `PDF "${docName}" udah siap! Coba tanya: Apa isi dokumen ini?`;
    renderDocList();
    if (window.innerWidth <= 768) closeSidebar();
}

// ============================================================
// UPLOAD PDF
// ============================================================
const fileInput = document.getElementById('fileInput');
const uploadZone = document.getElementById('uploadZone');

uploadZone.addEventListener('click', () => fileInput.click());
uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.style.borderColor = 'var(--primary)'; });
uploadZone.addEventListener('dragleave', (e) => { uploadZone.style.borderColor = 'var(--primary-mid)'; });
uploadZone.addEventListener('drop', async (e) => {
    e.preventDefault();
    uploadZone.style.borderColor = 'var(--primary-mid)';
    const files = Array.from(e.dataTransfer.files).filter(f => f.type === 'application/pdf');
    if (files.length) await uploadFiles(files);
});

fileInput.addEventListener('change', async (e) => {
    if (e.target.files.length) await uploadFiles(Array.from(e.target.files));
    fileInput.value = '';
});

async function uploadFiles(files) {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));

    const progressDiv = document.getElementById('uploadProgress');
    const progressFill = document.getElementById('progressFill');
    const progressPercent = document.getElementById('progressPercent');
    const progressText = document.getElementById('progressText');

    progressDiv.style.display = 'block';
    progressFill.style.width = '0%';
    progressPercent.textContent = '0%';
    progressText.textContent = 'Mengupload PDF...';

    // Simulate progress (since real progress is hard)
    let fakeProgress = 0;
    const fakeInterval = setInterval(() => {
        fakeProgress += Math.random() * 15;
        if (fakeProgress > 90) fakeProgress = 90;
        progressFill.style.width = fakeProgress + '%';
        progressPercent.textContent = Math.round(fakeProgress) + '%';
    }, 300);

    try {
        const response = await authenticatedFetch(`${API_URL}/api/upload`, {
            method: 'POST',
            body: formData
        });

        clearInterval(fakeInterval);
        progressFill.style.width = '100%';
        progressPercent.textContent = '100%';
        progressText.textContent = 'Selesai!';

        if (response.ok) {
            await loadDocuments();
            if (allDocuments.length > 0) {
                selectDocument(allDocuments[0].id, allDocuments[0].name);
            }
            showAlert('success', `✅ ${files.length} PDF berhasil diproses!`);
            setTimeout(() => { progressDiv.style.display = 'none'; }, 1000);
        } else {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }
    } catch (error) {
        clearInterval(fakeInterval);
        progressDiv.style.display = 'none';
        showAlert('error', '❌ Gagal upload: ' + error.message);
    }
}

// ============================================================
// CHAT FUNCTIONS
// ============================================================
// Tambahkan/update fungsi-fungsi ini di script.js

// Update sendMessage untuk handle streaming dengan benar
async function sendMessage() {
    const input = document.getElementById('chatInput');
    const text = input.value.trim();
    if (!text) return;

    if (allDocuments.length === 0) {
        showAlert('warning', '⚠️ Upload PDF dulu ya!');
        return;
    }

    // Kalau belum pilih dokumen, pilih otomatis yang pertama
    if (!currentDocId && allDocuments.length > 0) {
        selectDocument(allDocuments[0].id, allDocuments[0].name);
    }

    const wb = document.getElementById('welcomeBanner');
    if (wb) wb.style.display = 'none';

    addMessage('user', text);
    input.value = '';
    input.style.height = '';
    input.rows = 1;

    showTyping();

    try {
        const response = await authenticatedFetch(`${API_URL}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: text,
                doc_id: currentDocId  // Optional, bisa null
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Chat request failed');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let assistantMessageElement = null;
        let fullAnswer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n').filter(l => l.trim());

            for (const line of lines) {
                try {
                    const data = JSON.parse(line);
                    if (!data.done) {
                        if (!assistantMessageElement) {
                            removeTyping();
                            assistantMessageElement = addMessage('ai', '', true);
                        }
                        fullAnswer += data.token;
                        // Update bubble content
                        const bubble = assistantMessageElement.querySelector('.message-bubble');
                        if (bubble) {
                            bubble.innerHTML = formatMessage(fullAnswer);
                        }
                        scrollToBottom();
                    } else if (data.done && data.sources) {
                        if (assistantMessageElement) {
                            addSourcesToMessage(assistantMessageElement, data.sources);
                        }
                    }
                } catch (e) {
                    console.error('Parse error:', e);
                }
            }
        }

        if (!assistantMessageElement) {
            removeTyping();
            addMessage('ai', 'Maaf, terjadi error. Silakan coba lagi.');
        }
    } catch (error) {
        removeTyping();
        addMessage('ai', '❌ Error: ' + error.message);
    }
}

// Fix uploadFiles - backend expects 'files' as field name
async function uploadFiles(files) {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));  // ← 'files' not 'file'

    const progressDiv = document.getElementById('uploadProgress');
    const progressFill = document.getElementById('progressFill');
    const progressPercent = document.getElementById('progressPercent');
    const progressText = document.getElementById('progressText');

    progressDiv.style.display = 'block';
    progressFill.style.width = '0%';
    progressPercent.textContent = '0%';
    progressText.textContent = 'Mengupload PDF...';

    // Simulate progress
    let fakeProgress = 0;
    const fakeInterval = setInterval(() => {
        fakeProgress += Math.random() * 15;
        if (fakeProgress > 90) fakeProgress = 90;
        progressFill.style.width = fakeProgress + '%';
        progressPercent.textContent = Math.round(fakeProgress) + '%';
    }, 300);

    try {
        const response = await authenticatedFetch(`${API_URL}/api/upload`, {
            method: 'POST',
            body: formData
        });

        clearInterval(fakeInterval);

        if (response.ok) {
            progressFill.style.width = '100%';
            progressPercent.textContent = '100%';
            progressText.textContent = 'Selesai!';

            const data = await response.json();
            await loadDocuments();
            showAlert('success', `✅ ${data.message}`);

            setTimeout(() => {
                progressDiv.style.display = 'none';
            }, 1500);
        } else {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }
    } catch (error) {
        clearInterval(fakeInterval);
        progressDiv.style.display = 'none';
        showAlert('error', '❌ Gagal upload: ' + error.message);
    }
}

function addMessage(role, text, returnElement = false) {
    const chatArea = document.getElementById('chatArea');
    const msg = document.createElement('div');
    msg.className = 'chat-message ' + role;

    const avatar = role === 'user' ? '👤' : '🤖';
    const formatted = formatMessage(text);

    msg.innerHTML = `
      <div class="message-avatar ${role}">${avatar}</div>
      <div class="message-bubble ${role}">${formatted}</div>
    `;

    chatArea.appendChild(msg);
    scrollToBottom();

    if (returnElement) return msg;
}

function formatMessage(text) {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
}

function addSourcesToMessage(messageElement, sources) {
    const bubble = messageElement.querySelector('.message-bubble');
    let sourcesHtml = '<div class="source-citations">';
    sources.forEach(src => {
        sourcesHtml += `<span class="source-chip" onclick="showSourcePreview('${src.source.replace(/'/g, "\\'")}', ${src.page})">📄 ${src.source} (Hal ${src.page})</span>`;
    });
    sourcesHtml += '</div>';
    bubble.insertAdjacentHTML('beforeend', sourcesHtml);
}

function showSourcePreview(filename, page) {
    showAlert('info', `📖 Sumber: ${filename}, halaman ${page}`);
}

let typingEl = null;

function showTyping() {
    const chatArea = document.getElementById('chatArea');
    typingEl = document.createElement('div');
    typingEl.className = 'chat-message ai';
    typingEl.id = 'typingIndicator';
    typingEl.innerHTML = `
      <div class="message-avatar ai">🤖</div>
      <div class="message-bubble ai">
        <div class="typing-indicator"><span></span><span></span><span></span></div>
      </div>
    `;
    chatArea.appendChild(typingEl);
    scrollToBottom();
}

function removeTyping() {
    if (typingEl) { typingEl.remove(); typingEl = null; }
}

function scrollToBottom() {
    const chatArea = document.getElementById('chatArea');
    chatArea.scrollTop = chatArea.scrollHeight;
}

function clearChat() {
    if (!confirm('Yakin mau hapus semua chat?')) return;
    document.getElementById('chatArea').innerHTML = `
      <div class="welcome-banner" id="welcomeBanner">
        <span class="welcome-icon">🤖</span>
        <h1>Chat dibersihkan!</h1>
        <p class="welcome-sub">Upload PDF lo, terus tanya apa aja tentang isinya.</p>
      </div>
    `;
}

function sendQuickQ(text) {
    document.getElementById('chatInput').value = text;
    sendMessage();
}

function handleEnter(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function showAlert(type, message) {
    const chatArea = document.getElementById('chatArea');
    const el = document.createElement('div');
    el.className = 'alert alert-' + type;
    el.style.cssText = 'max-width:480px; align-self:center; margin-bottom:16px;';
    el.innerHTML = `<span class="alert-icon">${type === 'success' ? '✅' : type === 'warning' ? '⚠️' : 'ℹ️'}</span><span>${message}</span>`;
    chatArea.appendChild(el);
    scrollToBottom();
    setTimeout(() => {
        el.style.transition = 'opacity 0.5s ease';
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 500);
    }, 4000);
}

// Auto-resize textarea
const textarea = document.getElementById('chatInput');
if (textarea) {
    textarea.addEventListener('input', function () {
        this.style.height = '';
        this.style.height = Math.min(this.scrollHeight, 100) + 'px';
    });
}

// Sidebar functions
function openSidebar() {
    document.getElementById('sidebar').classList.add('open');
    document.getElementById('sidebarOverlay').classList.add('show');
    document.body.style.overflow = 'hidden';
}

function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebarOverlay').classList.remove('show');
    document.body.style.overflow = '';
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeSidebar(); });