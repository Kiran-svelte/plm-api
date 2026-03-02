"""Main entry point for PLM data generation"""
import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.utils import get_config, setup_logger
from src.generators.data_generator import DataGenerator

def main():
    """Main function"""

    parser = argparse.ArgumentParser(
        description="PLM - Private Language Model Data Generation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate data using default config
  python main.py generate

  # Generate with custom topics
  python main.py generate --topics "Python" "Web dev" "AI basics"

  # Generate 100 questions per topic
  python main.py generate --questions-per-topic 100

  # Use custom config file
  python main.py generate --config custom_config.yaml

  # Display current configuration
  python main.py config
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Generate command
    gen_parser = subparsers.add_parser('generate', help='Generate training data')
    gen_parser.add_argument(
        '--topics',
        nargs='+',
        help='Topics to generate data for (overrides config)'
    )
    gen_parser.add_argument(
        '--questions-per-topic',
        type=int,
        help='Number of questions per topic (overrides config)'
    )
    gen_parser.add_argument(
        '--output',
        help='Output file path (default: auto-generated)'
    )
    gen_parser.add_argument(
        '--config',
        help='Path to config file (default: configs/config.yaml)'
    )
    gen_parser.add_argument(
        '--no-validation',
        action='store_true',
        help='Disable quality validation (faster but lower quality)'
    )

    # Config command
    config_parser = subparsers.add_parser('config', help='Display configuration')
    config_parser.add_argument(
        '--file',
        help='Config file to display (default: configs/config.yaml)'
    )

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate configuration')
    validate_parser.add_argument(
        '--config',
        help='Path to config file (default: configs/config.yaml)'
    )

    args = parser.parse_args()

    # Load config
    config_path = None
    if hasattr(args, 'config') and args.config:
        config_path = args.config
    elif hasattr(args, 'file') and args.file:
        config_path = args.file

    config = get_config(config_path)

    # Setup logging
    logger = setup_logger(
        'plm',
        log_file=config.get('logging.file', './logs/plm.log'),
        level=config.get('logging.level', 'INFO')
    )

    # Execute command
    if args.command == 'generate':
        # Override config with args
        if args.no_validation:
            config.config['data_generation']['enable_validation'] = False

        # Create generator
        generator = DataGenerator()

        # Prepare arguments
        topics = args.topics if args.topics else None
        questions_per_topic = args.questions_per_topic
        output_file = args.output

        # Run generation
        logger.info("Starting data generation...")
        generator.run(
            topics=topics,
            questions_per_topic=questions_per_topic,
            output_file=output_file
        )

    elif args.command == 'config':
        # Display config
        print("\n" + "="*60)
        print("PLM Configuration")
        print("="*60)
        print(f"\nProject: {config.get('project.name')}")
        print(f"Version: {config.get('project.version')}")
        print(f"\nQuestion Generator API: {config.get('api.question_generator')}")
        print(f"Answer Generator API: {config.get('api.answer_generator')}")
        print(f"Quality Validator API: {config.get('api.quality_validator')}")
        print(f"\nQuestions per topic: {config.get('data_generation.questions_per_topic')}")
        print(f"Quality threshold: {config.get('data_generation.quality_threshold')}")
        print(f"Enable validation: {config.get('data_generation.enable_validation')}")
        print(f"\nTopics configured: {len(config.get('data_generation.topics', []))}")

        topics = config.get('data_generation.topics', [])
        if topics:
            print("\nTopics:")
            for i, topic in enumerate(topics[:5], 1):
                print(f"  {i}. {topic}")
            if len(topics) > 5:
                print(f"  ... and {len(topics) - 5} more")

        print("\n" + "="*60 + "\n")

    elif args.command == 'validate':
        # Validate config
        print("\nValidating configuration...")

        if config.validate():
            print("✅ Configuration is valid!\n")
            sys.exit(0)
        else:
            print("❌ Configuration is invalid!\n")
            print("Please check the errors above and update your .env file")
            sys.exit(1)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
