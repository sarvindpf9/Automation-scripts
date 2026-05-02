"""Parser tests use the real NTT-SOW.pdf fixture — no mocks."""
import os
import pytest
from pathlib import Path

from sow_mcp.parser import extract_text_pdf, parse_sow
from sow_mcp.models import SowDocument

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "NTT-SOW.pdf"

_has_fixture = FIXTURE_PDF.exists()
_has_api_key = bool(os.getenv("ANTHROPIC_API_KEY"))

needs_fixture = pytest.mark.skipif(
    not _has_fixture, reason="NTT-SOW.pdf fixture not present"
)
needs_llm = pytest.mark.skipif(
    not _has_fixture or not _has_api_key,
    reason="NTT-SOW.pdf fixture or ANTHROPIC_API_KEY not present",
)


@needs_fixture
def test_extract_text_returns_nonempty():
    text = extract_text_pdf(FIXTURE_PDF)
    assert len(text) > 500
    assert "Platform9" in text
    assert "NTT" in text


@needs_fixture
def test_extract_text_captures_scope_headings():
    text = extract_text_pdf(FIXTURE_PDF)
    assert "Scope of Work" in text


@needs_llm
def test_parse_sow_returns_document():
    doc = parse_sow(str(FIXTURE_PDF))
    assert isinstance(doc, SowDocument)
    assert doc.customer
    assert doc.project_title
    assert len(doc.scope_sections) > 0


@needs_llm
def test_parse_sow_ntt_customer():
    doc = parse_sow(str(FIXTURE_PDF))
    assert doc.customer == "NTT"


@needs_llm
def test_parse_sow_datacenters():
    doc = parse_sow(str(FIXTURE_PDF))
    roles = {dc.role for dc in doc.datacenters}
    assert "canary" in roles
    assert "production" in roles


@needs_llm
def test_parse_sow_vm_count():
    doc = parse_sow(str(FIXTURE_PDF))
    assert doc.vm_count == 1000


@needs_llm
def test_parse_sow_has_integrations():
    doc = parse_sow(str(FIXTURE_PDF))
    integration_text = " ".join(doc.integrations).lower()
    assert "netapp" in integration_text or "storage" in integration_text


@needs_llm
def test_parse_sow_scope_sections_have_activities():
    doc = parse_sow(str(FIXTURE_PDF))
    for section in doc.scope_sections:
        assert section.id
        assert section.title
        assert len(section.activities) > 0, (
            f"Section {section.id} '{section.title}' has no activities"
        )


@needs_llm
def test_parse_sow_to_dict_is_serialisable():
    import json
    doc = parse_sow(str(FIXTURE_PDF))
    payload = json.dumps(doc.to_dict())
    assert len(payload) > 100


def test_parse_sow_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        parse_sow("/nonexistent/path/sow.pdf")


def test_parse_sow_unsupported_type_raises():
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"not a pdf")
        name = f.name
    try:
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_sow(name)
    finally:
        os.unlink(name)
