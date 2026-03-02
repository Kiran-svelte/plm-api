# PLM v2.0 — Living AI Pet with Multi-Modal Private Language Models

Build your own **private, evolving AI assistant** that never leaks your data, learns from your domain, and grows through 6 evolution stages from Egg 🥚 to Legend 🐉.

> **v2.0 is live!** PLM now includes the Pet Personality Engine, Privacy Proxy, and Multi-Modal support (Text + Code + Image + Voice). See [PLM_V2_ARCHITECTURE.md](PLM_V2_ARCHITECTURE.md) for the full technical spec.

## What is PLM?

PLM (Private Language Models) is a complete enterprise AI platform for creating **specialized, continuously-learning private models** without sending your sensitive data to any third party. Each model has a living pet personality that evolves as it trains.

### Feature Comparison: v1 vs v2.0

| Feature | PLM v1 | PLM v2.0 |
|---------|--------|---------|
| **Modalities** | Text only | Text + Code + Image + Voice |
| **Privacy** | Runs on private infra | PII stripped before every API call |
| **Personality** | Static assistant | Living pet (Egg → Legend) |
| **Code support** | None | DeepSeek-R1 code gen + Qwen2.5 review |
| **Privacy audit** | None | Full privacy audit log |
| **Frontend** | Basic | Pet status, privacy badge, modality tabs |

### Key Features

- **🐣 Living AI Pet**: Models evolve through 6 stages (Egg → Hatchling → Juvenile → Adult → Master → Legend) based on real training metrics
- **🔒 Privacy Proxy**: PII is stripped from every query (email, phone, SSN, IP, company names) before it reaches any external API
- **🎯 Multi-Modal**: One system handles Text Q&A, Code generation/review, Image analysis, and Voice scripts
- **🧠 RAG-Enhanced**: Unlimited context through vector knowledge base (all-MiniLM-L6-v2, 384 dims)
- **✅ Fact-Checked**: Multi-model verification via Groq + SambaNova + Gemini
- **📈 Continuously Learning**: Learns from real usage and improves automatically
- **🏢 Multi-Tenant SaaS**: Full RBAC, per-org system prompts, billing tiers

## Architecture (v2.0)

```
┌─────────────────────────────────────────────────────────────────┐
│                         PLM v2.0                                │
│                                                                  │
│  User Query                                                      │
│      │                                                           │
│      ▼                                                           │
│  ┌──────────────────┐                                           │
│  │  Privacy Proxy   │  strips email, phone, SSN, IP, names      │
│  └────────┬─────────┘                                           │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │ Modality Router  │  text / code / image / voice              │
│  └──┬──────┬──┬──┬──┘                                           │
│     │  code│  │  │voice                                         │
│     ▼      ▼  ▼  ▼                                              │
│  text   code img  voice                                         │
│  Q&A   svc  desc  script                                        │
│     │      │  │  │                                              │
│     └──────┴──┴──┘                                              │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │    RAG System    │  shared knowledge base                    │
│  └────────┬─────────┘                                           │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │  FreeAPIManager  │  Groq / SambaNova / Gemini                │
│  │  OR fine-tuned   │  (receives only sanitized queries)        │
│  └────────┬─────────┘                                           │
│           ▼                                                      │
│  Privacy rehydration → Response to user                         │
│                                                                  │
│  ┌──────────────────┐                                           │
│  │ Pet Personality  │  stage/mood/XP updated from real metrics  │
│  └──────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
```

## Pet Evolution Guide

Your model evolves automatically as it trains:

| Stage | Emoji | Training Examples | Accuracy | Personality |
|-------|-------|-------------------|----------|-------------|
| Egg | 🥚 | 0 | — | Dormant |
| Hatchling | 🐣 | 50+ | — | Curious |
| Juvenile | 🐥 | 500+ | 60%+ | Eager |
| Adult | 🦅 | 2,000+ | 80%+ | Confident |
| Master | 🦁 | 10,000+ | 90%+ | Authoritative |
| Legend | 🐉 | 50,000+ | 95%+ | Sage |

## Privacy Guarantee

