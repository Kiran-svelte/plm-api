"""Simple verification script to check PLM setup"""
import sys
from pathlib import Path

def check_structure():
    """Check if all required files and folders exist"""
    print("Checking PLM project structure...")
    print("="*60)

    required_files = [
        "main.py",
        "requirements.txt",
        "README.md",
        "QUICKSTART.md",
        ".env",
        ".env.example",
        ".gitignore",
        "Modelfile",
        "configs/config.yaml",
        "src/__init__.py",
        "src/utils/__init__.py",
        "src/utils/config.py",
        "src/utils/logger.py",
        "src/utils/stats.py",
        "src/generators/__init__.py",
        "src/generators/question_generator.py",
        "src/generators/answer_generator.py",
        "src/generators/validator.py",
        "src/generators/data_generator.py",
        "notebooks/train_model.ipynb",
        "test_model.py",
        "deploy_ollama.sh",
        "deploy_ollama.bat",
    ]

    required_dirs = [
        "src",
        "src/utils",
        "src/generators",
        "configs",
        "notebooks",
        "data",
        "data/raw",
        "data/processed",
        "models",
        "logs",
    ]

    missing_files = []
    missing_dirs = []

    # Check files
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)
        else:
            print(f"[OK] {file}")

    # Check directories
    for dir in required_dirs:
        if not Path(dir).exists():
            missing_dirs.append(dir)
        else:
            print(f"[OK] {dir}/")

    print("="*60)

    if missing_files or missing_dirs:
        print("\n[ERROR] Setup incomplete!")
        if missing_files:
            print("\nMissing files:")
            for f in missing_files:
                print(f"  - {f}")
        if missing_dirs:
            print("\nMissing directories:")
            for d in missing_dirs:
                print(f"  - {d}/")
        return False
    else:
        print("\n[OK] Project structure is complete!")
        return True

def check_dependencies():
    """Check if dependencies can be imported"""
    print("\n" + "="*60)
    print("Checking dependencies...")
    print("="*60)

    dependencies = {
        'anthropic': 'Anthropic API',
        'openai': 'OpenAI API',
        'yaml': 'YAML parser (PyYAML)',
        'dotenv': 'Environment loader (python-dotenv)',
        'tqdm': 'Progress bars',
        'rich': 'Rich terminal output',
    }

    missing = []
    installed = []

    for module, name in dependencies.items():
        try:
            __import__(module)
            installed.append(name)
            print(f"✓ {name}")
        except ImportError:
            missing.append(name)
            print(f"✗ {name}")

    print("="*60)

    if missing:
        print("\n⚠️  Missing dependencies!")
        print("\nInstall them with:")
        print("  pip install -r requirements.txt")
        return False
    else:
        print("\n✅ All dependencies installed!")
        return True

def check_config():
    """Check configuration"""
    print("\n" + "="*60)
    print("Checking configuration...")
    print("="*60)

    # Check .env file
    env_file = Path(".env")
    if not env_file.exists():
        print("✗ .env file not found")
        print("\n⚠️  Configuration incomplete!")
        print("\nCreate .env file with your API keys:")
        print("  cp .env.example .env")
        print("  # Then edit .env and add your keys")
        return False

    # Read .env and check for keys
    with open(".env") as f:
        content = f.read()

    has_anthropic = "ANTHROPIC_API_KEY=" in content and "sk-ant-" in content
    has_openai = "OPENAI_API_KEY=" in content and "sk-" in content

    if has_anthropic:
        print("✓ Anthropic API key configured")
    else:
        print("✗ Anthropic API key not configured")

    if has_openai:
        print("✓ OpenAI API key configured")
    else:
        print("✗ OpenAI API key not configured")

    print("="*60)

    if not (has_anthropic or has_openai):
        print("\n⚠️  No API keys configured!")
        print("\nEdit .env file and add at least one API key:")
        print("  ANTHROPIC_API_KEY=sk-ant-your-key-here")
        print("  OPENAI_API_KEY=sk-your-key-here")
        return False

    print("\n✅ Configuration looks good!")
    return True

def main():
    """Run all checks"""
    print("\n" + "="*60)
    print("PLM SETUP VERIFICATION")
    print("="*60)
    print()

    structure_ok = check_structure()
    deps_ok = check_dependencies()
    config_ok = check_config()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Project Structure: {'✅ OK' if structure_ok else '❌ Issues'}")
    print(f"Dependencies: {'✅ OK' if deps_ok else '❌ Missing'}")
    print(f"Configuration: {'✅ OK' if config_ok else '❌ Incomplete'}")
    print("="*60)

    if structure_ok and deps_ok and config_ok:
        print("\n🎉 PLM is ready to use!")
        print("\nNext steps:")
        print("  1. Review topics in configs/config.yaml")
        print("  2. Run: python main.py validate")
        print("  3. Run: python main.py generate")
        print("\nSee QUICKSTART.md for detailed instructions.")
        return 0
    else:
        print("\n⚠️  Setup incomplete. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
