"""
PLM SaaS Platform - REST API
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parent))

from multi_tenant import MultiTenantManager
from startup_generator import StartupDataGenerator

app = FastAPI(
    title="PLM SaaS Platform",
    description="Generate custom AI models for startups",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize manager
manager = MultiTenantManager()

# Models
class StartupCreate(BaseModel):
    name: str
    niche: str
    topics: List[str]

class GenerateRequest(BaseModel):
    num_examples: int = 1000

# Routes

@app.get("/")
async def root():
    return {"message": "PLM SaaS Platform API", "version": "1.0.0"}

@app.get("/stats")
async def get_platform_stats():
    """Get platform-wide statistics"""
    return manager.get_stats()

@app.post("/startups")
async def create_startup(startup: StartupCreate):
    """Onboard a new startup"""
    startup_id = manager.create_startup(
        name=startup.name,
        niche=startup.niche,
        topics=startup.topics
    )
    return {
        "startup_id": startup_id,
        "message": f"Startup {startup.name} created successfully"
    }

@app.get("/startups")
async def list_startups():
    """List all startups"""
    return manager.list_startups()

@app.get("/startups/{startup_id}")
async def get_startup(startup_id: str):
    """Get startup details"""
    startup = manager.get_startup(startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    # Add generation progress
    workspace = Path(f"./workspaces/{startup_id}")
    stats_file = workspace / "stats.json"

    if stats_file.exists():
        with open(stats_file, 'r') as f:
            startup['generation_stats'] = json.load(f)

    return startup

@app.post("/startups/{startup_id}/generate")
async def generate_data(
    startup_id: str,
    request: GenerateRequest,
    background_tasks: BackgroundTasks
):
    """Start data generation for a startup"""
    startup = manager.get_startup(startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    workspace = Path(f"./workspaces/{startup_id}")

    # Update status
    manager.update_status(startup_id, "model_status", "generating")

    # Start generation in background
    def generate_task():
        generator = StartupDataGenerator(startup_id, workspace)
        generator.generate_batch(request.num_examples)
        manager.update_status(startup_id, "model_status", "ready_for_training")

    background_tasks.add_task(generate_task)

    return {
        "message": f"Generation started for {startup['name']}",
        "num_examples": request.num_examples,
        "status": "generating"
    }

@app.get("/startups/{startup_id}/data")
async def get_training_data(startup_id: str):
    """Get generated training data"""
    startup = manager.get_startup(startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    workspace = Path(f"./workspaces/{startup_id}")
    data_file = workspace / "training_data.json"

    if not data_file.exists():
        return {"data": [], "count": 0}

    with open(data_file, 'r') as f:
        data = json.load(f)

    return {
        "data": data[:10],  # Return first 10 for preview
        "count": len(data),
        "full_data_path": str(data_file)
    }

@app.get("/startups/{startup_id}/download")
async def download_model_package(startup_id: str):
    """Get model package for deployment"""
    startup = manager.get_startup(startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    workspace = Path(f"./workspaces/{startup_id}")
    deployment_guide = workspace / "DEPLOYMENT_GUIDE.md"

    # Create deployment package info
    package = {
        "startup_id": startup_id,
        "name": startup['name'],
        "niche": startup['niche'],
        "training_data": str(workspace / "training_data.json"),
        "instructions": "Follow the Colab notebook to train your model",
        "deployment_guide": str(deployment_guide) if deployment_guide.exists() else None
    }

    return package

@app.delete("/startups/{startup_id}")
async def delete_startup(startup_id: str):
    """Delete a startup (admin only)"""
    startup = manager.get_startup(startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    # Remove from clients
    del manager.clients[startup_id]
    manager._save_clients()

    return {"message": f"Startup {startup_id} deleted"}

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
