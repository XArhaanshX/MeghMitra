from __future__ import annotations

import json
from pathlib import Path

import pytest
from ankur_schemas.rule import DACPRule

REPO_ROOT = Path(__file__).resolve().parent.parent
SIRSA_FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "sirsa_dacp.json"
SIRSA_PDF_PATH = REPO_ROOT / "data" / "raw" / "HAR16-Sirsa-30-06-2011.pdf"


@pytest.fixture
def sirsa_fixture_data() -> dict:
    return json.loads(SIRSA_FIXTURE_PATH.read_text())


@pytest.fixture
def sirsa_rules(sirsa_fixture_data: dict) -> list[DACPRule]:
    return [DACPRule(**raw) for raw in sirsa_fixture_data["rules"]]


@pytest.fixture
def sirsa_pdf_path() -> Path:
    if not SIRSA_PDF_PATH.exists():
        pytest.skip(f"fixture PDF not present at {SIRSA_PDF_PATH}")
    return SIRSA_PDF_PATH
