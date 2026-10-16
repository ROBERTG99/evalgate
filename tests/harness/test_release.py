"""Release preparation (T-44): one version everywhere and a CHANGELOG section for it."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def project_version() -> str:
    return str(tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"])


def test_version_matches_changelog() -> None:
    version = project_version()
    changelog = (ROOT / "CHANGELOG.md").read_text()
    released = re.findall(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", changelog, flags=re.M)
    assert released and released[0] == version, (released, version)
    assert "## [Unreleased]" in changelog
    assert f"[{version}]: https://github.com/ROBERTG99/evalgate/releases/tag/v{version}" in changelog


def test_package_reports_the_same_version() -> None:
    import evalgate

    assert evalgate.__version__ == project_version()


def test_action_examples_pin_the_release_tag() -> None:
    readme = (ROOT / "README.md").read_text()
    for pinned in re.findall(r"ROBERTG99/evalgate/action@(v[\w.]+)", readme):
        assert pinned == f"v{project_version()}"
