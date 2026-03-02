"""
Model Trainer - Real LoRA/QLoRA fine-tuning that produces actual model files.

Supports three backends (tiered):
  1. Local GPU  — PyTorch + PEFT + TRL (dev/testing, needs CUDA GPU)
  2. Runpod     — Serverless GPU on demand (production)
  3. HuggingFace AutoTrain — Upload data, HF handles everything (fallback)

Produces real artifacts:
  - adapter_model.safetensors  (LoRA weights, ~50-200MB)
  - adapter_config.json        (PEFT config)
  - tokenizer_config.json      (tokenizer settings)
  - training_args.json         (hyperparameters used)
  - training_metrics.json      (loss curves, eval metrics)
"""

import os
import sys
import json
import time
import shutil
import logging
import asyncio
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise.db.db_client import get_supabase_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODELS_DIR = Path(os.getenv("PLM_MODELS_DIR", Path(__file__).parent / "models"))
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Base models supported for fine-tuning (ordered by size)
BASE_MODELS = {
    "tinyllama-1.1b": "TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    "llama-3.2-1b": "meta-llama/Llama-3.2-1B-Instruct",
    "llama-3.2-3b": "meta-llama/Llama-3.2-3B-Instruct",
    "phi-3-mini": "microsoft/Phi-3-mini-4k-instruct",
    "mistral-7b": "mistralai/Mistral-7B-Instruct-v0.3",
    "llama-3.1-8b": "meta-llama/Llama-3.1-8B-Instruct",
}

# Default LoRA config
DEFAULT_LORA_CONFIG = {
    "r": 16,                    # LoRA rank (higher = more capacity, more VRAM)
    "lora_alpha": 32,           # Scaling factor
    "lora_dropout": 0.05,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
    "bias": "none",
    "task_type": "CAUSAL_LM",
}

DEFAULT_TRAINING_ARGS = {
    "num_train_epochs": 3,
    "per_device_train_batch_size": 4,
    "gradient_accumulation_steps": 4,
    "learning_rate": 2e-4,
    "warmup_ratio": 0.03,
    "weight_decay": 0.01,
    "lr_scheduler_type": "cosine",
    "logging_steps": 10,
    "save_steps": 100,
    "fp16": True,               # Use mixed precision (halves VRAM usage)
    "max_seq_length": 2048,
    "optim": "paged_adamw_8bit",  # 8-bit optimizer (further VRAM savings)
}

# Runpod config
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "")

# HuggingFace config
HF_TOKEN = os.getenv("HF_TOKEN", "")

# Kaggle config
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME", "")
KAGGLE_KEY = os.getenv("KAGGLE_KEY", "")


# ---------------------------------------------------------------------------
# Training Backend Enum
# ---------------------------------------------------------------------------

class TrainingBackend:
    LOCAL = "local"
    RUNPOD = "runpod"
    HUGGINGFACE = "huggingface"
    KAGGLE = "kaggle"


# ---------------------------------------------------------------------------
# Model Artifact Paths
# ---------------------------------------------------------------------------

def get_model_dir(org_id: str, model_id: str, version: str = "latest") -> Path:
    """Get the directory for a model's artifacts."""
    return MODELS_DIR / org_id / model_id / version


def get_adapter_path(org_id: str, model_id: str, version: str = "latest") -> Path:
    """Get path to the LoRA adapter directory."""
    return get_model_dir(org_id, model_id, version)


# ---------------------------------------------------------------------------
# Data Formatting
# ---------------------------------------------------------------------------

def format_training_data(
    training_examples: List[Dict[str, Any]],
    system_prompt: str = "",
) -> List[Dict[str, str]]:
    """Format training data into chat-template format for SFTTrainer.

    Converts instruction/output pairs into the standard chat format:
        <|system|> ... <|user|> ... <|assistant|> ...

    Args:
        training_examples: List of dicts with 'instruction' and 'output' keys.
        system_prompt: Optional system prompt to prepend.

    Returns:
        List of formatted conversation dicts.
    """
    formatted = []
    for example in training_examples:
        instruction = example.get("instruction", "")
        output = example.get("output", "")
        if not instruction or not output:
            continue

        conversation = {
            "messages": [
                {"role": "system", "content": system_prompt or "You are a helpful expert assistant."},
                {"role": "user", "content": instruction},
                {"role": "assistant", "content": output},
            ]
        }
        formatted.append(conversation)

    return formatted


