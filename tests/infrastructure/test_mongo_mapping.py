from updater.domain.models import Target, Vulnerability
from updater.infrastructure.mongo import target_to_document, vulnerability_to_document


def test_target_document_contains_normalized_name_and_raw_metadata():
    target = Target(name=" Adobe Reader ", aliases=["Acrobat"], raw_metadata={"notes": "contest"})

    document = target_to_document(target)

    assert document["name"] == " Adobe Reader "
    assert document["normalized_name"] == "adobe reader"
    assert document["aliases"] == ["Acrobat"]
    assert document["raw_metadata"] == {"notes": "contest"}


def test_vulnerability_document_uses_advisory_id_as_unique_key():
    vulnerability = Vulnerability(advisory_id="CVE-2025-1234", sources=["nvd"], aliases=["ZDI-CAN-12345"])

    document = vulnerability_to_document(vulnerability)

    assert document["advisory_id"] == "CVE-2025-1234"
    assert document["aliases"] == ["ZDI-CAN-12345"]
    assert document["sources"] == ["nvd"]
