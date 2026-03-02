"""
Unit tests for enterprise.code_service
Tests language detection, quality scoring, and training example generation.
No external API calls are made — all tests are pure unit tests.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from enterprise.code_service import CodeService, get_code_service, SUPPORTED_LANGUAGES


def _make_service() -> CodeService:
    return CodeService()


# ---------------------------------------------------------------------------
# detect_language tests
# ---------------------------------------------------------------------------

class TestDetectLanguage:

    def test_python_detected_by_name(self):
        svc = _make_service()
        assert svc.detect_language("Write a Python function to parse JSON") == "python"

    def test_python_detected_by_py_alias(self):
        svc = _make_service()
        assert svc.detect_language("Create a py script for data processing") == "python"

    def test_javascript_detected(self):
        svc = _make_service()
        assert svc.detect_language("Build a JavaScript async function") == "javascript"

    def test_js_alias_detected(self):
        svc = _make_service()
        assert svc.detect_language("Write a JS event handler") == "javascript"

    def test_typescript_detected(self):
        svc = _make_service()
        assert svc.detect_language("Create a TypeScript interface") == "typescript"

    def test_tsx_alias_detected(self):
        svc = _make_service()
        assert svc.detect_language("Build a tsx React component") == "typescript"

    def test_sql_detected(self):
        svc = _make_service()
        assert svc.detect_language("Write a SQL query to join tables") == "sql"

    def test_postgres_alias_detected(self):
        svc = _make_service()
        assert svc.detect_language("Optimize this PostgreSQL query") == "sql"

    def test_go_detected_with_boundary(self):
        svc = _make_service()
        # "golang" or "go lang" should detect Go
        result = svc.detect_language("Write a function using golang concurrency")
        assert result == "go"

    def test_bash_detected(self):
        svc = _make_service()
        assert svc.detect_language("Write a bash script to automate backups") == "bash"

    def test_shell_alias_detected(self):
        svc = _make_service()
        assert svc.detect_language("Create a shell script for deployment") == "bash"

    def test_java_detected(self):
        svc = _make_service()
        assert svc.detect_language("Create a Java Spring Boot controller") == "java"

    def test_rust_detected(self):
        svc = _make_service()
        assert svc.detect_language("Write a Rust function with ownership") == "rust"

    def test_docker_yaml_detected(self):
        svc = _make_service()
        assert svc.detect_language("Write a docker-compose YAML service") == "yaml"

    def test_unknown_returns_none(self):
        svc = _make_service()
        assert svc.detect_language("How do I optimize a database?") is None

    def test_empty_query_returns_none(self):
        svc = _make_service()
        assert svc.detect_language("") is None

    def test_case_insensitive(self):
        svc = _make_service()
        assert svc.detect_language("PYTHON function") == "python"
        assert svc.detect_language("JAVASCRIPT module") == "javascript"

    def test_no_false_positive_in_concatenate(self):
        """'c' inside 'concatenate' should not match the C language."""
        svc = _make_service()
        # "concatenate" should not trigger C language detection
        result = svc.detect_language("How do I concatenate strings?")
        # This should be None or python/js, not "c"
        assert result != "c"

    def test_all_supported_languages_are_detectable(self):
        """Each canonical language name should be self-detectable."""
        svc = _make_service()
        # Languages that have unambiguous query templates
        detectable = {
            "python": "Write a python function",
            "javascript": "Write a javascript function",
            "typescript": "Create a typescript interface",
            "java": "Write a java class",
            "rust": "Create a rust struct",
            "sql": "Write a sql query",
            "bash": "Create a bash script",
            "yaml": "Write a yaml config",
            "html": "Create an html5 template",
            "css": "Write css styles",
        }
        for lang, query in detectable.items():
            result = svc.detect_language(query)
            assert result == lang, f"Expected '{lang}' for: '{query}', got '{result}'"


# ---------------------------------------------------------------------------
# score_response_quality tests
# ---------------------------------------------------------------------------

class TestScoreResponseQuality:

    def test_empty_response_low_score(self):
        svc = _make_service()
        # Empty string is below the baseline
        score = svc.score_response_quality("")
        assert score < 0.5

    def test_code_block_increases_score(self):
        svc = _make_service()
        without_block = "Here is a function that does the task."
        with_block = "Here is the code:\n```python\ndef hello():\n    return 'world'\n```"
        assert svc.score_response_quality(with_block) > svc.score_response_quality(without_block)

    def test_refusal_lowers_score(self):
        svc = _make_service()
        refusal = "I cannot write code for this. As a language model, I am unable to assist."
        score = svc.score_response_quality(refusal)
        assert score < 0.4

    def test_rich_code_response_high_score(self):
        svc = _make_service()
        rich = '''
```python
from typing import List

def binary_search(arr: List[int], target: int) -> int:
    """Find target in sorted array. Returns index or -1."""
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
```
This function implements binary search with O(log n) time complexity.
'''
        score = svc.score_response_quality(rich, language="python")
        assert score >= 0.7

    def test_score_is_between_zero_and_one(self):
        svc = _make_service()
        test_responses = [
            "",
            "No.",
            "Here is a simple function:\n```\ndef hello(): pass\n```",
            "I cannot help with that request.",
            "import os\ndef main():\n    try:\n        pass\n    except Exception as e:\n        print(e)\n    return None",
        ]
        for resp in test_responses:
            score = svc.score_response_quality(resp)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for: '{resp[:30]}'"


# ---------------------------------------------------------------------------
# generate_training_example tests
# ---------------------------------------------------------------------------

class TestGenerateTrainingExample:

    def test_returns_required_fields(self):
        svc = _make_service()
        ex = svc.generate_training_example(
            query="Write a Python sort function",
            response="```python\ndef sort(lst): return sorted(lst)\n```",
            language="python",
            org_niche="technology",
        )
        assert "instruction" in ex
        assert "output" in ex
        assert "input_text" in ex
        assert "metadata" in ex
        assert "quality_score" in ex

    def test_language_tag_in_instruction(self):
        svc = _make_service()
        ex = svc.generate_training_example("query", "response", "python", "tech")
        assert "python" in ex["instruction"].lower() or "CODE" in ex["instruction"]

    def test_operation_in_metadata(self):
        svc = _make_service()
        for op in ["generate", "review", "explain"]:
            ex = svc.generate_training_example("q", "r", "python", "tech", operation=op)
            assert ex["metadata"]["operation"] == op

    def test_modality_always_code(self):
        svc = _make_service()
        ex = svc.generate_training_example("query", "response", None, "tech")
        assert ex["metadata"]["modality"] == "code"

    def test_quality_score_is_float_in_range(self):
        svc = _make_service()
        ex = svc.generate_training_example("query", "response", "python", "tech")
        score = ex["quality_score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_niche_preserved_in_metadata(self):
        svc = _make_service()
        ex = svc.generate_training_example("q", "r", "sql", "healthcare")
        assert ex["metadata"]["niche"] == "healthcare"

    def test_no_language_generates_generic_tag(self):
        svc = _make_service()
        ex = svc.generate_training_example("What does this do?", "It does X.", None, "tech")
        assert "instruction" in ex
        assert isinstance(ex["instruction"], str)


# ---------------------------------------------------------------------------
# Singleton test
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_code_service_returns_same_instance(self):
        s1 = get_code_service()
        s2 = get_code_service()
        assert s1 is s2

    def test_returns_code_service_instance(self):
        s = get_code_service()
        assert isinstance(s, CodeService)
