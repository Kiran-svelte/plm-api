"""Main data generation pipeline orchestrator"""
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from tqdm import tqdm

from ..generators import QuestionGenerator, AnswerGenerator, QualityValidator
from ..utils import get_logger, get_config, StatsTracker

logger = get_logger(__name__)

class DataGenerator:
    """Main orchestrator for data generation pipeline"""

    def __init__(self):
        """Initialize data generator"""
        self.config = get_config()

        # Initialize components
        self.question_gen = QuestionGenerator()
        self.answer_gen = AnswerGenerator()
        self.validator = QualityValidator()

        # Stats tracking
        self.stats = StatsTracker(self.config.get('logging.stats_file', './logs/stats.json'))

        # Settings
        self.enable_validation = self.config.get('data_generation.enable_validation', True)
        self.save_interval = self.config.get('data_generation.save_interval', 100)

        # Storage
        self.training_data = []
        self.rejected_data = []

        logger.info("DataGenerator initialized")

    def generate_qa_pair(self, question: str) -> Dict[str, Any] | None:
        """Generate a single Q&A pair with validation"""
        start_time = time.time()

        try:
            # Generate answer
            logger.debug(f"Generating answer for: {question[:50]}...")
            answer = self.answer_gen.generate(question)

            self.stats.increment('total_answers_generated')
            self.stats.add_api_call(self.answer_gen.api_type)

            # Basic validation
            if not self.validator.basic_validation(question, answer):
                logger.debug("Failed basic validation")
                self.stats.increment('total_rejected')
                return None

            # Advanced validation (optional)
            if self.enable_validation:
                validation = self.validator.validate(question, answer)

                self.stats.increment('total_validated')
                self.stats.add_api_call(self.validator.api_type)
                self.stats.add_quality_score(validation['score'])

                if not validation['is_acceptable']:
                    logger.debug(f"Failed quality validation: {validation['reason']}")
                    self.stats.increment('total_rejected')

                    self.rejected_data.append({
                        'question': question,
                        'answer': answer,
                        'validation': validation,
                        'timestamp': datetime.now().isoformat()
                    })

                    return None

                # Create training pair
                pair = {
                    'instruction': question,
                    'output': answer,
                    'metadata': {
                        'quality_score': validation['score'],
                        'quality_reason': validation['reason'],
                        'timestamp': datetime.now().isoformat(),
                        'question_api': self.question_gen.api_type,
                        'answer_api': self.answer_gen.api_type
                    }
                }

            else:
                # No validation - just create pair
                pair = {
                    'instruction': question,
                    'output': answer,
                    'metadata': {
                        'timestamp': datetime.now().isoformat(),
                        'question_api': self.question_gen.api_type,
                        'answer_api': self.answer_gen.api_type
                    }
                }

            generation_time = time.time() - start_time
            self.stats.add_generation_time(generation_time)
            self.stats.increment('total_accepted')

            return pair

        except Exception as e:
            logger.error(f"Error generating Q&A pair: {e}")
            self.stats.add_error(str(e))
            return None

    def generate_for_topic(self, topic: str, num_questions: int = 50) -> List[Dict[str, Any]]:
        """Generate training data for a single topic"""
        logger.info(f"Generating data for topic: {topic}")

        # Generate questions
        logger.info(f"Generating {num_questions} questions...")
        questions_data = self.question_gen.generate(topic, num_questions)

        self.stats.increment('total_questions_generated', len(questions_data))
        self.stats.add_api_call(self.question_gen.api_type)
        self.stats.add_topic(topic)

        # Generate Q&A pairs
        topic_data = []

        for q_data in tqdm(questions_data, desc=f"Processing {topic}"):
            question = q_data.get('question') if isinstance(q_data, dict) else str(q_data)
            if not question:
                logger.debug("Skipping entry with no question")
                continue

            pair = self.generate_qa_pair(question)

            if pair:
                topic_data.append(pair)

            # Rate limiting
            time.sleep(0.5)

        logger.info(f"Generated {len(topic_data)} valid Q&A pairs for '{topic}'")

        return topic_data

    def generate_dataset(self, topics: List[str] = None, questions_per_topic: int = None) -> List[Dict[str, Any]]:
        """Generate complete training dataset"""
        # Use config defaults if not provided
        if topics is None:
            topics = self.config.get('data_generation.topics', [])

        if questions_per_topic is None:
            questions_per_topic = self.config.get('data_generation.questions_per_topic', 50)

        logger.info(f"Starting dataset generation for {len(topics)} topics")
        logger.info(f"Target: {questions_per_topic} questions per topic")

        # Generate data for each topic
        for i, topic in enumerate(topics, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Topic {i}/{len(topics)}: {topic}")
            logger.info(f"{'='*60}")

            try:
                topic_data = self.generate_for_topic(topic, questions_per_topic)
                self.training_data.extend(topic_data)

                # Save periodically
                if len(self.training_data) % self.save_interval == 0:
                    self.save_checkpoint()

            except Exception as e:
                logger.error(f"Error processing topic '{topic}': {e}")
                self.stats.add_error(f"Topic '{topic}': {str(e)}")

        logger.info(f"\n{'='*60}")
        logger.info(f"Dataset generation complete!")
        logger.info(f"Total examples generated: {len(self.training_data)}")
        logger.info(f"{'='*60}\n")

        return self.training_data

    def save_checkpoint(self):
        """Save current progress"""
        checkpoint_file = Path(self.config.get('paths.processed_data_dir')) / f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(self.training_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Checkpoint saved: {checkpoint_file} ({len(self.training_data)} examples)")

    def save_dataset(self, output_file: str = None):
        """Save final training dataset"""
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = Path(self.config.get('paths.processed_data_dir')) / f"training_data_{timestamp}.json"

        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Save training data
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.training_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Training dataset saved: {output_file}")
        logger.info(f"Total examples: {len(self.training_data)}")

        # Save rejected data
        if self.rejected_data:
            rejected_file = output_file.parent / f"rejected_{output_file.name}"
            with open(rejected_file, 'w', encoding='utf-8') as f:
                json.dump(self.rejected_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Rejected data saved: {rejected_file} ({len(self.rejected_data)} examples)")

        # Save stats
        self.stats.save()
        self.stats.print_summary()

        return output_file

    def run(self, topics: List[str] = None, questions_per_topic: int = None, output_file: str = None):
        """Run complete generation pipeline"""
        logger.info("="*60)
        logger.info("PLM DATA GENERATION PIPELINE")
        logger.info("="*60)

        # Generate dataset
        self.generate_dataset(topics, questions_per_topic)

        # Save results
        output_file = self.save_dataset(output_file)

        logger.info("\n✅ Data generation complete!")
        logger.info(f"📁 Output file: {output_file}")

        return output_file