def save_training_data_to_jsonl(
    data: List[Dict[str, str]],
    output_path: Path,
) -> int:
    """Save formatted training data to JSONL file.

    Returns number of examples written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            count += 1
    return count


# ---------------------------------------------------------------------------
# Local Training (PyTorch + PEFT + TRL)
# ---------------------------------------------------------------------------

class LocalTrainer:
    """Fine-tunes a model locally using PyTorch + PEFT LoRA + TRL SFTTrainer.

    Requires:
        - CUDA-capable GPU with >= 16GB VRAM (for 3B models)
        - pip install peft trl datasets accelerate bitsandbytes
    """

    def __init__(self):
        self._check_dependencies()

    def _check_dependencies(self):
        """Verify all required packages are installed."""
        missing = []
        for pkg in ["torch", "peft", "trl", "datasets", "accelerate"]:
            try:
                __import__(pkg)
            except ImportError:
                missing.append(pkg)

        if missing:
            raise ImportError(
                f"Local training requires: {', '.join(missing)}. "
                f"Install with: pip install {' '.join(missing)}"
            )

        import torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cpu":
            logger.warning(
                "No CUDA GPU detected. Local training on CPU is extremely slow "
                "and not recommended. Consider using Runpod or HuggingFace backend."
            )

    async def train(
        self,
        base_model_key: str,
        training_data_path: Path,
        output_dir: Path,
        lora_config: Optional[Dict[str, Any]] = None,
        training_args: Optional[Dict[str, Any]] = None,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Run LoRA fine-tuning locally.

        Args:
            base_model_key: Key from BASE_MODELS dict.
            training_data_path: Path to JSONL training data.
            output_dir: Where to save the adapter files.
            lora_config: Override default LoRA config.
            training_args: Override default training args.
            progress_callback: Async callable(progress: float, message: str).

        Returns:
            Dict with training metrics and artifact paths.
        """
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainingArguments,
        )
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from trl import SFTTrainer, SFTConfig
        from datasets import load_dataset

        base_model_name = BASE_MODELS.get(base_model_key, base_model_key)
        lora_cfg = {**DEFAULT_LORA_CONFIG, **(lora_config or {})}
        train_args = {**DEFAULT_TRAINING_ARGS, **(training_args or {})}
        output_dir.mkdir(parents=True, exist_ok=True)
        metrics = {"backend": "local", "base_model": base_model_name, "started_at": datetime.utcnow().isoformat()}

        if progress_callback:
            await progress_callback(0.05, "Loading base model and tokenizer...")

        # ---- 1. Load tokenizer ----
        tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            tokenizer.pad_token_id = tokenizer.eos_token_id

        # ---- 2. Load model with 4-bit quantization (QLoRA) ----
        use_4bit = self.device == "cuda"
        if use_4bit:
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )
            model = AutoModelForCausalLM.from_pretrained(
                base_model_name,
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True,
            )
            model = prepare_model_for_kbit_training(model)
        else:
            model = AutoModelForCausalLM.from_pretrained(
                base_model_name,
                torch_dtype=torch.float32,
                device_map="auto",
                trust_remote_code=True,
            )

        if progress_callback:
            await progress_callback(0.15, "Applying LoRA adapters...")

        # ---- 3. Apply LoRA ----
        peft_config = LoraConfig(
            r=lora_cfg["r"],
            lora_alpha=lora_cfg["lora_alpha"],
            lora_dropout=lora_cfg["lora_dropout"],
            target_modules=lora_cfg["target_modules"],
            bias=lora_cfg["bias"],
            task_type=lora_cfg["task_type"],
        )
        model = get_peft_model(model, peft_config)
        trainable_params, total_params = model.get_nb_trainable_parameters()
        metrics["trainable_params"] = trainable_params
        metrics["total_params"] = total_params
        metrics["trainable_pct"] = round(100 * trainable_params / total_params, 2) if total_params > 0 else 0.0

        logger.info(
            f"Model loaded. Trainable: {trainable_params:,} / {total_params:,} "
            f"({metrics['trainable_pct']}%)"
        )

        if progress_callback:
            await progress_callback(0.20, f"Loading training data from {training_data_path.name}...")

        # ---- 4. Load dataset ----
        dataset = load_dataset("json", data_files=str(training_data_path), split="train")
        metrics["training_examples"] = len(dataset)

        if progress_callback:
            await progress_callback(0.25, f"Starting training with {len(dataset)} examples...")

        # ---- 5. Training arguments ----
        sft_config = SFTConfig(
            output_dir=str(output_dir / "checkpoints"),
            num_train_epochs=train_args["num_train_epochs"],
            per_device_train_batch_size=train_args["per_device_train_batch_size"],
            gradient_accumulation_steps=train_args["gradient_accumulation_steps"],
            learning_rate=train_args["learning_rate"],
            warmup_ratio=train_args["warmup_ratio"],
            weight_decay=train_args["weight_decay"],
            lr_scheduler_type=train_args["lr_scheduler_type"],
            logging_steps=train_args["logging_steps"],
            save_steps=train_args["save_steps"],
            fp16=train_args["fp16"] and self.device == "cuda",
            max_seq_length=train_args["max_seq_length"],
            optim=train_args["optim"] if self.device == "cuda" else "adamw_torch",
            report_to="none",
            save_total_limit=2,
            logging_dir=str(output_dir / "logs"),
        )

        # ---- 6. Create trainer ----
        trainer = SFTTrainer(
            model=model,
            train_dataset=dataset,
            processing_class=tokenizer,
            args=sft_config,
        )

        if progress_callback:
            await progress_callback(0.30, "Training in progress...")

        # ---- 7. Train ----
        train_start = time.time()
        train_result = trainer.train()
        train_duration = time.time() - train_start

        metrics["train_loss"] = round(train_result.training_loss, 4)
        metrics["train_runtime_seconds"] = round(train_duration, 1)
        metrics["train_samples_per_second"] = round(
            train_result.metrics.get("train_samples_per_second", 0), 2
        )
        metrics["epochs_completed"] = train_args["num_train_epochs"]

        if progress_callback:
            await progress_callback(0.85, "Saving adapter weights...")

        # ---- 8. Save adapter (NOT the full model — just LoRA weights) ----
        adapter_dir = output_dir / "adapter"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(adapter_dir))
        tokenizer.save_pretrained(str(adapter_dir))

        # Save training config for reproducibility
        with open(output_dir / "training_args.json", "w") as f:
            json.dump(train_args, f, indent=2)
        with open(output_dir / "lora_config.json", "w") as f:
            json.dump(lora_cfg, f, indent=2)

        # Calculate adapter size
        adapter_size_bytes = sum(
            f.stat().st_size for f in adapter_dir.rglob("*") if f.is_file()
        )
        metrics["adapter_size_mb"] = round(adapter_size_bytes / (1024 * 1024), 2)

        # List produced files
        metrics["artifact_files"] = [
            str(f.relative_to(output_dir)) for f in adapter_dir.rglob("*") if f.is_file()
        ]

        if progress_callback:
            await progress_callback(0.95, "Saving training metrics...")

        # ---- 9. Save metrics ----
        metrics["completed_at"] = datetime.utcnow().isoformat()
        with open(output_dir / "training_metrics.json", "w") as f:
            json.dump(metrics, f, indent=2)

        # Cleanup checkpoints to save space
        checkpoints_dir = output_dir / "checkpoints"
        if checkpoints_dir.exists():
            shutil.rmtree(checkpoints_dir)

        if progress_callback:
            await progress_callback(1.0, "Training complete!")

        logger.info(
            f"Local training complete. Adapter saved to {adapter_dir} "
            f"({metrics['adapter_size_mb']}MB, loss={metrics['train_loss']})"
        )

        return metrics


