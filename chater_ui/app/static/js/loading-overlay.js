/**
 * Loading overlay for long-running API calls (e.g. POST /modify_food_manual).
 * Use: loadingOverlay.show() before fetch, loadingOverlay.hide() in finally().
 * Page must include: <link rel="stylesheet" href=".../loading-overlay.css"> and this script.
 */
(function () {
    var overlay = null;
    var textEl = null;

    function getOrCreateOverlay() {
        if (overlay) return overlay;
        overlay = document.createElement('div');
        overlay.className = 'loading-overlay';
        overlay.setAttribute('aria-hidden', 'true');
        overlay.innerHTML =
            '<div class="loading-overlay__box">' +
            '  <div class="loading-overlay__spinner"></div>' +
            '  <p class="loading-overlay__text" data-loading-text></p>' +
            '</div>';
        textEl = overlay.querySelector('[data-loading-text]');
        document.body.appendChild(overlay);
        return overlay;
    }

    function show(message) {
        var el = getOrCreateOverlay();
        if (textEl) {
            textEl.textContent = message || 'Обробка запиту…';
        }
        el.classList.add('is-visible');
        el.setAttribute('aria-hidden', 'false');
    }

    function hide() {
        if (overlay) {
            overlay.classList.remove('is-visible');
            overlay.setAttribute('aria-hidden', 'true');
        }
    }

    window.loadingOverlay = {
        show: show,
        hide: hide
    };
})();
