"""FREE API adapters for Groq, SambaNova, Gemini, and OpenRouter"""
import os
import json
import requests
from typing import List, Dict, Any, Generator
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

from ..utils import get_logger

# Load environment variables
load_dotenv()

logger = get_logger(__name__)

class GroqClient:
    """Groq API client (FREE, fast)"""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4000) -> str:
        """Send chat request to Groq"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()

        result = response.json()
        choices = result.get("choices") or []
        if not choices:
            raise ValueError(f"Groq API returned no choices: {result}")
        return choices[0]["message"]["content"]

    def chat_stream(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4000) -> Generator[str, None, None]:
        """Stream chat response from Groq (OpenAI-compatible SSE)."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=60,
            stream=True
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if not decoded.startswith("data: "):
                continue
            payload = decoded[6:]
            if payload.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
            except json.JSONDecodeError:
                continue

class SambanovaClient:
    """SambaNova API client (FREE)"""

    def __init__(self, api_key: str, model: str = "Meta-Llama-3.1-70B-Instruct"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.sambanova.ai/v1"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4000) -> str:
        """Send chat request to SambaNova"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()

        result = response.json()
        choices = result.get("choices") or []
        if not choices:
            raise ValueError(f"SambaNova API returned no choices: {result}")
        return choices[0]["message"]["content"]

class HuggingFaceClient:
    """HuggingFace Inference API client (FREE tier available)"""

    def __init__(self, api_key: str, model: str = "mistralai/Mistral-7B-Instruct-v0.2"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api-inference.huggingface.co/models"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4000) -> str:
        """Send chat request to HuggingFace Inference API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Convert messages to prompt format
        prompt = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                prompt += f"<s>[INST] <<SYS>>\n{content}\n<</SYS>>\n\n"
            elif role == "user":
                if prompt and not prompt.endswith("[INST] "):
                    prompt += f"[INST] {content} [/INST]"
                else:
                    prompt += f"{content} [/INST]"
            elif role == "assistant":
                prompt += f" {content}</s><s>[INST] "

        data = {
            "inputs": prompt,
            "parameters": {
                "temperature": temperature,
                "max_new_tokens": min(max_tokens, 2048),
                "return_full_text": False
            }
        }

        response = requests.post(
            f"{self.base_url}/{self.model}",
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()

        result = response.json()
        if isinstance(result, list) and len(result) > 0:
            return result[0].get("generated_text", "")
        elif isinstance(result, dict) and "generated_text" in result:
            return result["generated_text"]
        else:
            raise ValueError(f"HuggingFace API returned unexpected format: {result}")

    def inference(self, model_id: str, prompt: str, temperature: float = 0.7, max_tokens: int = 1024) -> str:
        """Run inference on a specific model (for custom fine-tuned models)"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "inputs": prompt,
            "parameters": {
                "temperature": temperature,
                "max_new_tokens": min(max_tokens, 2048),
                "return_full_text": False
            }
        }

        response = requests.post(
            f"{self.base_url}/{model_id}",
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()

        result = response.json()
        if isinstance(result, list) and len(result) > 0:
            return result[0].get("generated_text", "")
        return str(result)


class OpenRouterClient:
    """OpenRouter API client - access to many models with unified API"""

    def __init__(self, api_key: str, model: str = "meta-llama/llama-3.1-8b-instruct:free"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4000) -> str:
        """Send chat request to OpenRouter"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://plm-enterprise.app",
            "X-Title": "PLM Enterprise"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()

        result = response.json()
        choices = result.get("choices") or []
        if not choices:
            raise ValueError(f"OpenRouter API returned no choices: {result}")
        return choices[0]["message"]["content"]

    def chat_stream(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4000) -> Generator[str, None, None]:
        """Stream chat response from OpenRouter (OpenAI-compatible SSE)."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://plm-enterprise.app",
            "X-Title": "PLM Enterprise"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=120,
            stream=True
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if not decoded.startswith("data: "):
                continue
            payload = decoded[6:]
            if payload.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
            except json.JSONDecodeError:
                continue


class OpenAIClient:
    """OpenAI API client (GPT-4o-mini / GPT-4o)"""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4000) -> str:
        """Send chat request to OpenAI"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        response.raise_for_status()

        result = response.json()
        choices = result.get("choices") or []
        if not choices:
            raise ValueError(f"OpenAI API returned no choices: {result}")
        return choices[0]["message"]["content"]

    def chat_stream(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4000) -> Generator[str, None, None]:
        """Stream chat response from OpenAI (SSE)."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=120,
            stream=True
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if not decoded.startswith("data: "):
                continue
            payload = decoded[6:]
            if payload.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
            except json.JSONDecodeError:
                continue


class GeminiClient:
    """Google Gemini API client (FREE)"""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4000) -> str:
        """Send chat request to Gemini"""
        # Convert messages to Gemini format
        # Gemini doesn't support "system" role natively — prepend system content
        # to the first user message instead.
        contents = []
        system_prefix = ""
        for msg in messages:
            if msg["role"] == "system":
                system_prefix += msg["content"] + "\n\n"
                continue
            role = "user" if msg["role"] == "user" else "model"
            text = msg["content"]
            if system_prefix and role == "user":
                text = system_prefix + text
                system_prefix = ""
            contents.append({
                "role": role,
                "parts": [{"text": text}]
            })

        data = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"

        response = requests.post(
            url,
            json=data,
            timeout=30
        )
        response.raise_for_status()

        result = response.json()
        candidates = result.get("candidates") or []
        if not candidates:
            raise ValueError(f"Gemini API returned no candidates: {result}")
        parts = candidates[0].get("content", {}).get("parts") or []
        if not parts:
            raise ValueError(f"Gemini API returned no content parts: {result}")
        return parts[0]["text"]

class FreeAPIManager:
    """Manager for FREE APIs with fallback support"""

    def __init__(self):
        """Initialize all FREE API clients"""
        self.clients = {}

        # Initialize Groq
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            self.clients["groq"] = GroqClient(
                groq_key,
                os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            )
            logger.info("✓ Groq client initialized")

        # Initialize SambaNova
        sambanova_key = os.getenv("SAMBANOVA_API_KEY")
        if sambanova_key:
            self.clients["sambanova"] = SambanovaClient(
                sambanova_key,
                os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.1-70B-Instruct")
            )
            logger.info("✓ SambaNova client initialized")

        # Initialize Gemini
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            self.clients["gemini"] = GeminiClient(
                gemini_key,
                os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            )
            logger.info("✓ Gemini client initialized")

        # Initialize HuggingFace
        hf_key = os.getenv("HF_API_KEY") or os.getenv("HUGGINGFACE_API_KEY")
        if hf_key:
            self.clients["huggingface"] = HuggingFaceClient(
                hf_key,
                os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")
            )
            logger.info("✓ HuggingFace client initialized")

        # Initialize OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            self.clients["openai"] = OpenAIClient(
                openai_key,
                os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            )
            logger.info("✓ OpenAI client initialized")

        # Initialize OpenRouter (access to many models)
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            self.clients["openrouter"] = OpenRouterClient(
                openrouter_key,
                os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
            )
            logger.info("✓ OpenRouter client initialized")

        # Fallback order
        fallback_order = os.getenv("FALLBACK_ORDER", "openrouter,openai,groq,huggingface,sambanova,gemini")
        self.fallback_order = [x.strip() for x in fallback_order.split(",")]

        logger.info(f"FREE API Manager initialized with {len(self.clients)} clients")
        logger.info(f"Fallback order: {self.fallback_order}")

    def chat(self, api_name: str, messages: List[Dict[str, str]],
             temperature: float = 0.7, max_tokens: int = 4000,
             enable_fallback: bool = True,
             model_override: str = None) -> tuple[str, str]:
        """
        Send chat request with automatic fallback.

        Args:
            api_name: Primary API to use ('groq', 'sambanova', 'gemini', 'huggingface').
            messages: Chat messages list.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            enable_fallback: Whether to try other APIs if the primary fails.
            model_override: Temporarily use a different model for this call only.
                            The client's original model is restored afterwards.

        Returns:
            tuple: (response_text, api_used)
        """
        if not self.clients:
            raise Exception(
                "No LLM API keys configured. Set GROQ_API_KEY, SAMBANOVA_API_KEY, or GEMINI_API_KEY in your environment."
            )

        # Try primary API
        if api_name in self.clients:
            try:
                logger.debug(f"Trying {api_name}...")
                client = self.clients[api_name]
                original_model = client.model if model_override else None
                if model_override:
                    client.model = model_override
                try:
                    response = client.chat(messages, temperature, max_tokens)
                finally:
                    if original_model is not None:
                        client.model = original_model
                logger.debug(f"✓ {api_name} succeeded")
                return response, api_name
            except Exception as e:
                logger.warning(f"✗ {api_name} failed: {e}")
                if not enable_fallback:
                    raise

        # Try fallbacks
        if enable_fallback:
            for fallback_api in self.fallback_order:
                if fallback_api == api_name:
                    continue
                if fallback_api not in self.clients:
                    continue

                try:
                    logger.info(f"Falling back to {fallback_api}...")
                    response = self.clients[fallback_api].chat(messages, temperature, max_tokens)
                    logger.info(f"✓ {fallback_api} succeeded (fallback)")
                    return response, fallback_api
                except Exception as e:
                    logger.warning(f"✗ {fallback_api} failed: {e}")

        raise Exception("All APIs failed")

    def chat_stream(self, api_name: str, messages: List[Dict[str, str]],
                    temperature: float = 0.7, max_tokens: int = 4000) -> tuple[Generator[str, None, None], str]:
        """
        Stream chat response. Currently only Groq supports streaming.
        Falls back to non-streaming if streaming not available.

        Returns:
            tuple: (generator of text chunks, api_used)
        """
        if not self.clients:
            raise Exception(
                "No LLM API keys configured. Set GROQ_API_KEY, SAMBANOVA_API_KEY, or GEMINI_API_KEY in your environment."
            )

        # Try Groq streaming first (it has native SSE support)
        if "groq" in self.clients:
            try:
                client = self.clients["groq"]
                gen = client.chat_stream(messages, temperature, max_tokens)
                return gen, "groq"
            except Exception as e:
                logger.warning(f"Groq streaming failed: {e}")

        # Fallback: use non-streaming and yield entire result
        response, api_used = self.chat(api_name, messages, temperature, max_tokens, enable_fallback=True)

        def single_chunk() -> Generator[str, None, None]:
            yield response

        return single_chunk(), api_used

    def health_check(self) -> Dict[str, bool]:
        """Check health of all APIs"""
        health = {}

        test_messages = [{"role": "user", "content": "Hello"}]

        for api_name, client in self.clients.items():
            try:
                client.chat(test_messages, temperature=0.1, max_tokens=10)
                health[api_name] = True
                logger.info(f"✓ {api_name} health check passed")
            except Exception as e:
                health[api_name] = False
                logger.error(f"✗ {api_name} health check failed: {e}")

        return health
