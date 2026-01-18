// vcpkg-harbor dashboard JavaScript

// HTMX configuration
document.body.addEventListener('htmx:configRequest', function(evt) {
    // Add any custom headers here
});

// Handle HTMX errors
document.body.addEventListener('htmx:responseError', function(evt) {
    console.error('HTMX request failed:', evt.detail);
});

// Auto-refresh indicator
document.body.addEventListener('htmx:beforeRequest', function(evt) {
    const indicator = evt.detail.elt.querySelector('.htmx-indicator');
    if (indicator) {
        indicator.style.display = 'inline';
    }
});

document.body.addEventListener('htmx:afterRequest', function(evt) {
    const indicator = evt.detail.elt.querySelector('.htmx-indicator');
    if (indicator) {
        indicator.style.display = 'none';
    }
});

// Format bytes to human readable
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        // Show success feedback
        console.log('Copied to clipboard');
    }, function(err) {
        console.error('Failed to copy:', err);
    });
}
