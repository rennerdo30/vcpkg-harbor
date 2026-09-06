# Cache consistency requirements

- Package identities cannot address the internal `_harbor` storage namespace.
- Cache writes require authentication when authentication is enabled, including
  paths beginning with dashboard names.
- Cross-tag deduplication requires matching SHA-256 content digests. Conflicting
  bytes return HTTP 409 without creating a tag reference.
- Missing objects can be re-uploaded and stale references can be deleted.
- Tag mutations, including retention and object deletion, run serially in one
  writer process. Tagged deployments support one worker and one replica.
- Tag validation errors return HTTP 400 before storage operations.

# Proxy routing requirements

- `VCPKG_PROXY_ROOT_PATH` is applied by the application. The CLI must not also
  pass it as uvicorn's `root_path` argument.
- Both prefix-preserving and prefix-stripping proxies must serve dashboard
  pages, bundled assets, and cache HEAD/GET/PUT/DELETE requests.
- Regression coverage must launch the real CLI so server path transformations
  are included in routing tests.
