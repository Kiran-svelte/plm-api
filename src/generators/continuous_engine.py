"""Continuous learning engine - The core autonomous system"""
import time
import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from collections import deque

from .free_api_clients import FreeAPIManager
from ..utils import get_logger, get_config, StatsTracker

logger = get_logger(__name__)

class ContinuousLearningEngine:
    """Autonomous continuous learning system"""

    def __init__(self):
        """Initialize the continuous learning engine"""
        self.config = get_config()
        self.api_manager = FreeAPIManager()
        self.stats = StatsTracker()

        # Settings
        self.continuous_mode = os.getenv("CONTINUOUS_MODE", "true").lower() == "true"
        self.auto_train_threshold = int(os.getenv("AUTO_TRAIN_THRESHOLD", "1000"))
        self.generation_interval = int(os.getenv("GENERATION_INTERVAL", "30"))
        self.max_daily_examples = int(os.getenv("MAX_DAILY_EXAMPLES", "5000"))
        self.min_quality_score = int(os.getenv("MIN_QUALITY_SCORE", "6"))

        # Self-healing
        self.enable_fallback = os.getenv("ENABLE_FALLBACK", "true").lower() == "true"
        self.max_retries = int(os.getenv("MAX_RETRIES", "5"))
        self.auto_recovery = os.getenv("AUTO_RECOVERY", "true").lower() == "true"

        # API selection
        self.question_api = os.getenv("QUESTION_GENERATOR_API", "groq")
        self.answer_api = os.getenv("ANSWER_GENERATOR_API", "sambanova")
        self.validator_api = os.getenv("VALIDATOR_API", "gemini")

        # Storage
        self.training_data = []
        self.daily_count = 0
        self.last_health_check = time.time()
        self.errors = deque(maxlen=100)  # Keep last 100 errors

        # State
        self.running = False
        self.total_generated = 0

        logger.info("=" * 60)
        logger.info("Continuous Learning Engine Initialized")
        logger.info("=" * 60)
        logger.info(f"Mode: {'CONTINUOUS' if self.continuous_mode else 'MANUAL'}")
        logger.info(f"Auto-train threshold: {self.auto_train_threshold} examples")
        logger.info(f"Generation interval: {self.generation_interval}s")
        logger.info(f"Max daily examples: {self.max_daily_examples}")
        logger.info(f"APIs: Q={self.question_api}, A={self.answer_api}, V={self.validator_api}")
        logger.info("=" * 60)

    def health_check(self) -> bool:
        """Perform health check on all systems"""
        logger.info("Running health check...")

        try:
            # Check APIs
            api_health = self.api_manager.health_check()

            all_healthy = all(api_health.values())

            if all_healthy:
                logger.info("✓ All systems healthy")
            else:
                unhealthy = [k for k, v in api_health.items() if not v]
                logger.warning(f"✗ Unhealthy APIs: {unhealthy}")

            self.last_health_check = time.time()
            return all_healthy

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def generate_question(self, topic: str) -> str | None:
        """Generate a single question"""
        try:
            messages = [{
                "role": "user",
                "content": f"""Generate ONE specific, practical question about: {topic}

Requirements:
- Clear and specific
- Practical and useful
- Not too basic, not too advanced
- Good for training an AI

Return ONLY the question, nothing else."""
            }]

            response, api_used = self.api_manager.chat(
                self.question_api,
                messages,
                temperature=0.8,
                max_tokens=200,
                enable_fallback=self.enable_fallback
            )

            question = response.strip()
            self.stats.add_api_call(api_used)

            logger.debug(f"Generated question via {api_used}: {question[:50]}...")
            return question

        except Exception as e:
            logger.error(f"Failed to generate question: {e}")
            self.errors.append({"type": "question_gen", "error": str(e), "time": datetime.now().isoformat()})
            return None

    def generate_answer(self, question: str) -> str | None:
        """Generate answer for a question"""
        try:
            messages = [{
                "role": "user",
                "content": f"""Provide a comprehensive, expert answer to this question:

{question}

Requirements:
- Be detailed and accurate
- Include examples if relevant
- Be clear and well-structured
- Provide practical value"""
            }]

            response, api_used = self.api_manager.chat(
                self.answer_api,
                messages,
                temperature=0.7,
                max_tokens=1500,
                enable_fallback=self.enable_fallback
            )

            self.stats.add_api_call(api_used)
            logger.debug(f"Generated answer via {api_used} ({len(response)} chars)")
            return response

        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            self.errors.append({"type": "answer_gen", "error": str(e), "time": datetime.now().isoformat()})
            return None

    def validate_quality(self, question: str, answer: str) -> tuple[float, bool]:
        """Validate Q&A quality"""
        try:
            messages = [{
                "role": "user",
                "content": f"""Rate this Q&A pair on a scale of 1-10 based on:
- Question clarity (0-2)
- Answer accuracy (0-4)
- Answer completeness (0-2)
- Practical value (0-2)

Question: {question}

Answer: {answer}

Respond with ONLY a number from 1-10."""
            }]

            response, api_used = self.api_manager.chat(
                self.validator_api,
                messages,
                temperature=0.3,
                max_tokens=50,
                enable_fallback=self.enable_fallback
            )

            # Extract number
            score_str = ''.join(filter(str.isdigit, response))
            score = float(score_str) if score_str else 5.0
            score = max(1.0, min(10.0, score))  # Clamp between 1-10

            self.stats.add_api_call(api_used)
            self.stats.add_quality_score(score)

            is_acceptable = score >= self.min_quality_score

            logger.debug(f"Quality score: {score}/10 ({api_used}) - {'ACCEPTED' if is_acceptable else 'REJECTED'}")

            return score, is_acceptable

        except Exception as e:
            logger.warning(f"Validation failed: {e}, accepting by default")
            return 6.0, True  # Default to accepting if validation fails

    def generate_training_example(self, topic: str) -> Dict[str, Any] | None:
        """Generate one complete training example"""
        logger.info(f"Generating example for topic: {topic}")

        # Generate question
        question = self.generate_question(topic)
        if not question:
            return None

        self.stats.increment('total_questions_generated')

        # Generate answer
        answer = self.generate_answer(question)
        if not answer:
            return None

        self.stats.increment('total_answers_generated')

        # Validate
        score, is_acceptable = self.validate_quality(question, answer)
        self.stats.increment('total_validated')

        if not is_acceptable:
            self.stats.increment('total_rejected')
            logger.info(f"Example rejected (score: {score}/{self.min_quality_score})")
            return None

        self.stats.increment('total_accepted')

        # Create training example
        example = {
            "instruction": question,
            "output": answer,
            "metadata": {
                "topic": topic,
                "quality_score": score,
                "timestamp": datetime.now().isoformat(),
                "apis_used": {
                    "question": self.question_api,
                    "answer": self.answer_api,
                    "validator": self.validator_api
                }
            }
        }

        logger.info(f"✓ Example generated (score: {score}/10)")
        return example

    def save_training_data(self):
        """Save accumulated training data"""
        if not self.training_data:
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = Path(self.config.get('paths.processed_data_dir')) / f"continuous_training_{timestamp}.json"
        filename.parent.mkdir(parents=True, exist_ok=True)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.training_data, f, indent=2, ensure_ascii=False)

        logger.info(f"💾 Saved {len(self.training_data)} examples to {filename}")
        self.stats.save()

    def should_trigger_training(self) -> bool:
        """Check if we should trigger auto-training"""
        total_examples = len(self.training_data)

        if total_examples >= self.auto_train_threshold:
            logger.info(f"🎯 Training threshold reached: {total_examples}/{self.auto_train_threshold}")
            return True

        return False

    def trigger_training(self):
        """Trigger automatic training"""
        logger.info("=" * 60)
        logger.info("🚀 TRIGGERING AUTO-TRAINING")
        logger.info("=" * 60)

        # Save current data
        self.save_training_data()

        logger.info("Training would start here (not implemented in this demo)")
        logger.info("Next steps:")
        logger.info("1. Upload data to Colab")
        logger.info("2. Run training notebook")
        logger.info("3. Download trained model")
        logger.info("4. Update local model")

        # Reset for next batch
        self.training_data = []

    def run_generation_cycle(self):
        """Run one generation cycle"""
        topics = self.config.get('data_generation.topics', ['Python programming', 'Web development'])

        if not topics:
            logger.warning("No topics configured, skipping generation cycle")
            return

        # Pick random topic
        import random
        topic = random.choice(topics)

        # Generate example
        example = self.generate_training_example(topic)

        if example:
            self.training_data.append(example)
            self.total_generated += 1
            self.daily_count += 1

            logger.info(f"📊 Progress: {len(self.training_data)}/{self.auto_train_threshold} | Today: {self.daily_count}/{self.max_daily_examples}")

            # Check if we should trigger training
            if self.should_trigger_training():
                self.trigger_training()

            # Save periodically
            if len(self.training_data) % 50 == 0:
                self.save_training_data()

    def run(self):
        """Main continuous learning loop"""
        logger.info("\n" + "=" * 60)
        logger.info("🤖 STARTING CONTINUOUS LEARNING ENGINE")
        logger.info("=" * 60)

        self.running = True

        # Initial health check
        if not self.health_check():
            logger.warning("Initial health check failed, but continuing...")

        logger.info("\n🔄 Entering continuous learning loop...")
        logger.info("Press Ctrl+C to stop\n")

        try:
            cycle = 0
            while self.running:
                cycle += 1
                logger.info(f"\n--- Cycle {cycle} ---")

                # Check daily limit
                if self.daily_count >= self.max_daily_examples:
                    logger.info(f"Daily limit reached ({self.max_daily_examples}), pausing until tomorrow")
                    time.sleep(3600)  # Sleep 1 hour
                    continue

                # Run generation
                try:
                    self.run_generation_cycle()
                except Exception as e:
                    logger.error(f"Error in generation cycle: {e}")
                    self.errors.append({"type": "cycle", "error": str(e), "time": datetime.now().isoformat()})

                    if self.auto_recovery:
                        logger.info("Auto-recovery enabled, continuing...")
                        time.sleep(self.generation_interval * 2)
                    else:
                        raise

                # Health check periodically
                if time.time() - self.last_health_check > 600:  # Every 10 min
                    self.health_check()

                # Wait before next cycle
                time.sleep(self.generation_interval)

        except KeyboardInterrupt:
            logger.info("\n\n🛑 Stopping continuous learning engine...")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
        finally:
            self.stop()

    def stop(self):
        """Stop the engine and cleanup"""
        self.running = False

        logger.info("\n" + "=" * 60)
        logger.info("📊 FINAL STATISTICS")
        logger.info("=" * 60)

        self.stats.print_summary()

        # Save final data
        if self.training_data:
            self.save_training_data()

        logger.info("\n✅ Continuous learning engine stopped")
