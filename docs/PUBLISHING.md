# Publishing the Vantiva Integration to HACS

This guide covers everything needed to publish the Vantiva Home Assistant custom integration via HACS (Home Assistant Community Store), both as a custom repository and for submission to the HACS default repository list.

**Repository:** `github.com/davenicoll/ha-vantiva`  
**Domain:** `vantiva`  
**Date:** 2026-10-03

---

## 1. Required Repository Layout for HACS

### Directory Structure

HACS integrations must follow this exact structure:

```
ha-vantiva/
├── .github/
│   └── workflows/
│       ├── validate.yml      # Hassfest + HACS validation
│       └── release.yml        # (Optional) Zip release workflow
├── custom_components/
│   └── vantiva/              # Domain name (must match manifest)
│       ├── __init__.py
│       ├── manifest.json     # REQUIRED
│       ├── config_flow.py
│       ├── sensor.py         # Or other platform files
│       ├── strings.json
│       └── translations/
│           └── en.json
│       ├── brand/             # Local brand assets, INSIDE the integration dir (HA 2026.3.0+)
│       │   ├── icon.png       # 256x256
│       │   └── logo.png       # (Optional)
├── README.md                  # REQUIRED
└── hacs.json                  # REQUIRED
```

### Critical Rules

- **One integration per repository**: Only one subdirectory under `custom_components/` is allowed.
- **All files must be inside the integration directory**: Everything the integration needs must be under `custom_components/vantiva/`.
- **No root-level code**: Do not place `__init__.py` or other code files at the repository root (unless `content_in_root: true` is set in `hacs.json`, which is not recommended for integrations).

**Sources:**
- https://hacs.xyz/docs/publish/integration
- https://hacs.xyz/docs/publish/start
- https://developers.home-assistant.io/docs/creating_integration_file_structure

---

## 2. The `manifest.json` File

The `manifest.json` file is **required** and must be placed inside `custom_components/vantiva/`.

### Full Example for Vantiva

```json
{
  "domain": "vantiva",
  "name": "Vantiva",
  "version": "1.0.0",
  "codeowners": ["@davenicoll"],
  "config_flow": true,
  "dependencies": [],
  "documentation": "https://github.com/davenicoll/ha-vantiva",
  "integration_type": "hub",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/davenicoll/ha-vantiva/issues",
  "loggers": ["vantiva"],
  "requirements": []
}
```

### Key Explanations

| Key | Required | Description |
|-----|----------|-------------|
| `domain` | **Yes** | Short unique identifier (letters/underscores). Must match the directory name. Cannot be changed later. |
| `name` | **Yes** | Display name shown to users. |
| `version` | **Yes (custom integrations only)** | Must be parseable by AwesomeVersion (e.g., SemVer: `1.0.0`, CalVer: `2026.10.1`). Core integrations omit this. Should match release tags. |
| `codeowners` | **Yes** | GitHub usernames responsible for the integration. Format: `["@username"]` |
| `config_flow` | Optional | Set to `true` if the integration uses a config flow (requires `config_flow.py` to exist). |
| `dependencies` | Optional | List of other integrations that must load first (e.g., `["mqtt"]`). |
| `documentation` | **Yes** | URL to usage documentation. For custom integrations, typically the GitHub repository URL. |
| `integration_type` | **Yes (for config flow)** | One of: `device`, `entity`, `hardware`, `helper`, `hub`, `service`, `system`, `virtual`. Use `hub` for gateways managing multiple devices. |
| `iot_class` | **Yes** | One of: `assumed_state`, `cloud_polling`, `cloud_push`, `local_polling`, `local_push`, `calculated`. Use `local_polling` for local devices polled periodically. |
| `issue_tracker` | **Yes (custom only)** | URL where users report bugs. Core integrations omit this. |
| `loggers` | Optional | Logger names used by the integration (useful for debugging). |
| `requirements` | **Yes** | List of Python packages (pip format). Pin versions: `["aiohttp==3.8.1"]`. Custom integrations can use Git sources: `["mylib@git+https://github.com/user/repo.git@v1.0.0"]`. Should only list packages not already in Home Assistant Core's `requirements.txt`. |
| `quality_scale` | Optional | One of: `bronze`, `silver`, `gold`, `platinum`. See section 7 for details. |

