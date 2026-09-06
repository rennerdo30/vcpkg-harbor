"""Exercise proxy routing through the shipped CLI and a real HTTP server."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


@pytest.mark.parametrize("forwarded_prefix", ["", "/harbor"])
def test_cli_serves_both_proxy_layouts(tmp_path, forwarded_prefix):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
        "VCPKG_SERVER_HOST": "127.0.0.1",
        "VCPKG_SERVER_PORT": str(port),
        "VCPKG_SERVER_WORKERS": "1",
        "VCPKG_SERVER_RELOAD": "false",
        "VCPKG_PROXY_ROOT_PATH": "/harbor",
        "VCPKG_STORAGE_TYPE": "filesystem",
        "VCPKG_STORAGE_PATH": str(tmp_path / "cache"),
        "VCPKG_AUTH_ENABLED": "false",
        "VCPKG_LOG_FILE": str(tmp_path / "server.log"),
    }
    with (tmp_path / "process.log").open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "vcpkg_harbor"], cwd=tmp_path, env=env,
            stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2) as client:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        client.get(f"{forwarded_prefix}/health")
                        break
                    except httpx.ConnectError:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            log.seek(0)
                            pytest.fail(log.read())
                        time.sleep(0.05)
                for path in ["/health", "/packages", "/static/logo.svg"]:
                    response = client.get(f"{forwarded_prefix}{path}")
                    assert response.status_code == 200, response.text
                assert '/harbor/static/' in client.get(f"{forwarded_prefix}/").text
                package = f"{forwarded_prefix}/zlib/1.3.1/abc123/x64-linux"
                assert client.put(package, content=b"package").status_code == 200
                assert client.head(package).status_code == 200
                assert client.get(package).content == b"package"
                assert client.delete(package).status_code == 200
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