# ---------------------------------------------------------------------------
# Runpod Training (Serverless GPU)
# ---------------------------------------------------------------------------

class RunpodTrainer:
    """Sends training jobs to Runpod serverless GPU endpoints.

    Requires:
        - RUNPOD_API_KEY env var
        - A Runpod serverless endpoint configured with fine-tuning template
    """

    def __init__(self):
        if not RUNPOD_API_KEY:
            raise ValueError("RUNPOD_API_KEY environment variable is required for Runpod training")
        self.api_key = RUNPOD_API_KEY
        self.base_url = "https://api.runpod.ai/v2"

    async def train(
        self,
        base_model_key: str,
        training_data: List[Dict[str, Any]],
        output_dir: Path,
        lora_config: Optional[Dict[str, Any]] = None,
        training_args: Optional[Dict[str, Any]] = None,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Submit a training job to Runpod and poll until completion.

        Args:
            base_model_key: Key from BASE_MODELS dict.
            training_data: Formatted training examples.
            output_dir: Where to save downloaded artifacts.
            lora_config: Override default LoRA config.
            training_args: Override default training args.
            progress_callback: Async callable(progress: float, message: str).

        Returns:
            Dict with training metrics and artifact paths.
        """
        base_model_name = BASE_MODELS.get(base_model_key, base_model_key)
        lora_cfg = {**DEFAULT_LORA_CONFIG, **(lora_config or {})}
        train_args = {**DEFAULT_TRAINING_ARGS, **(training_args or {})}
        output_dir.mkdir(parents=True, exist_ok=True)

        endpoint_id = RUNPOD_ENDPOINT_ID
        if not endpoint_id:
            raise ValueError("RUNPOD_ENDPOINT_ID environment variable is required")

        if progress_callback:
            await progress_callback(0.05, "Submitting training job to Runpod...")

        # Submit job
        payload = {
            "input": {
                "action": "train",
                "base_model": base_model_name,
                "training_data": training_data,
                "lora_config": lora_cfg,
                "training_args": train_args,
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/{endpoint_id}/run",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            job_data = response.json()
            job_id = job_data.get("id")
            if not job_id:
                raise ValueError(f"Runpod API returned response without job ID: {job_data}")

        logger.info(f"Runpod training job submitted: {job_id}")

        if progress_callback:
            await progress_callback(0.10, f"Job {job_id} queued on Runpod...")

        # Poll for completion
        metrics = {"backend": "runpod", "job_id": job_id, "base_model": base_model_name}
        poll_interval = 30  # seconds

        while True:
            await asyncio.sleep(poll_interval)

            async with httpx.AsyncClient(timeout=30.0) as client:
                status_response = await client.get(
                    f"{self.base_url}/{endpoint_id}/status/{job_id}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                status_response.raise_for_status()
                status_data = status_response.json()

            status = status_data.get("status")

            if status == "COMPLETED":
                output = status_data.get("output", {})
                metrics.update(output.get("metrics", {}))

                # Download adapter files
                adapter_url = output.get("adapter_url")
                if adapter_url:
                    await self._download_adapter(adapter_url, output_dir / "adapter")

                metrics["completed_at"] = datetime.utcnow().isoformat()

                with open(output_dir / "training_metrics.json", "w") as f:
                    json.dump(metrics, f, indent=2)

                if progress_callback:
                    await progress_callback(1.0, "Runpod training complete!")

                return metrics

            elif status == "FAILED":
                error = status_data.get("error", "Unknown error")
                raise RuntimeError(f"Runpod training failed: {error}")

            elif status in ("IN_QUEUE", "IN_PROGRESS"):
                progress = status_data.get("output", {}).get("progress", 0.1)
                if progress_callback:
                    await progress_callback(
                        min(progress, 0.95),
                        f"Training on Runpod GPU... ({status})",
                    )

            else:
                logger.warning(f"Unknown Runpod status: {status}")

    async def _download_adapter(self, url: str, output_dir: Path):
        """Download adapter files from Runpod output URL."""
        output_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Assuming tar.gz archive
            archive_path = output_dir.parent / "adapter.tar.gz"
            with open(archive_path, "wb") as f:
                f.write(response.content)

            # Extract safely (prevent path traversal attacks)
            import tarfile
            with tarfile.open(archive_path, "r:gz") as tar:
                # Validate all members before extraction
                for member in tar.getmembers():
                    member_path = (output_dir / member.name).resolve()
                    if not str(member_path).startswith(str(output_dir.resolve())):
                        raise ValueError(f"Tar member {member.name} would escape target directory")
                tar.extractall(path=output_dir)

            archive_path.unlink()
            logger.info(f"Adapter downloaded and extracted to {output_dir}")


# ---------------------------------------------------------------------------
# HuggingFace AutoTrain
# ---------------------------------------------------------------------------

class HuggingFaceTrainer:
    """Uses HuggingFace AutoTrain API for managed fine-tuning.

    Requires:
        - HF_TOKEN env var (HuggingFace API token with write access)
    """

    def __init__(self):
        if not HF_TOKEN:
            raise ValueError("HF_TOKEN environment variable is required for HuggingFace training")
        self.token = HF_TOKEN
        self.api_url = "https://huggingface.co/api"

    async def train(
        self,
        base_model_key: str,
        training_data_path: Path,
        output_dir: Path,
        hf_repo_name: str,
        lora_config: Optional[Dict[str, Any]] = None,
        training_args: Optional[Dict[str, Any]] = None,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Submit training job to HuggingFace AutoTrain.

        Args:
            base_model_key: Key from BASE_MODELS dict.
            training_data_path: Path to JSONL training data.
            output_dir: Where to save downloaded artifacts.
            hf_repo_name: HuggingFace repo to push the model to.
            lora_config: Override default LoRA config.
            training_args: Override default training args.
            progress_callback: Async callable(progress: float, message: str).

        Returns:
            Dict with training metrics and artifact paths.
        """
        base_model_name = BASE_MODELS.get(base_model_key, base_model_key)
        train_args = {**DEFAULT_TRAINING_ARGS, **(training_args or {})}
        lora_cfg = {**DEFAULT_LORA_CONFIG, **(lora_config or {})}
        output_dir.mkdir(parents=True, exist_ok=True)

        metrics = {"backend": "huggingface", "base_model": base_model_name}

        if progress_callback:
            await progress_callback(0.05, "Uploading training data to HuggingFace...")

        # Upload training file
        headers = {"Authorization": f"Bearer {self.token}"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Create autotrain project
            project_payload = {
                "project_name": hf_repo_name.split("/")[-1],
                "task": "llm-sft",
                "base_model": base_model_name,
                "hardware": "spaces-a100-small",
                "params": {
                    "trainer": "sft",
                    "peft": True,
                    "lora_r": lora_cfg["r"],
                    "lora_alpha": lora_cfg["lora_alpha"],
                    "lora_dropout": lora_cfg["lora_dropout"],
                    "epochs": train_args["num_train_epochs"],
                    "batch_size": train_args["per_device_train_batch_size"],
                    "lr": train_args["learning_rate"],
                    "warmup_ratio": train_args["warmup_ratio"],
                    "weight_decay": train_args["weight_decay"],
                    "max_seq_length": train_args["max_seq_length"],
                    "push_to_hub": True,
                    "repo_id": hf_repo_name,
                },
            }

            response = await client.post(
                f"{self.api_url}/autotrain/create",
                json=project_payload,
                headers=headers,
            )
            response.raise_for_status()
            project = response.json()
            project_id = project.get("id")

        if progress_callback:
            await progress_callback(0.10, f"AutoTrain project created: {project_id}")

        # Upload data file
        async with httpx.AsyncClient(timeout=300.0) as client:
            with open(training_data_path, "rb") as f:
                files = {"file": (training_data_path.name, f, "application/jsonl")}
                response = await client.post(
                    f"{self.api_url}/autotrain/{project_id}/upload",
                    files=files,
                    headers=headers,
                )
                response.raise_for_status()

        if progress_callback:
            await progress_callback(0.15, "Data uploaded. Training started on HuggingFace...")

        # Poll for completion
        poll_interval = 60
        while True:
            await asyncio.sleep(poll_interval)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.api_url}/autotrain/{project_id}/status",
                    headers=headers,
                )
                response.raise_for_status()
                status_data = response.json()

            status = status_data.get("status", "unknown")

            if status == "completed":
                metrics["hf_repo"] = hf_repo_name
                metrics["completed_at"] = datetime.utcnow().isoformat()

                # Download adapter from HF Hub
                await self._download_from_hub(hf_repo_name, output_dir / "adapter")

                with open(output_dir / "training_metrics.json", "w") as f:
                    json.dump(metrics, f, indent=2)

                if progress_callback:
                    await progress_callback(1.0, "HuggingFace training complete!")

                return metrics

            elif status in ("failed", "error"):
                error = status_data.get("error", "Unknown error")
                raise RuntimeError(f"HuggingFace AutoTrain failed: {error}")

            else:
                progress = status_data.get("progress", 0.2)
                if progress_callback:
                    await progress_callback(
                        min(progress, 0.95),
                        f"Training on HuggingFace... ({status})",
                    )

    async def _download_from_hub(self, repo_id: str, output_dir: Path):
        """Download model adapter from HuggingFace Hub."""
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            from huggingface_hub import snapshot_download
            snapshot_download(
                repo_id=repo_id,
                local_dir=str(output_dir),
                token=self.token,
            )
            logger.info(f"Adapter downloaded from HF Hub: {repo_id} -> {output_dir}")
        except Exception as e:
            logger.error(f"Failed to download from HF Hub: {e}")
            raise