**Important Notes:**

- The `version` key is **mandatory for custom integrations** and should be updated with each release.
- `requirements` must be on PyPI for core integrations, but custom integrations can bundle code or use Git sources.
- Beta HA versions can be specified with `b0` suffix (e.g., `2026.10.0b0`).

**Sources:**
- https://developers.home-assistant.io/docs/creating_integration_manifest

---

## 3. The `hacs.json` File

The `hacs.json` file is **required** and must be placed at the **repository root**.

### Example for Vantiva

```json
{
  "name": "Vantiva",
  "homeassistant": "2026.6.0",
  "hacs": "2.0.5"
}
```

### Optional Keys

| Key | Type | Purpose |
|-----|------|---------|
| `name` | string | **Required.** Display name in HACS UI. |
| `homeassistant` | string | Minimum Home Assistant version required. |
| `hacs` | string | Minimum HACS version required. |
| `zip_release` | bool | Set to `true` if releases include a zip file. Requires `filename` key. |
| `filename` | string | Name of the zip file to download (e.g., `"vantiva.zip"`). Required if `zip_release: true`. |
| `content_in_root` | bool | Set to `true` if integration files are at root instead of `custom_components/<domain>/`. Not recommended. |
| `hide_default_branch` | bool | Prevents HACS from offering the default branch for download. |
| `persistent_directory` | string | Relative path to preserve across upgrades (integrations only). |
| `country` | string | ISO 3166-1 alpha-2 code if integration is country-specific. |

### Release Strategy

**Without `zip_release`** (recommended for starting):
- HACS downloads files directly from the repository.
- Users get the latest release tag, or the default branch if no releases exist.

**With `zip_release`**:
- You create a release workflow that zips `custom_components/vantiva/` and uploads it as a release asset.
- Set `"zip_release": true` and `"filename": "vantiva.zip"` in `hacs.json`.
- HACS downloads and extracts the zip file.

**Sources:**
- https://hacs.xyz/docs/publish/start
- https://hacs.xyz/docs/publish/integration

---

## 4. GitHub Actions Workflows

### 4.1 Validation Workflow

Create `.github/workflows/validate.yml`:

```yaml
name: Validate

on:
  workflow_dispatch:
  schedule:
    - cron: "0 0 * * *"  # Daily at midnight
  push:
    branches:
      - main
  pull_request:
    branches:
      - main

permissions: {}

jobs:
  hassfest:
    name: Hassfest validation
    runs-on: ubuntu-latest
    steps:
      - name: Checkout the repository
        uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Run hassfest validation
        uses: home-assistant/actions/hassfest@master

  hacs:
    name: HACS validation
    runs-on: ubuntu-latest
    steps:
      - name: Run HACS validation
        uses: hacs/action@main
        with:
          category: integration
          # Remove this 'ignore' after adding brand images
          ignore: brands
```

**What this validates:**
- **Hassfest**: Validates `manifest.json` structure, checks dependencies, verifies requirements format, etc.
- **HACS**: Validates repository structure, checks for required files, verifies `hacs.json` format, etc.

### 4.2 Release Workflow (Optional)

Create `.github/workflows/release.yml` if using `zip_release`:

```yaml
name: Release

on:
  release:
    types: [published]

permissions:
  contents: write

jobs:
  release:
    name: Prepare release
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Zip integration
        run: |
          cd custom_components
          zip -r ../vantiva.zip vantiva/

      - name: Upload zip to release
        uses: softprops/action-gh-release@v1
        with:
          files: vantiva.zip
```

**Workflow:**
1. Create a GitHub release with a tag (e.g., `v1.0.0`).
2. Workflow zips `custom_components/vantiva/` into `vantiva.zip`.
3. Zip is automatically attached to the release.
4. HACS downloads the zip when users install or update.

