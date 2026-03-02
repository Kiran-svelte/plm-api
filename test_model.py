"""Test your deployed Ollama model"""
import sys

try:
    import ollama
except ImportError:
    print("❌ Ollama Python package not installed!")
    print("\nInstall it with:")
    print("  pip install ollama")
    sys.exit(1)

MODEL_NAME = "my-private-ai"

def test_model():
    """Test the deployed model with sample questions"""

    print("="*60)
    print("Testing Your Private AI Model")
    print("="*60)
    print()

    # Check if model exists
    try:
        models = ollama.list()
        model_names = [m['name'] for m in models['models']]

        if MODEL_NAME not in model_names and f"{MODEL_NAME}:latest" not in model_names:
            print(f"❌ Model '{MODEL_NAME}' not found!")
            print("\nAvailable models:")
            for name in model_names:
                print(f"  - {name}")
            print("\nPlease run the deployment script first:")
            print("  Windows: deploy_ollama.bat")
            print("  Linux/Mac: ./deploy_ollama.sh")
            return

    except Exception as e:
        print(f"❌ Error connecting to Ollama: {e}")
        print("\nMake sure Ollama is running!")
        return

    # Test questions
    test_questions = [
        "What is Python?",
        "Explain machine learning in simple terms",
        "How do I create a web API?",
    ]

    print(f"✅ Model '{MODEL_NAME}' found!\n")
    print("Testing with sample questions...\n")

    for i, question in enumerate(test_questions, 1):
        print(f"{'='*60}")
        print(f"Test {i}/{len(test_questions)}")
        print(f"{'='*60}")
        print(f"Question: {question}\n")
        print("Answer:")

        try:
            response = ollama.chat(
                model=MODEL_NAME,
                messages=[
                    {"role": "user", "content": question}
                ]
            )

            answer = response['message']['content']
            print(answer)
            print()

        except Exception as e:
            print(f"❌ Error: {e}")
            print()

    print("="*60)
    print("Testing complete!")
    print("="*60)
    print()
    print("Your model is working! You can now:")
    print(f"  • Use it in your code: ollama.chat(model='{MODEL_NAME}', ...)")
    print(f"  • Chat with it: ollama run {MODEL_NAME}")
    print("  • Integrate it into your applications")

def interactive_mode():
    """Interactive chat with your model"""

    print("="*60)
    print(f"Interactive Chat with {MODEL_NAME}")
    print("="*60)
    print("Type 'exit' or 'quit' to stop\n")

    while True:
        try:
            question = input("You: ").strip()

            if question.lower() in ['exit', 'quit', 'q']:
                print("\nGoodbye!")
                break

            if not question:
                continue

            print(f"\n{MODEL_NAME}: ", end="", flush=True)

            response = ollama.chat(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": question}],
                stream=True
            )

            for chunk in response:
                print(chunk['message']['content'], end="", flush=True)

            print("\n")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test your private AI model")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Start interactive chat mode")
    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
    else:
        test_model()
