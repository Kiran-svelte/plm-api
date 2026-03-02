"""
Unit tests for the OpenAI client in FreeAPIManager.
Tests cover client initialization, fallback order, and Kaggle training estimates.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.generators.free_api_clients import FreeAPIManager, OpenAIClient


# ---------------------------------------------------------------------------
# OpenAI client class tests
# ---------------------------------------------------------------------------

class TestOpenAIClientInit:
    """Tests for OpenAIClient.__init__()."""

    def test_default_model(self):
        client = OpenAIClient(api_key="test-key")
        assert client.model == "gpt-4o-mini"

    def test_custom_model(self):
        client = OpenAIClient(api_key="test-key", model="gpt-4o")
        assert client.model == "gpt-4o"

    def test_base_url(self):
        client = OpenAIClient(api_key="test-key")
        assert client.base_url == "https://api.openai.com/v1"

    def test_api_key_stored(self):
        client = OpenAIClient(api_key="sk-test-123")
        assert client.api_key == "sk-test-123"


# ---------------------------------------------------------------------------
# FreeAPIManager integration tests
# ---------------------------------------------------------------------------

class TestFreeAPIManagerOpenAI:
    """Tests for OpenAI integration in FreeAPIManager."""

    def test_openai_in_clients_when_key_set(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        # Clear any cached manager
        manager = FreeAPIManager()
        assert "openai" in manager.clients

    def test_openai_not_in_clients_without_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        manager = FreeAPIManager()
        assert "openai" not in manager.clients

    def test_openai_in_fallback_order(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        manager = FreeAPIManager()
        assert "openai" in manager.fallback_order

    def test_openai_client_type(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        manager = FreeAPIManager()
        assert isinstance(manager.clients["openai"], OpenAIClient)


# ---------------------------------------------------------------------------
# Kaggle training time estimates
# ---------------------------------------------------------------------------

# These tests require the supabase package (model_trainer imports db_client)
_has_supabase = True
try:
    import supabase
except ImportError:
    _has_supabase = False

_skip_if_no_supabase = pytest.mark.skipif(
    not _has_supabase, reason="supabase package not installed"
)


@_skip_if_no_supabase
class TestKaggleTrainingEstimates:
    """Tests for KaggleNotebookTrainer.estimate_training_time()."""

    def test_tinyllama_fastest(self):
        from enterprise.model_trainer import KaggleNotebookTrainer
        est = KaggleNotebookTrainer.estimate_training_time("tinyllama-1.1b", 500)
        assert est["estimated_training_hours"] > 0
        assert est["estimated_training_hours"] <= 3

    def test_large_model_slower(self):
        from enterprise.model_trainer import KaggleNotebookTrainer
        small = KaggleNotebookTrainer.estimate_training_time("tinyllama-1.1b", 500)
        large = KaggleNotebookTrainer.estimate_training_time("llama-3.1-8b", 500)
        assert large["estimated_training_hours"] > small["estimated_training_hours"]

    def test_more_examples_takes_longer(self):
        from enterprise.model_trainer import KaggleNotebookTrainer
        few = KaggleNotebookTrainer.estimate_training_time("llama-3.2-3b", 100)
        many = KaggleNotebookTrainer.estimate_training_time("llama-3.2-3b", 5000)
        assert many["estimated_training_hours"] >= few["estimated_training_hours"]

    def test_chat_available_immediately(self):
        from enterprise.model_trainer import KaggleNotebookTrainer
        est = KaggleNotebookTrainer.estimate_training_time("tinyllama-1.1b", 500)
        assert est["chat_available_in_hours"] <= 1.0

    def test_fine_tuned_ready_after_training(self):
        from enterprise.model_trainer import KaggleNotebookTrainer
        est = KaggleNotebookTrainer.estimate_training_time("tinyllama-1.1b", 500)
        assert est["fine_tuned_model_ready_in_hours"] > est["estimated_training_hours"]

    def test_estimate_has_required_fields(self):
        from enterprise.model_trainer import KaggleNotebookTrainer
        est = KaggleNotebookTrainer.estimate_training_time("llama-3.2-3b", 500)
        required_fields = [
            "estimated_training_hours",
            "gpu_type",
            "chat_available_in_hours",
            "fine_tuned_model_ready_in_hours",
            "agentic_tasks_ready_in_hours",
            "message",
        ]
        for field in required_fields:
            assert field in est, f"Missing field: {field}"

    def test_gpu_type_appropriate_for_model_size(self):
        from enterprise.model_trainer import KaggleNotebookTrainer
        small = KaggleNotebookTrainer.estimate_training_time("tinyllama-1.1b", 500)
        large = KaggleNotebookTrainer.estimate_training_time("mistral-7b", 500)
        assert small["gpu_type"] == "P100"
        assert large["gpu_type"] == "T4x2"

    def test_message_is_human_readable(self):
        from enterprise.model_trainer import KaggleNotebookTrainer
        est = KaggleNotebookTrainer.estimate_training_time("llama-3.2-3b", 500)
        assert "hours" in est["message"]
        assert "llama-3.2-3b" in est["message"]


# ---------------------------------------------------------------------------
# Training backend detection
# ---------------------------------------------------------------------------

@_skip_if_no_supabase
class TestTrainingBackendDetection:
    """Tests for training backend availability detection."""

    def test_kaggle_backend_available_with_keys(self, monkeypatch):
        from enterprise.model_trainer import ModelTrainer, TrainingBackend
        monkeypatch.setenv("KAGGLE_USERNAME", "testuser")
        monkeypatch.setenv("KAGGLE_KEY", "testkey123")
        # Need to reimport to pick up env vars
        import importlib
        import enterprise.model_trainer as mt
        importlib.reload(mt)
        trainer = mt.ModelTrainer()
        backends = trainer.get_available_backends()
        assert mt.TrainingBackend.KAGGLE in backends

    def test_kaggle_backend_not_available_without_keys(self, monkeypatch):
        monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
        monkeypatch.delenv("KAGGLE_KEY", raising=False)
        import importlib
        import enterprise.model_trainer as mt
        importlib.reload(mt)
        trainer = mt.ModelTrainer()
        backends = trainer.get_available_backends()
        assert mt.TrainingBackend.KAGGLE not in backends
