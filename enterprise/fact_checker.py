"""
Fact Checker - Multi-model verification and confidence scoring
Uses Groq + SambaNova + Gemini for real cross-model verification
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import List, Dict, Any, Optional
import logging
import asyncio
import re
from src.generators.free_api_clients import FreeAPIManager

logger = logging.getLogger(__name__)


class FactChecker:
    """Multi-model fact checking with real cross-model verification"""

    def __init__(self):
        """Initialize fact checker with all available API models."""
        try:
            self.api_manager = FreeAPIManager()
            # Discover which APIs are actually configured and available
            self.verification_apis: List[str] = []
            for api_name in ["groq", "sambanova", "gemini"]:
                if api_name in self.api_manager.clients:
                    self.verification_apis.append(api_name)
            self.ready = len(self.verification_apis) >= 1
            logger.info(
                f"Fact checker initialized with {len(self.verification_apis)} "
                f"verification models: {self.verification_apis}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize fact checker: {e}")
            self.ready = False
            self.verification_apis = []

    def is_ready(self) -> bool:
        """Check if fact checker is ready."""
        return self.ready

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def verify_answer(
        self,
        query: str,
        answer: str,
        context: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Verify an answer using real multi-model fact checking.

        Args:
            query: Original user query.
            answer: Generated answer to verify.
            context: Optional RAG context chunks used to produce the answer.

        Returns:
            List of per-claim verification results, each containing:
                - claim (str)
                - verified (bool)
                - confidence (float 0-1)
                - verdict (str)
                - source (str)
                - models_used (list[str])
                - models_agreed (bool)
                - per_model (list[dict])
        """
        if not self.ready:
            logger.warning("Fact checker not ready -- no API clients available")
            return []

        try:
            claims = await self._extract_claims(answer)
            if not claims:
                logger.info("No verifiable claims extracted from answer")
                return []

            # Verify every claim (sequentially to respect rate limits)
            fact_check_results: List[Dict[str, Any]] = []
            for claim in claims:
                result = await self._verify_claim(claim, context)
                fact_check_results.append(result)

            if fact_check_results:
                avg_conf = sum(r["confidence"] for r in fact_check_results) / len(fact_check_results)
                logger.info(
                    f"Fact checked {len(claims)} claims across "
                    f"{len(self.verification_apis)} models. "
                    f"Average confidence: {avg_conf:.2f}"
                )
            return fact_check_results

        except Exception as e:
            logger.error(f"Fact checking failed: {e}")
            return []

    # ------------------------------------------------------------------
    # AI-based claim extraction
    # ------------------------------------------------------------------

    async def _extract_claims(self, answer: str) -> List[str]:
        """
        Extract verifiable factual claims from *answer* using an LLM.

        Falls back to simple sentence splitting if the API call fails.
        """
        if not answer or len(answer.strip()) < 30:
            return []

        prompt = (
            "Extract the key factual claims from the following text. "
            "Return each claim on its own line, prefixed with \"- \". "
            "Only extract objectively verifiable factual statements -- "
            "skip opinions, questions, and vague language. "
            "Return at most 5 claims.\n\n"
            f"Text: {answer}\n\n"
            "Claims:"
        )

        try:
            if not self.verification_apis:
                raise ValueError("No verification APIs available")
            # Prefer the first available API for extraction (cheap, fast)
            extraction_api = self.verification_apis[0]
            response = await self._call_api(extraction_api, prompt, temperature=0.1)

            claims = self._parse_claim_list(response)
            if claims:
                logger.debug(f"AI extracted {len(claims)} claims via {extraction_api}")
                return claims[:5]
        except Exception as e:
            logger.warning(f"AI claim extraction failed, falling back to heuristic: {e}")

        # ---- Fallback: simple sentence heuristic ----
        return self._extract_claims_heuristic(answer)

    @staticmethod
    def _parse_claim_list(text: str) -> List[str]:
        """Parse a bullet-list response into individual claim strings."""
        claims: List[str] = []
        for line in text.splitlines():
            line = line.strip()
            # Accept lines starting with "- ", "* ", or a digit+period
            cleaned = re.sub(r"^[-*]\s+|^\d+[.)]\s*", "", line).strip()
            if cleaned and len(cleaned) > 15:
                # Drop anything that looks like a meta-instruction rather than a claim
                if cleaned.lower().startswith(("here are", "the following", "note:")):
                    continue
                claims.append(cleaned)
        return claims

    @staticmethod
    def _extract_claims_heuristic(answer: str) -> List[str]:
        """Simple sentence-split fallback for claim extraction."""
        sentences = re.split(r"(?<=[.!])\s+", answer)
        claims: List[str] = []
        for sent in sentences:
            sent = sent.strip()
            if len(sent) > 20 and not sent.endswith("?"):
                claims.append(sent)
            if len(claims) >= 5:
                break
        return claims[:5]

    # ------------------------------------------------------------------
    # Per-claim verification across ALL available models
    # ------------------------------------------------------------------

    async def _verify_claim(
        self,
        claim: str,
        context: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Verify a single claim by querying every available API in parallel
        and aggregating their verdicts via majority vote.
        """
        # Build context snippet
        context_text = ""
        if context:
            snippets = [c.get("content", "")[:200] for c in context[:3]]
            context_text = "\n".join(snippets)

        prompt = (
            "You are a rigorous fact checker. Determine whether the "
            "following claim is accurate.\n\n"
            f"Claim: {claim}\n\n"
            "Supporting context (may be incomplete):\n"
            f"{context_text if context_text else 'No context provided.'}\n\n"
            "Respond with EXACTLY one line in this format:\n"
            "<VERDICT>|<CONFIDENCE>|<EXPLANATION>\n\n"
            "Where:\n"
            "  VERDICT    = VERIFIED  or  UNVERIFIED  or  UNCERTAIN\n"
            "  CONFIDENCE = a decimal between 0.0 and 1.0\n"
            "  EXPLANATION = one-sentence justification\n\n"
            "Example: VERIFIED|0.92|The claim matches well-documented medical consensus."
        )

        # Fire requests to ALL available models concurrently
        tasks = [
            self._get_verification(api_name, prompt)
            for api_name in self.verification_apis
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Parse every model's response
        per_model: List[Dict[str, Any]] = []
        for api_name, raw in zip(self.verification_apis, raw_results):
            entry = self._parse_verification(api_name, raw)
            per_model.append(entry)

        # ---- Majority vote aggregation ----
        valid_entries = [e for e in per_model if e["verdict"] != "ERROR"]
        num_valid = len(valid_entries)

        if num_valid == 0:
            return {
                "claim": claim,
                "verified": False,
                "confidence": 0.0,
                "verdict": "ERROR",
                "source": "multi-model-verification",
                "models_used": self.verification_apis,
                "models_agreed": False,
                "per_model": per_model,
            }

        verified_count = sum(1 for e in valid_entries if e["verdict"] == "VERIFIED")
        unverified_count = sum(1 for e in valid_entries if e["verdict"] == "UNVERIFIED")
        uncertain_count = sum(1 for e in valid_entries if e["verdict"] == "UNCERTAIN")

        # Determine winning verdict
        if verified_count > num_valid / 2:
            final_verdict = "VERIFIED"
            verified = True
        elif unverified_count > num_valid / 2:
            final_verdict = "UNVERIFIED"
            verified = False
        else:
            final_verdict = "UNCERTAIN"
            verified = False

        # Weighted average confidence (all valid responses)
        avg_confidence = (
            sum(e["confidence"] for e in valid_entries) / num_valid
        )

        # Did every model agree on the same verdict?
        unique_verdicts = {e["verdict"] for e in valid_entries}
        models_agreed = len(unique_verdicts) == 1

        return {
            "claim": claim,
            "verified": verified,
            "confidence": round(avg_confidence, 4),
            "verdict": final_verdict,
            "source": "multi-model-verification",
            "models_used": [e["api"] for e in valid_entries],
            "models_agreed": models_agreed,
            "per_model": per_model,
        }

    # ------------------------------------------------------------------
    # Single-model verification call
    # ------------------------------------------------------------------

    async def _get_verification(self, api_name: str, prompt: str) -> str:
        """
        Call a specific API for verification.

        The underlying FreeAPIManager.chat() is synchronous (uses
        ``requests``), so we run it in a thread to avoid blocking the
        event loop and to enable true parallelism across APIs.
        """
        try:
            response = await self._call_api(
                api_name, prompt, temperature=0.1, enable_fallback=False,
            )
            return response
        except Exception as e:
            logger.error(f"Verification call to {api_name} failed: {e}")
            raise

    async def _call_api(
        self,
        api_name: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        enable_fallback: bool = True,
    ) -> str:
        """
        Thin async wrapper around FreeAPIManager.chat().

        Runs the blocking HTTP call in an executor thread so that
        multiple API calls can proceed concurrently with asyncio.gather.
        """
        messages = [{"role": "user", "content": prompt}]
        loop = asyncio.get_running_loop()
        response, _api_used = await loop.run_in_executor(
            None,
            lambda: self.api_manager.chat(
                api_name,
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_fallback=enable_fallback,
            ),
        )
        return response

    # ------------------------------------------------------------------
    # Response parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_verification(api_name: str, raw) -> Dict[str, Any]:
        """Parse a raw verification response (or exception) into a dict."""
        if isinstance(raw, Exception):
            return {
                "api": api_name,
                "verdict": "ERROR",
                "confidence": 0.0,
                "explanation": str(raw),
            }

        # Expect format: VERDICT|CONFIDENCE|EXPLANATION
        try:
            # Take only the first non-empty line that contains '|'
            for line in str(raw).splitlines():
                line = line.strip()
                if "|" in line:
                    parts = line.split("|", 2)
                    if len(parts) >= 2:
                        verdict_raw = parts[0].strip().upper()
                        confidence_raw = parts[1].strip()
                        explanation = parts[2].strip() if len(parts) > 2 else ""

                        # Normalise verdict
                        if "VERIFIED" in verdict_raw and "UN" not in verdict_raw:
                            verdict = "VERIFIED"
                        elif "UNVERIFIED" in verdict_raw:
                            verdict = "UNVERIFIED"
                        else:
                            verdict = "UNCERTAIN"

                        # Clamp confidence to [0, 1]
                        try:
                            confidence = max(0.0, min(1.0, float(confidence_raw)))
                        except ValueError:
                            confidence = 0.5

                        return {
                            "api": api_name,
                            "verdict": verdict,
                            "confidence": confidence,
                            "explanation": explanation,
                        }
        except Exception:
            pass

        # If we could not parse the structured format, try to infer verdict
        text_upper = str(raw).upper()
        if "UNVERIFIED" in text_upper:
            verdict = "UNVERIFIED"
        elif "VERIFIED" in text_upper:
            verdict = "VERIFIED"
        else:
            verdict = "UNCERTAIN"

        return {
            "api": api_name,
            "verdict": verdict,
            "confidence": 0.5,
            "explanation": str(raw)[:200],
        }

    # ------------------------------------------------------------------
    # Training-data quality validation (kept from original)
    # ------------------------------------------------------------------

    async def validate_training_quality(
        self,
        instruction: str,
        output: str,
    ) -> Dict[str, Any]:
        """
        Validate quality of a training Q&A pair.

        Args:
            instruction: Training instruction / question.
            output: Training output / answer.

        Returns:
            Dict with score (float), validated (bool), api_used (str),
            and details (str).
        """
        try:
            prompt = (
                "Evaluate the quality of this Q&A pair for training an AI model.\n\n"
                f"Question: {instruction}\n\n"
                f"Answer: {output}\n\n"
                "Rate on a scale of 1-10 based on:\n"
                "1. Accuracy of information\n"
                "2. Completeness of answer\n"
                "3. Clarity and coherence\n"
                "4. Relevance to question\n"
                "5. Professional quality\n\n"
                "Respond with: <score>|<strengths>|<weaknesses>\n"
                "Example: 9|Comprehensive and accurate|Minor grammar issue"
            )

            # Use the first available API; let FreeAPIManager handle fallback
            primary_api = self.verification_apis[0] if self.verification_apis else "groq"
            messages = [{"role": "user", "content": prompt}]
            loop = asyncio.get_running_loop()
            response, api_used = await loop.run_in_executor(
                None,
                lambda: self.api_manager.chat(
                    primary_api,
                    messages,
                    temperature=0.3,
                    enable_fallback=True,
                ),
            )

            # Parse response
            score = 8.0  # sensible default
            parts = response.split("|")
            if parts:
                try:
                    score = float(parts[0].strip())
                except ValueError:
                    pass

            return {
                "score": score,
                "validated": score >= 7.0,
                "api_used": api_used,
                "details": response,
            }

        except Exception as e:
            logger.error(f"Quality validation failed: {e}")
            return {
                "score": 5.0,
                "validated": False,
                "error": str(e),
            }
