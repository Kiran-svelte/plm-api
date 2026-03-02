"""
PLM SaaS Platform - Multi-Tenant Architecture
Generate custom AI models for 50+ startups
"""

import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

class StartupClient:
    """Represents a single startup customer"""

    def __init__(self, startup_id: str, name: str, niche: str, topics: List[str]):
        self.startup_id = startup_id
        self.name = name
        self.niche = niche
        self.topics = topics
        self.created_at = datetime.now().isoformat()
        self.status = "active"
        self.data_generated = 0
        self.model_status = "pending"

        # Create workspace
        self.workspace = Path(f"./workspaces/{startup_id}")
        self.workspace.mkdir(parents=True, exist_ok=True)

    def to_dict(self):
        return {
            "startup_id": self.startup_id,
            "name": self.name,
            "niche": self.niche,
            "topics": self.topics,
            "created_at": self.created_at,
            "status": self.status,
            "data_generated": self.data_generated,
            "model_status": self.model_status,
            "workspace": str(self.workspace)
        }

    def save(self):
        """Save client configuration"""
        config_file = self.workspace / "config.json"
        with open(config_file, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

class MultiTenantManager:
    """Manages multiple startup clients"""

    def __init__(self):
        self.workspaces_dir = Path("./workspaces")
        self.workspaces_dir.mkdir(exist_ok=True)

        self.clients_file = Path("./clients.json")
        self.clients = self._load_clients()

    def _load_clients(self) -> Dict[str, Dict]:
        """Load all clients from storage"""
        if self.clients_file.exists():
            with open(self.clients_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_clients(self):
        """Save all clients to storage"""
        with open(self.clients_file, 'w') as f:
            json.dump(self.clients, f, indent=2)

    def create_startup(self, name: str, niche: str, topics: List[str]) -> str:
        """Onboard a new startup"""
        startup_id = str(uuid.uuid4())[:8]

        client = StartupClient(startup_id, name, niche, topics)
        client.save()

        self.clients[startup_id] = client.to_dict()
        self._save_clients()

        print(f"[OK] Created startup: {name} (ID: {startup_id})")
        return startup_id

    def get_startup(self, startup_id: str) -> Dict:
        """Get startup details"""
        return self.clients.get(startup_id)

    def list_startups(self) -> List[Dict]:
        """List all startups"""
        return list(self.clients.values())

    def update_status(self, startup_id: str, key: str, value: Any):
        """Update startup status"""
        if startup_id in self.clients:
            self.clients[startup_id][key] = value
            self._save_clients()

    def get_stats(self) -> Dict:
        """Get platform statistics"""
        total = len(self.clients)
        active = sum(1 for c in self.clients.values() if c['status'] == 'active')
        total_data = sum(c['data_generated'] for c in self.clients.values())

        models_pending = sum(1 for c in self.clients.values() if c['model_status'] == 'pending')
        models_training = sum(1 for c in self.clients.values() if c['model_status'] == 'training')
        models_ready = sum(1 for c in self.clients.values() if c['model_status'] == 'ready')

        return {
            "total_startups": total,
            "active_startups": active,
            "total_data_generated": total_data,
            "models_pending": models_pending,
            "models_training": models_training,
            "models_ready": models_ready
        }

# Example usage
if __name__ == "__main__":
    manager = MultiTenantManager()

    # Example: Onboard 5 startups
    startups = [
        {
            "name": "HealthTech AI",
            "niche": "Healthcare Technology",
            "topics": ["Medical AI", "Patient care", "Healthcare data", "Telemedicine", "Medical diagnosis"]
        },
        {
            "name": "FinanceBot Pro",
            "niche": "Financial Technology",
            "topics": ["Personal finance", "Investment strategies", "Crypto trading", "Financial planning", "Tax optimization"]
        },
        {
            "name": "EduLearn AI",
            "niche": "Educational Technology",
            "topics": ["Online learning", "Course creation", "Student engagement", "Learning analytics", "Educational content"]
        },
        {
            "name": "DevTools Plus",
            "niche": "Developer Tools",
            "topics": ["Code review", "CI/CD", "Testing automation", "DevOps", "Code quality"]
        },
        {
            "name": "MarketBoost AI",
            "niche": "Digital Marketing",
            "topics": ["SEO optimization", "Content marketing", "Social media", "Email campaigns", "Marketing analytics"]
        }
    ]

    print("\n" + "="*60)
    print("ONBOARDING STARTUPS")
    print("="*60 + "\n")

    for startup in startups:
        manager.create_startup(**startup)

    print("\n" + "="*60)
    print("PLATFORM STATISTICS")
    print("="*60)

    stats = manager.get_stats()
    for key, value in stats.items():
        print(f"{key:.<30} {value}")

    print("\n" + "="*60)
