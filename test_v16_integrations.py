from services.provider_integrations_v16 import (
    provider_status,
    validate_provider_action,
)
from services.youtube_growth_targets import evaluate_view_target


def test_provider_status_never_returns_secret_values():
    status = provider_status({
        "CONNECTSAFELY_API_KEY": "secret-cs",
        "MAGICPOST_API_KEY": "secret-mp",
        "SUPERGROW_API_KEY": "secret-sg",
        "VIDIQ_API_KEY": "secret-v",
        "TUBEBUDDY_API_KEY": "secret-t",
    })
    rendered = repr(status)
    for secret in ("secret-cs", "secret-mp", "secret-sg", "secret-v", "secret-t"):
        assert secret not in rendered
    assert status["connectsafely"]["status"] == "configured_unverified"
    assert status["vidiq"]["status"] == "unsupported_api"


def test_provider_action_validation_fails_closed_for_unverified_apis():
    assert validate_provider_action("vidiq", "keyword_research") == {
        "allowed": False,
        "reason": "vendor_api_contract_not_verified",
    }
    assert validate_provider_action("tubebuddy", "tag_research")["allowed"] is False


def test_connectsafely_comment_requires_human_review():
    result = validate_provider_action("connectsafely", "comment_action_review")
    assert result["allowed"] is True
    assert result["mode"] == "human_review"


def test_unknown_action_is_rejected():
    assert validate_provider_action("magicpost", "delete_linkedin_account")["allowed"] is False


def test_youtube_target_waits_for_real_metrics():
    result = evaluate_view_target(None)
    assert result["status"] == "awaiting_metrics"
    assert result["remaining_views"] is None


def test_youtube_target_gap_uses_reported_views_only():
    result = evaluate_view_target(1250)
    assert result["status"] == "in_progress"
    assert result["remaining_views"] == 3750
    assert result["attainment_percent"] == 25.0


def test_youtube_target_met():
    result = evaluate_view_target(5200)
    assert result["status"] == "target_met"
    assert result["remaining_views"] == 0
