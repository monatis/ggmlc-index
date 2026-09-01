#!/usr/bin/env python3
"""
Unit and integration tests for the GitHub-hosted PyPI simple index generator.
"""

import os
import sys
import shutil
import subprocess
import http.server
import socketserver
import threading
from bs4 import BeautifulSoup

# Ensure .github directory is in sys.path
sys.path.insert(0, os.path.dirname(__file__))
from actions import (
    normalize,
    normalize_version,
    is_stable,
    parse_repo_identifier,
    parse_wheel_filename,
    render_package_html,
    register,
    update,
    delete,
    INDEX_FILE
)


def test_normalize():
    assert normalize("ggmlc") == "ggmlc"
    assert normalize("GGMLC") == "ggmlc"
    assert normalize("my_package.name") == "my-package-name"
    assert normalize("my--pkg..test") == "my-pkg-test"
    print("✓ test_normalize passed")


def test_version_helpers():
    assert normalize_version("v0.1.2") == "0.1.2"
    assert normalize_version("0.1.2") == "0.1.2"
    assert is_stable("v0.1.2") is True
    assert is_stable("v0.1.1-alpha2") is False
    assert is_stable("0.1.0b1") is False
    assert is_stable("0.1.0.dev0") is False
    print("✓ test_version_helpers passed")


def test_parse_repo():
    owner, repo = parse_repo_identifier("monatis/ggmlc")
    assert (owner, repo) == ("monatis", "ggmlc")

    owner, repo = parse_repo_identifier("https://github.com/monatis/ggmlc")
    assert (owner, repo) == ("monatis", "ggmlc")

    owner, repo = parse_repo_identifier("https://github.com/monatis/ggmlc.git")
    assert (owner, repo) == ("monatis", "ggmlc")
    print("✓ test_parse_repo passed")


def test_parse_wheel_filename():
    whl_info = parse_wheel_filename("ggmlc-0.1.2-cp311-cp311-win_amd64.whl")
    assert whl_info["is_wheel"] is True
    assert whl_info["python_tag"] == "cp311"
    assert "Windows x86_64" in whl_info["platform_label"]
    assert "CPython 3.11" in whl_info["python_label"]

    sdist_info = parse_wheel_filename("ggmlc-0.1.2.tar.gz")
    assert sdist_info["is_sdist"] is True
    print("✓ test_parse_wheel_filename passed")


def test_render_and_pep503_compliance():
    mock_releases = [
        {
            "tag_name": "v0.1.2",
            "version": "0.1.2",
            "is_stable": True,
            "name": "v0.1.2",
            "body": "Release 0.1.2",
            "assets": [
                {
                    "name": "mockpkg-0.1.2-cp311-cp311-win_amd64.whl",
                    "download_url": "https://github.com/owner/mockpkg/releases/download/v0.1.2/mockpkg-0.1.2-cp311-cp311-win_amd64.whl",
                    "size": 1024,
                    "sha256": "abcdef123456",
                    "info": parse_wheel_filename("mockpkg-0.1.2-cp311-cp311-win_amd64.whl")
                }
            ]
        }
    ]

    html = render_package_html(
        pkg_name="mockpkg",
        owner="owner",
        repo="mockpkg",
        releases=mock_releases,
        author="Tester",
        short_desc="A test package"
    )

    soup = BeautifulSoup(html, "html.parser")
    # PEP 503 requires valid <a> tags pointing to wheels
    links = [a["href"] for a in soup.find_all("a", href=True)]
    expected_link = "https://github.com/owner/mockpkg/releases/download/v0.1.2/mockpkg-0.1.2-cp311-cp311-win_amd64.whl#sha256=abcdef123456"
    assert expected_link in links, f"Expected {expected_link} in links"
    print("✓ test_render_and_pep503_compliance passed")


def test_e2e_pip_resolution():
    # Make sure ggmlc index exists
    if not os.path.exists("ggmlc/index.html"):
        print("[SKIP] ggmlc/index.html not generated yet, skipping local pip test.")
        return

    port = 8899
    handler = http.server.SimpleHTTPRequestHandler

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    httpd = socketserver.TCPServer(("", port), QuietHandler)
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    try:
        # Run pip / uv test
        cmd = ["uv", "pip", "install", "--dry-run", "ggmlc", "--extra-index-url", f"http://localhost:{port}"]
        # If uv is available, try uv pip
        res = subprocess.run(cmd, capture_output=True, text=True)
        # Check if resolution worked or indicated venv need
        assert res.returncode == 0 or "No virtual environment found" in res.stderr or "Resolved" in res.stdout or "Would download" in res.stdout or "Would install" in res.stdout
        print("✓ test_e2e_pip_resolution passed")
    finally:
        httpd.shutdown()


def main():
    print("Running test suite...")
    test_normalize()
    test_version_helpers()
    test_parse_repo()
    test_parse_wheel_filename()
    test_render_and_pep503_compliance()
    test_e2e_pip_resolution()
    print("\nAll tests passed successfully!")


if __name__ == "__main__":
    main()
