/**
 * Assistant IA flottant — InvoiceApp
 * Injecte un bouton flottant + un panneau de chat sur la page courante.
 * La conversation (historique brut envoyé à Gemini + bulles affichées)
 * est conservée dans sessionStorage : elle survit à la navigation entre
 * les pages de l'app tant que l'onglet reste ouvert.
 */
(function () {
    'use strict';

    if (window.__aiAssistantLoaded) return;
    window.__aiAssistantLoaded = true;

    const API_CHAT_URL = '/api/ai-chat/';
    const API_INIT_URL = '/api/ai-chat/init/';
    const STORAGE_KEY = 'ia_invoiceapp_conversation_v1';

    // ─────────────────────────────────────────────────────────
    // Styles (namespacés, thème sombre fixe indépendant de la page)
    // ─────────────────────────────────────────────────────────
    const css = `
    #ia-fab {
        position: fixed;
        right: 22px;
        bottom: 22px;
        width: 58px;
        height: 58px;
        border-radius: 50%;
        background: linear-gradient(135deg, #6366F1, #818CF8);
        box-shadow: 0 6px 20px rgba(99,102,241,0.45);
        border: none;
        cursor: pointer;
        z-index: 999998;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    #ia-fab:hover { transform: scale(1.06); box-shadow: 0 8px 26px rgba(99,102,241,0.55); }
    #ia-fab svg { width: 26px; height: 26px; }
    #ia-fab-badge {
        position: absolute;
        top: -2px;
        right: -2px;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: #10B981;
        border: 2px solid #0F1629;
        display: none;
    }

    #ia-panel {
        position: fixed;
        right: 22px;
        bottom: 92px;
        width: 380px;
        max-width: calc(100vw - 32px);
        height: min(640px, calc(100vh - 130px));
        background: #131B32;
        border: 1px solid rgba(99,102,241,0.25);
        border-radius: 18px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.55);
        display: none;
        flex-direction: column;
        overflow: hidden;
        z-index: 999999;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    #ia-panel.ia-open { display: flex; }

    #ia-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 14px 16px;
        background: linear-gradient(135deg, #1A2238, #1F2A44);
        border-bottom: 1px solid rgba(99,102,241,0.2);
        flex-shrink: 0;
    }
    #ia-header-title { display: flex; align-items: center; gap: 8px; }
    #ia-header-title .ia-dot {
        width: 8px; height: 8px; border-radius: 50%; background: #10B981;
        box-shadow: 0 0 6px #10B981;
    }
    #ia-header-title span { color: #E2E8F0; font-weight: 600; font-size: 14.5px; }
    #ia-header-sub { color: #64748B; font-size: 11px; margin-top: 1px; }
    #ia-header-actions { display: flex; gap: 6px; }
    #ia-header-actions button {
        background: transparent;
        border: none;
        color: #94A3B8;
        cursor: pointer;
        width: 28px; height: 28px;
        border-radius: 8px;
        display: flex; align-items: center; justify-content: center;
        transition: background 0.15s, color 0.15s;
    }
    #ia-header-actions button:hover { background: rgba(255,255,255,0.08); color: #E2E8F0; }
    #ia-header-actions svg { width: 16px; height: 16px; }

    #ia-messages {
        flex: 1;
        overflow-y: auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
    }
    #ia-messages::-webkit-scrollbar { width: 6px; }
    #ia-messages::-webkit-scrollbar-thumb { background: rgba(99,102,241,0.3); border-radius: 3px; }

    .ia-msg { max-width: 88%; font-size: 13.5px; line-height: 1.5; word-wrap: break-word; }
    .ia-msg.ia-user { align-self: flex-end; }
    .ia-msg.ia-assistant { align-self: flex-start; }
    .ia-bubble {
        padding: 10px 13px;
        border-radius: 14px;
        white-space: normal;
    }
    .ia-user .ia-bubble {
        background: linear-gradient(135deg, #6366F1, #4F46E5);
        color: #fff;
        border-bottom-right-radius: 4px;
    }
    .ia-assistant .ia-bubble {
        background: #1A2238;
        color: #E2E8F0;
        border: 1px solid rgba(255,255,255,0.06);
        border-bottom-left-radius: 4px;
    }
    .ia-bubble ul { margin: 6px 0; padding-left: 18px; }
    .ia-bubble li { margin: 3px 0; }
    .ia-bubble strong { color: #A5B4FC; }
    .ia-assistant .ia-bubble strong { color: #818CF8; }
    .ia-user .ia-bubble strong { color: #E0E7FF; }

    .ia-welcome {
        text-align: center;
        color: #64748B;
        font-size: 12.5px;
        padding: 24px 12px 8px;
        line-height: 1.6;
    }
    .ia-welcome b { color: #94A3B8; }

    .ia-typing { display: flex; gap: 4px; align-items: center; padding: 4px 2px; }
    .ia-typing span {
        width: 6px; height: 6px; border-radius: 50%; background: #6366F1;
        animation: ia-bounce 1.2s infinite ease-in-out;
    }
    .ia-typing span:nth-child(2) { animation-delay: 0.15s; }
    .ia-typing span:nth-child(3) { animation-delay: 0.3s; }
    @keyframes ia-bounce { 0%, 60%, 100% { opacity: 0.35; transform: translateY(0); } 30% { opacity: 1; transform: translateY(-3px); } }

    #ia-inputbar {
        display: flex;
        align-items: flex-end;
        gap: 8px;
        padding: 12px;
        border-top: 1px solid rgba(99,102,241,0.15);
        background: #0F1629;
        flex-shrink: 0;
    }
    #ia-input {
        flex: 1;
        resize: none;
        background: #1A2238;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        color: #E2E8F0;
        padding: 9px 12px;
        font-size: 13.5px;
        font-family: inherit;
        max-height: 100px;
        outline: none;
    }
    #ia-input:focus { border-color: rgba(99,102,241,0.5); }
    #ia-input::placeholder { color: #64748B; }
    #ia-send {
        background: #6366F1;
        border: none;
        width: 38px; height: 38px;
        border-radius: 11px;
        cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        flex-shrink: 0;
        transition: background 0.15s, opacity 0.15s;
    }
    #ia-send:hover { background: #4F46E5; }
    #ia-send:disabled { opacity: 0.4; cursor: not-allowed; }
    #ia-send svg { width: 16px; height: 16px; }

    @media (max-width: 480px) {
        #ia-panel {
            right: 10px;
            left: 10px;
            width: auto;
            bottom: 82px;
            height: min(70vh, calc(100vh - 110px));
        }
        #ia-fab { right: 16px; bottom: 16px; }
    }
    `;

    const styleTag = document.createElement('style');
    styleTag.id = 'ia-assistant-styles';
    styleTag.textContent = css;
    document.head.appendChild(styleTag);

    // ─────────────────────────────────────────────────────────
    // Markup
    // ─────────────────────────────────────────────────────────
    const fab = document.createElement('button');
    fab.id = 'ia-fab';
    fab.type = 'button';
    fab.setAttribute('aria-label', 'Ouvrir l\'assistant IA');
    fab.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 3C7.03 3 3 6.58 3 11c0 2.39 1.19 4.53 3.08 6.02-.11.98-.5 2.3-1.47 3.6a.5.5 0 00.5.78c2.02-.4 3.62-1.28 4.6-1.95.99.35 2.08.55 3.29.55 4.97 0 9-3.58 9-8s-4.03-8-9-8z" fill="white"/>
        </svg>
        <span id="ia-fab-badge"></span>
    `;
    document.body.appendChild(fab);

    const panel = document.createElement('div');
    panel.id = 'ia-panel';
    panel.innerHTML = `
        <div id="ia-header">
            <div>
                <div id="ia-header-title"><span class="ia-dot"></span><span>Assistant IA</span></div>
                <div id="ia-header-sub">Ventes · Finances · Stock</div>
            </div>
            <div id="ia-header-actions">
                <button type="button" id="ia-clear" title="Effacer la conversation">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0-1 14a2 2 0 01-2 2H7a2 2 0 01-2-2L4 6"/></svg>
                </button>
                <button type="button" id="ia-close" title="Fermer">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
                </button>
            </div>
        </div>
        <div id="ia-messages"></div>
        <div id="ia-inputbar">
            <textarea id="ia-input" rows="1" placeholder="Pose une question sur tes ventes, finances, stock…"></textarea>
            <button type="button" id="ia-send" title="Envoyer">
                <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
            </button>
        </div>
    `;
    document.body.appendChild(panel);

    const messagesEl = panel.querySelector('#ia-messages');
    const inputEl = panel.querySelector('#ia-input');
    const sendBtn = panel.querySelector('#ia-send');
    const closeBtn = panel.querySelector('#ia-close');
    const clearBtn = panel.querySelector('#ia-clear');

    // ─────────────────────────────────────────────────────────
    // État persistant (sessionStorage → survit à la navigation)
    // ─────────────────────────────────────────────────────────
    function loadState() {
        try {
            const raw = sessionStorage.getItem(STORAGE_KEY);
            if (raw) return JSON.parse(raw);
        } catch (e) { /* stockage indisponible ou corrompu */ }
        return { contents: [], messages: [] };
    }
    function saveState() {
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch (e) { /* quota dépassé : on continue sans persister */ }
    }
    let state = loadState();

    function getCookie(name) {
        const match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return match ? decodeURIComponent(match.pop()) : '';
    }

    // Garantit la présence du cookie csrftoken avant le premier envoi.
    fetch(API_INIT_URL, { credentials: 'same-origin' }).catch(function () {});

    // ─────────────────────────────────────────────────────────
    // Rendu
    // ─────────────────────────────────────────────────────────
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function formatText(text) {
        let safe = escapeHtml(text);
        safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // Regroupe les lignes commençant par "- " ou "* " en <ul><li>
        const lines = safe.split('\n');
        let html = '';
        let inList = false;
        lines.forEach(function (line) {
            const trimmed = line.trim();
            if (/^[-*]\s+/.test(trimmed)) {
                if (!inList) { html += '<ul>'; inList = true; }
                html += '<li>' + trimmed.replace(/^[-*]\s+/, '') + '</li>';
            } else {
                if (inList) { html += '</ul>'; inList = false; }
                html += (line === '' ? '<br>' : line + '<br>');
            }
        });
        if (inList) html += '</ul>';
        return html;
    }

    function renderWelcomeIfEmpty() {
        if (state.messages.length > 0) return;
        const welcome = document.createElement('div');
        welcome.className = 'ia-welcome';
        welcome.innerHTML = "👋 Bonjour ! Je suis ton assistant IA.<br>Demande-moi par exemple : <br><b>« Quel est l'état financier ce mois-ci ? »</b><br><b>« Quels produits sont en rupture ? »</b>";
        messagesEl.appendChild(welcome);
    }

    function appendBubble(role, text) {
        const wrap = document.createElement('div');
        wrap.className = 'ia-msg ' + (role === 'user' ? 'ia-user' : 'ia-assistant');
        const bubble = document.createElement('div');
        bubble.className = 'ia-bubble';
        bubble.innerHTML = formatText(text);
        wrap.appendChild(bubble);
        messagesEl.appendChild(wrap);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return wrap;
    }

    function renderAll() {
        messagesEl.innerHTML = '';
        renderWelcomeIfEmpty();
        state.messages.forEach(function (m) { appendBubble(m.role, m.text); });
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function showTyping() {
        const wrap = document.createElement('div');
        wrap.className = 'ia-msg ia-assistant';
        wrap.id = 'ia-typing-indicator';
        wrap.innerHTML = '<div class="ia-bubble"><div class="ia-typing"><span></span><span></span><span></span></div></div>';
        messagesEl.appendChild(wrap);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }
    function hideTyping() {
        const el = document.getElementById('ia-typing-indicator');
        if (el) el.remove();
    }

    // ─────────────────────────────────────────────────────────
    // Ouverture / fermeture
    // ─────────────────────────────────────────────────────────
    function openPanel() {
        panel.classList.add('ia-open');
        renderAll();
        inputEl.focus();
    }
    function closePanel() {
        panel.classList.remove('ia-open');
    }
    fab.addEventListener('click', function () {
        if (panel.classList.contains('ia-open')) closePanel();
        else openPanel();
    });
    closeBtn.addEventListener('click', closePanel);

    clearBtn.addEventListener('click', function () {
        state = { contents: [], messages: [] };
        saveState();
        renderAll();
    });

    // ─────────────────────────────────────────────────────────
    // Envoi de message
    // ─────────────────────────────────────────────────────────
    let sending = false;

    async function sendMessage() {
        const text = inputEl.value.trim();
        if (!text || sending) return;

        sending = true;
        sendBtn.disabled = true;
        inputEl.value = '';
        inputEl.style.height = 'auto';

        state.messages.push({ role: 'user', text: text });
        saveState();
        // Retire le message de bienvenue au premier envoi et affiche la bulle utilisateur
        const welcomeEl = messagesEl.querySelector('.ia-welcome');
        if (welcomeEl) welcomeEl.remove();
        appendBubble('user', text);
        showTyping();

        try {
            const resp = await fetch(API_CHAT_URL, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify({ message: text, contents: state.contents }),
            });

            hideTyping();

            if (!resp.ok) {
                const msg = "Une erreur est survenue. Réessaie dans un instant.";
                state.messages.push({ role: 'assistant', text: msg });
                appendBubble('assistant', msg);
                saveState();
                return;
            }

            const data = await resp.json();
            const reply = data.reply || "Je n'ai pas pu générer de réponse.";
            state.contents = data.contents || state.contents;
            state.messages.push({ role: 'assistant', text: reply });
            appendBubble('assistant', reply);
            saveState();
        } catch (err) {
            hideTyping();
            const msg = "Connexion impossible. Vérifie ta connexion internet et réessaie.";
            state.messages.push({ role: 'assistant', text: msg });
            appendBubble('assistant', msg);
            saveState();
        } finally {
            sending = false;
            sendBtn.disabled = false;
        }
    }

    sendBtn.addEventListener('click', sendMessage);
    inputEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    inputEl.addEventListener('input', function () {
        inputEl.style.height = 'auto';
        inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + 'px';
    });
})();
