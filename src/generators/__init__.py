"""Generator modules for PLM"""
# Only import what's actually needed
try:
    from .question_generator import QuestionGenerator
    from .answer_generator import AnswerGenerator
    from .validator import QualityValidator
except ImportError:
    # Old modules need paid APIs, skip them
    QuestionGenerator = None
    AnswerGenerator = None
    QualityValidator = None

# Always import FREE API modules
from .free_api_clients import FreeAPIManager
from .continuous_engine import ContinuousLearningEngine

__all__ = ['FreeAPIManager', 'ContinuousLearningEngine']
