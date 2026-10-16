from pathlib import Path


def test_gitignore_license_spec_copy(root: Path) -> None:
    gitignore = (root / ".gitignore").read_text()
    for entry in [
        ".venv/",
        ".coverage",
        "dist/",
        ".evalgate/",
        ".tools/",
        ".env",
        "!.env.example",
        "node_modules/",
        "test-results/",
        "evals/reports/*.json",
    ]:
        assert entry in gitignore.splitlines(), entry
    editorconfig = (root / ".editorconfig").read_text()
    assert "end_of_line = lf" in editorconfig
    assert "[Makefile]\nindent_style = tab" in editorconfig
    license_text = (root / "LICENSE").read_text()
    assert license_text.startswith("MIT License")
    assert "ROBERTG99" in license_text
    spec = root / "docs/specs/000-build-spec.md"
    assert spec.exists()
    assert spec.read_text().startswith("# BUILD: evalgate")
