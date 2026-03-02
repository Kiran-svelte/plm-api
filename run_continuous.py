"""Run the continuous learning engine"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.generators.continuous_engine import ContinuousLearningEngine
from src.utils import setup_logger, get_config

def main():
    """Run continuous learning"""

    # Setup logging
    config = get_config()
    logger = setup_logger(
        'plm.continuous',
        log_file=config.get('logging.file', './logs/continuous_learning.log'),
        level=config.get('logging.level', 'INFO')
    )

    # Create and run engine
    engine = ContinuousLearningEngine()

    try:
        engine.run()
    except KeyboardInterrupt:
        logger.info("\nStopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
