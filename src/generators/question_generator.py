"""Question generation module supporting multiple APIs"""
import json
import time
from typing import List, Dict, Any
from anthropic import Anthropic
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..utils import get_logger, get_config

logger = get_logger(__name__)

class QuestionGenerator:
    """Generate questions using OpenAI or Claude API"""

    def __init__(self):
        """Initialize question generator"""
        self.config = get_config()

        # Get API selection
        self.api_type = self.config.get('api.question_generator', 'openai')

        # Initialize API clients
        if self.api_type == 'openai' or True:  # Always init both for flexibility
            self.openai_client = OpenAI(api_key=self.config.openai_api_key)
            self.openai_model = self.config.get('api.openai.question_model', 'gpt-4')

        if self.api_type == 'claude' or True:
            self.claude_client = Anthropic(api_key=self.config.anthropic_api_key)
            self.claude_model = self.config.get('api.claude.question_model', 'claude-sonnet-4-5-20241022')

        self.max_tokens = self.config.get('api.claude.max_tokens', 4000)
        self.temperature = self.config.get('api.claude.temperature', 0.7)

        logger.info(f"QuestionGenerator initialized with API: {self.api_type}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def generate_with_openai(self, topic: str, num_questions: int = 10) -> List[Dict[str, str]]:
        """Generate questions using OpenAI"""
        logger.debug(f"Generating {num_questions} questions about '{topic}' with OpenAI")

        prompt = f"""Generate {num_questions} diverse, high-quality questions about: {topic}

Requirements:
- Different difficulty levels (beginner, intermediate, advanced)
- Different question types (how-to, why, what, explain, compare, best practices)
- Practical and useful for learning
- Clear and specific
- No duplicate or very similar questions

Return as a JSON array ONLY (no other text):
[
  {{"question": "question 1"}},
  {{"question": "question 2"}},
  ...
]"""

        try:
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            content = response.choices[0].message.content.strip() if response.choices else None
            if not content:
                raise ValueError("OpenAI returned empty choices")

            # Extract JSON from response
            if '```json' in content:
                parts = content.split('```json')
                content = parts[1].split('```')[0].strip() if len(parts) > 1 else content
            elif '```' in content:
                parts = content.split('```')
                content = parts[1].split('```')[0].strip() if len(parts) > 1 else content

            questions = json.loads(content)
            logger.info(f"Generated {len(questions)} questions with OpenAI")

            return questions

        except Exception as e:
            logger.error(f"Error generating questions with OpenAI: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def generate_with_claude(self, topic: str, num_questions: int = 10) -> List[Dict[str, str]]:
        """Generate questions using Claude"""
        logger.debug(f"Generating {num_questions} questions about '{topic}' with Claude")

        prompt = f"""Generate {num_questions} diverse, high-quality questions about: {topic}

Requirements:
- Different difficulty levels (beginner, intermediate, advanced)
- Different question types (how-to, why, what, explain, compare, best practices)
- Practical and useful for learning
- Clear and specific
- No duplicate or very similar questions

Return as a JSON array ONLY (no other text):
[
  {{"question": "question 1"}},
  {{"question": "question 2"}},
  ...
]"""

        try:
            response = self.claude_client.messages.create(
                model=self.claude_model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text.strip() if response.content else None
            if not content:
                raise ValueError("Claude returned empty content")

            # Extract JSON from response
            if '```json' in content:
                parts = content.split('```json')
                content = parts[1].split('```')[0].strip() if len(parts) > 1 else content
            elif '```' in content:
                parts = content.split('```')
                content = parts[1].split('```')[0].strip() if len(parts) > 1 else content

            questions = json.loads(content)
            logger.info(f"Generated {len(questions)} questions with Claude")

            return questions

        except Exception as e:
            logger.error(f"Error generating questions with Claude: {e}")
            raise

    def generate(self, topic: str, num_questions: int = 10) -> List[Dict[str, str]]:
        """Generate questions using configured API"""

        if self.api_type == 'openai':
            return self.generate_with_openai(topic, num_questions)
        elif self.api_type == 'claude':
            return self.generate_with_claude(topic, num_questions)
        else:
            raise ValueError(f"Unknown API type: {self.api_type}")

    def generate_batch(self, topics: List[str], questions_per_topic: int = 10) -> Dict[str, List[Dict[str, str]]]:
        """Generate questions for multiple topics"""
        logger.info(f"Generating questions for {len(topics)} topics")

        results = {}

        for i, topic in enumerate(topics, 1):
            logger.info(f"Processing topic {i}/{len(topics)}: {topic}")

            try:
                questions = self.generate(topic, questions_per_topic)
                results[topic] = questions

                # Rate limiting
                time.sleep(1)

            except Exception as e:
                logger.error(f"Failed to generate questions for '{topic}': {e}")
                results[topic] = []

        return results
