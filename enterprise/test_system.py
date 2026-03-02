"""
Quick Test Script - Verify Enterprise System Works

Tests all major components:
1. Supabase connection
2. RAG system
3. Fact checker
4. Training pipeline
5. API endpoints (if running)
"""

import sys
from pathlib import Path

# Add both enterprise and parent directory to path
enterprise_dir = Path(__file__).parent
parent_dir = enterprise_dir.parent
sys.path.insert(0, str(parent_dir))
sys.path.insert(0, str(enterprise_dir))

import asyncio
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_supabase():
    """Test Supabase connection"""
    print("\n" + "="*80)
    print("TEST 1: SUPABASE CONNECTION")
    print("="*80)

    try:
        from enterprise.db.db_client import get_supabase_client

        db = get_supabase_client()
        healthy = await db.health_check()

        if healthy:
            print("[OK] Supabase connection successful")
            return True
        else:
            print("[FAIL] Supabase connection failed")
            return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


async def test_rag_system():
    """Test RAG system"""
    print("\n" + "="*80)
    print("TEST 2: RAG SYSTEM")
    print("="*80)

    try:
        from enterprise.rag_system import RAGSystem

        rag = RAGSystem()

        if rag.is_ready():
            print("[OK] RAG system initialized")

            # Test embedding generation
            text = "This is a test document for RAG system"
            embedding = rag.generate_embedding(text)

            if embedding and len(embedding) > 0:
                print(f"[OK] Embedding generated: {len(embedding)} dimensions")
                return True
            else:
                print("[FAIL] Failed to generate embedding")
                return False
        else:
            print("[FAIL] RAG system not ready")
            return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


async def test_fact_checker():
    """Test fact checker"""
    print("\n" + "="*80)
    print("TEST 3: FACT CHECKER")
    print("="*80)

    try:
        from enterprise.fact_checker import FactChecker

        checker = FactChecker()

        if checker.is_ready():
            print("[OK] Fact checker initialized")

            # Test validation
            question = "What is Python?"
            answer = "Python is a high-level programming language known for its simplicity."

            result = await checker.validate_training_quality(question, answer)

            if result.get("score", 0) > 0:
                print(f"[OK] Validation working. Score: {result['score']}/10")
                return True
            else:
                print("[FAIL] Validation failed")
                return False
        else:
            print("[FAIL] Fact checker not ready")
            return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


async def test_training_pipeline():
    """Test training pipeline"""
    print("\n" + "="*80)
    print("TEST 4: TRAINING PIPELINE")
    print("="*80)

    try:
        from enterprise.training_pipeline import TrainingPipeline

        pipeline = TrainingPipeline()
        print("[OK] Training pipeline initialized")

        # Test topic generation
        topics = pipeline._generate_topics_from_niche("Healthcare AI")

        if topics and len(topics) > 0:
            print(f"[OK] Topic generation working. Generated {len(topics)} topics")
            print(f"     Sample: {topics[0]}")
            return True
        else:
            print("[FAIL] Topic generation failed")
            return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


async def test_api_endpoints():
    """Test API endpoints (if running)"""
    print("\n" + "="*80)
    print("TEST 5: API ENDPOINTS")
    print("="*80)

    try:
        import requests

        # Test health endpoint
        response = requests.get("http://localhost:8000/health", timeout=5)

        if response.status_code == 200:
            data = response.json()
            print("[OK] API health endpoint working")
            print(f"     Status: {data.get('status')}")
            print(f"     Supabase: {data.get('supabase')}")
            print(f"     RAG: {data.get('rag_system')}")
            return True
        else:
            print(f"[FAIL] API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("[SKIP] API not running (start with: uvicorn backend.api:app)")
        return None
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


async def test_full_flow():
    """Test complete flow: Create org → Generate data → Query"""
    print("\n" + "="*80)
    print("TEST 6: COMPLETE FLOW")
    print("="*80)

    try:
        from enterprise.db.db_client import get_supabase_client
        from enterprise.training_pipeline import TrainingPipeline
        import uuid

        db = get_supabase_client()
        pipeline = TrainingPipeline()

        # Create test organization
        org_slug = f"test-org-{uuid.uuid4().hex[:8]}"
        org = await db.create_organization(
            name="Test Organization",
            slug=org_slug,
            niche="Test Niche",
            tier="professional"
        )

        print(f"[OK] Created test organization: {org['id']}")

        # Create test model
        model = await db.create_model(
            org_id=org["id"],
            name="Test Model",
            base_model="llama-3.2-3b"
        )

        print(f"[OK] Created test model: {model['id']}")

        # Generate 2 training examples
        print("[...] Generating 2 training examples (takes ~20 seconds)...")

        await pipeline.generate_training_data(
            org_id=org["id"],
            model_id=model["id"],
            num_examples=2,
            topics=["Test topic 1", "Test topic 2"]
        )

        # Verify data was generated
        training_data = await db.get_training_data(
            org_id=org["id"],
            model_id=model["id"]
        )

        if len(training_data) > 0:
            print(f"[OK] Complete flow working! Generated {len(training_data)} examples")
            print(f"     Sample: {training_data[0]['instruction'][:100]}...")
            return True
        else:
            print("[FAIL] No training data generated")
            return False

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print(" PLM ENTERPRISE - SYSTEM TEST")
    print("="*80)

    results = {
        "Supabase Connection": await test_supabase(),
        "RAG System": await test_rag_system(),
        "Fact Checker": await test_fact_checker(),
        "Training Pipeline": await test_training_pipeline(),
        "API Endpoints": await test_api_endpoints(),
    }

    # Run full flow test if basic components work
    if all(v for v in results.values() if v is not None):
        print("\n[INFO] All basic tests passed. Running complete flow test...")
        results["Complete Flow"] = await test_full_flow()

    # Summary
    print("\n" + "="*80)
    print(" TEST SUMMARY")
    print("="*80)

    for test_name, result in results.items():
        if result is True:
            status = "[PASS]"
        elif result is False:
            status = "[FAIL]"
        else:
            status = "[SKIP]"

        print(f"{status} {test_name}")

    passed = sum(1 for v in results.values() if v is True)
    total = len([v for v in results.values() if v is not None])

    print("\n" + "="*80)
    print(f" RESULT: {passed}/{total} tests passed")
    print("="*80)

    if passed == total:
        print("\n[SUCCESS] All tests passed! System is ready for deployment.")
    else:
        print("\n[WARNING] Some tests failed. Check errors above.")


if __name__ == "__main__":
    asyncio.run(main())
