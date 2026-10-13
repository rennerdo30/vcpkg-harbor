/*
 * vcpkg-harbor colour theme.
 *
 * Loaded synchronously in <head> so the stored choice is applied before the
 * first paint. Three modes: "system" (follow prefers-color-scheme, the
 * default), "light" and "dark". The choice lives in localStorage and is
 * reflected as data-theme on <html>, which static/css/style.css keys off.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'vcpkg-harbor-theme';
    var MODES = ['system', 'light', 'dark'];
    var DEFAULT_MODE = 'system';
    var LABELS = {
        system: 'Colour theme: match system',
        light: 'Colour theme: light',
        dark: 'Colour theme: dark'
    };
    var TOGGLE_SELECTOR = '[data-theme-toggle]';
    var root = document.documentElement;

    function readMode() {
        try {
            var stored = window.localStorage.getItem(STORAGE_KEY);
            return MODES.indexOf(stored) === -1 ? DEFAULT_MODE : stored;
        } catch (error) {
            // Storage can be blocked (private mode, sandboxed iframe).
            return DEFAULT_MODE;
        }
    }

    function saveMode(mode) {
        try {
            if (mode === DEFAULT_MODE) {
                window.localStorage.removeItem(STORAGE_KEY);
            } else {
                window.localStorage.setItem(STORAGE_KEY, mode);
            }
        } catch (error) {
            // The choice then lasts for this page view only.
        }
    }

    function applyMode(mode) {
        if (mode === DEFAULT_MODE) {
            root.removeAttribute('data-theme');
        } else {
            root.setAttribute('data-theme', mode);
        }
    }

    function syncToggle(button, mode) {
        button.setAttribute('data-mode', mode);
        button.setAttribute('aria-label', LABELS[mode]);
        button.title = LABELS[mode];
    }

    applyMode(readMode());

    document.addEventListener('DOMContentLoaded', function () {
        var button = document.querySelector(TOGGLE_SELECTOR);
        if (!button) {
            return;
        }
        syncToggle(button, readMode());
        button.hidden = false;
        button.addEventListener('click', function () {
            var current = button.getAttribute('data-mode') || DEFAULT_MODE;
            var next = MODES[(MODES.indexOf(current) + 1) % MODES.length];
            applyMode(next);
            saveMode(next);
            syncToggle(button, next);
        });
    });
})();
