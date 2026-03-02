"""Configuration loader and manager"""
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any

class Config:
    """Configuration manager for PLM"""

    def __init__(self, config_path: str = None):
        """Initialize configuration"""
        # Load environment variables
        load_dotenv()

        # Set default config path
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "configs" / "config.yaml"

        # Load YAML config
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        # Override with environment variables
        self._load_env_overrides()

    def _load_env_overrides(self):
        """Override config with environment variables"""
        # API keys
        self.anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
        self.openai_api_key = os.getenv('OPENAI_API_KEY')

        # API selection
        question_api = os.getenv('QUESTION_GENERATOR_API')
        if question_api:
            self.config['api']['question_generator'] = question_api

        answer_api = os.getenv('ANSWER_GENERATOR_API')
        if answer_api:
            self.config['api']['answer_generator'] = answer_api

        validator_api = os.getenv('VALIDATOR_API')
        if validator_api:
            self.config['api']['quality_validator'] = validator_api

        # Data generation settings
        questions_per_topic = os.getenv('QUESTIONS_PER_TOPIC')
        if questions_per_topic:
            self.config['data_generation']['questions_per_topic'] = int(questions_per_topic)

        quality_threshold = os.getenv('QUALITY_THRESHOLD')
        if quality_threshold:
            self.config['data_generation']['quality_threshold'] = int(quality_threshold)

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot notation (e.g., 'api.claude.max_tokens')"""
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

        return value if value is not None else default

    def validate(self) -> bool:
        """Validate required configuration"""
        errors = []

        # Check API keys
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY not set")

        if not self.openai_api_key:
            errors.append("OPENAI_API_KEY not set")

        # Check if at least one API is properly configured
        if self.config['api']['question_generator'] not in ['openai', 'claude']:
            errors.append("Invalid QUESTION_GENERATOR_API")

        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            return False

        return True

    def __repr__(self):
        return f"<Config: {self.config['project']['name']} v{self.config['project']['version']}>"

# Global config instance
_config = None

def get_config(config_path: str = None) -> Config:
    """Get global config instance"""
    global _config
    if _config is None:
        _config = Config(config_path)
    return _config
