"""Quick test to diagnose FREE API issues"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

print("\n=== Testing FREE API Connections ===\n")

# Test 1: Groq
print("1. GROQ API")
print("-" * 40)
groq_key = os.getenv("GROQ_API_KEY")
print(f"API Key: {groq_key[:20]}...")

try:
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": "Say 'Working'"}],
            "max_tokens": 10
        },
        timeout=30
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {result['choices'][0]['message']['content']}")
        print("[OK] Groq works!")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"[FAIL] {e}")

# Test 2: SambaNova
print("\n2. SAMBANOVA API")
print("-" * 40)
sambanova_key = os.getenv("SAMBANOVA_API_KEY")
print(f"API Key: {sambanova_key[:20]}...")

try:
    response = requests.post(
        "https://api.sambanova.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {sambanova_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "Meta-Llama-3.1-70B-Instruct",
            "messages": [{"role": "user", "content": "Say 'Working'"}],
            "max_tokens": 10
        },
        timeout=30
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {result['choices'][0]['message']['content']}")
        print("[OK] SambaNova works!")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"[FAIL] {e}")

# Test 3: Gemini
print("\n3. GEMINI API")
print("-" * 40)
gemini_key = os.getenv("GEMINI_API_KEY")
print(f"API Key: {gemini_key[:20]}...")

try:
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}",
        json={
            "contents": [{
                "role": "user",
                "parts": [{"text": "Say 'Working'"}]
            }]
        },
        timeout=30
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {result['candidates'][0]['content']['parts'][0]['text']}")
        print("[OK] Gemini works!")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"[FAIL] {e}")

print("\n" + "=" * 40)
