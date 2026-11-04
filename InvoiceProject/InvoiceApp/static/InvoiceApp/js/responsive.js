/**
 * MerchandBlock — Responsive Navigation Script
 */
document.addEventListener('DOMContentLoaded', function () {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;

    const menuSVG = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>';
    const closeSVG = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';

    const menuBtn = document.createElement('button');
    menuBtn.className = 'mobile-menu-btn';
    menuBtn.type = 'button';
    menuBtn.innerHTML = menuSVG;
    menuBtn.setAttribute('aria-label', 'Ouvrir le menu');
    document.body.appendChild(menuBtn);

    const overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    document.body.appendChild(overlay);

    function toggleMenu() {
        const isOpen = sidebar.classList.toggle('open');
        overlay.classList.toggle('active', isOpen);
        menuBtn.innerHTML = isOpen ? closeSVG : menuSVG;
        document.body.style.overflow = isOpen ? 'hidden' : '';
    }

    menuBtn.addEventListener('click', toggleMenu);
    overlay.addEventListener('click', toggleMenu);

    const navLinks = sidebar.querySelectorAll('.nav-item, .logout-btn');
    navLinks.forEach(function (link) {
        link.addEventListener('click', function () {
            if (window.innerWidth <= 992 && sidebar.classList.contains('open')) {
                toggleMenu();
            }
        });
    });

    window.addEventListener('resize', function () {
        if (window.innerWidth > 992 && sidebar.classList.contains('open')) {
            sidebar.classList.remove('open');
            overlay.classList.remove('active');
            menuBtn.innerHTML = menuSVG;
            document.body.style.overflow = '';
        }
    });
});
