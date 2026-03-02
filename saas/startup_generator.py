"""
Automated Data Generation for Each Startup
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.generators.continuous_engine import ContinuousLearningEngine
from src.utils import setup_logger
import os
import json

class StartupDataGenerator:
    """Generate training data for a specific startup"""

    def __init__(self, startup_id: str, workspace: Path):
        self.startup_id = startup_id
        self.workspace = Path(workspace)
        self.config_file = self.workspace / "config.json"

        # Load startup config
        with open(self.config_file, 'r') as f:
            self.config = json.load(f)

        # Setup logging
        log_file = self.workspace / "generation.log"
        self.logger = setup_logger(
            f'plm.startup.{startup_id}',
            log_file=str(log_file),
            level='INFO'
        )

        self.logger.info(f"Initialized for {self.config['name']}")

    def generate_batch(self, num_examples: int = 100):
        """Generate a batch of training examples"""
        self.logger.info(f"Starting generation of {num_examples} examples")

        # Create custom engine for this startup
        engine = ContinuousLearningEngine()

        # Override topics with startup-specific ones
        topics = self.config['topics']

        self.logger.info(f"Topics: {topics}")

        generated = []
        for i in range(num_examples):
            import random
            topic = random.choice(topics)

            try:
                example = engine.generate_training_example(topic)

                if example:
                    generated.append(example)
                    self.logger.info(f"Generated {len(generated)}/{num_examples}")

                    # Save periodically
                    if len(generated) % 10 == 0:
                        self._save_data(generated)

            except Exception as e:
                self.logger.error(f"Error generating example: {e}")

        # Final save
        self._save_data(generated)

        # Update startup stats
        self._update_stats(len(generated))

        self.logger.info(f"Generation complete: {len(generated)} examples")
        return generated

    def _save_data(self, data: list):
        """Save training data"""
        output_file = self.workspace / "training_data.json"

        # Load existing if any
        existing = []
        if output_file.exists():
            with open(output_file, 'r') as f:
                existing = json.load(f)

        # Merge
        existing.extend(data)

        # Save
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved {len(existing)} examples to {output_file}")

    def _update_stats(self, count: int):
        """Update generation stats"""
        stats_file = self.workspace / "stats.json"

        stats = {
            "total_generated": count,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(stats_file, 'w') as f:
            json.dump(stats, f, indent=2)

        # Update global clients.json
        clients_file = Path("./clients.json")
        if clients_file.exists():
            with open(clients_file, 'r') as f:
                clients = json.load(f)

            if self.startup_id in clients:
                clients[self.startup_id]['data_generated'] = count

                with open(clients_file, 'w') as f:
                    json.dump(clients, f, indent=2)

if __name__ == "__main__":
    # Example: Generate for a specific startup
    import sys

    if len(sys.argv) < 2:
        print("Usage: python startup_generator.py <startup_id> [num_examples]")
        sys.exit(1)

    startup_id = sys.argv[1]
    num_examples = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    workspace = Path(f"./workspaces/{startup_id}")

    if not workspace.exists():
        print(f"Error: Startup {startup_id} not found")
        sys.exit(1)

    generator = StartupDataGenerator(startup_id, workspace)
    generator.generate_batch(num_examples)
