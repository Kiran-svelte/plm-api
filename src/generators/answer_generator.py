"""Answer generation module supporting multiple APIs"""
import time
from typing import Dict, Any
from anthropic import Anthropic
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..utils import get_logger, get_config

logger = get_logger(__name__)

class AnswerGenerator:
    """Generate answers using OpenAI or Claude API"""

    def __init__(self):
        """Initialize answer generator"""
        self.config = get_config()

        # Get API selection
        self.api_type = self.config.get('api.answer_generator', 'claude')

        # Initialize API clients
        if self.api_type == 'openai' or True:
            self.openai_client = OpenAI(api_key=self.config.openai_api_key)
            self.openai_model = self.config.get('api.openai.answer_model', 'gpt-4')

        if self.api_type == 'claude' or True:
            self.claude_client = Anthropic(api_key=self.config.anthropic_api_key)
            self.claude_model = self.config.get('api.claude.answer_model', 'claude-sonnet-4-5-20241022')

        self.max_tokens = self.config.get('api.claude.max_tokens', 4000)
        self.temperature = self.config.get('api.claude.temperature', 0.7)

        logger.info(f"AnswerGenerator initialized with API: {self.api_type}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def generate_with_openai(self, question: str) -> str:
        """Generate answer using OpenAI"""
        logger.debug(f"Generating answer with OpenAI for: {question[:50]}...")

        prompt = f"""Provide a comprehensive, expert-level answer to the following question:

{question}

Requirements:
- Be detailed and thorough
- Include examples where relevant
- Explain concepts clearly
- Use proper formatting (markdown)
- Be accurate and up-to-date
- Provide practical, actionable information"""

        try:
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            answer = response.choices[0].message.content.strip() if response.choices else None
            if not answer:
                raise ValueError("OpenAI returned empty choices")
            logger.debug(f"Generated answer ({len(answer)} chars) with OpenAI")

            return answer

        except Exception as e:
            logger.error(f"Error generating answer with OpenAI: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def generate_with_claude(self, question: str) -> str:
        """Generate answer using Claude"""
        logger.debug(f"Generating answer with Claude for: {question[:50]}...")

        prompt = f"""Provide a comprehensive, expert-level answer to the following question:

{question}

Requirements:
- Be detailed and thorough
- Include examples where relevant
- Explain concepts clearly
- Use proper formatting (markdown)
- Be accurate and up-to-date
- Provide practical, actionable information"""

        try:
            response = self.claude_client.messages.create(
                model=self.claude_model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}]
            )

            answer = response.content[0].text.strip() if response.content else None
            if not answer:
                raise ValueError("Claude returned empty content")
            logger.debug(f"Generated answer ({len(answer)} chars) with Claude")

            return answer

        except Exception as e:
            logger.error(f"Error generating answer with Claude: {e}")
            raise

    def generate(self, question: str) -> str:
        """Generate answer using configured API"""

        if self.api_type == 'openai':
            return self.generate_with_openai(question)
        elif self.api_type == 'claude':
            return self.generate_with_claude(question)
        else:
            raise ValueError(f"Unknown API type: {self.api_type}")

    def generate_batch(self, questions: list) -> list:
        """Generate answers for multiple questions"""
        logger.info(f"Generating answers for {len(questions)} questions")

        answers = []

        for i, question in enumerate(questions, 1):
            logger.info(f"Processing question {i}/{len(questions)}")

            try:
                answer = self.generate(question)
                answers.append(answer)

                # Rate limiting
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Failed to generate answer: {e}")
                answers.append(None)

        return answers