PLM v2.0 guarantees:

1. **Zero PII to external APIs** — The Privacy Proxy strips emails, phone numbers, SSNs, IP addresses, and company names from every query before it reaches Groq, SambaNova, or Gemini
2. **Training data is PII-free** — `sanitize_training_prompt()` applies extra-strict rules; PII keyword lines are removed entirely from training examples
3. **Full audit trail** — Every sanitization event is logged to `privacy_audit` table
4. **On-premise option** — Fine-tuned models run locally via Ollama (no external API calls at all)

## Multi-Modal Capabilities

```
POST /organizations/{org_id}/models/{model_id}/multi-modal

{
  "query": "Write a Python function to calculate compound interest",
  "modality": "code",    ← "text" | "code" | "image" | "voice" (auto-detected if omitted)
  "use_rag": true,
  "save_training_example": true
}
```

| Modality | Trigger | Engine |
|----------|---------|--------|
| Text | Default | Groq (with fallback) |
| Code | "write", "implement", "debug", etc. | DeepSeek-R1 via Groq |
| Image | "describe image", "analyze diagram", etc. | Groq + attachment detection |
| Voice | "voice script", "TTS", "podcast script", etc. | Groq (speech-optimized) |

## Quick Start

### 1. Installation

```bash
git clone https://github.com/Kiran-svelte/PLM
cd PLM
pip install -r requirements.txt
# or for minimal install:
pip install -r enterprise/requirements_light.txt
```

### 2. Configuration

```bash
cp .env.example .env
# Edit .env with your API keys:
# GROQ_API_KEY=...
# SAMBANOVA_API_KEY=...
# GEMINI_API_KEY=...
# SUPABASE_URL=...
# SUPABASE_ANON_KEY=...
```

### 3. Database Setup

```bash
# Run the schema (includes v2.0 tables: pet_status, privacy_audit, multi_modal_queries)
psql $DATABASE_URL < enterprise/db/schema.sql
```

### 4. Start the Backend

```bash
cd enterprise/backend
uvicorn api:app --reload --port 8000
```

### 5. Start the Frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

## Project Structure

```
PLM/
├── enterprise/
│   ├── backend/
│   │   └── api.py                  # FastAPI with RBAC + new endpoints
│   ├── db/
│   │   └── schema.sql              # Database schema (incl. v2.0 tables)
│   ├── tests/
│   │   ├── test_pet_personality.py # 51 unit tests
│   │   ├── test_privacy_proxy.py   # 24 unit tests
│   │   └── test_modality_router.py # 17 unit tests
│   ├── pet_personality.py          # 🆕 Living AI pet evolution engine
│   ├── privacy_proxy.py            # 🆕 PII sanitization layer
│   ├── modality_router.py          # 🆕 Multi-modal query router
│   ├── code_service.py             # 🆕 Code gen/review service
│   ├── rag_system.py               # Vector knowledge base
│   ├── fact_checker.py             # Multi-model verification
│   └── continuous_learner.py       # Usage-based learning
├── frontend/
│   ├── components/
│   │   ├── PetStatus.tsx           # 🆕 Pet evolution dashboard
│   │   ├── PrivacyBadge.tsx        # 🆕 Privacy mode indicator
│   │   ├── ModalitySelector.tsx    # 🆕 Text/Code/Image/Voice tabs
│   │   └── ChatPanel.tsx           # Main chat interface
│   └── app/
│       └── dashboard/page.tsx
├── src/
│   └── generators/
│       └── free_api_clients.py     # Groq, SambaNova, Gemini clients
├── PLM_V2_ARCHITECTURE.md          # 🆕 Detailed v2.0 technical spec
└── README.md                       # This file
```

## New API Endpoints (v2.0)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/organizations/{org_id}/models/{model_id}/pet-status` | Get pet evolution status |
| `POST` | `/organizations/{org_id}/models/{model_id}/multi-modal` | Multi-modal query |

## Running Tests

```bash
# Run all v2.0 unit tests (no external dependencies)
python -m pytest enterprise/tests/ -v

# 83 tests covering pet personality, privacy proxy, and modality router
```