**Sources:**
- https://developers.home-assistant.io/blog/2020/04/16/hassfest
- https://github.com/home-assistant/actions
- https://hacs.xyz/docs/publish/action
- https://github.com/ludeeus/integration_blueprint (template repository)

---

## 5. HACS Default Repository Submission

To get the Vantiva integration included in the HACS default repository list, follow this checklist.

### Prerequisites

1. **Repository must be public** and on GitHub.
2. **Already addable as a custom repository** (test this first).
3. **Both GitHub Actions must pass** (hassfest and HACS validation) with no errors or ignores.
4. **At least one full GitHub release** published (not just a tag).
5. **Repository metadata**:
   - Description set
   - Topics/tags added (e.g., `home-assistant`, `hacs`, `integration`)
   - Issues enabled
6. **Brand assets**: Either `custom_components/<domain>/brand/icon.png`, or the domain present in `home-assistant/brands`. (The HACS action checks `<integration path>/brand/icon.png`; a repo-root `brand/` is ignored.)

### Submission Process

1. **Fork** the `hacs/default` repository.
2. **Create a branch** from `master`.
3. **Edit** the `./integration` file and add your repository URL in **alphabetical order**:
   ```
   davenicoll/ha-vantiva
   ```
   (Do NOT add to the end; insert alphabetically.)
4. **Submit a pull request** from your personal GitHub account (not an organization account).
5. **Fill out the PR template** completely and accurately.
6. **Set `country` key** in `hacs.json` if the integration is country-specific.

### Automated Checks

All of these checks must pass:

- **Brands**: Brand directory with at least `icon.png`, or domain in `home-assistant/brands`.
- **Manifest**: Valid integration `manifest.json`.
- **hacs-validation**: Same validation HACS runs.
- **HACS manifest**: `hacs.json` contains at least `name`.
- **Archived**: Repository is not archived.
- **Releases**: At least one release exists.
- **Owner**: Submitter is the repository owner or major contributor.
- **Repository**: Has description, issues enabled, and topics.
- **lint jq / lint sorted**: PR files are valid JSON and properly sorted.

### Timeline

- Reviews can take **months** due to backlog.
- Track progress via the open, non-draft PRs in `hacs/default`.
- Once merged, the repository appears in HACS after the next scheduled scan.

**Eligibility Notes:**
- Only the repository owner or major contributor may submit.
- Alpha/beta testing integrations or overrides of core integrations are not accepted (can still be used as custom repositories).

**Sources:**
- https://hacs.xyz/docs/publish/include

---

## 6. End-User Installation

### 6.1 Install as Custom Repository

Users can add the Vantiva integration before it's in the default HACS repository:

**Steps in HACS:**
1. Open HACS in Home Assistant.
2. Click the **three dots** (⋮) in the upper right.
3. Select **Custom repositories**.
4. Enter the repository URL: `https://github.com/davenicoll/ha-vantiva`
5. Select category: **Integration**
6. Click **ADD**.
7. Search for "Vantiva" in HACS and install.

### 6.2 My Home Assistant Redirect Link

Provide users with a one-click installation link:

```
https://my.home-assistant.io/redirect/hacs_repository/?owner=davenicoll&repository=ha-vantiva&category=integration
```

When clicked, this:
- Opens the user's Home Assistant instance.
- Navigates directly to the Vantiva repository in HACS.
- User clicks "Download" to install.

**Parameters:**
- `owner`: GitHub username or organization (`davenicoll`)
- `repository`: Repository name (`ha-vantiva`)
- `category`: Must be `integration`

**Note:** Users must have their Home Assistant instance URL configured on `my.home-assistant.io` for this to work.

**Sources:**
- https://hacs.xyz/docs/faq/custom_repositories
- https://my.home-assistant.io/create-link/

---

## 7. Brand Assets

### 7.1 Local Brand Assets (Recommended)

