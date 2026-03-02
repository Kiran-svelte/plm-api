"""
PLM Enterprise Background Worker
Celery-based worker for async training, data generation, and maintenance tasks
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import logging
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("plm.worker")

# Try Celery if available, otherwise run standalone
try:
    from celery import Celery
    from celery.schedules import crontab

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    worker_app = Celery("plm_worker", broker=REDIS_URL, backend=REDIS_URL)
    worker_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        beat_schedule={
            "check-retrain-triggers": {
                "task": "enterprise.continuous_worker.check_all_retrain_triggers",
                "schedule": crontab(hour="*/6"),  # Every 6 hours
            },
            "cleanup-old-logs": {
                "task": "enterprise.continuous_worker.cleanup_old_data",
                "schedule": crontab(hour=3, minute=0),  # Daily at 3am
            },
            "health-report": {
                "task": "enterprise.continuous_worker.generate_health_report",
                "schedule": crontab(hour="*/1"),  # Every hour
            },
        },
    )
    HAS_CELERY = True
    logger.info("Celery worker initialized with Redis broker")

except ImportError:
    HAS_CELERY = False
    logger.warning("Celery not installed, running in standalone mode")
    worker_app = None


def run_async(coro):
    """Helper to run async code from sync context"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _check_all_retrain_triggers():
    """Check all models for retrain triggers"""
    from enterprise.db.db_client import get_supabase_client

    db = get_supabase_client(use_service_role=True)
    logger.info("Checking retrain triggers for all models...")

    try:
        response = (
            db.client.table("models")
            .select("*, organizations(*)")
            .eq("status", "deployed")
            .execute()
        )

        for model in (response.data or []):
            org_id = model["organization_id"]
            model_id = model["id"]

            # Check days since last deploy
            deployed_at = model.get("deployed_at")
            should_retrain = False
            reason = ""

            if deployed_at:
                deployed_date = datetime.fromisoformat(
                    deployed_at.replace("Z", "+00:00")
                )
                days_since = (
                    datetime.utcnow() - deployed_date.replace(tzinfo=None)
                ).days
                if days_since >= 7:
                    should_retrain = True
                    reason = "scheduled_weekly"

            # Check new training data count
            if not should_retrain:
                since_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
                td_response = (
                    db.client.table("training_data")
                    .select("id", count="exact")
                    .eq("organization_id", org_id)
                    .eq("model_id", model_id)
                    .gte("created_at", since_date)
                    .execute()
                )

                new_count = td_response.count if td_response.count is not None else len(td_response.data or [])
                threshold = int(os.getenv("AUTO_TRAIN_THRESHOLD", "100"))
                if new_count >= threshold:
                    should_retrain = True
                    reason = "new_data_threshold"

            if should_retrain:
                logger.info(
                    f"Triggering retrain for model {model_id} (reason: {reason})"
                )
                # Index new training data into knowledge base
                from enterprise.rag_system import RAGSystem
                from enterprise.continuous_learner import ContinuousLearner

                learner = ContinuousLearner()
                await learner._trigger_retrain(org_id, model_id, reason)

                # Advance model phase after retrain
                from enterprise.phase_manager import ModelPhaseManager
                phase_mgr = ModelPhaseManager(db)
                await phase_mgr.check_and_advance(org_id, model_id)

        logger.info("Retrain trigger check complete")

    except Exception as e:
        logger.error(f"Failed to check retrain triggers: {e}")


async def _cleanup_old_data():
    """Clean up old query logs and temporary data"""
    from enterprise.db.db_client import get_supabase_client

    db = get_supabase_client()
    cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()

    try:
        # Clean old audit logs (keep 90 days)
        db.client.table("audit_logs").delete().lt("created_at", cutoff).execute()
        logger.info("Cleaned up old audit logs (90+ days)")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")


async def _generate_health_report():
    """Generate system health report"""
    from enterprise.db.db_client import get_supabase_client
    from src.generators.free_api_clients import FreeAPIManager

    db = get_supabase_client()
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "database": False,
        "apis": {},
        "models": {"total": 0, "deployed": 0, "failed": 0},
    }

    try:
        # Check database
        report["database"] = await db.health_check()

        # Check APIs
        api_manager = FreeAPIManager()
        report["apis"] = api_manager.health_check()

        # Check models
        models_response = db.client.table("models").select("status").execute()
        for m in (models_response.data or []):
            report["models"]["total"] += 1
            if m["status"] == "deployed":
                report["models"]["deployed"] += 1
            elif m["status"] == "failed":
                report["models"]["failed"] += 1

        logger.info(f"Health report: {report}")
        return report

    except Exception as e:
        logger.error(f"Health report generation failed: {e}")
        report["error"] = str(e)
        return report


# Register Celery tasks if available
if HAS_CELERY and worker_app:

    @worker_app.task(name="enterprise.continuous_worker.check_all_retrain_triggers")
    def check_all_retrain_triggers():
        return run_async(_check_all_retrain_triggers())

    @worker_app.task(name="enterprise.continuous_worker.cleanup_old_data")
    def cleanup_old_data():
        return run_async(_cleanup_old_data())

    @worker_app.task(name="enterprise.continuous_worker.generate_health_report")
    def generate_health_report():
        return run_async(_generate_health_report())

    @worker_app.task(name="enterprise.continuous_worker.process_training_job")
    def process_training_job(job_id: str, org_id: str, model_id: str, config: dict):
        from enterprise.training_pipeline import TrainingPipeline

        pipeline = TrainingPipeline()
        return run_async(
            pipeline.train_model(job_id, org_id, model_id, config)
        )

    @worker_app.task(name="enterprise.continuous_worker.process_data_generation")
    def process_data_generation(
        org_id: str, model_id: str, num_examples: int, topics: list
    ):
        from enterprise.training_pipeline import TrainingPipeline

        pipeline = TrainingPipeline()
        return run_async(
            pipeline.generate_training_data(org_id, model_id, num_examples, topics)
        )


# Standalone mode (no Celery)
if __name__ == "__main__":
    import time

    logger.info("Starting PLM worker in standalone mode...")
    logger.info("Running periodic tasks in a loop (Ctrl+C to stop)")

    while True:
        try:
            logger.info("--- Running scheduled tasks ---")
            run_async(_check_all_retrain_triggers())
            run_async(_generate_health_report())
            logger.info("--- Tasks complete. Sleeping 6 hours ---")
            time.sleep(21600)  # 6 hours
        except KeyboardInterrupt:
            logger.info("Worker stopped.")
            break
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            time.sleep(60)
