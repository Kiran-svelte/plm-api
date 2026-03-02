"""
Example: How to use your private AI model

This example shows different ways to interact with your deployed model.
"""

import sys

try:
    import ollama
except ImportError:
    print("Error: ollama package not installed")
    print("Install with: pip install ollama")
    sys.exit(1)

# Configuration
MODEL_NAME = "my-private-ai"

# Example 1: Simple question
def example_simple():
    print("Example 1: Simple Question")
    print("="*60)

    response = ollama.chat(
        model=MODEL_NAME,
        messages=[
            {'role': 'user', 'content': 'What is Python?'}
        ]
    )

    print("Question: What is Python?")
    print(f"Answer: {response['message']['content']}\n")

# Example 2: Conversation with context
def example_conversation():
    print("Example 2: Multi-turn Conversation")
    print("="*60)

    messages = [
        {'role': 'user', 'content': 'What is a REST API?'},
    ]

    # First turn
    response = ollama.chat(model=MODEL_NAME, messages=messages)
    print("User: What is a REST API?")
    print(f"AI: {response['message']['content']}\n")

    # Add to conversation history
    messages.append(response['message'])
    messages.append({'role': 'user', 'content': 'Can you give me an example?'})

    # Second turn
    response = ollama.chat(model=MODEL_NAME, messages=messages)
    print("User: Can you give me an example?")
    print(f"AI: {response['message']['content']}\n")

# Example 3: Streaming response
def example_streaming():
    print("Example 3: Streaming Response")
    print("="*60)
    print("Question: Explain machine learning")
    print("Answer: ", end="", flush=True)

    for chunk in ollama.chat(
        model=MODEL_NAME,
        messages=[{'role': 'user', 'content': 'Explain machine learning'}],
        stream=True
    ):
        print(chunk['message']['content'], end="", flush=True)

    print("\n")

# Example 4: Temperature variations
def example_temperature():
    print("Example 4: Temperature Variations")
    print("="*60)

    question = "What is artificial intelligence?"

    # Low temperature (more focused)
    print("Low Temperature (0.3) - Focused:")
    response = ollama.generate(
        model=MODEL_NAME,
        prompt=question,
        options={'temperature': 0.3}
    )
    print(response['response'][:200] + "...\n")

    # High temperature (more creative)
    print("High Temperature (0.9) - Creative:")
    response = ollama.generate(
        model=MODEL_NAME,
        prompt=question,
        options={'temperature': 0.9}
    )
    print(response['response'][:200] + "...\n")

# Example 5: Embeddings (if supported)
def example_embeddings():
    print("Example 5: Text Embeddings")
    print("="*60)

    try:
        response = ollama.embeddings(
            model=MODEL_NAME,
            prompt="Python programming language"
        )
        print(f"Generated {len(response['embedding'])} dimensional embedding")
        print(f"First 5 values: {response['embedding'][:5]}\n")
    except Exception as e:
        print(f"Embeddings not supported or error: {e}\n")

# Example 6: Batch processing
def example_batch():
    print("Example 6: Batch Processing")
    print("="*60)

    questions = [
        "What is Python?",
        "What is JavaScript?",
        "What is SQL?"
    ]

    print("Processing multiple questions:\n")

    for i, question in enumerate(questions, 1):
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[{'role': 'user', 'content': question}]
        )
        print(f"{i}. {question}")
        print(f"   Answer: {response['message']['content'][:100]}...\n")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("PLM Usage Examples")
    print("="*60)
    print()

    # Check if model exists
    try:
        models = ollama.list()
        if not any(MODEL_NAME in m['name'] for m in models.get('models', [])):
            print(f"Error: Model '{MODEL_NAME}' not found!")
            print("\nRun deployment script first:")
            print("  Windows: deploy_ollama.bat")
            print("  Linux/Mac: ./deploy_ollama.sh")
            sys.exit(1)
    except Exception as e:
        print(f"Error connecting to Ollama: {e}")
        print("\nMake sure Ollama is running!")
        sys.exit(1)

    # Run examples
    try:
        example_simple()
        example_conversation()
        example_streaming()
        example_temperature()
        example_batch()

        print("="*60)
        print("Examples complete!")
        print("="*60)
        print("\nYou can now integrate this into your applications!")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
