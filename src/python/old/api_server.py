from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any, Optional
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import json

# Load environment variables
load_dotenv()

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_KEY", "")
)

class SystemEvent(BaseModel):
    event_type: str
    timestamp: datetime
    user: str
    data: Dict[str, Any]
    severity: Optional[str] = "info"

@app.post("/events")
async def log_event(event: SystemEvent):
    """Log a system event to the database"""
    try:
        # Insert event into Supabase
        data = {
            "event_type": event.event_type,
            "timestamp": event.timestamp.isoformat(),
            "user": event.user,
            "data": json.dumps(event.data),
            "severity": event.severity
        }
        
        result = supabase.table("system_events").insert(data).execute()
        return {"status": "success", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/events/{user_id}")
async def get_user_events(user_id: str, limit: int = 100):
    """Get events for a specific user"""
    try:
        result = supabase.table("system_events")\
            .select("*")\
            .eq("user", user_id)\
            .order("timestamp", desc=True)\
            .limit(limit)\
            .execute()
        return {"status": "success", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/events/severity/{severity}")
async def get_events_by_severity(severity: str, limit: int = 100):
    """Get events filtered by severity"""
    try:
        result = supabase.table("system_events")\
            .select("*")\
            .eq("severity", severity)\
            .order("timestamp", desc=True)\
            .limit(limit)\
            .execute()
        return {"status": "success", "data": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
