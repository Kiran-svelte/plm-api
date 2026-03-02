"""
Modality Router - PLM v2.0
Routes queries to the appropriate service handler based on detected input/output type.
All modalities share the same RAG knowledge base and niche system prompt.

Supported modalities:
- text:  Standard text Q&A (existing generate_answer_with_context flow)
- code:  Code generation, review, and explanation via CodeService
- image: Image analysis descriptions using niche domain knowledge
- voice: TTS-optimized script generation with niche terminology

Detection priority (to avoid conflicts):
  1. Attachments (image type → MODALITY_IMAGE)
  2. Voice keywords (voice/TTS/podcast script)
  3. Image keywords (image/diagram/picture)
  4. Code keywords (function/implement/debug etc.)
  5. Default: text

Graceful degradation: if any modality handler fails, routes to text handler
and sets 'degraded_from' in the response.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Modality identifiers
# ---------------------------------------------------------------------------
MODALITY_TEXT = "text"
MODALITY_CODE = "code"
MODALITY_IMAGE = "image"
MODALITY_VOICE = "voice"

SUPPORTED_MODALITIES = [MODALITY_TEXT, MODALITY_CODE, MODALITY_IMAGE, MODALITY_VOICE]

# ---------------------------------------------------------------------------
# Keyword patterns for modality detection
# Voice is checked first to avoid "voice script" → code ("script" keyword)
# ---------------------------------------------------------------------------

# Voice/audio content creation
_VOICE_KEYWORDS = re.compile(
    r"\b(?:voice\s+script|tts|text.to.speech|read\s+aloud|narrate|"
    r"podcast\s+(?:script|episode)|audio\s+script|"
    r"spoken\s+(?:word|content|text)|pronunciation|"
    r"speech\s+(?:script|text)|say\s+this\s+aloud|"
    r"text\s+to\s+(?:speech|audio))\b",
    re.IGNORECASE,
)

# Image/visual content
_IMAGE_KEYWORDS = re.compile(
    r"\b(?:image|picture|photo|screenshot|diagram|chart|graph|figure|"
    r"describe\s+(?:this\s+)?(?:image|picture|photo|diagram)|"
    r"what(?:'s|\s+is)\s+in\s+this\s+(?:image|picture|photo)|"
    r"analyze\s+this\s+(?:image|diagram)|look\s+at\s+this|"
    r"visual\s+analysis|image\s+description)\b",
    re.IGNORECASE,
)

# Code / programming
_CODE_KEYWORDS = re.compile(
    r"\b(?:code|function|class|script|implement|debug|fix\s+(?:this|the)|"
    r"refactor|write\s+a\s+(?:function|class|method|test|script)|"
    r"build\s+(?:a|an)\s+(?:function|class|api|endpoint|service)|"
    r"algorithm|snippet|compile|program(?:me)?|method|"
    r"api\s+endpoint|unit\s+test|integration\s+test|sql\s+query|"
    r"regex|bash\s+command|shell\s+script|makefile|dockerfile|"
    r"generate\s+code|review\s+(?:this\s+)?code|explain\s+(?:this\s+)?code|"
    r"convert\s+(?:this\s+)?(?:to|from)\s+(?:python|java|javascript|typescript|go|rust))\b",
    re.IGNORECASE,
)

# Code sub-operation detection
_CODE_REVIEW_KEYWORDS = re.compile(
    r"\b(?:review|audit|check|critique|assess|evaluate)\s+(?:this\s+)?(?:code|function|class|method)\b",
    re.IGNORECASE,
)
_CODE_EXPLAIN_KEYWORDS = re.compile(
    r"\b(?:explain|what\s+does|how\s+does|describe|walk\s+me\s+through)\s+(?:this\s+)?(?:code|function|class|snippet)\b",
    re.IGNORECASE,
)

# Image attachment type suffixes
_IMAGE_ATTACHMENT_TYPES = frozenset(["image", "png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"])


class ModalityRouter:
    """
    Routes queries to the appropriate modality handler.
    Falls back gracefully if a modality's service is unavailable.

    Uses lazy-loaded singletons for all services to avoid startup overhead.
    """

    def __init__(self) -> None:
        self._api_manager = None

    def _get_api_manager(self):
        """Lazy-load the shared FreeAPIManager singleton."""
        if self._api_manager is None:
            from src.generators.free_api_clients import FreeAPIManager
            self._api_manager = FreeAPIManager()
        return self._api_manager

    def detect_modality(
        self,
        query: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Analyze query + attachments to determine the appropriate modality.

        Detection priority (most to least specific):
        1. Attachment types (image attachment → image modality)
        2. Voice keywords (very specific multi-word phrases)
        3. Image keywords
        4. Code keywords
        5. Default: text

        Args:
            query: User query text.
            attachments: Optional list of attachment dicts with 'type' and 'url' keys.

        Returns:
            One of: 'text', 'code', 'image', 'voice'.
        """
        # Attachment-based detection takes highest priority
        if attachments:
            for attachment in attachments:
                att_type = (attachment.get("type") or "").lower().lstrip(".")
                if att_type in _IMAGE_ATTACHMENT_TYPES:
                    return MODALITY_IMAGE
                # Check URL extension as fallback
                url = (attachment.get("url") or "").lower()
                for ext in _IMAGE_ATTACHMENT_TYPES:
                    if url.endswith(f".{ext}"):
                        return MODALITY_IMAGE

        # Keyword-based detection (most-specific first)
        if _VOICE_KEYWORDS.search(query):
            return MODALITY_VOICE
        if _IMAGE_KEYWORDS.search(query):
            return MODALITY_IMAGE
        if _CODE_KEYWORDS.search(query):
            return MODALITY_CODE

        return MODALITY_TEXT

    def detect_code_operation(self, query: str) -> str:
        """
        Detect the specific code operation requested.

        Returns:
            One of: 'generate', 'review', 'explain'.
        """
        if _CODE_REVIEW_KEYWORDS.search(query):
            return "review"
        if _CODE_EXPLAIN_KEYWORDS.search(query):
            return "explain"
        return "generate"

    async def route_query(
        self,
        query: str,
        org_id: str,
        model_id: str,
        modality: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        org_niche: str = "general",
        temperature: float = 0.7,
        context: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Route query to the appropriate service handler.

        If the modality handler raises any exception, the router automatically
        falls back to the text handler and sets 'degraded_from' in the result.

        Args:
            query: User query text.
            org_id: Organisation UUID.
            model_id: Model UUID.
            modality: Explicit modality override; auto-detected if None.
            attachments: Optional list of attachments.
            system_prompt: Per-org system prompt.
            org_niche: Organisation's domain niche.
            temperature: Generation temperature.
            context: RAG context chunks (pre-fetched by caller).

        Returns:
            Dict with 'response', 'modality', 'api_used', 'training_example',
            and optional 'degraded_from', 'detected_language'.
        """
        detected = modality if modality in SUPPORTED_MODALITIES else self.detect_modality(
            query, attachments
        )

        handlers = {
            MODALITY_TEXT: self._handle_text,
            MODALITY_CODE: self._handle_code,
            MODALITY_IMAGE: self._handle_image_description,
            MODALITY_VOICE: self._handle_voice_script,
        }

        handler = handlers.get(detected, self._handle_text)
        shared_kwargs = dict(
            query=query,
            org_id=org_id,
            model_id=model_id,
            system_prompt=system_prompt,
            org_niche=org_niche,
            temperature=temperature,
            context=context or [],
            attachments=attachments or [],
        )

        try:
            result = await handler(**shared_kwargs)
            result["modality"] = detected
            return result
        except Exception as exc:
            logger.error(
                f"Modality handler '{detected}' failed: {exc}. Falling back to text."
            )
            result = await self._handle_text(**{**shared_kwargs, "attachments": []})
            result["modality"] = MODALITY_TEXT
            result["degraded_from"] = detected
            return result

    # ------------------------------------------------------------------
    # Per-modality handlers
    # ------------------------------------------------------------------

    async def _handle_text(
        self,
        query: str,
        org_id: str,
        model_id: str,
        system_prompt: Optional[str],
        org_niche: str,
        temperature: float,
        context: List[Dict[str, Any]],
        attachments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Standard text Q&A — delegates to the existing generate_answer_with_context flow.
        """
        from enterprise.backend.api import generate_answer_with_context
        response, api_used = await generate_answer_with_context(
            query=query,
            context=context,
            temperature=temperature,
            system_prompt=system_prompt,
            org_niche=org_niche,
        )
        return {
            "response": response,
            "api_used": api_used,
            "training_example": self._make_training_example(
                query, response, MODALITY_TEXT, org_niche
            ),
        }

    async def _handle_code(
        self,
        query: str,
        org_id: str,
        model_id: str,
        system_prompt: Optional[str],
        org_niche: str,
        temperature: float,
        context: List[Dict[str, Any]],
        attachments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Code generation, review, or explanation with niche context.
        Detects the specific operation from the query.
        """
        from enterprise.code_service import get_code_service
        svc = get_code_service()

        # Enrich system prompt with RAG context if available
        enriched_prompt = system_prompt
        if context:
            ctx_text = "\n\n".join(c.get("content", "") for c in context if c.get("content"))
            base = system_prompt or f"You are an expert {org_niche} software engineer."
            enriched_prompt = (
                f"{base}\n\n"
                f"Use the following domain knowledge when generating or reviewing code:\n"
                f"{ctx_text}"
            )

        language = svc.detect_language(query)
        operation = self.detect_code_operation(query)

        if operation == "review":
            # Extract the first fenced code block from the query.
            # If the user provides multiple blocks, only the first is reviewed;
            # they can submit subsequent blocks as separate review requests.
            code_match = re.search(r"```[\w]*\n?(.*?)```", query, re.DOTALL)
            code_to_review = code_match.group(1).strip() if code_match else query
            response, api_used = await svc.review_code(
                code=code_to_review,
                org_niche=org_niche,
                context=enriched_prompt,
                temperature=min(temperature, 0.3),
            )
        elif operation == "explain":
            # Extract the first fenced code block from the query.
            code_match = re.search(r"```[\w]*\n?(.*?)```", query, re.DOTALL)
            code_to_explain = code_match.group(1).strip() if code_match else query
            response, api_used = await svc.explain_code(
                code=code_to_explain,
                org_niche=org_niche,
                temperature=min(temperature, 0.4),
            )
        else:
            response, api_used = await svc.generate_code(
                query=query,
                org_niche=org_niche,
                system_prompt=enriched_prompt,
                language=language,
                temperature=min(temperature, 0.3),
            )

        training_ex = svc.generate_training_example(
            query=query,
            response=response,
            language=language,
            org_niche=org_niche,
            operation=operation,
        )
        return {
            "response": response,
            "api_used": api_used,
            "detected_language": language,
            "code_operation": operation,
            "training_example": training_ex,
        }

    async def _handle_image_description(
        self,
        query: str,
        org_id: str,
        model_id: str,
        system_prompt: Optional[str],
        org_niche: str,
        temperature: float,
        context: List[Dict[str, Any]],
        attachments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Image analysis descriptions using niche knowledge.
        Incorporates RAG context and niche expertise into visual analysis.
        """
        api_manager = self._get_api_manager()

        ctx_text = "\n\n".join(
            c.get("content", "") for c in context if c.get("content")
        ) if context else ""
        sys_msg = system_prompt or (
            f"You are a {org_niche} expert specializing in visual analysis and documentation. "
            f"When describing images, apply your {org_niche} domain expertise to:\n"
            f"- Identify domain-specific elements, symbols, and conventions\n"
            f"- Interpret data visualizations through a {org_niche} lens\n"
            f"- Use precise {org_niche} terminology\n"
            f"- Connect visual information to {org_niche} best practices\n"
            f"Be structured: describe what's shown, then interpret its significance."
        )
        if ctx_text:
            sys_msg += f"\n\nDomain knowledge for context:\n{ctx_text}"

        # Build user message, incorporating image attachment URLs if provided
        user_msg = query
        if attachments:
            image_urls = [
                a.get("url") for a in attachments
                if (a.get("type") or "").lower().lstrip(".") in _IMAGE_ATTACHMENT_TYPES
                and a.get("url")
            ]
            if image_urls:
                urls_text = "\n".join(f"- {url}" for url in image_urls)
                user_msg = f"Images to analyze:\n{urls_text}\n\nRequest: {query}"

        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": user_msg},
        ]

        response, api_used = await asyncio.to_thread(
            api_manager.chat,
            "groq",
            messages,
            temperature,
            2048,
            True,  # enable_fallback
        )

        return {
            "response": response,
            "api_used": api_used,
            "training_example": self._make_training_example(
                query, response, MODALITY_IMAGE, org_niche
            ),
        }

    async def _handle_voice_script(
        self,
        query: str,
        org_id: str,
        model_id: str,
        system_prompt: Optional[str],
        org_niche: str,
        temperature: float,
        context: List[Dict[str, Any]],
        attachments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        TTS script generation optimized for natural spoken delivery.
        Applies niche terminology and defines technical terms inline.
        """
        api_manager = self._get_api_manager()

        ctx_text = "\n\n".join(
            c.get("content", "") for c in context if c.get("content")
        ) if context else ""
        sys_msg = system_prompt or (
            f"You are a {org_niche} expert creating engaging, natural-sounding spoken-word content. "
            f"Follow these TTS writing principles:\n"
            f"- Write in complete, natural sentences — avoid bullet points and lists\n"
            f"- Spell out numbers and abbreviations (e.g. 'three hundred' not '300', 'for example' not 'e.g.')\n"
            f"- Define technical {org_niche} terms inline the first time they appear\n"
            f"- Use transitions to guide listeners ('first', 'next', 'finally')\n"
            f"- Avoid special characters, markdown, or symbols that don't translate to speech\n"
            f"- Aim for a conversational, confident tone that builds trust with the listener."
        )
        if ctx_text:
            sys_msg += f"\n\nDomain knowledge for accuracy:\n{ctx_text}"

        messages = [
            {"role": "system", "content": sys_msg},
            {
                "role": "user",
                "content": f"Create a spoken-word script for: {query}",
            },
        ]

        response, api_used = await asyncio.to_thread(
            api_manager.chat,
            "groq",
            messages,
            min(temperature, 0.6),  # Slightly lower for coherent narration
            2048,
            True,
        )

        return {
            "response": response,
            "api_used": api_used,
            "training_example": self._make_training_example(
                query, response, MODALITY_VOICE, org_niche
            ),
        }

    # ------------------------------------------------------------------
    # Training example builder
    # ------------------------------------------------------------------

    def _make_training_example(
        self,
        query: str,
        response: str,
        modality: str,
        org_niche: str,
        operation: str = "",
    ) -> Dict[str, Any]:
        """
        Build a training example dict compatible with the training_data table.

        Quality score is heuristic:
        - code: uses code-specific signals (see CodeService.score_response_quality)
        - text/image/voice: based on response length and content richness

        Args:
            query: User query.
            response: Generated response.
            modality: Modality identifier.
            org_niche: Organisation niche.
            operation: Sub-operation for code (generate/review/explain).

        Returns:
            Training example dict.
        """
        op_tag = f"/{operation}" if operation else ""
        quality = self._heuristic_quality(response, modality)

        return {
            "instruction": f"[{modality.upper()}{op_tag.upper()}] {query}",
            "output": response,
            "input_text": "",
            "metadata": {
                "modality": modality,
                "operation": operation or modality,
                "niche": org_niche,
                "source": "modality_router",
            },
            "quality_score": quality,
        }

    def _heuristic_quality(self, response: str, modality: str) -> float:
        """
        Compute a heuristic quality score for a non-code modality response.

        Args:
            response: Response text.
            modality: Modality identifier.

        Returns:
            Float in [0.0, 1.0].
        """
        if not response:
            return 0.0

        word_count = len(response.split())

        # Base score from length
        if word_count < 20:
            base = 0.3
        elif word_count < 50:
            base = 0.6
        elif word_count < 200:
            base = 0.75
        else:
            base = 0.85

        # Voice: penalize presence of markdown/bullets
        if modality == MODALITY_VOICE:
            if re.search(r"[\*#\-]\s", response):
                base -= 0.1

        # Image: reward structured descriptions
        if modality == MODALITY_IMAGE:
            if re.search(r"\b(?:shows?|depicts?|contains?|illustrates?)\b", response, re.IGNORECASE):
                base += 0.05

        # Penalize generic refusals
        if re.search(r"\bI cannot|I don't know|I'm not able\b", response, re.IGNORECASE):
            base -= 0.3

        return max(0.0, min(1.0, round(base, 2)))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_modality_router: Optional[ModalityRouter] = None


def get_modality_router() -> ModalityRouter:
    """Return the lazily-initialised ModalityRouter singleton."""
    global _modality_router
    if _modality_router is None:
        _modality_router = ModalityRouter()
    return _modality_router
