"""Quality validation module for Q&A pairs"""
import re
from typing import Dict, Any, Tuple
from anthropic import Anthropic
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..utils import get_logger, get_config

logger = get_logger(__name__)

class QualityValidator:
    """Validate quality of generated Q&A pairs"""

    def __init__(self):
        """Initialize quality validator"""
        self.config = get_config()

        # Get API selection
        self.api_type = self.config.get('api.quality_validator', 'claude')

        # Initialize API clients
        if self.api_type == 'openai' or True:
            self.openai_client = OpenAI(api_key=self.config.openai_api_key)
            self.openai_model = self.config.get('api.openai.validator_model', 'gpt-4')

        if self.api_type == 'claude' or True:
            self.claude_client = Anthropic(api_key=self.config.anthropic_api_key)
            self.claude_model = self.config.get('api.claude.validator_model', 'claude-opus-4-5-20251101')

        self.quality_threshold = self.config.get('data_generation.quality_threshold', 7)

        logger.info(f"QualityValidator initialized with API: {self.api_type}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def validate_with_openai(self, question: str, answer: str) -> Tuple[float, str]:
        """Validate Q&A quality using OpenAI"""
        logger.debug(f"Validating Q&A with OpenAI")

        prompt = f"""Rate the quality of this Q&A pair on a scale of 1-10.

Question: {question}

Answer: {answer}

Evaluation criteria:
1. Question clarity and relevance (1-2 points)
2. Answer accuracy and completeness (1-4 points)
3. Answer clarity and structure (1-2 points)
4. Practical value and usefulness (1-2 points)

Respond in this exact format:
SCORE: [number 1-10]
REASON: [brief explanation]"""

        try:
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200
            )

            content = response.choices[0].message.content.strip() if response.choices else None
            if not content:
                raise ValueError("OpenAI returned empty choices")

            # Parse score and reason
            score_match = re.search(r'SCORE:\s*(\d+)', content)
            reason_match = re.search(r'REASON:\s*(.+)', content, re.DOTALL)

            score = float(score_match.group(1)) if score_match else 5.0
            reason = reason_match.group(1).strip() if reason_match else "No reason provided"

            logger.debug(f"Validation score: {score}/10")

            return score, reason

        except Exception as e:
            logger.error(f"Error validating with OpenAI: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def validate_with_claude(self, question: str, answer: str) -> Tuple[float, str]:
        """Validate Q&A quality using Claude"""
        logger.debug(f"Validating Q&A with Claude")

        prompt = f"""Rate the quality of this Q&A pair on a scale of 1-10.

Question: {question}

Answer: {answer}

Evaluation criteria:
1. Question clarity and relevance (1-2 points)
2. Answer accuracy and completeness (1-4 points)
3. Answer clarity and structure (1-2 points)
4. Practical value and usefulness (1-2 points)

Respond in this exact format:
SCORE: [number 1-10]
REASON: [brief explanation]"""

        try:
            response = self.claude_client.messages.create(
                model=self.claude_model,
                max_tokens=200,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text.strip() if response.content else None
            if not content:
                raise ValueError("Claude returned empty content")

            # Parse score and reason
            score_match = re.search(r'SCORE:\s*(\d+)', content)
            reason_match = re.search(r'REASON:\s*(.+)', content, re.DOTALL)

            score = float(score_match.group(1)) if score_match else 5.0
            reason = reason_match.group(1).strip() if reason_match else "No reason provided"

            logger.debug(f"Validation score: {score}/10")

            return score, reason

        except Exception as e:
            logger.error(f"Error validating with Claude: {e}")
            raise

    def validate(self, question: str, answer: str) -> Dict[str, Any]:
        """Validate Q&A pair quality"""

        if self.api_type == 'openai':
            score, reason = self.validate_with_openai(question, answer)
        elif self.api_type == 'claude':
            score, reason = self.validate_with_claude(question, answer)
        else:
            raise ValueError(f"Unknown API type: {self.api_type}")

        is_acceptable = score >= self.quality_threshold

        return {
            'score': score,
            'reason': reason,
            'is_acceptable': is_acceptable,
            'threshold': self.quality_threshold
        }

    def basic_validation(self, question: str, answer: str) -> bool:
        """Basic validation without API (fast)"""

        # Check minimum length
        if len(question) < 10:
            logger.debug("Question too short")
            return False

        if len(answer) < 50:
            logger.debug("Answer too short")
            return False

        # Check for common issues
        if "I don't know" in answer.lower():
            logger.debug("Answer contains 'I don't know'")
            return False

        if "I cannot" in answer.lower() or "I can't" in answer.lower():
            logger.debug("Answer contains rejection")
            return False

        return True
