"""
Model Server - Loads and serves fine-tuned LoRA models for inference.

Supports:
  - Loading base model + LoRA adapter for real local inference
  - Automatic fallback to API-based generation when no local model available
  - Model hot-swapping (load different adapters per org)
  - CPU and GPU inference

Produces real model output from real fine-tuned weights — not API wrappers.
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

# Model cache: {model_path: (model, tokenizer)}
_loaded_models: Dict[str, Any] = {}
_MAX_CACHED_MODELS = int(os.getenv("PLM_MAX_CACHED_MODELS", "2"))


class ModelServer:
    """Serves fine-tuned LoRA models for inference.

    On startup or first request, loads the base model + LoRA adapter into
    memory. Subsequent requests reuse the loaded model.

    If no fine-tuned model exists for an org, returns None so the caller
    can fall back to API-based generation.
    """

    def __init__(self):
        self._check_dependencies()
        self.ready = False

    def _check_dependencies(self):
        """Check if inference dependencies are available."""
        try:
            import torch
            self.has_torch = True
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            self.has_torch = False
            self.device = None
            logger.warning("PyTorch not installed. Local model inference unavailable.")

    def is_available(self) -> bool:
        """Check if local model serving is possible."""
        return self.has_torch

    def get_loaded_models(self) -> List[str]:
        """Return list of currently loaded model paths."""
        return list(_loaded_models.keys())

    async def load_model(self, adapter_path: str, base_model_name: str) -> bool:
        """Load a base model with LoRA adapter into memory.

        Args:
            adapter_path: Path to the LoRA adapter directory.
            base_model_name: HuggingFace model ID for the base model.

        Returns:
            True if model loaded successfully.
        """
        if not self.has_torch:
            logger.error("Cannot load model: PyTorch not installed")
            return False

        if adapter_path in _loaded_models:
            logger.info(f"Model already loaded: {adapter_path}")
            return True

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
            from peft import PeftModel

            logger.info(f"Loading model: base={base_model_name}, adapter={adapter_path}")
            load_start = time.time()

            # Load tokenizer from adapter (includes any special tokens)
            tokenizer = AutoTokenizer.from_pretrained(adapter_path, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            # Load base model
            if self.device == "cuda":
                # Try 4-bit quantized loading for GPU
                try:
                    bnb_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.bfloat16,
                    )
                    base_model = AutoModelForCausalLM.from_pretrained(
                        base_model_name,
                        quantization_config=bnb_config,
                        device_map="auto",
                        trust_remote_code=True,
                    )
                except Exception:
                    # Fallback to float16
                    base_model = AutoModelForCausalLM.from_pretrained(
                        base_model_name,
                        torch_dtype=torch.float16,
                        device_map="auto",
                        trust_remote_code=True,
                    )
            else:
                # CPU: float32
                base_model = AutoModelForCausalLM.from_pretrained(
                    base_model_name,
                    torch_dtype=torch.float32,
                    device_map="cpu",
                    trust_remote_code=True,
                )

            # Load LoRA adapter on top of base model
            model = PeftModel.from_pretrained(base_model, adapter_path)
            model.eval()

            # Evict oldest cached model if we're at capacity
            if len(_loaded_models) >= _MAX_CACHED_MODELS:
                oldest_key = next(iter(_loaded_models))
                del _loaded_models[oldest_key]
                logger.info(f"Evicted cached model: {oldest_key}")

            # Cache
            _loaded_models[adapter_path] = {
                "model": model,
                "tokenizer": tokenizer,
                "base_model_name": base_model_name,
                "loaded_at": time.time(),
                "device": self.device,
            }

            load_time = time.time() - load_start
            logger.info(f"Model loaded in {load_time:.1f}s on {self.device}: {adapter_path}")
            self.ready = True
            return True

        except Exception as e:
            logger.error(f"Failed to load model from {adapter_path}: {e}")
            return False

    async def generate(
        self,
        adapter_path: str,
        base_model_name: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_new_tokens: int = 2048,
        top_p: float = 0.9,
        repetition_penalty: float = 1.1,
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Generate text using a fine-tuned model.

        Args:
            adapter_path: Path to the LoRA adapter directory.
            base_model_name: HuggingFace model ID for the base model.
            messages: Chat messages in [{"role": ..., "content": ...}] format.
            temperature: Sampling temperature.
            max_new_tokens: Maximum tokens to generate.
            top_p: Nucleus sampling threshold.
            repetition_penalty: Penalty for repeated tokens.

        Returns:
            Tuple of (generated_text, metadata) or None if model unavailable.
            metadata includes: tokens_generated, generation_time_ms, device.
        """
        if not self.has_torch:
            return None

        # Ensure model is loaded
        if adapter_path not in _loaded_models:
            adapter_dir = Path(adapter_path)
            if not adapter_dir.exists():
                logger.warning(f"Adapter path does not exist: {adapter_path}")
                return None

            success = await self.load_model(adapter_path, base_model_name)
            if not success:
                return None

        cached = _loaded_models[adapter_path]
        model = cached["model"]
        tokenizer = cached["tokenizer"]

        try:
            import torch

            # Format messages using tokenizer's chat template
            if hasattr(tokenizer, "apply_chat_template"):
                prompt = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
            else:
                # Manual formatting fallback
                prompt = ""
                for msg in messages:
                    role = msg["role"]
                    content = msg["content"]
                    if role == "system":
                        prompt += f"<|system|>\n{content}\n"
                    elif role == "user":
                        prompt += f"<|user|>\n{content}\n"
                    elif role == "assistant":
                        prompt += f"<|assistant|>\n{content}\n"
                prompt += "<|assistant|>\n"

            # Tokenize
            inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096)
            input_ids = inputs["input_ids"].to(model.device)
            attention_mask = inputs["attention_mask"].to(model.device)

            gen_start = time.time()

            # Generate
            with torch.no_grad():
                outputs = model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    max_new_tokens=max_new_tokens,
                    temperature=max(temperature, 0.01),  # Avoid division by zero
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    do_sample=temperature > 0,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                )

            gen_time = time.time() - gen_start

            # Decode only the new tokens
            new_tokens = outputs[0][input_ids.shape[1]:]
            generated_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
            tokens_generated = len(new_tokens)

            metadata = {
                "source": "fine_tuned_model",
                "adapter_path": adapter_path,
                "base_model": base_model_name,
                "tokens_generated": tokens_generated,
                "generation_time_ms": int(gen_time * 1000),
                "device": str(model.device),
                "temperature": temperature,
            }

            logger.info(
                f"Generated {tokens_generated} tokens in {gen_time:.2f}s "
                f"on {model.device} from {adapter_path}"
            )

            return generated_text, metadata

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return None

    async def unload_model(self, adapter_path: str):
        """Unload a model from memory.

        Args:
            adapter_path: Path to the adapter to unload.
        """
        if adapter_path in _loaded_models:
            del _loaded_models[adapter_path]
            logger.info(f"Unloaded model: {adapter_path}")

            # Force garbage collection
            try:
                import torch
                import gc
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

    async def get_model_info(self, adapter_path: str) -> Optional[Dict[str, Any]]:
        """Get info about a loaded model.

        Returns:
            Dict with model info or None if not loaded.
        """
        if adapter_path not in _loaded_models:
            return None

        cached = _loaded_models[adapter_path]
        return {
            "adapter_path": adapter_path,
            "base_model": cached["base_model_name"],
            "device": cached["device"],
            "loaded_at": cached["loaded_at"],
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_model_server: Optional[ModelServer] = None


def get_model_server() -> ModelServer:
    """Get or create the ModelServer singleton."""
    global _model_server
    if _model_server is None:
        _model_server = ModelServer()
    return _model_server
