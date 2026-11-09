from legal_gateway import MatterIntake, SignedDocument, plan_follow_up


def test_signed_delivery_follow_up_uses_matter_deadline_and_recipient():
    intake = MatterIntake("matter-42", "example.test", "client@example.test", "2026-11-15")
    document = SignedDocument("doc-7", "Engagement letter", "2026-10-28")

    follow_up = plan_follow_up(intake, document)

    assert follow_up.due_on == "2026-11-15"
    assert follow_up.recipient == "client@example.test"
    assert "Engagement letter" in follow_up.message

