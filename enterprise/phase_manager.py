"""
PLM Model Phase Manager
State machine tracking model lifecycle:
  COLLECTING -> READY_TO_TRAIN -> TRAINING -> DEPLOYED -> LEARNING
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

PHASES = ["collecting", "ready_to_train", "training", "deployed", "learning"]
DEFAULT_DATA_TARGET = int(os.getenv("AUTO_TRAIN_THRESHOLD", "100"))  # examples before first training


class ModelPhaseManager:
    """Central state machine managing model lifecycle phases."""

    def __init__(self, db):
        self.db = db

    async def get_phase(self, org_id: str, model_id: str) -> Dict[str, Any]:
        """Get current phase info for a model with live stats."""
        model = await self.db.get_model(model_id)
        if not model:
            return {"phase": "collecting", "training_data_count": 0}

        metrics = model.get("metrics") or {}
        phase = metrics.get("phase", "collecting")
        has_adapter = metrics.get("has_adapter", False)
        gpu_backend = metrics.get("gpu_backend")
        data_target = metrics.get("training_data_target", DEFAULT_DATA_TARGET)

        # Get live training data count
        count = await self.db.get_training_data_count(org_id, model_id)

        # Determine privacy availability
        privacy_available = has_adapter and self._check_model_server_available()

        # Calculate generation rate (examples in last hour)
        rate_per_hour = await self._estimate_generation_rate(org_id, model_id)
        examples_today = await self._get_today_count(org_id, model_id)

        # Estimate readiness
        estimated_ready_at = None
        if phase == "collecting" and rate_per_hour > 0 and count < data_target:
            hours_remaining = (data_target - count) / rate_per_hour
            estimated_ready_at = (datetime.utcnow() + timedelta(hours=hours_remaining)).isoformat()

        # Training activity (visible during training or after)
        training_activity = None
        if phase in ("training", "deployed", "learning"):
            training_activity = {
                "started_at": metrics.get("training_started_at"),
                "completed_at": metrics.get("last_training_at"),
                "backend_used": metrics.get("gpu_backend", "unknown"),
                "base_model": model.get("base_model", "tinyllama-1.1b"),
                "data_used": metrics.get("last_train_data_count", count),
                "current_step": metrics.get("training_current_step", ""),
                "steps_log": metrics.get("training_steps_log", []),
                "training_results": metrics.get("training_results"),
            }

        return {
            "phase": phase,
            "sub_status": metrics.get("sub_status"),
            "training_data_count": count,
            "training_data_target": data_target,
            "progress_pct": min(100.0, (count / max(data_target, 1)) * 100),
            "has_adapter": has_adapter,
            "privacy_mode_available": privacy_available,
            "privacy_mode_forced": metrics.get("privacy_mode_forced", False),
            "auto_learning_enabled": metrics.get("auto_learning_enabled", True),
            "gpu_backend": gpu_backend,
            "base_model": model.get("base_model", "tinyllama-1.1b"),
            "estimated_ready_at": estimated_ready_at,
            "generation_rate_per_hour": rate_per_hour,
            "examples_generated_today": examples_today,
            "last_training_at": metrics.get("last_training_at"),
            "training_activity": training_activity,
        }

    async def check_and_advance(self, org_id: str, model_id: str) -> str:
        """Check conditions and advance phase if appropriate."""
        model = await self.db.get_model(model_id)
        if not model:
            return "collecting"

        metrics = model.get("metrics") or {}
        current_phase = metrics.get("phase", "collecting")
        has_adapter = metrics.get("has_adapter", False)
        gpu_backend = metrics.get("gpu_backend")
        data_target = metrics.get("training_data_target", DEFAULT_DATA_TARGET)

        count = await self.db.get_training_data_count(org_id, model_id)

        if current_phase == "collecting":
            if count >= data_target:
                if gpu_backend:
                    await self._transition(model_id, metrics, "ready_to_train")
                    return "ready_to_train"
                else:
                    await self._set_sub_status(model_id, metrics, "waiting_for_gpu")
                    return "collecting"

        elif current_phase == "ready_to_train":
            # Auto-trigger training
            return await self._trigger_training(org_id, model_id, metrics)

        elif current_phase == "deployed":
            # Transition to learning mode
            await self._transition(model_id, metrics, "learning")
            return "learning"

        elif current_phase == "learning":
            # Check retrain threshold (500 new examples since last training)
            retrain_threshold = metrics.get("retrain_threshold", 500)
            last_train_count = metrics.get("last_train_data_count", 0)
            new_since_train = count - last_train_count
            if new_since_train >= retrain_threshold and gpu_backend:
                return await self._trigger_training(org_id, model_id, metrics)

        return current_phase

    async def on_training_complete(
        self, model_id: str, success: bool,
        adapter_path: Optional[str] = None,
        training_metrics: Optional[Dict] = None,
    ):
        """Called when a training job completes."""
        model = await self.db.get_model(model_id)
        metrics = (model.get("metrics") or {}) if model else {}

        if success and adapter_path:
            count = 0
            if model:
                org_id = model.get("organization_id", "")
                count = await self.db.get_training_data_count(org_id, model_id)

            updates = {
                **metrics,
                "phase": "deployed",
                "sub_status": None,
                "has_adapter": True,
                "adapter_path": adapter_path,
                "last_training_at": datetime.utcnow().isoformat(),
                "last_train_data_count": count,
            }
            if training_metrics:
                updates["training_results"] = training_metrics

            await self.db.update_model_status(model_id, "deployed", updates)
            logger.info(f"Model {model_id} deployed with adapter at {adapter_path}")
        else:
            # Training failed — revert to collecting
            updates = {**metrics, "phase": "collecting", "sub_status": "training_failed"}
            await self.db.update_model_status(model_id, "ready", updates)
            logger.warning(f"Training failed for model {model_id}, reverting to collecting")

    async def set_gpu_backend(self, model_id: str, backend: str, config: Dict[str, Any]):
        """Configure GPU backend for a model."""
        model = await self.db.get_model(model_id)
        metrics = (model.get("metrics") or {}) if model else {}

        metrics["gpu_backend"] = backend
        metrics["gpu_config"] = config

        await self.db.update_model_status(model_id, model.get("status", "ready"), metrics)
        logger.info(f"GPU backend set to {backend} for model {model_id}")

        # Re-check phase advancement with GPU now available
        if model:
            await self.check_and_advance(model.get("organization_id", ""), model_id)

    async def _trigger_training(self, org_id: str, model_id: str, metrics: Dict) -> str:
        """Create training job and transition to training phase."""
        metrics["training_started_at"] = datetime.utcnow().isoformat()
        metrics["training_current_step"] = "Initializing training pipeline"
        metrics["training_steps_log"] = [
            {"step": "Starting", "time": datetime.utcnow().isoformat(), "detail": "Training triggered automatically"},
        ]
        await self._transition(model_id, metrics, "training")

        try:
            from enterprise.training_pipeline import TrainingPipeline
            pipeline = TrainingPipeline()

            # Get the model's base_model key
            model = await self.db.get_model(model_id)
            base_model = model.get("base_model", "tinyllama-1.1b") if model else "tinyllama-1.1b"

            import asyncio
            asyncio.create_task(self._run_training(org_id, model_id, base_model, pipeline))
        except Exception as exc:
            logger.error(f"Failed to start training for model {model_id}: {exc}")
            await self._transition(model_id, metrics, "collecting")
            return "collecting"

        return "training"

    async def _run_training(self, org_id: str, model_id: str, base_model: str, pipeline):
        """Background task: run the actual training."""
        try:
            # Log: fetching training data
            await self._log_training_step(model_id, "Preparing data", "Loading training examples from database")

            result = await pipeline.train_model(
                org_id=org_id,
                model_id=model_id,
                base_model=base_model,
            )

            # Log: training completed, checking results
            await self._log_training_step(model_id, "Checking results", "Training finished, verifying adapter files")

            # Determine success
            model = await self.db.get_model(model_id)
            metrics = (model.get("metrics") or {}) if model else {}
            adapter_path = metrics.get("adapter_path")
            has_adapter = metrics.get("has_adapter", False)

            if has_adapter:
                await self._log_training_step(model_id, "Deploying model", f"Adapter saved at {adapter_path}")

            await self.on_training_complete(
                model_id, success=has_adapter, adapter_path=adapter_path
            )
        except Exception as exc:
            logger.error(f"Training failed for {model_id}: {exc}")
            await self._log_training_step(model_id, "Failed", str(exc))
            await self.on_training_complete(model_id, success=False)

    async def _log_training_step(self, model_id: str, step: str, detail: str = ""):
        """Append a step to the training activity log in model metrics."""
        try:
            model = await self.db.get_model(model_id)
            if not model:
                return
            metrics = model.get("metrics") or {}
            steps_log = metrics.get("training_steps_log", [])
            steps_log.append({
                "step": step,
                "time": datetime.utcnow().isoformat(),
                "detail": detail,
            })
            # Keep last 20 entries to avoid metrics bloat
            metrics["training_steps_log"] = steps_log[-20:]
            metrics["training_current_step"] = step
            await self.db.update_model_status(model_id, model.get("status", "ready"), metrics)
        except Exception as exc:
            logger.warning(f"Failed to log training step for {model_id}: {exc}")

    async def _transition(self, model_id: str, metrics: Dict, new_phase: str):
        """Transition model to a new phase."""
        metrics["phase"] = new_phase
        metrics["sub_status"] = None
        metrics["phase_changed_at"] = datetime.utcnow().isoformat()
        await self.db.update_model_status(model_id, "ready", metrics)
        logger.info(f"Model {model_id} transitioned to phase: {new_phase}")

    async def _set_sub_status(self, model_id: str, metrics: Dict, sub_status: str):
        """Set sub-status without changing phase."""
        metrics["sub_status"] = sub_status
        await self.db.update_model_status(
            model_id, "ready", metrics
        )

    def _check_model_server_available(self) -> bool:
        """Check if model server can run local inference."""
        try:
            from enterprise.model_server import ModelServer
            server = ModelServer()
            return server.is_available()
        except Exception:
            return False

    async def _estimate_generation_rate(self, org_id: str, model_id: str) -> float:
        """Estimate examples generated per hour based on recent activity."""
        try:
            data = await self.db.get_training_data(org_id, model_id, limit=100)
            if not data or len(data) < 2:
                return 0.0

            # Look at timestamps of recent entries
            timestamps = []
            for d in data:
                created = d.get("created_at")
                if created:
                    if isinstance(created, str):
                        try:
                            ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
                            timestamps.append(ts)
                        except (ValueError, TypeError):
                            pass

            if len(timestamps) < 2:
                return 0.0

            timestamps.sort()
            time_span = (timestamps[-1] - timestamps[0]).total_seconds()
            if time_span <= 0:
                return 0.0

            hours = time_span / 3600.0
            return len(timestamps) / max(hours, 0.01)
        except Exception:
            return 0.0

    async def _get_today_count(self, org_id: str, model_id: str) -> int:
        """Get count of examples generated today."""
        try:
            today = datetime.utcnow().date().isoformat()
            result = (
                self.db.client.table("training_data")
                .select("id", count="exact")
                .eq("organization_id", org_id)
                .eq("model_id", model_id)
                .gte("created_at", today)
                .execute()
            )
            return result.count if result.count else 0
        except Exception:
            return 0
