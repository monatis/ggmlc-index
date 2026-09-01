#!/usr/bin/env python3
"""
GitHub-hosted PyPI Simple Index Generator
Fetches pre-built wheel artifacts and distribution archives from GitHub Releases
and maintains a PEP 503 / PEP 691 compliant simple repository index.
"""

import os
import sys
import re
import json
import copy
import shutil
import argparse
import urllib.request
import urllib.error
from datetime import datetime
from bs4 import BeautifulSoup

INDEX_FILE = "index.html"
TEMPLATE_FILE = "pkg_template.html"
DEFAULT_INDEX_URL = "https://monatis.github.io/ggmlc-index/"

INDEX_CARD_TEMPLATE = '''
<a class="card" href="{norm_pkg_name}/">
    <div class="card-header">
        <span class="pkg-title">{pkg_name}</span>
        <span class="version">{norm_version}</span>
    </div>
    <div class="description">
        {short_desc}
    </div>
</a>'''


def normalize(name):
    """Normalize package name according to PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def normalize_version(version):
    """Normalize version string (strip leading 'v')."""
    version = version.strip()
    return version[1:] if version.lower().startswith("v") else version


def is_stable(version):
    """Check if version is considered a stable release."""
    v = version.lower()
    return not any(tag in v for tag in ["dev", "a", "b", "rc", "alpha", "beta", "pre"])


def parse_repo_identifier(repo_input):
    """Extract owner and repo from URL or 'owner/repo' string."""
    if not repo_input:
        return None, None
    repo_input = repo_input.strip().rstrip("/")
    if "github.com" in repo_input:
        parts = repo_input.split("github.com/")[-1].split("/")
        if len(parts) >= 2:
            return parts[0], parts[1].replace(".git", "")
    elif "/" in repo_input:
        parts = repo_input.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1].replace(".git", "")
    return None, None


def parse_wheel_filename(filename):
    """Parse PEP 427 wheel filename or source distribution name for human-friendly display."""
    info = {
        "filename": filename,
        "is_wheel": False,
        "is_sdist": False,
        "python_tag": "Any",
        "abi_tag": "",
        "platform_tag": "Source",
        "platform_label": "Source Distribution",
        "python_label": "Source"
    }

    if filename.endswith(".whl"):
        info["is_wheel"] = True
        base = filename[:-4]
        parts = base.split("-")
        if len(parts) >= 5:
            # {distribution}-{version}(-{build})?-{python_tag}-{abi_tag}-{platform_tag}
            python_tag = parts[-3]
            abi_tag = parts[-2]
            platform_tag = parts[-1]

            info["python_tag"] = python_tag
            info["abi_tag"] = abi_tag
            info["platform_tag"] = platform_tag

            # Friendly Python label
            py_versions = []
            for tag in python_tag.split("."):
                if tag.startswith("cp"):
                    ver = tag[2:]
                    if len(ver) == 2:
                        py_versions.append(f"CPython {ver[0]}.{ver[1]}")
                    elif len(ver) == 3:
                        py_versions.append(f"CPython {ver[0]}.{ver[1:]}")
                    else:
                        py_versions.append(f"CPython {ver}")
                elif tag.startswith("py"):
                    ver = tag[2:]
                    if ver == "3":
                        py_versions.append("Python 3")
                    elif ver == "2":
                        py_versions.append("Python 2")
                    elif len(ver) == 2:
                        py_versions.append(f"Python {ver[0]}.{ver[1]}")
                    else:
                        py_versions.append(f"Python {ver}")
                else:
                    py_versions.append(tag)
            info["python_label"] = ", ".join(py_versions) if py_versions else python_tag

            # Friendly Platform label
            plat_labels = []
            plat_lower = platform_tag.lower()
            if "win_amd64" in plat_lower:
                plat_labels.append("Windows x86_64")
            elif "win32" in plat_lower or "win_arm64" in plat_lower:
                plat_labels.append(platform_tag)
            elif "macosx" in plat_lower:
                if "arm64" in plat_lower or "universal2" in plat_lower:
                    plat_labels.append("macOS (Apple Silicon)")
                elif "x86_64" in plat_lower:
                    plat_labels.append("macOS (Intel)")
                else:
                    plat_labels.append("macOS")
            elif "manylinux" in plat_lower or "musllinux" in plat_lower:
                if "x86_64" in plat_lower:
                    plat_labels.append("Linux x86_64")
                elif "aarch64" in plat_lower or "arm64" in plat_lower:
                    plat_labels.append("Linux aarch64")
                else:
                    plat_labels.append("Linux")
            elif "any" in plat_lower:
                plat_labels.append("Universal / Pure Python")
            else:
                plat_labels.append(platform_tag)
            info["platform_label"] = " / ".join(plat_labels)

    elif filename.endswith((".tar.gz", ".zip", ".tgz", ".tar.bz2")):
        info["is_sdist"] = True
        info["platform_label"] = "Source Archive"
        info["python_label"] = "Source"

    return info


def make_request(url, token=None):
    """Make HTTP request with optional GitHub token."""
    headers = {"User-Agent": "pip-index-builder/1.0"}
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req)


def fetch_releases_api(owner, repo, tag=None, token=None):
    """Fetch releases from GitHub REST API."""
    if tag and tag.lower() not in ["all", "latest"]:
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
        with make_request(url, token) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [data]
    elif tag and tag.lower() == "latest":
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        with make_request(url, token) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [data]
    else:
        url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=100"
        with make_request(url, token) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data


def fetch_releases_fallback(owner, repo, tag=None):
    """Fallback fetcher when API rate limit is exceeded."""
    tags_to_fetch = []
    if tag and tag.lower() not in ["all", "latest"]:
        tags_to_fetch = [tag]
    else:
        # Scrape release page for tags
        url = f"https://github.com/{owner}/{repo}/releases"
        with make_request(url) as resp:
            html = resp.read().decode("utf-8")
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            match = re.search(rf"/{re.escape(owner)}/{re.escape(repo)}/releases/tag/([^\"/]+)", a["href"])
            if match:
                t = match.group(1)
                if t not in tags_to_fetch:
                    tags_to_fetch.append(t)

    releases = []
    for t in tags_to_fetch:
        exp_url = f"https://github.com/{owner}/{repo}/releases/expanded_assets/{t}"
        try:
            with make_request(exp_url) as resp:
                exp_html = resp.read().decode("utf-8")
        except Exception:
            continue
        exp_soup = BeautifulSoup(exp_html, "html.parser")
        assets = []
        for a in exp_soup.find_all("a", href=True):
            href = a["href"]
            if "/releases/download/" in href:
                filename = href.split("/")[-1].split("?")[0]
                full_url = f"https://github.com{href}" if href.startswith("/") else href
                assets.append({
                    "name": filename,
                    "browser_download_url": full_url,
                    "size": 0
                })
        if assets:
            releases.append({
                "tag_name": t,
                "name": t,
                "prerelease": not is_stable(t),
                "body": "",
                "assets": assets
            })
    return releases


def get_releases(owner, repo, tag=None, token=None):
    """Get releases with automatic fallback."""
    try:
        raw_releases = fetch_releases_api(owner, repo, tag, token)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            print(f"[WARN] GitHub API rate limit reached ({e.code}), falling back to web fetcher...")
            raw_releases = fetch_releases_fallback(owner, repo, tag)
        elif e.code == 404 and tag:
            print(f"[ERROR] Release tag '{tag}' not found in {owner}/{repo}.")
            raise
        else:
            raise

    formatted = []
    for r in raw_releases:
        tag_name = r.get("tag_name", "")
        if not tag_name:
            continue
        assets = []
        for a in r.get("assets", []):
            name = a.get("name", "")
            if name.endswith((".whl", ".tar.gz", ".zip", ".tgz", ".tar.bz2")):
                digest = a.get("digest")
                sha256 = ""
                if digest and digest.startswith("sha256:"):
                    sha256 = digest.split("sha256:")[-1]
                assets.append({
                    "name": name,
                    "download_url": a.get("browser_download_url", f"https://github.com/{owner}/{repo}/releases/download/{tag_name}/{name}"),
                    "size": a.get("size", 0),
                    "sha256": sha256,
                    "info": parse_wheel_filename(name)
                })
        if assets:
            formatted.append({
                "tag_name": tag_name,
                "version": normalize_version(tag_name),
                "is_stable": is_stable(tag_name),
                "name": r.get("name") or tag_name,
                "body": r.get("body", ""),
                "assets": assets
            })
    return formatted


def package_exists(soup, package_name):
    """Check if package is already in root index.html."""
    norm_pkg = normalize(package_name)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip("/")
        if href == norm_pkg:
            return True
    return False


def update_root_index(pkg_name, latest_version, short_desc):
    """Add or update package card in root index.html."""
    norm_pkg_name = normalize(pkg_name)
    norm_version = normalize_version(latest_version)

    if not os.path.exists(INDEX_FILE):
        raise FileNotFoundError(f"Root index file '{INDEX_FILE}' not found.")

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    card_soup = BeautifulSoup(INDEX_CARD_TEMPLATE.format(
        norm_pkg_name=norm_pkg_name,
        pkg_name=pkg_name,
        norm_version=norm_version,
        short_desc=short_desc
    ), "html.parser")
    new_card = card_soup.find("a")

    existing_card = None
    for a in soup.find_all("a", href=True):
        if a["href"].strip("/") == norm_pkg_name:
            existing_card = a
            break

    if existing_card:
        existing_card.replace_with(new_card)
    else:
        pkg_header = soup.find(class_="text-header")
        if pkg_header:
            pkg_header.insert_after(new_card)
        else:
            container = soup.find(class_="container") or soup.body
            container.append(new_card)

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(soup.prettify())


def remove_from_root_index(pkg_name):
    """Remove package card from root index.html."""
    norm_pkg_name = normalize(pkg_name)
    if not os.path.exists(INDEX_FILE):
        return

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    for a in soup.find_all("a", href=True):
        if a["href"].strip("/") == norm_pkg_name:
            a.decompose()

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(soup.prettify())


def format_file_size(size_bytes):
    """Format bytes into readable size."""
    if not size_bytes or size_bytes <= 0:
        return ""
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def render_package_html(pkg_name, owner, repo, releases, author="", short_desc="", homepage=""):
    """Render package index.html containing all release wheels and interactive UI."""
    norm_pkg = normalize(pkg_name)
    homepage = homepage or f"https://github.com/{owner}/{repo}"

    # Determine latest stable or latest version
    stable_releases = [r for r in releases if r["is_stable"]]
    latest_release = stable_releases[0] if stable_releases else (releases[0] if releases else None)
    latest_tag = latest_release["tag_name"] if latest_release else ""
    latest_version = latest_release["version"] if latest_release else ""

    # Build versions sidebar and distribution files HTML
    version_items_html = []
    files_sections_html = []

    for idx, r in enumerate(releases):
        tag = r["tag_name"]
        ver = r["version"]
        is_stab = r["is_stable"]
        badge_class = "latest" if (r == latest_release) else ("stable" if is_stab else "prerelease")
        badge_text = "Latest stable" if (r == latest_release) else ("Stable" if is_stab else "Prerelease")
        selected_class = " selected" if (r == latest_release) else ""

        version_items_html.append(f'''
        <div id="ver-{tag}" class="version-item{selected_class}" onclick="selectVersion('{tag}')">
          <span class="version-tag">{tag}</span>
          <span class="version-badge {badge_class}">{badge_text}</span>
        </div>''')

        # Wheel & distribution files for this release
        file_cards = []
        for asset in r["assets"]:
            fname = asset["name"]
            durl = asset["download_url"]
            sha = asset["sha256"]
            href = f"{durl}#sha256={sha}" if sha else durl
            info = asset["info"]
            size_str = format_file_size(asset["size"])

            file_cards.append(f'''
            <div class="file-card">
              <div class="file-header">
                <a class="file-link" href="{href}">{fname}</a>
              </div>
              <div class="file-badges">
                <span class="badge badge-platform">{info["platform_label"]}</span>
                <span class="badge badge-python">{info["python_label"]}</span>
                {f'<span class="badge badge-size">{size_str}</span>' if size_str else ''}
              </div>
            </div>''')

        files_sections_html.append(f'''
        <div id="files-{tag}" class="files-version-section" {'style="display:none;"' if (r != latest_release) else ''}>
          <div class="files-header">
            <h4>Files for {tag}</h4>
          </div>
          <div class="files-list">
            {"".join(file_cards)}
          </div>
        </div>''')

    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            template = f.read()
    else:
        raise FileNotFoundError(f"Template file '{TEMPLATE_FILE}' not found.")

    raw_readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md"

    html = template
    html = html.replace("{{PACKAGE_NAME}}", pkg_name)
    html = html.replace("{{NORM_PACKAGE_NAME}}", norm_pkg)
    html = html.replace("{{LATEST_VERSION}}", latest_version)
    html = html.replace("{{LATEST_TAG}}", latest_tag)
    html = html.replace("{{HOMEPAGE}}", homepage)
    html = html.replace("{{REPO_OWNER}}", owner)
    html = html.replace("{{REPO_NAME}}", repo)
    html = html.replace("{{AUTHOR}}", author)
    html = html.replace("{{SHORT_DESC}}", short_desc)
    html = html.replace("{{LONG_DESC}}", raw_readme_url)
    html = html.replace("<!-- {{VERSIONS_LIST}} -->", "\n".join(version_items_html))
    html = html.replace("<!-- {{FILES_SECTIONS}} -->", "\n".join(files_sections_html))

    return html


def register(pkg_name=None, repo=None, tag="all", author=None, short_desc=None, homepage=None, token=None):
    """Register a new package or refresh existing package with release artifacts."""
    owner, repo_name = parse_repo_identifier(repo or homepage)
    if not owner or not repo_name:
        raise ValueError(f"Invalid repository specification: {repo or homepage}")

    pkg_name = pkg_name or repo_name
    norm_pkg = normalize(pkg_name)
    author = author or owner
    short_desc = short_desc or f"Pre-built wheels for {pkg_name}"
    homepage = homepage or f"https://github.com/{owner}/{repo_name}"

    print(f"Fetching release artifacts for {owner}/{repo_name} (tag: {tag})...")
    releases = get_releases(owner, repo_name, tag=tag, token=token)
    if not releases:
        raise ValueError(f"No release artifacts (.whl, .tar.gz) found for {owner}/{repo_name}")

    print(f"Found {len(releases)} releases with distribution artifacts.")
    for r in releases:
        print(f"  - Release {r['tag_name']}: {len(r['assets'])} files")

    os.makedirs(norm_pkg, exist_ok=True)
    rendered_html = render_package_html(pkg_name, owner, repo_name, releases, author, short_desc, homepage)

    pkg_index_path = os.path.join(norm_pkg, INDEX_FILE)
    with open(pkg_index_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)
    print(f"Wrote package index to {pkg_index_path}")

    latest_stable = [r for r in releases if r["is_stable"]]
    latest_ver = latest_stable[0]["version"] if latest_stable else releases[0]["version"]
    update_root_index(pkg_name, latest_ver, short_desc)
    print(f"Updated root index for {pkg_name} ({latest_ver})")


def update(pkg_name=None, repo=None, tag="all", token=None):
    """Update an existing package with new release artifacts."""
    norm_pkg = normalize(pkg_name) if pkg_name else None
    existing_page = None

    if norm_pkg and os.path.exists(os.path.join(norm_pkg, INDEX_FILE)):
        existing_page = os.path.join(norm_pkg, INDEX_FILE)

    owner, repo_name = parse_repo_identifier(repo) if repo else (None, None)
    author = ""
    short_desc = ""
    homepage = ""

    if existing_page:
        with open(existing_page, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        btn = soup.find("button", id="repoHomepage")
        if btn and "onclick" in btn.attrs:
            m = re.search(r"openLinkInNewTab\('([^']+)'\)", btn["onclick"])
            if m:
                homepage = m.group(1)
                if not owner:
                    owner, repo_name = parse_repo_identifier(homepage)
        author_elem = soup.find(id="author-name")
        if author_elem:
            author = author_elem.text.strip()
        desc_elem = soup.find(id="package-short-desc")
        if desc_elem:
            short_desc = desc_elem.text.strip()

    if not owner or not repo_name:
        raise ValueError(f"Could not determine repository for package {pkg_name}. Please supply --repo.")

    pkg_name = pkg_name or repo_name
    register(pkg_name=pkg_name, repo=f"{owner}/{repo_name}", tag=tag, author=author, short_desc=short_desc, homepage=homepage, token=token)


def delete(pkg_name, version=None):
    """Delete a package or a specific version from the index."""
    norm_pkg = normalize(pkg_name)
    pkg_dir = norm_pkg

    if not os.path.exists(pkg_dir):
        print(f"Package directory {pkg_dir} does not exist.")
        remove_from_root_index(pkg_name)
        return

    if version:
        pkg_index_path = os.path.join(pkg_dir, INDEX_FILE)
        with open(pkg_index_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        # Remove version item and files section
        ver_item = soup.find(id=f"ver-{version}")
        if ver_item:
            ver_item.decompose()
        files_sec = soup.find(id=f"files-{version}")
        if files_sec:
            files_sec.decompose()

        with open(pkg_index_path, "w", encoding="utf-8") as f:
            f.write(soup.prettify())
        print(f"Deleted version {version} from {pkg_name}.")
    else:
        shutil.rmtree(pkg_dir, ignore_errors=True)
        remove_from_root_index(pkg_name)
        print(f"Deleted package {pkg_name} completely.")


def sync_all(token=None):
    """Sync all registered packages in root index.html."""
    if not os.path.exists(INDEX_FILE):
        return
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"].strip("/")
        if href and os.path.isdir(href) and os.path.exists(os.path.join(href, INDEX_FILE)):
            print(f"\n--- Syncing package {href} ---")
            try:
                update(pkg_name=href, tag="all", token=token)
            except Exception as e:
                print(f"[ERROR] Failed to sync {href}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Manage GitHub-hosted PyPI index with pre-built release wheels.")
    parser.add_argument("action", nargs="?", default=os.environ.get("PKG_ACTION", "REGISTER"),
                        choices=["REGISTER", "UPDATE", "DELETE", "SYNC"], help="Action to perform")
    parser.add_argument("--repo", default=os.environ.get("PKG_REPO") or os.environ.get("PKG_HOMEPAGE"),
                        help="GitHub repository (e.g. monatis/ggmlc or https://github.com/monatis/ggmlc)")
    parser.add_argument("--name", default=os.environ.get("PKG_NAME"),
                        help="Package name (defaults to repository name)")
    parser.add_argument("--tag", default=os.environ.get("PKG_TAG") or os.environ.get("PKG_VERSION", "all"),
                        help="Release tag to index (e.g. v0.1.2 or 'all')")
    parser.add_argument("--author", default=os.environ.get("PKG_AUTHOR"),
                        help="Package author name")
    parser.add_argument("--desc", default=os.environ.get("PKG_SHORT_DESC"),
                        help="Short package description")
    parser.add_argument("--homepage", default=os.environ.get("PKG_HOMEPAGE"),
                        help="Package homepage URL")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
                        help="GitHub API access token")

    args = parser.parse_args()
    action = args.action.upper()

    if action == "REGISTER":
        register(pkg_name=args.name, repo=args.repo, tag=args.tag,
                 author=args.author, short_desc=args.desc, homepage=args.homepage, token=args.token)
    elif action == "UPDATE":
        update(pkg_name=args.name, repo=args.repo, tag=args.tag, token=args.token)
    elif action == "DELETE":
        delete(pkg_name=args.name, version=args.tag if args.tag != "all" else None)
    elif action == "SYNC":
        sync_all(token=args.token)


if __name__ == "__main__":
    main()