**As of Home Assistant 2026.3.0**, custom integrations can bundle brand icons in a `brand/` directory **inside the integration directory** (`custom_components/vantiva/brand/`), per https://developers.home-assistant.io/docs/creating_integration_file_structure.

**Directory structure:**
```
ha-vantiva/
└── custom_components/vantiva/brand/
    ├── icon.png       # 256x256 px, 1:1 aspect ratio
    ├── icon@2x.png    # 512x512 px (optional, hDPI)
    ├── logo.png       # Landscape, shortest side 128-256 px (optional)
    └── logo@2x.png    # Shortest side 256-512 px (optional, hDPI)
```

**Requirements:**
- **icon.png**: Square (1:1 aspect), 256x256 px
- **icon@2x.png**: Square, 512x512 px (optional, for high-DPI displays)
- **logo.png**: Brand logo, landscape preferred, shortest side 128-256 px
- **logo@2x.png**: hDPI logo, shortest side 256-512 px
- All files must be **PNG** format
- Use transparency where possible
- Optimize/compress files (lossless preferred)
- Design for white background (use `dark_` prefix for dark variants)

**Fallback behavior:**
- If `logo.png` is missing, `icon.png` is used.
- If `@2x` files are missing, standard versions are upscaled.

### 7.2 Submitting to home-assistant/brands (Legacy)

**Note:** The `custom_integrations` folder in `home-assistant/brands` is now considered legacy. Bundling icons locally is preferred.

If you choose to submit to the brands repository:

1. Fork `home-assistant/brands`.
2. Create `custom_integrations/vantiva/` directory.
3. Add icon files (same requirements as above).
4. Directory name **must match** the `domain` in `manifest.json`.
5. Submit a pull request.

**Important:**
- Custom integrations **must not use Home Assistant branded images** to avoid implying official status.
- If a core integration and custom integration share a domain, the core integration takes precedence.
- Merged brand images are cached (browser: 7 days, Cloudflare: 24 hours). Full cache flush happens with each major HA release.

**Sources:**
- https://github.com/home-assistant/brands
- https://developers.home-assistant.io/docs/creating_integration_file_structure#local-brand-images-for-custom-integrations

---

## 8. Integration Quality Scale

Home Assistant uses a quality scale framework to grade integrations on user experience, features, code quality, and developer experience.

### Tiers

- **🥉 Bronze**: Mandatory baseline for all new core integrations. Optional for custom integrations.
- **🥈 Silver**: Adds runtime reliability and robustness.
- **🥇 Gold**: Comprehensive, user-friendly support. Required for "Works with Home Assistant" program.
- **🏆 Platinum**: Technical excellence.
- **📦 Custom**: Community-distributed (e.g., via HACS). Not reviewed, audited, or supported by the Home Assistant project.

### Bronze Requirements (Relevant to Custom Integrations)

If you want to align with the quality scale (optional for custom integrations):

**Configuration & Setup:**
- ✅ `config_flow`: Set up through the UI (no YAML config).
- ✅ `test-before-configure`: Connection tested before config entry creation.
- ✅ `unique-config-entry`: Prevents duplicate config entries.
- ✅ `config-flow-test-coverage`: Config flow has automated tests.

**Runtime:**
- ✅ `runtime-data`: Uses `entry.runtime_data` instead of `hass.data[DOMAIN]`.

**Entities:**
- ✅ `entity-unique-id`: All entities have unique IDs.
- ✅ `has-entity-name`: Entities use `has_entity_name = True`.
- ✅ `appropriate-polling`: Uses `DataUpdateCoordinator` for polling or implements proper polling intervals.

**Code Quality:**
- ✅ `common-modules`: Uses Home Assistant helper modules (`homeassistant.helpers.*`).
- ✅ `dependency-transparency`: Dependencies are clear and documented.

**Documentation:**
- ✅ `docs-high-level-description`: High-level description of what the integration does.
- ✅ `docs-installation-instructions`: Step-by-step installation guide.
- ✅ `docs-configuration-parameters`: Documents all configuration options.

