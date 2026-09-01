<h1 align="center">ggmlc-index</h1>

<p align="center">
Custom PEP 503 compliant PyPI repository serving pre-built wheels (>100MB fatbinaries) directly from GitHub Releases.
</p>

---

## Overview

[PyPI](https://pypi.org) enforces strict package size limits (typically 100MB max per distribution file). For frameworks like [ggmlc](https://github.com/monatis/ggmlc) containing large multi-architecture pre-compiled CUDA fatbinaries, this custom repository acts as a lightweight, zero-cloud-cost simple index (PEP 503 / PEP 691) that serves pre-built wheel artifacts directly from GitHub Release assets without needing S3 or re-uploading wheels.

## How to Install

You can install packages indexed here by passing `--extra-index-url` to `pip` or `uv`:

```bash
pip install ggmlc --extra-index-url https://monatis.github.io/ggmlc-index/
```

Or with `uv`:

```bash
uv pip install ggmlc --extra-index-url https://monatis.github.io/ggmlc-index/
```

To install a specific release or prerelease version:

```bash
pip install ggmlc==0.1.2 --extra-index-url https://monatis.github.io/ggmlc-index/
pip install ggmlc==0.1.1-alpha2 --extra-index-url https://monatis.github.io/ggmlc-index/
```

`pip` / `uv` will automatically discover and download the matching wheel (e.g. `ggmlc-0.1.2-cp311-cp311-win_amd64.whl`, `ggmlc-0.1.2-cp311-cp311-manylinux_2_28_x86_64.whl`, `ggmlc-0.1.2-cp311-cp311-macosx_11_0_arm64.whl`) directly from GitHub Releases.

---

## Managing Indexed Packages via GitHub Actions

This repository includes GitHub Actions workflows to manage your index automatically:

### 1. Register a Package (`register.yml`)
- Go to the **Actions** tab $\rightarrow$ **register** $\rightarrow$ **Run workflow**
- Enter:
  - **repository**: GitHub repository (e.g. `monatis/ggmlc`)
  - **tag**: Release tag to index (e.g. `v0.1.2` or `all` to index all releases)
  - **package_name**: Optional package name override
  - **short_desc**: Optional description
- The action will fetch release assets via GitHub API, generate `pkg_name/index.html` with all wheel download URLs and metadata, update `index.html`, and create a Pull Request.

### 2. Update a Package (`update.yml`)
- Go to the **Actions** tab $\rightarrow$ **update** $\rightarrow$ **Run workflow**
- Enter:
  - **package_name**: e.g. `ggmlc`
  - **tag**: The new release tag (e.g. `v0.1.3` or `all`)
- The action fetches the new release assets, updates `ggmlc/index.html` and `index.html`, and opens a Pull Request.

### 3. Delete a Package or Version (`delete.yml`)
- Go to the **Actions** tab $\rightarrow$ **delete** $\rightarrow$ **Run workflow**
- Enter:
  - **package_name**: `ggmlc`
  - **version**: (Optional) Specific version tag to remove (leaves others intact). Leave empty to remove the whole package.

---

## Running Locally

To index or update packages locally:

```bash
# Using uv:
uv run --with beautifulsoup4 python update_pkgs.py

# Or via CLI:
uv run --with beautifulsoup4 python .github/actions.py REGISTER --repo monatis/ggmlc --tag all
```

To run tests:

```bash
uv run --with beautifulsoup4 python .github/tests.py
```

---

## License

MIT
