from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIRS = [REPO_ROOT / "src", REPO_ROOT / "frontend" / "src"]


def _source_files(*dirs: Path) -> list[Path]:
    files: list[Path] = []
    for d in dirs:
        if not d.exists():
            continue
        for pattern in ("**/*.py", "**/*.js", "**/*.ts", "**/*.tsx", "**/*.vue"):
            files.extend(d.glob(pattern))
    return files


SOURCE_FILES = _source_files(*SRC_DIRS)


def test_no_mock_encoder_in_source() -> None:
    """Regression: MockEncoder must not appear in production source code."""
    forbidden = "MockEncoder"
    hits: list[str] = []
    for path in SOURCE_FILES:
        text = path.read_text(encoding="utf-8")
        if forbidden in text:
            # Allow mentions in comments that explain the old name, but not usage
            for line_no, line in enumerate(text.splitlines(), start=1):
                if forbidden in line and not line.strip().startswith("#"):
                    hits.append(f"{path}:{line_no}")
                    break
    assert not hits, f"Forbidden '{forbidden}' found in:\n" + "\n".join(hits)


def test_no_direct_encoder_construction_outside_factory() -> None:
    """Regression: encoder classes must only be constructed inside build_encoder."""
    forbidden = ("DeterministicTestEncoder(", "OllamaEmbeddingEncoder(")
    hits: list[str] = []
    for path in SOURCE_FILES:
        # Factory is the one allowed place; tests are allowed to construct directly
        if "factory.py" in str(path) or "/tests/" in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if name in text:
                hits.append(f"{path}: {name}")
                break
    assert not hits, "Forbidden direct encoder construction found in:\n" + "\n".join(hits)


def test_main_py_uses_build_encoder() -> None:
    """Regression: main.py must wire encoders through build_encoder, never directly."""
    main_py = REPO_ROOT / "src" / "services" / "api" / "main.py"
    assert main_py.exists()
    text = main_py.read_text(encoding="utf-8")
    assert "build_encoder" in text, "main.py should import and use build_encoder"
    assert "DeterministicTestEncoder(" not in text
    assert "OllamaEmbeddingEncoder(" not in text
    assert "MockEncoder(" not in text
