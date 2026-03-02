# Installation & Setup Guide

## 1. Install Dependencies

```bash
cd D:\cmp\Plm
pip install -r requirements.txt
```

This installs:
- anthropic (Claude API)
- openai (GPT API)
- transformers, torch (for training)
- Other utilities

## 2. Configure API Keys

### Get API Keys

**Claude (Anthropic):**
1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Go to API Keys section
4. Create a new key
5. Copy the key (starts with `sk-ant-`)

**OpenAI:**
1. Go to https://platform.openai.com/
2. Sign up or log in
3. Go to API Keys section
4. Create a new key
5. Copy the key (starts with `sk-`)

### Add Keys to .env

Edit `D:\cmp\Plm\.env`:

```env
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here
OPENAI_API_KEY=sk-your-actual-key-here
```

**Important**: Never commit `.env` to git! It's already in `.gitignore`.

## 3. Customize Topics

Edit `configs/config.yaml`:

```yaml
data_generation:
  topics:
    - "Python programming basics"
    - "Web development with React"
    - "Machine learning fundamentals"
    # Add 10-100 topics for your niche
```

**Tip**: More specific topics = better expertise

## 4. Verify Setup

```bash
python verify_setup.py
```

You should see all checks pass.

## 5. Test with Sample

Start with a small test:

```bash
python main.py generate --topics "Python basics" --questions-per-topic 5
```

This generates only 5 questions (costs ~$1) to test the pipeline.

## 6. Generate Full Dataset

```bash
python main.py generate
```

This uses your config.yaml topics and generates the full dataset.

**Note**: This will take 1-3 hours and cost $30-60 in API usage.

## Common Installation Issues

### "pip not found"

Install Python 3.8+ from https://python.org

### "Permission denied"

Windows: Run as Administrator
Linux/Mac: Use `sudo pip install` or virtual environment

### "SSL Error"

Windows: Install certificates
```
pip install --upgrade certifi
```

### "Out of disk space"

Need ~10GB free for dependencies and models

## Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install
pip install -r requirements.txt
```

## Next Steps

After setup:
1. See QUICKSTART.md for usage guide
2. See README.md for detailed documentation
3. Run `python main.py --help` for commands

---

Need help? Check verify_setup.py output for specific issues.
