# PLM Quick Start Guide

Get your private AI model up and running in 30 minutes!

## Prerequisites

- Python 3.8+ installed
- OpenAI and/or Anthropic API keys
- Internet connection for data generation
- Google account (for Colab training)

## Step 1: Setup (5 minutes)

### Install Dependencies

```bash
cd D:\cmp\Plm
pip install -r requirements.txt
```

### Configure API Keys

Edit `.env` file:

```env
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here
OPENAI_API_KEY=sk-your-actual-key-here
```

### Customize Topics (Optional)

Edit `configs/config.yaml`:

```yaml
data_generation:
  topics:
    - "Python programming"
    - "Web development"
    # Add your topics here
```

## Step 2: Generate Training Data (1-3 hours)

### Validate Configuration

```bash
python main.py validate
```

You should see: ✅ Configuration is valid!

### Start Generation

```bash
# Generate with default settings (50 questions per topic)
python main.py generate

# Or specify custom settings
python main.py generate --questions-per-topic 100
```

**Expected output:**
- Progress bars for each topic
- Quality scores and acceptance rates
- Final JSON file in `data/processed/`

**Cost:** ~$30-60 for 10,000 examples

## Step 3: Train Model on Colab (4-8 hours)

### Upload to Colab

1. Go to [Google Colab](https://colab.research.google.com)
2. Upload `notebooks/train_model.ipynb`
3. Upload your `training_data_*.json` file

### Configure Training

In the notebook, set:

```python
MODEL_NAME = "meta-llama/Llama-3.2-3B-Instruct"  # Choose your size
TRAINING_DATA_FILE = "training_data_20260214_120000.json"  # Your file
```

### Start Training

1. Select Runtime → Change runtime type → GPU (T4)
2. Run all cells
3. Wait 4-8 hours
4. Download `my-private-model-v1` folder

**Cost:** Free with Colab (or $10/month for Pro)

## Step 4: Deploy with Ollama (5 minutes)

### Install Ollama

Download from [https://ollama.ai/download](https://ollama.ai/download)

### Place Trained Model

Extract downloaded model to:
```
D:\cmp\Plm\models\my-private-model-v1\
```

### Deploy

```bash
# Windows
deploy_ollama.bat

# Linux/Mac
chmod +x deploy_ollama.sh
./deploy_ollama.sh
```

You should see: ✅ Deployment successful!

## Step 5: Test Your Model (2 minutes)

### Run Tests

```bash
python test_model.py
```

See 3 sample questions answered by your model.

### Interactive Chat

```bash
python test_model.py --interactive
```

Chat with your model in real-time!

### Use in Code

```python
import ollama

response = ollama.chat(
    model='my-private-ai',
    messages=[
        {'role': 'user', 'content': 'What is Python?'}
    ]
)

print(response['message']['content'])
```

## Common Issues

### "No API key found"

Solution: Check `.env` file has correct keys

### "Out of memory" in Colab

Solution: Use smaller model (1B instead of 3B)

### "Model not found" in Ollama

Solution: Run deployment script again

### No responses or errors

Solution: Check Ollama is running (`ollama list`)

## Next Steps

1. **Test Thoroughly**: Ask many questions to evaluate quality
2. **Improve Data**: Generate more training data if needed
3. **Retrain**: Combine old and new data for better results
4. **Deploy**: Integrate into your applications
5. **Scale**: Create multiple specialized models

## Tips for Best Results

- Start with 100 examples to test the pipeline
- Use domain-specific topics for better expertise
- Enable quality validation (slower but better)
- Train for 3+ epochs for better quality
- Test on diverse questions before production

## Need Help?

1. Check `logs/plm.log` for errors
2. Review `logs/stats.json` for generation metrics
3. See README.md for detailed documentation
4. Verify API keys are correct and have credit

---

**Congratulations!** You now have your own private AI model! 🎉
