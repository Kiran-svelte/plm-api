"""Statistics tracking and monitoring"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from collections import defaultdict

class StatsTracker:
    """Track statistics for data generation"""

    def __init__(self, stats_file: str = "./logs/stats.json"):
        self.stats_file = Path(stats_file)
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)

        # Initialize stats
        self.stats = {
            'session_start': datetime.now().isoformat(),
            'total_questions_generated': 0,
            'total_answers_generated': 0,
            'total_validated': 0,
            'total_accepted': 0,
            'total_rejected': 0,
            'api_calls': defaultdict(int),
            'topics_processed': [],
            'quality_scores': [],
            'errors': [],
            'generation_times': []
        }

        # Load existing stats if available
        self._load_stats()

    def _load_stats(self):
        """Load existing stats from file"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    saved_stats = json.load(f)
                    # Merge with current stats
                    for key in ['total_questions_generated', 'total_answers_generated',
                                'total_validated', 'total_accepted', 'total_rejected']:
                        if key in saved_stats:
                            self.stats[key] = saved_stats[key]
            except Exception as e:
                print(f"Warning: Could not load stats file: {e}")

    def increment(self, key: str, value: int = 1):
        """Increment a counter"""
        if key in self.stats:
            self.stats[key] += value
        else:
            self.stats[key] = value

    def add_api_call(self, api_name: str):
        """Track API call"""
        self.stats['api_calls'][api_name] += 1

    def add_quality_score(self, score: float):
        """Track quality score"""
        self.stats['quality_scores'].append(score)

    def add_topic(self, topic: str):
        """Track processed topic"""
        if topic not in self.stats['topics_processed']:
            self.stats['topics_processed'].append(topic)

    def add_error(self, error: str):
        """Track error"""
        self.stats['errors'].append({
            'timestamp': datetime.now().isoformat(),
            'error': error
        })

    def add_generation_time(self, time_seconds: float):
        """Track generation time"""
        self.stats['generation_times'].append(time_seconds)

    def get_summary(self) -> Dict[str, Any]:
        """Get statistics summary"""
        avg_quality = sum(self.stats['quality_scores']) / len(self.stats['quality_scores']) if self.stats['quality_scores'] else 0
        avg_time = sum(self.stats['generation_times']) / len(self.stats['generation_times']) if self.stats['generation_times'] else 0

        acceptance_rate = (self.stats['total_accepted'] / self.stats['total_validated'] * 100) if self.stats['total_validated'] > 0 else 0

        return {
            'total_examples': self.stats['total_accepted'],
            'total_generated': self.stats['total_questions_generated'],
            'acceptance_rate': f"{acceptance_rate:.1f}%",
            'avg_quality_score': f"{avg_quality:.2f}",
            'avg_generation_time': f"{avg_time:.2f}s",
            'topics_processed': len(self.stats['topics_processed']),
            'total_api_calls': sum(self.stats['api_calls'].values()),
            'errors': len(self.stats['errors'])
        }

    def save(self):
        """Save stats to file"""
        # Convert defaultdict to regular dict for JSON serialization
        stats_to_save = dict(self.stats)
        stats_to_save['api_calls'] = dict(stats_to_save['api_calls'])

        with open(self.stats_file, 'w') as f:
            json.dump(stats_to_save, f, indent=2)

    def print_summary(self):
        """Print statistics summary"""
        summary = self.get_summary()

        print("\n" + "="*50)
        print("📊 GENERATION STATISTICS")
        print("="*50)

        for key, value in summary.items():
            key_formatted = key.replace('_', ' ').title()
            print(f"{key_formatted:.<30} {value}")

        print("="*50 + "\n")
