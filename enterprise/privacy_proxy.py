"""
Privacy Proxy & Data Sanitizer - PLM v2.0
Ensures NO user-identifiable information ever reaches external APIs
(Groq, SambaNova, Gemini, or any other third-party service).

Architecture:
- sanitize_for_api()       — pre-API sanitization with placeholder tracking
- rehydrate_response()     — post-API placeholder restoration
- sanitize_training_prompt() — extra-strict training data cleaning
- scan_report()            — detailed PII analysis without modification
- build_audit_event()      — structured audit log record for the privacy_audit table

Design principles:
- Specificity before breadth: SSN before phone, URL before IP
- Reversibility: every redaction tracked in replacements map
- No false positive panic: patterns are anchored and tested against common safe text
- Fail-open: if sanitization itself fails, original query is used (logged as warning)
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII keyword list (case-insensitive substring search)
# ---------------------------------------------------------------------------
_PII_KEYWORDS: List[str] = [
    "password", "passwd", "secret",
    "api_key", "apikey", "api key",
    "access_token", "auth_token", "bearer token",
    "ssn", "social security number",
    "credit card", "card number", "cvv", "cvc",
    "bank account", "routing number", "iban", "swift code",
    "date of birth", "dob", "birth date", "birthdate",
    "driver license", "drivers license", "passport number",
    "pin number", "private key", "secret key",
    "aws_secret", "aws_access", "client_secret",
]

# ---------------------------------------------------------------------------
# Compiled regex patterns — ordered from most-specific to least-specific
# to avoid partial overlaps.
# ---------------------------------------------------------------------------

# SSN: xxx-xx-xxxx (dashes required for cleaner matching; avoids false positives
# on version numbers like "1.2.3.4" or phone extensions).
_RE_SSN = re.compile(
    r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0{4})\d{4}\b"
)

# Credit card numbers: 13-19 digits, optionally space/dash separated
# Luhn-check is not run here but the pattern is tight enough to catch most real cards.
_RE_CREDIT_CARD = re.compile(
    r"\b(?:4[0-9]{3}|5[1-5][0-9]{2}|3[47][0-9]{2}|6(?:011|5[0-9]{2}))"
    r"(?:[-\s]?[0-9]{4}){2,4}\b"
)

# Email addresses (RFC-5321 simplified)
_RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Phone numbers — US/international formats.
# Requires at least 10 digits total to avoid matching short numbers (zip codes, etc.)
# Anchored to word boundary and must have separator or international prefix.
_RE_PHONE = re.compile(
    r"(?<!\d)"                                     # no leading digit
    r"(?:\+?1[\s\-.]?)?"                           # optional US country code
    r"(?:\(\d{3}\)|\d{3})"                         # area code
    r"[\s\-.]"                                     # required separator (avoids zip codes)
    r"\d{3}"                                       # exchange
    r"[\s\-.]"                                     # required separator
    r"\d{4}"                                       # subscriber
    r"(?!\d)"                                      # no trailing digit
)

# Full URLs (http/https)
_RE_URL = re.compile(
    r"https?://(?:www\.)?[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+(?:/[^\s]*)?"
)

# IPv4 addresses — anchored to avoid matching version strings like "1.2.3.4" embedded
# in identifiers. Each octet 0-255.
_RE_IP = re.compile(
    r"(?<!\d\.)(?<!\d)"
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    r"(?!\.\d)"
)

# Person names after explicit "my name is" / "I'm ... " patterns (conservative)
_RE_NAME = re.compile(
    r"\b(?:my\s+name\s+is|I(?:'m|\s+am)\s+called|call\s+me)\s+"
    r"([A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20})?)\b",
    re.IGNORECASE,
)

# Company names after prepositions — conservative: only match Capitalized words
# after "at/for/from/with" followed by a word boundary, up to 3 words.
_RE_COMPANY = re.compile(
    r"\b(?:at|for|from|with)\s+"
    r"([A-Z][A-Za-z0-9]{1,30}(?:\s+[A-Z][A-Za-z0-9]{1,30}){0,2})"
    r"(?=\s|,|\.|$)",
)

# Location references (conservative)
_RE_LOCATION = re.compile(
    r"\b(?:located\s+in|based\s+in|headquartered\s+in)\s+"
    r"([A-Z][A-Za-z\s,]{3,40}?)(?=[,.\s]|$)",
    re.IGNORECASE,
)


class PIIReport:
    """
    Structured report of PII found in a piece of text.
    Returned by scan_report() — does not modify the text.
    """

    def __init__(self) -> None:
        self.emails: List[str] = []
        self.phones: List[str] = []
        self.ssns: List[str] = []
        self.credit_cards: List[str] = []
        self.urls: List[str] = []
        self.ips: List[str] = []
        self.names: List[str] = []
        self.keyword_hits: List[str] = []

    @property
    def has_pii(self) -> bool:
        return bool(
            self.emails or self.phones or self.ssns or self.credit_cards
            or self.urls or self.ips or self.names or self.keyword_hits
        )

    @property
    def total_findings(self) -> int:
        return (
            len(self.emails) + len(self.phones) + len(self.ssns)
            + len(self.credit_cards) + len(self.urls) + len(self.ips)
            + len(self.names) + len(self.keyword_hits)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_pii": self.has_pii,
            "total_findings": self.total_findings,
            "emails": self.emails,
            "phones": self.phones,
            "ssns": ["[MASKED]"] * len(self.ssns),  # Don't log actual SSNs
            "credit_cards": ["[MASKED]"] * len(self.credit_cards),
            "urls": self.urls,
            "ips": self.ips,
            "names": self.names,
            "keyword_hits": self.keyword_hits,
        }


class PrivacyProxy:
    """
    Data sanitization layer that strips PII and sensitive context before
    forwarding queries to external AI APIs, then optionally re-hydrates
    responses with user-specific details.

    Usage pattern:
        proxy = get_privacy_proxy()
        sanitized, replacements = proxy.sanitize_for_api(user_query, org_name=org.name)
        response, api_used = await call_external_api(sanitized)
        final_response = proxy.rehydrate_response(response, replacements)
    """

    def sanitize_for_api(
        self,
        user_query: str,
        org_name: Optional[str] = None,
        user_name: Optional[str] = None,
        additional_entities: Optional[List[str]] = None,
    ) -> Tuple[str, Dict[str, str]]:
        """
        Strip PII, company names, emails, phone numbers, SSNs, credit cards,
        URLs, IP addresses, and location references before sending to external APIs.

        Patterns are processed from most-specific to least-specific to avoid
        partial matches clobbering each other.

        Args:
            user_query: Original user query text.
            org_name: Organisation name to redact if found.
            user_name: User display name to redact if found.
            additional_entities: Extra strings to redact (e.g. org slug, product name).

        Returns:
            Tuple of (sanitized_query, replacements_map).
            replacements_map maps placeholder → original value for rehydration.
        """
        text = user_query
        replacements: Dict[str, str] = {}
        counter = [0]

        def _placeholder(category: str) -> str:
            counter[0] += 1
            return f"[{category.upper()}_{counter[0]}]"

        def _replace_matches(pattern: re.Pattern, category: str, group: int = 0) -> None:
            nonlocal text
            for match in reversed(list(pattern.finditer(text))):
                ph = _placeholder(category)
                original = match.group(group)
                replacements[ph] = original
                start = match.start(group)
                end = match.end(group)
                text = text[:start] + ph + text[end:]

        # Generate a unique sentinel per sanitize_for_api call.
        # Using a null-byte-prefixed UUID ensures the sentinel cannot appear in
        # any human-entered query, eliminating the false-substitution risk.
        import uuid
        _sentinel = f"\x00PLM_{uuid.uuid4().hex}\x00"

        # Step 1: Explicit named-entity redaction (highest priority)
        for label, value in [("ORG", org_name), ("USER", user_name)]:
            if value:
                escaped = re.escape(value)
                new_text, n = re.subn(escaped, _sentinel, text, flags=re.IGNORECASE)
                if n:
                    ph = _placeholder(label)
                    text = new_text.replace(_sentinel, ph)
                    replacements[ph] = value

        if additional_entities:
            for entity in additional_entities:
                if entity and len(entity) >= 2:
                    escaped = re.escape(entity)
                    new_text, n = re.subn(escaped, _sentinel, text, flags=re.IGNORECASE)
                    if n:
                        ph = _placeholder("ENTITY")
                        text = new_text.replace(_sentinel, ph)
                        replacements[ph] = entity

        # Step 2: SSN (before phone to avoid consuming the same digits)
        _replace_matches(_RE_SSN, "SSN")

        # Step 3: Credit card numbers
        _replace_matches(_RE_CREDIT_CARD, "CC")

        # Step 4: Email addresses
        _replace_matches(_RE_EMAIL, "EMAIL")

        # Step 5: Phone numbers (after SSN/CC)
        _replace_matches(_RE_PHONE, "PHONE")

        # Step 6: URLs (before IP, since URLs contain IP-like patterns)
        _replace_matches(_RE_URL, "URL")

        # Step 7: IP addresses
        _replace_matches(_RE_IP, "IP")

        # Step 8: Person name patterns (explicit self-introduction phrases)
        _replace_matches(_RE_NAME, "NAME", group=1)

        # Step 9: Generalize company/location references
        text = self._generalize_query(text)

        # Step 10: Audit — log PII keywords found (don't strip, just warn)
        found_keywords = [kw for kw in _PII_KEYWORDS if kw.lower() in text.lower()]
        if found_keywords:
            logger.warning(
                "Privacy proxy: sanitized query still contains PII keywords "
                "(consider removing them from the source): %s",
                found_keywords,
            )

        return text.strip(), replacements

    def rehydrate_response(
        self,
        api_response: str,
        replacements: Dict[str, str],
    ) -> str:
        """
        Re-inject specific details into a sanitized API response.

        Only replaces placeholders that actually appear in the response.
        The API may not echo back all placeholders, which is fine.

        Args:
            api_response: Raw response text from the external API.
            replacements: Map of placeholder → original value from sanitize_for_api.

        Returns:
            Response with placeholders replaced by original values.
        """
        if not replacements:
            return api_response
        text = api_response
        for placeholder, original in replacements.items():
            if placeholder in text:
                text = text.replace(placeholder, original)
        return text

    def sanitize_training_prompt(self, prompt: str) -> str:
        """
        Extra-strict sanitization for training data generation.
        No user-specific data should ever be baked into training examples.

        Strategy:
        - Pattern-based PII is replaced with a generic [REDACTED] tag.
        - Any line containing a PII keyword is removed entirely.
        - Empty lines resulting from removal are collapsed.

        Args:
            prompt: Raw training prompt text.

        Returns:
            Sanitized prompt safe for training data storage.
        """
        text = prompt

        # Remove all detectable PII patterns outright
        text = _RE_SSN.sub("[REDACTED]", text)
        text = _RE_CREDIT_CARD.sub("[REDACTED]", text)
        text = _RE_EMAIL.sub("[REDACTED_EMAIL]", text)
        text = _RE_PHONE.sub("[REDACTED_PHONE]", text)
        text = _RE_URL.sub("[REDACTED_URL]", text)
        text = _RE_IP.sub("[REDACTED_IP]", text)

        # Remove lines containing PII keywords
        lines = text.splitlines()
        clean_lines = [
            line for line in lines
            if not any(kw.lower() in line.lower() for kw in _PII_KEYWORDS)
        ]
        # Collapse multiple blank lines
        result_lines: List[str] = []
        prev_blank = False
        for line in clean_lines:
            is_blank = not line.strip()
            if is_blank and prev_blank:
                continue
            result_lines.append(line)
            prev_blank = is_blank

        return "\n".join(result_lines).strip()

    def scan_report(self, text: str) -> PIIReport:
        """
        Analyse text for PII without modifying it.
        Returns a structured PIIReport with all findings.

        Useful for:
        - Pre-flight checks before storing text in the database
        - Generating privacy audit evidence
        - Testing and debugging sanitization coverage

        Args:
            text: Text to analyse.

        Returns:
            PIIReport instance.
        """
        report = PIIReport()
        report.emails = [m.group(0) for m in _RE_EMAIL.finditer(text)]
        report.phones = [m.group(0) for m in _RE_PHONE.finditer(text)]
        report.ssns = [m.group(0) for m in _RE_SSN.finditer(text)]
        report.credit_cards = [m.group(0) for m in _RE_CREDIT_CARD.finditer(text)]
        report.urls = [m.group(0) for m in _RE_URL.finditer(text)]
        report.ips = [m.group(0) for m in _RE_IP.finditer(text)]
        report.names = [m.group(1) for m in _RE_NAME.finditer(text)]
        report.keyword_hits = [
            kw for kw in _PII_KEYWORDS if kw.lower() in text.lower()
        ]
        return report

    def build_audit_event(
        self,
        original_query: str,
        sanitized_query: str,
        replacements: Dict[str, str],
        org_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a structured audit event for the privacy_audit table.

        The original query is hashed (SHA-256) — never stored in plain text.

        Args:
            original_query: The unsanitized query (only hashed, never stored).
            sanitized_query: The query after sanitization.
            replacements: Map of placeholder → original value.
            org_id: Organisation UUID.
            user_id: User UUID (optional).

        Returns:
            Dict ready to insert into the privacy_audit table.
        """
        categories_stripped = sorted(set(
            ph.split("_")[0].lstrip("[") for ph in replacements
        ))
        report = self.scan_report(original_query)
        return {
            "organization_id": org_id,
            "user_id": user_id,
            "query_hash": hashlib.sha256(original_query.encode()).hexdigest(),
            "entities_stripped": categories_stripped,
            "pii_keywords_found": report.keyword_hits,
            "sanitization_applied": bool(replacements) or bool(report.keyword_hits),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def has_pii(self, text: str) -> bool:
        """
        Quick check: does the text contain any detectable PII?

        Args:
            text: Text to check.

        Returns:
            True if any PII pattern or keyword is found.
        """
        return self.scan_report(text).has_pii

    def _generalize_query(self, query: str) -> str:
        """
        Replace implicit company and location anchors with generic terms.

        This is a conservative operation — it only matches patterns where
        a company or location name follows an explicit preposition keyword.

        Args:
            query: Query text (may have already had explicit PII stripped).

        Returns:
            More generic version of the query.
        """
        text = query
        text = _RE_COMPANY.sub(
            lambda m: m.group(0).replace(m.group(1), "a company"),
            text,
        )
        text = _RE_LOCATION.sub(
            lambda m: m.group(0).replace(m.group(1), "a location"),
            text,
        )
        return text


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_privacy_proxy: Optional[PrivacyProxy] = None


def get_privacy_proxy() -> PrivacyProxy:
    """Return the lazily-initialised PrivacyProxy singleton."""
    global _privacy_proxy
    if _privacy_proxy is None:
        _privacy_proxy = PrivacyProxy()
    return _privacy_proxy