**Brand:**
- ✅ `brands`: Brand assets available (local or in `home-assistant/brands`).

### Higher Tiers

**Silver** adds: unload support, reauthentication, active code owner, 95%+ test coverage, automatic recovery from errors.

**Gold** adds: discovery, UI reconfiguration, translations, diagnostics, firmware updates, extensive documentation.

**Platinum** adds: full typing, fully async, efficient data handling.

### `quality_scale.yaml` File

Core integrations can declare their quality scale tier by creating a `quality_scale.yaml` file:

```yaml
rules:
  config_flow: done
  test-before-configure: done
  unique-config-entry: done
  runtime-data: done
  entity-unique-id: done
  has-entity-name: done
  appropriate-polling: done
  common-modules: done
  dependency-transparency: done
  docs-high-level-description: done
  docs-installation-instructions: done
  docs-configuration-parameters: done
  brands: done
  config-flow-test-coverage: done
```

**Note:** This file is only used for core integrations. Custom integrations can align with the rules but don't submit a `quality_scale.yaml`.

**Sources:**
- https://developers.home-assistant.io/docs/core/integration-quality-scale/

---

## 9. Testing with pytest-homeassistant-custom-component

### Installation

```bash
pip install pytest-homeassistant-custom-component
```

### Version Matching

The package is regenerated daily against published Home Assistant releases, including betas. The tracked HA version is recorded in the package's `ha_version` constant.

**Version strategy:**
- Minor version bump = extraction logic changed
- Patch version bump = automatic update tied to new HA release

As of 2026-10-03, the package tracks **Home Assistant 2026.10.0b0**.

### Usage

**Import changes:**
- Core uses: `from tests.common import MockConfigEntry`
- Custom integrations use: `from pytest_homeassistant_custom_component.common import MockConfigEntry`

**Required fixtures:**
- `enable_custom_integrations`: Required for HA versions ≥2021.6.0b0.
- Some fixtures (e.g., `recorder_mock`) must be initialized before `enable_custom_integrations`.

**pytest configuration:**

Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

**Fixture loading:**

`load_fixture` expects a `fixtures/` folder alongside tests:
```
tests/
├── fixtures/
│   └── sample_data.json
└── test_sensor.py
```

### Example Config Flow Test

```python
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.config_entries import ConfigEntryState

async def test_config_flow(hass, enable_custom_integrations):
    """Test the config flow."""
    result = await hass.config_entries.flow.async_init(
        "vantiva",
        context={"source": "user"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"host": "192.168.1.1"}
    )
    
    assert result["type"] == "create_entry"
    assert result["title"] == "Vantiva"
    
    entry = hass.config_entries.async_entries("vantiva")[0]
    assert entry.state == ConfigEntryState.LOADED
```

**Sources:**
- https://github.com/MatthewFlamm/pytest-homeassistant-custom-component
- https://pypi.org/project/pytest-homeassistant-custom-component/

---

## 10. Current Home Assistant Requirements

### Python Version

**As of 2026-10-03:**
- Home Assistant core requires **Python 3.14.2 or higher**
- Verified from: `https://github.com/home-assistant/core/blob/dev/pyproject.toml`
  - `requires-python = ">=3.14.2"`
  - Classifier: `"Programming Language :: Python :: 3.14"`

### Version Numbering

Home Assistant uses **CalVer** (calendar versioning):
- Format: `YYYY.MM.PATCH` (e.g., `2026.10.1`)
- Major releases monthly
- Patch releases as needed
- Beta releases: `YYYY.MM.0b0` format

### Development Environment

For local testing:
1. Install Python 3.14.2+
2. Create virtual environment: `python3 -m venv venv`
3. Activate: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
4. Install HA: `pip install homeassistant`
5. Run: `hass --script check_config -c config/` (validates configuration)

**Sources:**
- https://developers.home-assistant.io/docs/development_environment
- https://github.com/home-assistant/core/blob/dev/pyproject.toml

---

## 11. Pre-Submission Checklist