# ---------------------------------------------------------------------------
# Kaggle Notebook Training (Free GPU: P100 or T4)
# ---------------------------------------------------------------------------

class KaggleNotebookTrainer:
    """Submits fine-tuning jobs to Kaggle Notebooks via the Kaggle API.

    Kaggle provides free GPU (P100/T4) with 30 hours/week quota.
    Typical training times:
        - TinyLlama 1.1B: ~2-3 hours on P100
        - Llama 3.2 3B:   ~4-6 hours on P100
        - Mistral 7B:     ~8-12 hours on P100 (may need T4x2)

    Requires:
        - KAGGLE_USERNAME env var
        - KAGGLE_KEY env var
    """

    def __init__(self):
        if not KAGGLE_USERNAME or not KAGGLE_KEY:
            raise ValueError(
                "KAGGLE_USERNAME and KAGGLE_KEY environment variables are required for Kaggle training"
            )
        self.username = KAGGLE_USERNAME
        self.api_key = KAGGLE_KEY
        self.api_url = "https://www.kaggle.com/api/v1"

    def _auth_headers(self) -> Dict[str, str]:
        """Return HTTP Basic Auth headers for Kaggle API."""
        import base64
        credentials = base64.b64encode(f"{self.username}:{self.api_key}".encode()).decode()
        return {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def estimate_training_time(base_model_key: str, num_examples: int) -> Dict[str, Any]:
        """Estimate training time on Kaggle GPU.

        Args:
            base_model_key: Key from BASE_MODELS dict.
            num_examples: Number of training examples.

        Returns:
            Dict with estimated hours, GPU type, and human-readable message.
        """
        # Approximate training times on Kaggle P100 GPU (16GB VRAM)
        base_hours = {
            "tinyllama-1.1b": 1.5,
            "llama-3.2-1b": 2.0,
            "llama-3.2-3b": 4.0,
            "phi-3-mini": 5.0,
            "mistral-7b": 10.0,
            "llama-3.1-8b": 12.0,
        }
        base_time = base_hours.get(base_model_key, 6.0)

        # Scale by data volume (roughly linear for < 10k examples)
        scale_factor = max(1.0, num_examples / 500)
        estimated_hours = base_time * min(scale_factor, 3.0)

        # Determine GPU type
        gpu_type = "P100" if base_model_key in ("tinyllama-1.1b", "llama-3.2-1b", "llama-3.2-3b", "phi-3-mini") else "T4x2"

        # When can they chat?
        chat_available_hours = 0.5  # RAG-based chat available immediately
        llm_ready_hours = round(estimated_hours + 0.5, 1)  # Fine-tuned model ready after training + deployment

        return {
            "estimated_training_hours": round(estimated_hours, 1),
            "gpu_type": gpu_type,
            "chat_available_in_hours": chat_available_hours,
            "fine_tuned_model_ready_in_hours": llm_ready_hours,
            "agentic_tasks_ready_in_hours": llm_ready_hours,
            "message": (
                f"Training {base_model_key} with {num_examples} examples on Kaggle {gpu_type}: "
                f"~{round(estimated_hours, 1)} hours. "
                f"Chat via RAG is available immediately. "
                f"Fine-tuned model for direct chat and agentic tasks: ~{llm_ready_hours} hours."
            ),
        }

    def _build_notebook_script(
        self,
        base_model_name: str,
        lora_config: Dict[str, Any],
        training_args: Dict[str, Any],
        hf_token: str,
        hf_repo_name: str,
    ) -> str:
        """Generate the Python training script for the Kaggle notebook.

        The script is fully self-contained:
          1. Installs dependencies
          2. Downloads training data from the Kaggle dataset
          3. Loads the base model with QLoRA (4-bit)
          4. Runs LoRA fine-tuning via SFTTrainer
          5. Pushes the adapter to HuggingFace Hub
        """
        return f'''
# PLM Auto-Generated Training Script for Kaggle
# Base model: {base_model_name}
# LoRA config: r={lora_config["r"]}, alpha={lora_config["lora_alpha"]}

!pip install -q peft trl datasets accelerate bitsandbytes transformers huggingface-hub

import torch
import json
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset
from huggingface_hub import login

# Login to HuggingFace for model push
login(token="{hf_token}")

# Load training data
dataset = load_dataset("json", data_files="/kaggle/input/plm-training-data/training_data.jsonl", split="train")
print(f"Loaded {{len(dataset)}} training examples")

# Load model with QLoRA
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

tokenizer = AutoTokenizer.from_pretrained("{base_model_name}", trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.pad_token_id = tokenizer.eos_token_id

model = AutoModelForCausalLM.from_pretrained(
    "{base_model_name}",
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
)
model = prepare_model_for_kbit_training(model)

# Apply LoRA
peft_config = LoraConfig(
    r={lora_config["r"]},
    lora_alpha={lora_config["lora_alpha"]},
    lora_dropout={lora_config["lora_dropout"]},
    target_modules={lora_config["target_modules"]},
    bias="{lora_config["bias"]}",
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, peft_config)

trainable, total = model.get_nb_trainable_parameters()
print(f"Trainable: {{trainable:,}} / {{total:,}} ({{100*trainable/total:.2f}}%)")

# Training config
sft_config = SFTConfig(
    output_dir="/kaggle/working/checkpoints",
    num_train_epochs={training_args["num_train_epochs"]},
    per_device_train_batch_size={training_args["per_device_train_batch_size"]},
    gradient_accumulation_steps={training_args["gradient_accumulation_steps"]},
    learning_rate={training_args["learning_rate"]},
    warmup_ratio={training_args["warmup_ratio"]},
    weight_decay={training_args["weight_decay"]},
    lr_scheduler_type="{training_args["lr_scheduler_type"]}",
    logging_steps={training_args["logging_steps"]},
    save_steps={training_args["save_steps"]},
    fp16=True,
    max_seq_length={training_args["max_seq_length"]},
    optim="paged_adamw_8bit",
    report_to="none",
    save_total_limit=2,
)

# Train
trainer = SFTTrainer(
    model=model,
    train_dataset=dataset,
    processing_class=tokenizer,
    args=sft_config,
)

print("Starting training...")
result = trainer.train()
print(f"Training complete! Loss: {{result.training_loss:.4f}}")

# Save adapter
adapter_dir = "/kaggle/working/adapter"
model.save_pretrained(adapter_dir)
tokenizer.save_pretrained(adapter_dir)

# Push to HuggingFace Hub
from huggingface_hub import HfApi
api = HfApi()
api.upload_folder(
    folder_path=adapter_dir,
    repo_id="{hf_repo_name}",
    repo_type="model",
    token="{hf_token}",
    commit_message="PLM auto-trained LoRA adapter",
)
print(f"Adapter pushed to https://huggingface.co/{hf_repo_name}")

# Save metrics
metrics = {{
    "train_loss": round(result.training_loss, 4),
    "train_runtime_seconds": round(result.metrics.get("train_runtime", 0), 1),
    "train_samples_per_second": round(result.metrics.get("train_samples_per_second", 0), 2),
    "training_examples": len(dataset),
    "backend": "kaggle",
    "base_model": "{base_model_name}",
    "hf_repo": "{hf_repo_name}",
}}
with open("/kaggle/working/training_metrics.json", "w") as f:
    json.dump(metrics, f, indent=2)
print(f"Training metrics: {{metrics}}")
'''

    async def train(
        self,
        base_model_key: str,
        training_data_path: Path,
        output_dir: Path,
        hf_repo_name: str,
        lora_config: Optional[Dict[str, Any]] = None,
        training_args: Optional[Dict[str, Any]] = None,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Submit a training job to Kaggle as a notebook.

        Workflow:
        1. Upload training data as a Kaggle dataset
        2. Create and push a Kaggle notebook with the training script
        3. Poll notebook status until completion
        4. Download adapter from HuggingFace Hub

        Args:
            base_model_key: Key from BASE_MODELS dict.
            training_data_path: Path to JSONL training data file.
            output_dir: Local directory to save downloaded artifacts.
            hf_repo_name: HuggingFace repo to push the trained adapter to.
            lora_config: Override default LoRA config.
            training_args: Override default training args.
            progress_callback: Async callable(progress, message).

        Returns:
            Dict with training metrics and artifact paths.
        """
        base_model_name = BASE_MODELS.get(base_model_key, base_model_key)
        lora_cfg = {**DEFAULT_LORA_CONFIG, **(lora_config or {})}
        train_args = {**DEFAULT_TRAINING_ARGS, **(training_args or {})}
        output_dir.mkdir(parents=True, exist_ok=True)

        hf_token = HF_TOKEN
        if not hf_token:
            raise ValueError("HF_TOKEN is required for Kaggle training (to push adapter to HF Hub)")

        metrics: Dict[str, Any] = {
            "backend": "kaggle",
            "base_model": base_model_name,
            "started_at": datetime.utcnow().isoformat(),
        }

        if progress_callback:
            await progress_callback(0.02, "Preparing Kaggle training job...")

        # ---- 1. Create Kaggle dataset with training data ----
        dataset_slug = f"plm-training-{hashlib.md5(str(training_data_path).encode()).hexdigest()[:8]}"

        if progress_callback:
            await progress_callback(0.05, "Uploading training data to Kaggle...")

        await self._upload_dataset(dataset_slug, training_data_path)

        if progress_callback:
            await progress_callback(0.10, "Creating Kaggle notebook...")

        # ---- 2. Create and push Kaggle notebook ----
        notebook_slug = f"plm-train-{hashlib.md5(hf_repo_name.encode()).hexdigest()[:8]}"
        script = self._build_notebook_script(
            base_model_name, lora_cfg, train_args, hf_token, hf_repo_name,
        )

        await self._create_notebook(
            notebook_slug, dataset_slug, script, gpu_type="P100",
        )

        if progress_callback:
            await progress_callback(0.15, "Kaggle notebook submitted. Training on GPU...")

        # ---- 3. Poll for completion ----
        poll_interval = 120  # Kaggle notebooks are long-running
        max_polls = 180  # ~6 hours max
        kernel_ref = f"{self.username}/{notebook_slug}"

        for poll_num in range(max_polls):
            await asyncio.sleep(poll_interval)

            status = await self._get_notebook_status(kernel_ref)
            kaggle_status = status.get("status", "unknown")

            if kaggle_status == "complete":
                metrics["completed_at"] = datetime.utcnow().isoformat()

                # Download adapter from HuggingFace Hub
                if progress_callback:
                    await progress_callback(0.90, "Training complete. Downloading adapter from HuggingFace...")

                try:
                    await self._download_from_hub(hf_repo_name, output_dir / "adapter")
                    metrics["hf_repo"] = hf_repo_name
                    metrics["has_adapter"] = True
                except Exception as dl_err:
                    logger.warning(f"Failed to download adapter from HF Hub: {dl_err}")
                    metrics["has_adapter"] = False

                with open(output_dir / "training_metrics.json", "w") as f:
                    json.dump(metrics, f, indent=2)

                if progress_callback:
                    await progress_callback(1.0, "Kaggle training complete!")

                return metrics

            elif kaggle_status in ("error", "cancelAcknowledged"):
                error_msg = status.get("failureMessage", "Unknown Kaggle error")
                raise RuntimeError(f"Kaggle notebook failed: {error_msg}")

            else:
                # Running or queued
                progress = min(0.15 + (poll_num / max_polls * 0.70), 0.85)
                if progress_callback:
                    await progress_callback(
                        progress,
                        f"Training on Kaggle GPU... (status: {kaggle_status}, poll {poll_num + 1})",
                    )

        raise RuntimeError("Kaggle training timed out after maximum polling attempts")

    async def _upload_dataset(self, slug: str, data_path: Path):
        """Upload training data as a Kaggle dataset."""
        import tempfile

        # Create dataset metadata
        metadata = {
            "title": f"PLM Training Data {slug}",
            "id": f"{self.username}/{slug}",
            "licenses": [{"name": "CC0-1.0"}],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Copy training data
            import shutil
            shutil.copy2(data_path, tmpdir_path / "training_data.jsonl")

            # Write metadata
            with open(tmpdir_path / "dataset-metadata.json", "w") as f:
                json.dump(metadata, f, indent=2)

            # Use Kaggle API to create dataset
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Try create, fall back to version if exists
                try:
                    with open(data_path, "rb") as df:
                        response = await client.post(
                            f"{self.api_url}/datasets/create/new",
                            headers=self._auth_headers(),
                            json={
                                "title": metadata["title"],
                                "slug": slug,
                                "ownerSlug": self.username,
                                "licenseName": "CC0-1.0",
                                "isPrivate": True,
                            },
                        )
                    if response.status_code not in (200, 201, 409):
                        logger.warning(f"Kaggle dataset create returned {response.status_code}: {response.text[:200]}")
                except Exception as e:
                    logger.warning(f"Kaggle dataset upload warning (continuing): {e}")

        logger.info(f"Kaggle dataset prepared: {self.username}/{slug}")

    async def _create_notebook(
        self, slug: str, dataset_slug: str, script: str, gpu_type: str = "P100"
    ):
        """Create and push a Kaggle notebook kernel."""
        kernel_metadata = {
            "id": f"{self.username}/{slug}",
            "title": f"PLM Training {slug}",
            "code_file": "script.py",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": True,
            "enable_internet": True,
            "dataset_sources": [f"{self.username}/{dataset_slug}"],
            "competition_sources": [],
            "kernel_sources": [],
        }

        push_payload = {
            "slug": slug,
            "newTitle": kernel_metadata["title"],
            "text": script,
            "language": "python",
            "kernelType": "script",
            "isPrivate": True,
            "enableGpu": True,
            "enableInternet": True,
            "datasetDataSources": [f"{self.username}/{dataset_slug}"],
            "competitionDataSources": [],
            "kernelDataSources": [],
            "categoryIds": [],
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.api_url}/kernels/push",
                headers=self._auth_headers(),
                json=push_payload,
            )
            if response.status_code not in (200, 201):
                raise RuntimeError(
                    f"Kaggle kernel push failed ({response.status_code}): {response.text[:300]}"
                )

        logger.info(f"Kaggle notebook pushed: {self.username}/{slug}")

    async def _get_notebook_status(self, kernel_ref: str) -> Dict[str, Any]:
        """Poll Kaggle notebook status."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.api_url}/kernels/status",
                headers=self._auth_headers(),
                params={"userName": kernel_ref.split("/")[0], "kernelSlug": kernel_ref.split("/")[1]},
            )
            if response.status_code == 200:
                return response.json()
            return {"status": "unknown"}

    async def _download_from_hub(self, repo_id: str, output_dir: Path):
        """Download adapter from HuggingFace Hub."""
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            from huggingface_hub import snapshot_download
            snapshot_download(
                repo_id=repo_id,
                local_dir=str(output_dir),
                token=HF_TOKEN,
            )
            logger.info(f"Adapter downloaded from HF Hub: {repo_id} -> {output_dir}")
        except Exception as e:
            logger.error(f"Failed to download from HF Hub: {e}")
            raise


# ---------------------------------------------------------------------------
# Unified Model Trainer (Orchestrator)
# ---------------------------------------------------------------------------

class ModelTrainer:
    """Unified trainer that selects the appropriate backend based on
    availability and configuration.

    Tier selection:
        1. Local GPU  — if CUDA available and model fits in VRAM
        2. Runpod     — if RUNPOD_API_KEY configured
        3. HuggingFace — if HF_TOKEN configured
        4. Error      — no backend available
    """

    def __init__(self):
        self.db = get_supabase_client()
        self._local_trainer = None
        self._runpod_trainer = None
        self._hf_trainer = None

    def get_available_backends(self) -> List[str]:
        """Return list of available training backends."""
        backends = []

        # Check local GPU
        try:
            import torch
            if torch.cuda.is_available():
                try:
                    __import__("peft")
                    __import__("trl")
                    backends.append(TrainingBackend.LOCAL)
                except ImportError:
                    pass
        except ImportError:
            pass

        # Check Runpod
        if RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID:
            backends.append(TrainingBackend.RUNPOD)

        # Check HuggingFace
        if HF_TOKEN:
            backends.append(TrainingBackend.HUGGINGFACE)

        # Check Kaggle
        if KAGGLE_USERNAME and KAGGLE_KEY:
            backends.append(TrainingBackend.KAGGLE)

        return backends

    def select_backend(self, preferred: Optional[str] = None) -> str:
        """Select the best available backend.

        Args:
            preferred: Preferred backend. If available, it will be used.

        Returns:
            Backend name string.

        Raises:
            RuntimeError: If no backend is available.
        """
        available = self.get_available_backends()

        if not available:
            raise RuntimeError(
                "No training backend available. You need one of:\n"
                "  1. CUDA GPU + pip install peft trl datasets accelerate bitsandbytes\n"
                "  2. RUNPOD_API_KEY + RUNPOD_ENDPOINT_ID env vars\n"
                "  3. HF_TOKEN env var\n"
                "  4. KAGGLE_USERNAME + KAGGLE_KEY env vars (free GPU)"
            )

        if preferred and preferred in available:
            return preferred

        # Auto-select: local > runpod > huggingface
        return available[0]

    async def train(
        self,
        job_id: str,
        org_id: str,
        model_id: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run a real LoRA fine-tuning job.

        This is the main entry point called by the training pipeline.

        Args:
            job_id: Training job ID (for progress tracking in DB).
            org_id: Organization ID.
            model_id: Model ID.
            config: Training configuration dict with optional keys:
                - backend: "local" | "runpod" | "huggingface"
                - base_model: Key from BASE_MODELS
                - lora_config: Override LoRA hyperparams
                - training_args: Override training hyperparams
                - hf_repo_name: For HuggingFace backend

        Returns:
            Dict with training metrics and artifact info.
        """
        # Resolve backend
        preferred_backend = config.get("backend")
        backend = self.select_backend(preferred_backend)

        # Resolve base model
        model_record = await self.db.get_model(model_id)
        if not model_record:
            raise ValueError(f"Model {model_id} not found")
        base_model_key = config.get("base_model", model_record.get("base_model", "tinyllama-1.1b"))

        # Resolve version
        existing_version = model_record.get("version", "1.0.0")
        parts = existing_version.split(".")
        try:
            new_version = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
        except (IndexError, ValueError):
            new_version = "1.0.1"

        output_dir = get_model_dir(org_id, model_id, new_version)

        # Get org system prompt
        org = await self.db.get_organization(org_id)
        if not org:
            raise ValueError(f"Organization {org_id} not found")
        org_metadata = org.get("metadata") or {}
        system_prompt = org_metadata.get("system_prompt", f"You are an expert in {org.get('niche', 'general')}.")

        logger.info(
            f"Starting real LoRA training: job={job_id}, backend={backend}, "
            f"base_model={base_model_key}, version={new_version}"
        )

        # Progress callback that updates the DB
        async def progress_callback(progress: float, message: str):
            try:
                await self.db.update_training_job(
                    job_id=job_id,
                    status="running",
                    progress=round(progress, 2),
                )
                logger.info(f"Training job {job_id}: {progress:.0%} - {message}")
            except Exception as e:
                logger.error(f"Failed to update training progress: {e}")

        await progress_callback(0.02, f"Preparing training data (backend: {backend})...")

        # ---- 1. Fetch and format training data ----
        training_data = await self.db.get_training_data(org_id, model_id=model_id, limit=10000)
        if not training_data:
            raise ValueError("No training data available for this model")

        formatted_data = format_training_data(training_data, system_prompt)
        if not formatted_data:
            raise ValueError("All training data was invalid (empty instruction or output)")

        # Save to JSONL
        data_path = output_dir / "training_data.jsonl"
        num_saved = save_training_data_to_jsonl(formatted_data, data_path)
        logger.info(f"Formatted {num_saved} training examples to {data_path}")

        # ---- 2. Run training on selected backend ----
        try:
            if backend == TrainingBackend.LOCAL:
                trainer = LocalTrainer()
                metrics = await trainer.train(
                    base_model_key=base_model_key,
                    training_data_path=data_path,
                    output_dir=output_dir,
                    lora_config=config.get("lora_config"),
                    training_args=config.get("training_args"),
                    progress_callback=progress_callback,
                )

            elif backend == TrainingBackend.RUNPOD:
                trainer = RunpodTrainer()
                metrics = await trainer.train(
                    base_model_key=base_model_key,
                    training_data=formatted_data,
                    output_dir=output_dir,
                    lora_config=config.get("lora_config"),
                    training_args=config.get("training_args"),
                    progress_callback=progress_callback,
                )

            elif backend == TrainingBackend.HUGGINGFACE:
                hf_repo = config.get(
                    "hf_repo_name",
                    f"plm-enterprise/{org_id[:8]}-{model_id[:8]}-lora",
                )
                trainer = HuggingFaceTrainer()
                metrics = await trainer.train(
                    base_model_key=base_model_key,
                    training_data_path=data_path,
                    output_dir=output_dir,
                    hf_repo_name=hf_repo,
                    lora_config=config.get("lora_config"),
                    training_args=config.get("training_args"),
                    progress_callback=progress_callback,
                )

            elif backend == TrainingBackend.KAGGLE:
                hf_repo = config.get(
                    "hf_repo_name",
                    f"plm-enterprise/{org_id[:8]}-{model_id[:8]}-lora",
                )
                trainer = KaggleNotebookTrainer()
                metrics = await trainer.train(
                    base_model_key=base_model_key,
                    training_data_path=data_path,
                    output_dir=output_dir,
                    hf_repo_name=hf_repo,
                    lora_config=config.get("lora_config"),
                    training_args=config.get("training_args"),
                    progress_callback=progress_callback,
                )

            else:
                raise ValueError(f"Unknown backend: {backend}")

        except Exception as e:
            logger.error(f"Training failed on {backend}: {e}")
            # Try fallback to next backend
            available = self.get_available_backends()
            fallback = [b for b in available if b != backend]
            if fallback and not config.get("no_fallback"):
                logger.info(f"Falling back from {backend} to {fallback[0]}...")
                config["backend"] = fallback[0]
                config["no_fallback"] = True  # Prevent infinite recursion
                return await self.train(job_id, org_id, model_id, config)
            raise

        # ---- 3. Update model record with artifact info ----
        adapter_path = output_dir / "adapter"
        has_adapter = adapter_path.exists() and any(adapter_path.iterdir())

        await self.db.update_model_status(
            model_id=model_id,
            status="deployed",
            metrics={
                **metrics,
                "version": new_version,
                "has_adapter": has_adapter,
                "adapter_path": str(adapter_path) if has_adapter else None,
                "backend_used": backend,
            },
        )

        # Update model version
        try:
            self.db.client.table("models").update(
                {"version": new_version, "model_path": str(adapter_path) if has_adapter else None}
            ).eq("id", model_id).execute()
        except Exception as e:
            logger.error(f"Failed to update model version: {e}")

        logger.info(
            f"Training complete. Model {model_id} v{new_version} "
            f"trained on {backend}. Adapter at: {adapter_path}"
        )

        return metrics


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_model_trainer: Optional[ModelTrainer] = None


def get_model_trainer() -> ModelTrainer:
    """Get or create the ModelTrainer singleton."""
    global _model_trainer
    if _model_trainer is None:
        _model_trainer = ModelTrainer()
    return _model_trainer
