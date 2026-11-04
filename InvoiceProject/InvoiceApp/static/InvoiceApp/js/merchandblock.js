/**
 * MerchandBlock — Unified Theme & UI Controller
 * Default theme: 'light' (Clean B2B Slate + Deep Navy Sidebar)
 * Supports seamless switching between 'light' and 'dark' across all pages.
 */
(function () {
    const STORAGE_KEY = 'theme';
    const savedTheme = localStorage.getItem(STORAGE_KEY) || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);

    function getThemeIconSvg(theme) {
        if (theme === 'dark') {
            // Sun icon to switch to light
            return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>';
        }
        // Moon icon to switch to dark
        return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>';
    }

    window.syncMerchandBlockThemeButtons = function () {
        const current = document.documentElement.getAttribute('data-theme') || 'light';
        const buttons = document.querySelectorAll('#themeToggleBtn, .js-theme-toggle');
        buttons.forEach(function (btn) {
            btn.innerHTML = getThemeIconSvg(current);
            btn.setAttribute('title', current === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre');
        });
    };

    window.toggleTheme = function () {
        const html = document.documentElement;
        const current = html.getAttribute('data-theme') || 'light';
        const next = current === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        localStorage.setItem(STORAGE_KEY, next);
        window.syncMerchandBlockThemeButtons();
        if (typeof window.onMerchandBlockThemeChange === 'function') {
            window.onMerchandBlockThemeChange(next);
        }
    };

    document.addEventListener('DOMContentLoaded', function () {
        // Ensure a theme toggle button exists in .topbar-actions if not already present
        const topbarActions = document.querySelector('.topbar .topbar-actions');
        if (topbarActions && !document.getElementById('themeToggleBtn')) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.id = 'themeToggleBtn';
            btn.className = 'theme-toggle-btn js-theme-toggle';
            btn.onclick = window.toggleTheme;
            topbarActions.insertBefore(btn, topbarActions.firstChild);
        }
        window.syncMerchandBlockThemeButtons();
    });
})();
