/*
 * vcpkg-harbor dashboard behaviour.
 *
 * Progressive enhancement only: every page works without this file. It adds
 * locale-aware numbers and timestamps, copy-to-clipboard buttons and a visible
 * error state for failed HTMX requests.
 */
(function () {
    'use strict';

    var SELECTOR_NUMBER = '[data-number]';
    var SELECTOR_DATETIME = 'time[data-datetime]';
    var SELECTOR_COPY = '[data-copy]';
    var SELECTOR_COPY_LABEL = '[data-copy-label]';
    var ERROR_CONTAINER_ID = 'app-error';
    var COPY_RESET_MS = 2000;
    var ERROR_HIDE_MS = 8000;
    var LABEL_COPY = 'Copy';
    var LABEL_COPIED = 'Copied';
    var LABEL_COPY_FAILED = 'Press Ctrl+C';
    var LABEL_COPY_ERROR = 'Copy failed';
    var MESSAGE_REQUEST_FAILED = 'Could not refresh the latest data. Check that the server is reachable.';
    var ERROR_CLASSES = [
        'mb-6', 'flex', 'items-start', 'gap-3', 'rounded-xl', 'bg-rose-50', 'px-4', 'py-3',
        'text-sm', 'text-rose-800', 'ring-1', 'ring-rose-200'
    ];
    var DEBUG = new URLSearchParams(window.location.search).has('debug');

    function debug() {
        if (DEBUG && window.console) {
            console.debug.apply(console, ['[vcpkg-harbor]'].concat([].slice.call(arguments)));
        }
    }

    /* Re-format server-rendered numbers using the visitor's locale. */
    function localiseNumbers(root) {
        if (typeof Intl === 'undefined' || !Intl.NumberFormat) {
            return;
        }
        root.querySelectorAll(SELECTOR_NUMBER).forEach(function (el) {
            var raw = Number(el.getAttribute('data-number'));
            if (!isFinite(raw)) {
                return;
            }
            var decimals = Number.isInteger(raw) ? 0 : 2;
            el.textContent = new Intl.NumberFormat(undefined, {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals
            }).format(raw);
        });
    }

    /* Re-format timestamps using the visitor's locale and time zone. */
    function localiseDates(root) {
        if (typeof Intl === 'undefined' || !Intl.DateTimeFormat) {
            return;
        }
        root.querySelectorAll(SELECTOR_DATETIME).forEach(function (el) {
            var parsed = new Date(el.getAttribute('datetime'));
            if (isNaN(parsed.getTime())) {
                return;
            }
            el.textContent = new Intl.DateTimeFormat(undefined, {
                dateStyle: 'medium',
                timeStyle: 'short'
            }).format(parsed);
            el.title = parsed.toString();
        });
    }

    function setCopyLabel(button, text) {
        var label = button.querySelector(SELECTOR_COPY_LABEL);
        (label || button).textContent = text;
    }

    /* Clipboard write with a fallback for pages served over plain HTTP. */
    function writeToClipboard(text) {
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(text);
        }
        return new Promise(function (resolve, reject) {
            var helper = document.createElement('textarea');
            helper.value = text;
            helper.setAttribute('readonly', '');
            helper.style.position = 'fixed';
            helper.style.opacity = '0';
            document.body.appendChild(helper);
            helper.select();
            var copied = false;
            try {
                copied = document.execCommand('copy');
            } catch (error) {
                copied = false;
            }
            document.body.removeChild(helper);
            if (copied) {
                resolve();
            } else {
                reject(new Error('Clipboard unavailable'));
            }
        });
    }

    /* Last resort: select the snippet so the visitor can copy it by hand. */
    function selectSnippet(button) {
        var snippet = button.parentElement && button.parentElement.querySelector('code');
        if (!snippet || !window.getSelection) {
            return false;
        }
        var range = document.createRange();
        range.selectNodeContents(snippet);
        var selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        return true;
    }

    function onCopyClick(event) {
        var button = event.target.closest(SELECTOR_COPY);
        if (!button) {
            return;
        }
        writeToClipboard(button.getAttribute('data-copy')).then(function () {
            debug('copied to clipboard');
            setCopyLabel(button, LABEL_COPIED);
        }, function (error) {
            debug('clipboard failed', error);
            setCopyLabel(button, selectSnippet(button) ? LABEL_COPY_FAILED : LABEL_COPY_ERROR);
        }).then(function () {
            window.setTimeout(function () {
                setCopyLabel(button, LABEL_COPY);
            }, COPY_RESET_MS);
        });
    }

    function showError(message) {
        var container = document.getElementById(ERROR_CONTAINER_ID);
        if (!container) {
            return;
        }
        container.textContent = message;
        container.classList.remove('hidden');
        ERROR_CLASSES.forEach(function (name) {
            container.classList.add(name);
        });
        window.setTimeout(function () {
            container.classList.add('hidden');
        }, ERROR_HIDE_MS);
    }

    function enhance(root) {
        localiseNumbers(root);
        localiseDates(root);
    }

    document.addEventListener('DOMContentLoaded', function () {
        enhance(document);
        document.addEventListener('click', onCopyClick);
        debug('dashboard ready');
    });

    /* Content swapped in by HTMX needs the same treatment. */
    document.addEventListener('htmx:afterSwap', function (event) {
        enhance(event.target);
    });

    document.addEventListener('htmx:responseError', function (event) {
        debug('request failed', event.detail);
        showError(MESSAGE_REQUEST_FAILED);
    });

    document.addEventListener('htmx:sendError', function (event) {
        debug('network error', event.detail);
        showError(MESSAGE_REQUEST_FAILED);
    });
})();
