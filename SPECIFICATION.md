# Proxy routing requirements

- `VCPKG_PROXY_ROOT_PATH` is applied by the application. The CLI must not also
  pass it as uvicorn's `root_path` argument.
- Both prefix-preserving and prefix-stripping proxies must serve dashboard
  pages, bundled assets, and cache HEAD/GET/PUT/DELETE requests.
- Regression coverage must launch the real CLI so server path transformations
  are included in routing tests.
