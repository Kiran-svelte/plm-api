"""
Code Service - PLM v2.0
Code generation, review, explanation, and conversion with niche domain expertise.

Uses DeepSeek-R1 (via Groq) for code generation and Qwen2.5-Coder (via SambaNova)
for code review. Both fall back gracefully to default models if the specialized
models are unavailable.

Supported operations:
  - generate_code()          — Generate new code from a natural language request
  - review_code()            — Perform a structured code review
  - explain_code()           — Explain what a piece of code does in plain language
  - detect_language()        — Detect the target programming language from query text
  - score_response_quality() — Heuristic quality score for code responses
  - generate_training_example() — Build a training example from a code interaction
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Model identifiers for specialized code tasks
_CODE_GEN_MODEL = "deepseek-r1-distill-llama-70b"   # Groq DeepSeek-R1
_CODE_REVIEW_MODEL = "Qwen2.5-Coder-32B-Instruct"    # SambaNova Qwen2.5

# Supported languages: canonical name → list of detection aliases
_LANGUAGE_ALIASES: Dict[str, List[str]] = {
    "python": ["python", "py", "pytest", "django", "flask", "fastapi", "pandas", "numpy"],
    "typescript": ["typescript", "ts", "tsx", "next.js", "nextjs"],
    "javascript": ["javascript", "js", "node.js", "nodejs", "express", "react", "vue", "angular"],
    "java": ["java", "spring", "maven", "gradle", "junit"],
    "go": ["golang", "go lang", "goroutine"],
    "rust": ["rust", "cargo", "rustc"],
    "c": [" c ", "c99", "c11", "clang", "gcc"],
    "c++": ["c++", "cpp", "cmake", "clang++", "g++"],
    "c#": ["c#", "csharp", ".net", "dotnet", "asp.net", "unity"],
    "ruby": ["ruby", "rails", "rake", "rspec"],
    "php": ["php", "laravel", "symfony", "composer"],
    "swift": ["swift", "swiftui", "xcode", "ios"],
    "kotlin": ["kotlin", "android", "gradle"],
    "sql": ["sql", "mysql", "postgresql", "postgres", "sqlite", "t-sql", "plpgsql", "bigquery"],
    "bash": ["bash", "shell", "sh", "zsh", "bash script", "shell script"],
    "powershell": ["powershell", "ps1", "pwsh"],
    "yaml": ["yaml", "yml", "helm", "kubernetes", "docker-compose"],
    "json": ["json", "jsonpath", "jq"],
    "html": ["html", "html5", "jinja", "handlebars"],
    "css": ["css", "scss", "sass", "tailwind", "less"],
    "terraform": ["terraform", "hcl", "tf"],
    "r": [r"\br\b", "ggplot", "tidyverse", "dplyr"],
}

SUPPORTED_LANGUAGES = list(_LANGUAGE_ALIASES.keys())

# Signals that indicate high-quality code in a response
_QUALITY_SIGNALS_POSITIVE = [
    r"```",                      # code blocks present
    r"def |class |function ",    # function/class definitions
    r"import |require\(|use ",   # imports/dependencies
    r"#\s|//\s|/\*",             # comments
    r"try:|except:|catch",       # error handling
    r"return ",                  # return statements
]

_QUALITY_SIGNALS_NEGATIVE = [
    r"I cannot|I don't|I'm unable",  # refusals
    r"As an AI|As a language model",  # generic disclaimers
]


class CodeService:
    """
    Code generation, review, and explanation service with niche domain expertise.

    All methods return (response_text, api_used) tuples for consistency with
    the rest of the PLM API surface.
    """

    def __init__(self) -> None:
        """Initialize code service with lazy-loaded API manager."""
        self._api_manager = None

    def _get_api_manager(self):
        """Lazy-load the FreeAPIManager singleton."""
        if self._api_manager is None:
            from src.generators.free_api_clients import FreeAPIManager
            self._api_manager = FreeAPIManager()
        return self._api_manager

    async def generate_code(
        self,
        query: str,
        org_niche: str = "technology",
        system_prompt: Optional[str] = None,
        language: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Tuple[str, str]:
        """
        Generate code using DeepSeek-R1 via Groq with niche context.

        Args:
            query: The coding task or question.
            org_niche: Organisation's domain niche for context injection.
            system_prompt: Per-org system prompt override.
            language: Target programming language (injected into prompt if provided).
            temperature: Generation temperature (lower = more deterministic code).

        Returns:
            Tuple of (generated_code_response, api_used).
        """
        import asyncio
        api_manager = self._get_api_manager()

        lang_hint = f" in {language}" if language else ""
        sys_content = system_prompt or (
            f"You are an expert {org_niche} software engineer. "
            f"Generate clean, production-quality code{lang_hint} with:\n"
            f"- Proper error handling and validation\n"
            f"- Type annotations where the language supports them\n"
            f"- Concise inline comments explaining non-obvious logic\n"
            f"- {org_niche}-domain requirements and conventions in mind\n"
            f"Return the code in a fenced code block, then a brief explanation."
        )

        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": query},
        ]

        try:
            response, api_used = await asyncio.to_thread(
                api_manager.chat,
                "groq",
                messages,
                temperature,
                4096,
                True,                 # enable_fallback
                _CODE_GEN_MODEL,      # model_override
            )
            return response, api_used
        except Exception as exc:
            logger.error(f"Code generation failed (with model override): {exc}")
            # Retry without model override — use whatever Groq has available
            try:
                response, api_used = await asyncio.to_thread(
                    api_manager.chat,
                    "groq",
                    messages,
                    temperature,
                    4096,
                    True,
                )
                return response, api_used
            except Exception as fallback_exc:
                logger.error(f"Code generation fallback also failed: {fallback_exc}")
                raise

    async def review_code(
        self,
        code: str,
        org_niche: str = "technology",
        context: Optional[str] = None,
        temperature: float = 0.3,
    ) -> Tuple[str, str]:
        """
        Review code for correctness, best practices, and niche-specific concerns.
        Uses Qwen2.5-Coder via SambaNova for review, falls back to Groq.

        Args:
            code: Code snippet to review.
            org_niche: Domain niche for context-aware review.
            context: Additional context about what the code is supposed to do.
            temperature: Generation temperature.

        Returns:
            Tuple of (review_text, api_used).
        """
        import asyncio
        api_manager = self._get_api_manager()

        review_sys = (
            f"You are a senior {org_niche} engineer performing a thorough code review. "
            f"Structure your feedback under these headings:\n"
            f"**Correctness** — Does it do what's intended? Any bugs?\n"
            f"**Security** — Any vulnerabilities, injection risks, or data exposure?\n"
            f"**Performance** — Any inefficiencies, O(n²) loops, or resource leaks?\n"
            f"**Readability** — Naming, comments, complexity.\n"
            f"**{org_niche.capitalize()}-Specific** — Domain conventions and best practices.\n"
            f"Be specific: cite line numbers or code snippets where possible. "
            f"End with a concise summary of the most critical changes to make."
        )

        user_content = f"Review this code:\n\n```\n{code}\n```"
        if context:
            user_content = f"Context: {context}\n\n{user_content}"

        messages = [
            {"role": "system", "content": review_sys},
            {"role": "user", "content": user_content},
        ]

        try:
            response, api_used = await asyncio.to_thread(
                api_manager.chat,
                "sambanova",
                messages,
                temperature,
                4096,
                True,                  # enable_fallback
                _CODE_REVIEW_MODEL,    # model_override
            )
            return response, api_used
        except Exception as exc:
            logger.error(f"Code review via SambaNova/Qwen2.5 failed: {exc}")
            # Fallback to groq without model override
            try:
                response, api_used = await asyncio.to_thread(
                    api_manager.chat,
                    "groq",
                    messages,
                    temperature,
                    4096,
                    True,
                )
                return response, api_used
            except Exception as fallback_exc:
                logger.error(f"Code review fallback also failed: {fallback_exc}")
                raise

    async def explain_code(
        self,
        code: str,
        org_niche: str = "technology",
        audience: str = "intermediate developer",
        temperature: float = 0.4,
    ) -> Tuple[str, str]:
        """
        Explain what a piece of code does in plain language.

        Tailored to the niche and target audience. Useful for onboarding,
        documentation generation, and training data creation.

        Args:
            code: Code snippet to explain.
            org_niche: Domain niche for context-aware explanation.
            audience: Target audience level (e.g. "beginner", "intermediate developer",
                      "senior engineer", "non-technical stakeholder").
            temperature: Generation temperature.

        Returns:
            Tuple of (explanation_text, api_used).
        """
        import asyncio
        api_manager = self._get_api_manager()

        explain_sys = (
            f"You are a {org_niche} expert and technical communicator. "
            f"Explain code clearly to a {audience}. "
            f"Structure your explanation as:\n"
            f"1. **Purpose** — What this code does in one sentence.\n"
            f"2. **How it works** — Step-by-step walkthrough of key logic.\n"
            f"3. **{org_niche.capitalize()} context** — How this fits into {org_niche} workflows.\n"
            f"4. **Gotchas** — Any non-obvious behavior or edge cases to be aware of.\n"
            f"Use plain language. Define technical terms inline."
        )

        messages = [
            {"role": "system", "content": explain_sys},
            {"role": "user", "content": f"Explain this code:\n\n```\n{code}\n```"},
        ]

        response, api_used = await asyncio.to_thread(
            api_manager.chat,
            "groq",
            messages,
            temperature,
            2048,
            True,
        )
        return response, api_used

    def detect_language(self, query: str) -> Optional[str]:
        """
        Detect the programming language from the query text.

        Uses word-boundary matching to avoid false positives (e.g. "go" inside
        "algorithm" or "c" inside "concatenate").

        Args:
            query: User query text.

        Returns:
            Canonical language name or None.
        """
        query_lower = query.lower()
        for canonical, aliases in _LANGUAGE_ALIASES.items():
            for alias in aliases:
                # Aliases that already contain regex syntax are used as-is.
                # Short aliases (≤3 chars) are wrapped in word boundaries to avoid
                # false positives (e.g. bare "c" inside "concatenate").
                # Longer plain-string aliases use simple substring matching.
                if alias.startswith(r"\b") or alias.startswith("(?"):
                    # Already a regex pattern — use directly
                    if re.search(alias, query_lower):
                        return canonical
                elif len(alias) <= 3:
                    pattern = r"\b" + re.escape(alias) + r"\b"
                    if re.search(pattern, query_lower):
                        return canonical
                else:
                    if alias.lower() in query_lower:
                        return canonical
        return None

    def score_response_quality(self, response: str, language: Optional[str] = None) -> float:
        """
        Compute a heuristic quality score for a code response.

        Scores 0.0–1.0 based on:
        - Presence of code blocks (strong signal)
        - Language-specific constructs (function/class definitions, imports)
        - Comment presence
        - Error handling
        - Absence of refusal patterns

        Args:
            response: Generated code response text.
            language: Detected language (if known, used for language-specific scoring).

        Returns:
            Quality score in [0.0, 1.0].
        """
        score = 0.0  # Start from zero; length determines baseline

        # Length-derived starting score
        word_count = len(response.split())
        if word_count == 0:
            return 0.0
        elif word_count < 20:
            score = 0.3
        elif word_count < 50:
            score = 0.45
        elif word_count < 200:
            score = 0.55
        else:
            score = 0.65

        # Positive signals (up to +0.28 additional)
        positive_hits = 0
        for pattern in _QUALITY_SIGNALS_POSITIVE:
            if re.search(pattern, response, re.IGNORECASE):
                positive_hits += 1
        score += min(0.28, positive_hits * 0.07)

        # Negative signals (-0.2 each)
        for pattern in _QUALITY_SIGNALS_NEGATIVE:
            if re.search(pattern, response, re.IGNORECASE):
                score -= 0.2

        return max(0.0, min(1.0, round(score, 2)))

    def generate_training_example(
        self,
        query: str,
        response: str,
        language: Optional[str] = None,
        org_niche: str = "technology",
        operation: str = "generate",
    ) -> Dict[str, Any]:
        """
        Generate a code-specific training example for the niche model.

        Args:
            query: The original code question or instruction.
            response: The generated code response.
            language: Programming language used.
            org_niche: Organisation niche.
            operation: Type of code task ("generate", "review", "explain").

        Returns:
            Training example dict compatible with training_data table schema.
        """
        lang_tag = f"/{language}" if language else ""
        instruction = f"[Code{lang_tag}/{operation}] {query}"
        quality = self.score_response_quality(response, language)

        return {
            "instruction": instruction,
            "output": response,
            "input_text": "",
            "metadata": {
                "modality": "code",
                "language": language,
                "niche": org_niche,
                "operation": operation,
                "source": "code_service",
            },
            "quality_score": quality,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_code_service: Optional[CodeService] = None


def get_code_service() -> CodeService:
    """Return the lazily-initialised CodeService singleton."""
    global _code_service
    if _code_service is None:
        _code_service = CodeService()
    return _code_service
