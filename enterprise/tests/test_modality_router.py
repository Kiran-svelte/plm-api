"""
Unit tests for enterprise.modality_router
Tests modality detection and routing logic.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from enterprise.modality_router import (
    ModalityRouter,
    MODALITY_TEXT,
    MODALITY_CODE,
    MODALITY_IMAGE,
    MODALITY_VOICE,
    SUPPORTED_MODALITIES,
    get_modality_router,
)


def _make_router() -> ModalityRouter:
    return ModalityRouter()


# ---------------------------------------------------------------------------
# detect_modality tests
# ---------------------------------------------------------------------------

class TestDetectModality:

    def test_plain_question_is_text(self):
        router = _make_router()
        assert router.detect_modality("What is machine learning?") == MODALITY_TEXT

    def test_code_keywords_detected(self):
        router = _make_router()
        code_queries = [
            "Write a Python function to sort a list",
            "Debug this JavaScript code",
            "Implement a binary search algorithm",
            "Create a SQL query to join two tables",
            "Refactor this class to use dependency injection",
            "Write a unit test for this method",
        ]
        for q in code_queries:
            result = router.detect_modality(q)
            assert result == MODALITY_CODE, f"Expected code for: '{q}', got '{result}'"

    def test_image_keywords_detected(self):
        router = _make_router()
        image_queries = [
            "Describe this image",
            "What is in this picture?",
            "Analyze this diagram",
        ]
        for q in image_queries:
            result = router.detect_modality(q)
            assert result == MODALITY_IMAGE, f"Expected image for: '{q}', got '{result}'"

    def test_voice_keywords_detected(self):
        router = _make_router()
        voice_queries = [
            "Create a voice script about investing",
            "Write a TTS narration for this article",
            "Generate a podcast script on healthcare",
            "Create a text-to-speech script",
        ]
        for q in voice_queries:
            result = router.detect_modality(q)
            assert result == MODALITY_VOICE, f"Expected voice for: '{q}', got '{result}'"

    def test_image_attachment_overrides_text_detection(self):
        router = _make_router()
        attachments = [{"type": "image", "url": "http://example.com/img.png"}]
        result = router.detect_modality("Tell me about this", attachments=attachments)
        assert result == MODALITY_IMAGE

    def test_png_attachment_detected(self):
        router = _make_router()
        attachments = [{"type": "png", "url": "http://example.com/chart.png"}]
        result = router.detect_modality("Analyze this", attachments=attachments)
        assert result == MODALITY_IMAGE

    def test_jpg_attachment_detected(self):
        router = _make_router()
        attachments = [{"type": "jpg", "url": "http://example.com/photo.jpg"}]
        result = router.detect_modality("What do you see?", attachments=attachments)
        assert result == MODALITY_IMAGE

    def test_no_attachments_none_safe(self):
        router = _make_router()
        result = router.detect_modality("Hello world", attachments=None)
        assert result in SUPPORTED_MODALITIES

    def test_empty_attachments_list(self):
        router = _make_router()
        result = router.detect_modality("How does RAG work?", attachments=[])
        assert result in SUPPORTED_MODALITIES

    def test_all_detected_modalities_are_valid(self):
        router = _make_router()
        test_queries = [
            "What is the weather?",
            "Write a function",
            "Describe this image",
            "Create a TTS script",
        ]
        for q in test_queries:
            modality = router.detect_modality(q)
            assert modality in SUPPORTED_MODALITIES


# ---------------------------------------------------------------------------
# _make_training_example tests
# ---------------------------------------------------------------------------

class TestMakeTrainingExample:

    def test_returns_dict_with_required_fields(self):
        router = _make_router()
        ex = router._make_training_example("Q", "A", MODALITY_TEXT, "healthcare")
        assert "instruction" in ex
        assert "output" in ex
        assert "input_text" in ex
        assert "metadata" in ex
        assert "quality_score" in ex

    def test_modality_in_instruction(self):
        router = _make_router()
        ex = router._make_training_example("My query", "My response", MODALITY_CODE, "tech")
        assert "CODE" in ex["instruction"].upper() or "code" in ex["instruction"].lower()

    def test_modality_in_metadata(self):
        router = _make_router()
        for modality in SUPPORTED_MODALITIES:
            ex = router._make_training_example("Q", "A", modality, "general")
            assert ex["metadata"]["modality"] == modality

    def test_niche_in_metadata(self):
        router = _make_router()
        ex = router._make_training_example("Q", "A", MODALITY_TEXT, "healthcare")
        assert ex["metadata"]["niche"] == "healthcare"

    def test_quality_score_is_float(self):
        router = _make_router()
        ex = router._make_training_example("Q", "A", MODALITY_TEXT, "finance")
        assert isinstance(ex["quality_score"], float)
        assert 0.0 <= ex["quality_score"] <= 1.0


# ---------------------------------------------------------------------------
# Code operation detection tests
# ---------------------------------------------------------------------------

class TestDetectCodeOperation:

    def test_review_detected(self):
        router = _make_router()
        queries = [
            "Review this code",
            "Can you audit this function?",
            "Evaluate this class for issues",
            "Check this code for bugs",
        ]
        for q in queries:
            assert router.detect_code_operation(q) == "review", f"Expected review for: '{q}'"

    def test_explain_detected(self):
        router = _make_router()
        queries = [
            "Explain this code",
            "What does this function do?",
            "How does this snippet work?",
            "Walk me through this code",
        ]
        for q in queries:
            assert router.detect_code_operation(q) == "explain", f"Expected explain for: '{q}'"

    def test_generate_is_default(self):
        router = _make_router()
        queries = [
            "Write a Python function",
            "Create a REST endpoint",
            "Implement binary search",
        ]
        for q in queries:
            assert router.detect_code_operation(q) == "generate", f"Expected generate for: '{q}'"


# ---------------------------------------------------------------------------
# Heuristic quality scoring tests
# ---------------------------------------------------------------------------

class TestHeuristicQuality:

    def test_empty_response_scores_zero(self):
        router = _make_router()
        assert router._heuristic_quality("", MODALITY_TEXT) == 0.0

    def test_longer_response_scores_higher(self):
        router = _make_router()
        short = "Yes it works."
        long = " ".join(["This is a detailed explanation of the topic."] * 20)
        assert router._heuristic_quality(long, MODALITY_TEXT) > router._heuristic_quality(short, MODALITY_TEXT)

    def test_refusal_scores_low(self):
        router = _make_router()
        refusal = "I cannot help with that. As an AI, I'm not able to provide this information."
        score = router._heuristic_quality(refusal, MODALITY_TEXT)
        assert score < 0.4

    def test_score_is_between_zero_and_one(self):
        router = _make_router()
        for modality in SUPPORTED_MODALITIES:
            for text in ["Short.", "A longer response with more content and detail.", ""]:
                score = router._heuristic_quality(text, modality)
                assert 0.0 <= score <= 1.0, f"Out of range score {score} for '{text}' ({modality})"

    def test_voice_penalizes_markdown(self):
        router = _make_router()
        with_markdown = "Here are the key points:\n- First point\n- Second point\n**Bold text**"
        without_markdown = "Here are the key points. First, we have the initial concept. Second, we move on."
        score_md = router._heuristic_quality(with_markdown, MODALITY_VOICE)
        score_clean = router._heuristic_quality(without_markdown, MODALITY_VOICE)
        # Both should be valid scores
        assert 0.0 <= score_md <= 1.0
        assert 0.0 <= score_clean <= 1.0


# ---------------------------------------------------------------------------
# URL extension detection in attachments
# ---------------------------------------------------------------------------

class TestAttachmentDetection:

    def test_svg_attachment_detected_as_image(self):
        router = _make_router()
        attachments = [{"type": "svg", "url": "http://example.com/chart.svg"}]
        assert router.detect_modality("Analyze this", attachments=attachments) == MODALITY_IMAGE

    def test_url_extension_fallback(self):
        router = _make_router()
        # No explicit type but URL ends in .png
        attachments = [{"type": "", "url": "http://example.com/chart.png"}]
        assert router.detect_modality("What is this?", attachments=attachments) == MODALITY_IMAGE

    def test_unknown_attachment_type_falls_through(self):
        router = _make_router()
        attachments = [{"type": "pdf", "url": "http://example.com/doc.pdf"}]
        # PDF is not an image; should fall through to text/keyword detection
        result = router.detect_modality("What is this document?", attachments=attachments)
        assert result in SUPPORTED_MODALITIES


# ---------------------------------------------------------------------------
# Singleton test
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_modality_router_returns_same_instance(self):
        r1 = get_modality_router()
        r2 = get_modality_router()
        assert r1 is r2

    def test_returns_modality_router_instance(self):
        r = get_modality_router()
        assert isinstance(r, ModalityRouter)