## Roadmap

- [x] Pet Personality Engine (v2.0)
- [x] Privacy Proxy (v2.0)
- [x] Multi-Modal Router (v2.0)
- [x] Code Service with DeepSeek-R1 + Qwen2.5 (v2.0)
- [ ] Native image vision support (Claude Vision / GPT-4o)
- [ ] Voice-to-text input (Whisper integration)
- [ ] Pet NFT export
- [ ] Privacy audit dashboard in frontend
- [ ] Multi-modal training data UI

---

*PLM v2.0 — Your private AI that never stops growing.* 🐉



```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPENAI_API_KEY=sk-your-key-here
```

Edit `configs/config.yaml` to customize your topics:

```yaml
data_generation:
  topics:
    - "Your topic 1"
    - "Your topic 2"
    - "Your topic 3"
```

### 3. Generate Training Data

```bash
# Validate configuration
python main.py validate

# Generate data (this will take a while and use API credits)
python main.py generate

# Output: data/processed/training_data_TIMESTAMP.json
```

### 4. Train Model (on Google Colab)

1. Upload `training_data_*.json` to Google Colab
2. Upload `notebooks/train_model.ipynb` to Colab
3. Run all cells (takes 4-8 hours)
4. Download the trained model folder

### 5. Deploy to Ollama

```bash
# Windows
deploy_ollama.bat

# Linux/Mac
./deploy_ollama.sh
```

### 6. Use Your Model

```bash
# Test the model
python test_model.py

# Interactive chat
python test_model.py --interactive

# Use in your code
import ollama
response = ollama.chat(model='my-private-ai', messages=[...])
```

## Project Structure

```
Plm/
├── configs/
│   └── config.yaml              # Main configuration
├── src/
│   ├── generators/
│   │   ├── question_generator.py   # Question generation
│   │   ├── answer_generator.py     # Answer generation
│   │   ├── validator.py            # Quality validation
│   │   └── data_generator.py       # Main orchestrator
│   └── utils/
│       ├── config.py               # Config loader
│       ├── logger.py               # Logging
│       └── stats.py                # Statistics tracking
├── notebooks/
│   └── train_model.ipynb        # Colab training notebook
├── data/
│   ├── raw/                     # Raw data
│   └── processed/               # Training data
├── models/                      # Trained models
├── logs/                        # Logs and stats
├── main.py                      # Main entry point
├── test_model.py               # Model testing
├── deploy_ollama.bat           # Windows deployment
├── deploy_ollama.sh            # Linux/Mac deployment
├── Modelfile                   # Ollama configuration
├── requirements.txt            # Python dependencies
├── .env                        # API keys (DO NOT COMMIT!)
└── README.md                   # This file
```

## Usage

### Command Line Interface

```bash
# Generate data with default config
python main.py generate

# Generate with custom topics
python main.py generate --topics "Python" "Web dev" "AI"

# Generate 100 questions per topic
python main.py generate --questions-per-topic 100

# Skip quality validation (faster, lower quality)
python main.py generate --no-validation

# Show current configuration
python main.py config

# Validate configuration
python main.py validate
```

### Programmatic Usage

```python
from src.generators.data_generator import DataGenerator

# Create generator
generator = DataGenerator()

# Generate data
generator.run(
    topics=["Python", "Web dev"],
    questions_per_topic=50,
    output_file="./my_data.json"
)
```

## Configuration

### API Selection

Choose which API to use for each task in `.env`:

```env
QUESTION_GENERATOR_API=openai   # or "claude"
ANSWER_GENERATOR_API=claude     # or "openai"
VALIDATOR_API=claude            # or "openai"
```

**Recommended combinations:**

1. **Best Quality**: GPT-4 questions, Claude Opus answers
2. **Cost-Effective**: Claude Sonnet questions, Claude Sonnet answers
3. **Balanced**: GPT-4 questions, Claude Sonnet answers

### Topics

Edit `configs/config.yaml` to set your domain:

