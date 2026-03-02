"""
Quick Component Check - Verify all components can be imported
"""

import sys
from pathlib import Path

# Add paths
enterprise_dir = Path(__file__).parent
parent_dir = enterprise_dir.parent
sys.path.insert(0, str(parent_dir))
sys.path.insert(0, str(enterprise_dir))

print("=" * 80)
print(" PLM ENTERPRISE - QUICK COMPONENT CHECK")
print("=" * 80)

components = []

# Test 1: Supabase Client
try:
    from enterprise.db.db_client import SupabaseClient, get_supabase_client
    print("[OK] Supabase client imports successfully")
    components.append(("Supabase Client", True))
except Exception as e:
    print(f"[FAIL] Supabase client import failed: {e}")
    components.append(("Supabase Client", False))

# Test 2: RAG System
try:
    from enterprise.rag_system import RAGSystem
    print("[OK] RAG system imports successfully")
    components.append(("RAG System", True))
except Exception as e:
    print(f"[FAIL] RAG system import failed: {e}")
    components.append(("RAG System", False))

# Test 3: Fact Checker
try:
    from enterprise.fact_checker import FactChecker
    print("[OK] Fact checker imports successfully")
    components.append(("Fact Checker", True))
except Exception as e:
    print(f"[FAIL] Fact checker import failed: {e}")
    components.append(("Fact Checker", False))

# Test 4: Continuous Learner
try:
    from enterprise.continuous_learner import ContinuousLearner
    print("[OK] Continuous learner imports successfully")
    components.append(("Continuous Learner", True))
except Exception as e:
    print(f"[FAIL] Continuous learner import failed: {e}")
    components.append(("Continuous Learner", False))

# Test 5: Training Pipeline
try:
    from enterprise.training_pipeline import TrainingPipeline
    print("[OK] Training pipeline imports successfully")
    components.append(("Training Pipeline", True))
except Exception as e:
    print(f"[FAIL] Training pipeline import failed: {e}")
    components.append(("Training Pipeline", False))

# Test 6: Backend API
try:
    from enterprise.backend.api import app
    print("[OK] Backend API imports successfully")
    components.append(("Backend API", True))
except Exception as e:
    print(f"[FAIL] Backend API import failed: {e}")
    components.append(("Backend API", False))

# Test 7: FREE API Manager (from existing src)
try:
    from src.generators.free_api_clients import FreeAPIManager
    api_manager = FreeAPIManager()
    print("[OK] FREE API Manager working")
    components.append(("FREE API Manager", True))
except Exception as e:
    print(f"[FAIL] FREE API Manager failed: {e}")
    components.append(("FREE API Manager", False))

print("\n" + "=" * 80)
print(" SUMMARY")
print("=" * 80)

for name, status in components:
    status_str = "[PASS]" if status else "[FAIL]"
    print(f"{status_str} {name}")

passed = sum(1 for _, status in components if status)
total = len(components)

print("\n" + "=" * 80)
print(f" RESULT: {passed}/{total} components working")
print("=" * 80)

if passed == total:
    print("\n[SUCCESS] All components ready! System can be deployed.")
    print("\nNext steps:")
    print("1. Run: python test_system.py (for full integration test)")
    print("2. Run: python -m uvicorn enterprise.backend.api:app --reload")
    print("3. Access API docs: http://localhost:8000/docs")
elif passed >= total * 0.7:
    print("\n[PARTIAL] Most components ready. Some dependencies may need installation.")
    print("Install: pip install -r enterprise/requirements.txt")
else:
    print("\n[WARNING] Multiple components failed. Check dependencies.")
    print("Install: pip install -r enterprise/requirements.txt")