Before submitting to HACS default or making your first release:

### Repository Setup
- [ ] Repository is public on GitHub
- [ ] Repository has a description
- [ ] Repository has topics (e.g., `home-assistant`, `hacs`, `integration`)
- [ ] Issues are enabled
- [ ] README.md exists with usage instructions
- [ ] LICENSE file exists

### Integration Files
- [ ] `custom_components/vantiva/` directory structure
- [ ] `manifest.json` with all required keys (including `version`)
- [ ] `__init__.py` (can be minimal for platform-only integrations)
- [ ] Config flow implementation if `config_flow: true`
- [ ] `strings.json` and `translations/en.json` for UI strings

### HACS Files
- [ ] `hacs.json` at repository root
- [ ] Brand assets: `custom_components/vantiva/brand/icon.png` (256x256)
- [ ] Optional: `custom_components/vantiva/brand/logo.png`

### GitHub Actions
- [ ] `.github/workflows/validate.yml` (hassfest + HACS validation)
- [ ] Both workflows passing with no errors
- [ ] Optional: `.github/workflows/release.yml` if using zip releases

### Testing
- [ ] Can add as custom repository in HACS
- [ ] Integration installs successfully
- [ ] Config flow works
- [ ] Entities appear and update correctly
- [ ] No errors in Home Assistant logs

### Release
- [ ] Create GitHub release with tag matching `manifest.json` version
- [ ] Release notes describe changes
- [ ] If using `zip_release`, verify zip file is attached

### Documentation
- [ ] README explains what the integration does
- [ ] Installation instructions (custom repository + my.home-assistant.io link)
- [ ] Configuration steps
- [ ] Known issues/limitations
- [ ] Troubleshooting section

---

## 12. Resources

### Official Documentation
- HACS Publishing: https://hacs.xyz/docs/publish/start
- Home Assistant Integration Development: https://developers.home-assistant.io/docs/creating_integration_manifest
- Integration Quality Scale: https://developers.home-assistant.io/docs/core/integration-quality-scale/

### Tools & Templates
- Integration Blueprint: https://github.com/ludeeus/integration_blueprint
- HACS Action: https://github.com/hacs/action
- Hassfest Action: https://github.com/home-assistant/actions
- pytest-homeassistant-custom-component: https://github.com/MatthewFlamm/pytest-homeassistant-custom-component

### Community
- HACS Discord: https://discord.gg/apgchf8
- Home Assistant Developer Forum: https://community.home-assistant.io/c/development
- Home Assistant Discord: https://discord.gg/home-assistant

---

## Verification Status

✅ **Verified from official sources** (as of 2026-10-03):
- HACS publishing requirements and repository structure
- `manifest.json` keys and requirements (including `version` for custom integrations)
- `hacs.json` format and optional keys
- GitHub Actions workflows (hassfest, HACS validation)
- HACS default submission process and automated checks
- Brand asset requirements and submission process
- Integration quality scale tiers and rules
- Python 3.14.2+ requirement from `pyproject.toml`
- Home Assistant 2026.x version numbering
- pytest-homeassistant-custom-component usage

⚠️ **Could not fully verify**:
- Exact release workflow implementation (integration_blueprint doesn't include one; provided example workflow is based on common patterns)
- Whether `info.md` is fully deprecated (documentation suggests it's optional and not recommended for new integrations)
- Complete list of hassfest validation checks (action exists but internal checks not fully documented in fetched sources)

---

**Document prepared:** 2026-10-03  
**For:** Vantiva integration (`github.com/davenicoll/ha-vantiva`)  
**Domain:** `vantiva`


## Note: HACS action on a private repository

The HACS action reads `hacs.json` and `manifest.json` through `raw.githubusercontent.com`, which returns 404 for private repositories. On this private repo the action therefore reports "invalid hacs.json" and "manifest ... Got None" even though both files are valid (hassfest passes). These two checks will pass once the repository is public; the brand check is independent and passes with the bundled `brand/` directory.
