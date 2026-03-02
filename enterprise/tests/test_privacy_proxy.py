"""
Unit tests for enterprise.privacy_proxy
Tests PII detection/stripping, entity replacement, and rehydration.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from enterprise.privacy_proxy import PrivacyProxy, get_privacy_proxy


def _make_proxy() -> PrivacyProxy:
    return PrivacyProxy()


# ---------------------------------------------------------------------------
# PII detection tests (has_pii)
# ---------------------------------------------------------------------------

class TestHasPII:
    def test_clean_text_no_pii(self):
        proxy = _make_proxy()
        assert not proxy.has_pii("How do I optimize a SQL query?")

    def test_email_detected(self):
        proxy = _make_proxy()
        assert proxy.has_pii("My email is john@example.com")

    def test_phone_detected(self):
        proxy = _make_proxy()
        assert proxy.has_pii("Call me at 555-867-5309")

    def test_ssn_detected(self):
        proxy = _make_proxy()
        assert proxy.has_pii("My SSN is 123-45-6789")

    def test_ip_detected(self):
        proxy = _make_proxy()
        assert proxy.has_pii("Server is at 192.168.1.100")

    def test_password_keyword_detected(self):
        proxy = _make_proxy()
        assert proxy.has_pii("My password is hunter2")

    def test_api_key_keyword_detected(self):
        proxy = _make_proxy()
        assert proxy.has_pii("My api_key is abc123")

    def test_credit_card_keyword_detected(self):
        proxy = _make_proxy()
        assert proxy.has_pii("Credit card number 4111111111111111")


# ---------------------------------------------------------------------------
# sanitize_for_api tests
# ---------------------------------------------------------------------------

class TestSanitizeForAPI:

    def test_clean_query_unchanged(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api("What is the capital of France?")
        # Core content is preserved
        assert "France" in text or "capital" in text
        assert isinstance(replacements, dict)

    def test_email_stripped(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api("Contact alice@company.com for details")
        assert "alice@company.com" not in text
        assert any("alice@company.com" in v for v in replacements.values())

    def test_phone_stripped(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api("Call 555-123-4567 tomorrow")
        assert "555-123-4567" not in text
        assert len(replacements) >= 1

    def test_ssn_stripped(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api("My SSN is 234-56-7890")
        assert "234-56-7890" not in text
        assert len(replacements) >= 1

    def test_url_stripped(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api("Visit https://secretcorp.internal/api")
        assert "https://secretcorp.internal/api" not in text

    def test_ip_stripped(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api("Server 10.0.0.1 is down")
        assert "10.0.0.1" not in text
        assert len(replacements) >= 1

    def test_org_name_stripped(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api(
            "How does AcmeCorp handle billing?",
            org_name="AcmeCorp",
        )
        assert "AcmeCorp" not in text
        assert any("AcmeCorp" in v for v in replacements.values())

    def test_user_name_stripped(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api(
            "Alice needs help with this query",
            user_name="Alice",
        )
        assert "Alice" not in text
        assert any("Alice" in v for v in replacements.values())

    def test_additional_entities_stripped(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api(
            "Check the secretproject dashboard",
            additional_entities=["secretproject"],
        )
        assert "secretproject" not in text

    def test_replacements_map_returned(self):
        proxy = _make_proxy()
        _, replacements = proxy.sanitize_for_api("Email bob@acme.com or call 555-000-1234")
        assert len(replacements) >= 2

    def test_placeholders_use_category_prefix(self):
        proxy = _make_proxy()
        _, replacements = proxy.sanitize_for_api("Email test@example.com")
        assert all(k.startswith("[") and k.endswith("]") for k in replacements)

    def test_multiple_pii_types(self):
        proxy = _make_proxy()
        query = "User alice@corp.com called 555-111-2222 from 192.168.0.1"
        text, replacements = proxy.sanitize_for_api(query)
        assert "alice@corp.com" not in text
        assert "555-111-2222" not in text
        assert "192.168.0.1" not in text
        assert len(replacements) >= 3


# ---------------------------------------------------------------------------
# rehydrate_response tests
# ---------------------------------------------------------------------------

class TestRehydrateResponse:

    def test_placeholder_replaced_with_original(self):
        proxy = _make_proxy()
        response = "You can reach [EMAIL_1] for support."
        replacements = {"[EMAIL_1]": "help@example.com"}
        result = proxy.rehydrate_response(response, replacements)
        assert "help@example.com" in result
        assert "[EMAIL_1]" not in result

    def test_multiple_replacements(self):
        proxy = _make_proxy()
        response = "Contact [EMAIL_1] or call [PHONE_2]."
        replacements = {"[EMAIL_1]": "test@corp.com", "[PHONE_2]": "555-999-0000"}
        result = proxy.rehydrate_response(response, replacements)
        assert "test@corp.com" in result
        assert "555-999-0000" in result

    def test_empty_replacements_unchanged(self):
        proxy = _make_proxy()
        response = "The sky is blue."
        result = proxy.rehydrate_response(response, {})
        assert result == response

    def test_roundtrip_sanitize_then_rehydrate(self):
        proxy = _make_proxy()
        original = "Email me at jane@startup.io tomorrow"
        sanitized, replacements = proxy.sanitize_for_api(original)
        # Simulate API response that echoes back the placeholder
        api_response = f"I'll send an email to {list(replacements.keys())[0]} as requested."
        rehydrated = proxy.rehydrate_response(api_response, replacements)
        assert "jane@startup.io" in rehydrated


# ---------------------------------------------------------------------------
# sanitize_training_prompt tests
# ---------------------------------------------------------------------------

class TestSanitizeTrainingPrompt:

    def test_clean_prompt_unchanged(self):
        proxy = _make_proxy()
        clean = "Explain how neural networks work in healthcare."
        result = proxy.sanitize_training_prompt(clean)
        # Core content retained
        assert "neural networks" in result
        assert "healthcare" in result

    def test_email_removed_from_training_data(self):
        proxy = _make_proxy()
        prompt = "User admin@corp.com asked about pricing."
        result = proxy.sanitize_training_prompt(prompt)
        assert "admin@corp.com" not in result

    def test_phone_removed_from_training_data(self):
        proxy = _make_proxy()
        prompt = "Call 800-555-1234 for support details."
        result = proxy.sanitize_training_prompt(prompt)
        assert "800-555-1234" not in result

    def test_ssn_removed_from_training_data(self):
        proxy = _make_proxy()
        prompt = "Patient SSN 345-67-8901 needs review."
        result = proxy.sanitize_training_prompt(prompt)
        assert "345-67-8901" not in result

    def test_pii_keyword_line_removed(self):
        proxy = _make_proxy()
        prompt = "Good question about databases.\nMy password is 12345.\nSee database chapter 3."
        result = proxy.sanitize_training_prompt(prompt)
        assert "password is 12345" not in result

    def test_result_is_string(self):
        proxy = _make_proxy()
        result = proxy.sanitize_training_prompt("Any text here.")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Singleton test
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_privacy_proxy_returns_same_instance(self):
        p1 = get_privacy_proxy()
        p2 = get_privacy_proxy()
        assert p1 is p2

    def test_returns_privacy_proxy_instance(self):
        p = get_privacy_proxy()
        assert isinstance(p, PrivacyProxy)


# ---------------------------------------------------------------------------
# PIIReport / scan_report tests
# ---------------------------------------------------------------------------

from enterprise.privacy_proxy import PIIReport

class TestScanReport:

    def test_clean_text_no_findings(self):
        proxy = _make_proxy()
        report = proxy.scan_report("How do I optimize a PostgreSQL index?")
        assert not report.has_pii
        assert report.total_findings == 0

    def test_email_found_in_report(self):
        proxy = _make_proxy()
        report = proxy.scan_report("Email alice@example.com for details")
        assert "alice@example.com" in report.emails
        assert report.has_pii

    def test_phone_found_in_report(self):
        proxy = _make_proxy()
        report = proxy.scan_report("Call 555-867-5309 now")
        assert len(report.phones) >= 1
        assert report.has_pii

    def test_ssn_found_in_report(self):
        proxy = _make_proxy()
        report = proxy.scan_report("SSN 123-45-6789")
        assert len(report.ssns) >= 1

    def test_ip_found_in_report(self):
        proxy = _make_proxy()
        report = proxy.scan_report("Server at 10.0.0.1")
        assert len(report.ips) >= 1

    def test_url_found_in_report(self):
        proxy = _make_proxy()
        report = proxy.scan_report("Visit https://corp.internal/api")
        assert len(report.urls) >= 1

    def test_credit_card_found_in_report(self):
        proxy = _make_proxy()
        report = proxy.scan_report("Card 4111-1111-1111-1111 is expired")
        assert len(report.credit_cards) >= 1

    def test_keyword_hits_included(self):
        proxy = _make_proxy()
        report = proxy.scan_report("My password needs to be reset")
        assert "password" in report.keyword_hits

    def test_total_findings_sum(self):
        proxy = _make_proxy()
        report = proxy.scan_report("Email test@corp.com and phone 555-111-2222")
        assert report.total_findings >= 2

    def test_to_dict_is_serializable(self):
        proxy = _make_proxy()
        report = proxy.scan_report("My SSN is 234-56-7890 and email is bob@test.com")
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "has_pii" in d
        assert "emails" in d
        # SSNs are masked in the report dict for safety
        assert all(v == "[MASKED]" for v in d["ssns"])


# ---------------------------------------------------------------------------
# Credit card detection tests
# ---------------------------------------------------------------------------

class TestCreditCardDetection:

    def test_visa_detected(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api("Card: 4111-1111-1111-1111")
        assert "4111-1111-1111-1111" not in text
        assert len(replacements) >= 1

    def test_mastercard_detected(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api("MC: 5500 0000 0000 0004")
        assert "5500 0000 0000 0004" not in text

    def test_short_numbers_not_detected(self):
        proxy = _make_proxy()
        # 4-digit number should not match credit card
        text, replacements = proxy.sanitize_for_api("Issue #4111 needs fixing")
        assert "#4111" in text or "4111" in text  # Not stripped

    def test_version_numbers_not_affected(self):
        proxy = _make_proxy()
        text, _ = proxy.sanitize_for_api("Python version 3.12.3 is installed")
        assert "3.12.3" in text  # Version numbers should not be stripped

    def test_clean_text_no_cc_detected(self):
        proxy = _make_proxy()
        report = proxy.scan_report("Optimize the query for PostgreSQL 14.2")
        assert len(report.credit_cards) == 0


# ---------------------------------------------------------------------------
# build_audit_event tests
# ---------------------------------------------------------------------------

class TestBuildAuditEvent:

    def test_returns_dict_with_required_fields(self):
        proxy = _make_proxy()
        original = "Email test@corp.com"
        sanitized, replacements = proxy.sanitize_for_api(original)
        event = proxy.build_audit_event(original, sanitized, replacements, "org-123", "user-456")
        assert "organization_id" in event
        assert "query_hash" in event
        assert "entities_stripped" in event
        assert "sanitization_applied" in event
        assert "created_at" in event

    def test_query_is_hashed_not_stored(self):
        proxy = _make_proxy()
        original = "Very sensitive query: alice@example.com"
        sanitized, replacements = proxy.sanitize_for_api(original)
        event = proxy.build_audit_event(original, sanitized, replacements, "org-1")
        # The original query should not appear in the event
        assert original not in str(event)
        # But the hash should be a 64-char hex string (SHA-256)
        assert len(event["query_hash"]) == 64

    def test_sanitization_applied_true_when_pii_found(self):
        proxy = _make_proxy()
        original = "Contact alice@example.com"
        sanitized, replacements = proxy.sanitize_for_api(original)
        event = proxy.build_audit_event(original, sanitized, replacements, "org-1")
        assert event["sanitization_applied"] is True

    def test_sanitization_applied_false_for_clean_query(self):
        proxy = _make_proxy()
        original = "What is machine learning?"
        sanitized, replacements = proxy.sanitize_for_api(original)
        event = proxy.build_audit_event(original, sanitized, replacements, "org-1")
        assert event["sanitization_applied"] is False


# ---------------------------------------------------------------------------
# Phone false-positive avoidance tests
# ---------------------------------------------------------------------------

class TestPhoneFalsePositives:

    def test_version_number_not_phone(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api("Version 3.12.3 has new features")
        assert "3.12.3" in text

    def test_zip_code_not_phone(self):
        proxy = _make_proxy()
        # 5-digit zip code should not be matched as phone
        text, _ = proxy.sanitize_for_api("Located in ZIP 94105")
        assert "94105" in text

    def test_short_id_not_phone(self):
        proxy = _make_proxy()
        text, _ = proxy.sanitize_for_api("Order ID: 12345")
        assert "12345" in text

    def test_real_phone_is_stripped(self):
        proxy = _make_proxy()
        text, replacements = proxy.sanitize_for_api("Call 415-555-1234 now")
        assert "415-555-1234" not in text
        assert len(replacements) >= 1
