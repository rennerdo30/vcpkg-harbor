# Web Dashboard

vcpkg-harbor includes a built-in web dashboard for monitoring and browsing the cache.

## Accessing the Dashboard

Open your browser to `http://localhost:15151/` (or your configured host/port).

## Dashboard Pages

### Home

The main dashboard shows:

- **Cache Statistics**: Total packages, storage used, hit rate
- **Request Metrics**: Total requests, response times
- **Recent Packages**: Recently cached packages
- **Quick Start Guide**: How to configure vcpkg

### Packages

Browse all cached packages:

- Search by package name
- View package versions
- See package sizes
- Navigate to package details

### Package Details

For each package:

- All cached versions
- SHA hashes
- File sizes
- Cache timestamps

### Statistics

Detailed statistics including:

- Cache hit/miss rates
- Upload/download counts
- Request breakdown (HEAD/GET/PUT)
- Largest packages
- Storage backend info

## Configuration

### Enable/Disable Dashboard

```bash
VCPKG_DASHBOARD_ENABLED=true  # or false
```

### Change Base Path

```bash
VCPKG_DASHBOARD_PATH=/dashboard
```

## HTMX Live Updates

The dashboard uses HTMX for automatic updates:

- Statistics refresh every 30 seconds
- No page reloads required
- Minimal bandwidth usage

## Customization

The dashboard uses Tailwind CSS loaded from CDN. Templates are in:

```
src/vcpkg_harbor/dashboard/templates/
├── base.html
├── index.html
├── packages.html
├── package_detail.html
├── stats.html
└── partials/
    ├── stats_summary.html
    └── recent_packages.html
```
