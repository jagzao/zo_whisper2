from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from deepseek_runner import generate_summary
import logging
from datetime import datetime
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DeepSeek Summary Service", version="1.0.0")

class TranscriptRequest(BaseModel):
    text: str

@app.get("/health")
def health_check():
    """Health check endpoint for Docker health checks"""
    try:
        # Basic health checks
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "deepseek-summary",
            "version": "1.0.0"
        }
        
        # Check environment variables
        if not os.getenv("OPENAI_API_KEY") and not os.getenv("DEEPSEEK_API_KEY"):
            health_status["status"] = "warning"
            health_status["message"] = "No API keys configured"
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/")
def root():
    """Root endpoint with service information"""
    return {
        "service": "DeepSeek Summary Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "summary": "/generate-summary"
        }
    }

@app.post("/generate-summary")
def summarize(request: TranscriptRequest):
    """Generate summary from transcript text"""
    try:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text content is required")
        
        logger.info(f"Generating summary for text of length: {len(request.text)}")
        summary = generate_summary(request.text)
        
        return {
            "summary": summary,
            "timestamp": datetime.now().isoformat(),
            "text_length": len(request.text)
        }
        
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")