```yaml
data_generation:
  topics:
    - "Your specific topic 1"
    - "Your specific topic 2"
    # Add 10-100+ topics for best results
```

### Quality Threshold

Set minimum quality score (1-10):

```yaml
data_generation:
  quality_threshold: 7  # Only accept 7+ rated Q&A pairs
  enable_validation: true
```

## Cost Estimation

### Data Generation

For 10,000 training examples:

- **GPT-4 Questions**: ~$5-10
- **Claude Sonnet Answers**: ~$15-30
- **Claude Opus Validation**: ~$10-20
- **Total**: ~$30-60

### Training

- **Google Colab Free**: $0
- **Google Colab Pro**: $10/month
- **Paid GPU**: $5-20 per run

### Total Cost

**Complete pipeline**: ~$30-80 one-time cost

## Training Details

### Model Sizes

Choose based on your GPU:

| Model | Size | GPU Memory | Training Time | Colab Tier |
|-------|------|------------|---------------|------------|
| Llama 3.2 1B | 1GB | 8GB | 2-4 hours | Free |
| Llama 3.2 3B | 3GB | 15GB | 4-8 hours | Free |
| Llama 3.2 7B | 7GB | 24GB | 8-12 hours | Pro |

### Training Parameters

Configured in `notebooks/train_model.ipynb`:

- **Epochs**: 3 (increase for better quality)
- **Batch Size**: 4 (decrease if out of memory)
- **Learning Rate**: 2e-4
- **LoRA**: Efficient fine-tuning (saves memory)

## Tips & Best Practices

### Data Generation

1. **Start Small**: Generate 100 examples first to test
2. **Quality > Quantity**: Enable validation for better results
3. **Diverse Topics**: More topics = more versatile model
4. **Domain-Specific**: Focus on your niche for expertise

### Training

1. **Data Size**: 5,000-10,000 examples is ideal
2. **GPU Selection**: Use free Colab for 1-3B models
3. **Monitor Loss**: Should decrease steadily
4. **Save Checkpoints**: Don't lose progress!

### Deployment

1. **Test First**: Use `test_model.py` before production
2. **System Prompt**: Customize in `Modelfile`
3. **Parameters**: Adjust temperature for creativity
4. **Context Window**: Increase for longer conversations

## Troubleshooting

### "No API key found"

- Check `.env` file exists and has correct keys
- Keys should start with `sk-ant-` (Claude) or `sk-` (OpenAI)

### "Out of memory" during training

- Use smaller model (1B instead of 3B)
- Reduce batch size in notebook
- Use Colab Pro for more memory

### "Model not found" in Ollama

- Run deployment script first
- Check model is in `./models/` folder
- Ensure Ollama is running

### Low quality responses

- Generate more training data
- Increase quality threshold
- Use better models for data generation
- Train for more epochs

## Advanced Usage

### Continuous Improvement

Generate new data and retrain periodically:

```bash
# Generate more data
python main.py generate --output data/batch_2.json

# Combine with existing data
# Retrain on Colab with merged dataset
```

### Custom Validation

Edit `src/generators/validator.py` to add custom checks:

```python
def custom_validation(self, question, answer):
    # Your validation logic
    if "specific_keyword" not in answer:
        return False
    return True
```

### Multiple Models

Train different models for different purposes:

```bash
# Generate domain-specific datasets
python main.py generate --topics "Python coding" --output coding_data.json
python main.py generate --topics "Business strategy" --output business_data.json

# Train separate models on Colab
# Deploy with different names
```

## Security & Privacy

- API keys stay local (never committed to git)
- Training data is yours (stored locally)
- Final model runs offline (no data sent to APIs)
- No telemetry or tracking

## License

This project is provided as-is for educational and personal use.

## Support

For issues or questions:

1. Check this README
2. Review error logs in `./logs/`
3. Check API key validity
4. Ensure dependencies are installed

## Roadmap

- [ ] Web UI for easier setup
- [ ] Automatic hyperparameter tuning
- [ ] Multi-modal support (images)
- [ ] Model evaluation benchmarks
- [ ] Cloud training integration

---

**Made with ❤️ for building private AI models**
