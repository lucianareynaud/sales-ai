import os
import uuid
import traceback
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from config import UPLOAD_DIR, SUPPORTED_FORMATS, OPENAI_API_KEY
from transcription import transcription_service
from db import supabase
from analysis_svc.pipeline import run_analysis_pipeline

# Initialize app
app = FastAPI(title="Whisper Transcription")

# Create upload directory
UPLOAD_DIR.mkdir(exist_ok=True)

# Check app mode
demo_mode = not bool(OPENAI_API_KEY) or OPENAI_API_KEY == "demo_mode"
if demo_mode:
    logger.warning("App running in demo mode. Set OPENAI_API_KEY in .env file for real transcriptions.")
else:
    logger.info(f"OpenAI API key configured: {OPENAI_API_KEY[:4]}***")

# Log Supabase status
logger.info("=== Supabase Status ===")
logger.info(f"Demo mode: {supabase.is_demo_mode}")
logger.info(f"Anon client: {'Available' if supabase.client else 'Unavailable'}")
logger.info(f"Admin client: {'Available' if supabase.admin_client else 'Unavailable'}")
logger.info(f"Storage bucket: {os.getenv('SUPABASE_STORAGE_BUCKET', 'transcripts')}")
logger.info("=====================")

# Set up static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Models
class TranscriptionResponse(BaseModel):
    transcript_id: str
    filename: str
    transcript: str
    duration_seconds: int
    language: str
    file_url: Optional[str] = None

class ErrorResponse(BaseModel):
    detail: str

class TranscriptListItem(BaseModel):
    id: str
    transcript: str
    storage_path: str
    duration_seconds: int
    language: str
    created_at: str
    
class SalesAnalysisResponse(BaseModel):
    transcript_id: str
    sales_data: Dict[str, Any]

# Routes
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the home page"""
    return templates.TemplateResponse(
        "index.html", 
        {"request": request}
    )

@app.post("/transcribe/", response_model=TranscriptionResponse)
async def transcribe(file: UploadFile = File(...)):
    """Transcribe an audio/video file and store the transcript in Supabase (without uploading the file)"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    # Check format
    if not transcription_service.validate_file(file.filename):
        supported_formats = ", ".join([".mp3", ".wav", ".m4a", ".mp4", ".mov", ".ogg"]) 
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported format. Supported formats include: {supported_formats}, and more."
        )
    
    # Generate a unique filename for local storage
    file_id = str(uuid.uuid4())
    file_ext = os.path.splitext(file.filename)[1].lower()
    temp_file_path = UPLOAD_DIR / f"{file_id}{file_ext}"
    
    try:
        # Save uploaded file locally first
        with open(temp_file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"File '{file.filename}' saved locally as '{temp_file_path}' ({os.path.getsize(temp_file_path)} bytes)")
        
        # Process the file (now only stores transcript, not the file)
        result = transcription_service.process_and_store(
            file_path=str(temp_file_path),
            original_filename=file.filename,
            language="pt"
        )
        
        # Verify the result contains required fields
        if not result or not isinstance(result, dict):
            raise ValueError(f"Invalid result from transcription service: {result}")
        
        for required_field in ["transcript_id", "transcript"]:
            if required_field not in result or not result[required_field]:
                raise ValueError(f"Missing required field in result: {required_field}")
        
        # Log results            
        if "transcript_id" in result:
            logger.info(f"✅ Transcript saved with ID: {result['transcript_id']}")
            
        # Always keep the local file as we're not uploading to storage
        logger.info(f"Keeping local file: {temp_file_path}")
        
        # Remove upload_success field from response since we don't upload
        if "upload_success" in result:
            del result["upload_success"]
        
        # Also remove file_url as it's just a local reference
        if "file_url" in result:
            del result["file_url"]
            
        return result
    
    except Exception as e:
        # Clean up on error
        try:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                logger.info(f"Deleted temporary file after error: {temp_file_path}")
        except Exception as cleanup_error:
            logger.warning(f"Cleanup error: {str(cleanup_error)}")
        
        error_message = str(e)
        logger.error(f"Error during transcription: {error_message}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_message)

@app.get("/transcripts/", response_model=List[TranscriptListItem])
async def list_transcripts():
    """Get all stored transcripts"""
    try:
        transcripts = supabase.get_all_transcripts()
        return transcripts
    except Exception as e:
        logger.error(f"Error listing transcripts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcripts/{transcript_id}", response_model=dict)
async def get_transcript_api(transcript_id: str):
    """Get details of a specific transcript via API"""
    try:
        transcript = supabase.get_transcript(transcript_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
        return transcript
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcript: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcript/{transcript_id}", response_class=HTMLResponse)
async def get_transcript_page(request: Request, transcript_id: str):
    """Render a page showing a specific transcript"""
    try:
        # Pass the transcript ID to the template
        return templates.TemplateResponse(
            "index.html", 
            {"request": request, "transcript_id": transcript_id}
        )
    except Exception as e:
        logger.error(f"Error loading transcript page: {str(e)}")
        return RedirectResponse(url="/")

@app.post("/transcripts/{transcript_id}/analyze", response_model=SalesAnalysisResponse)
async def analyze_transcript(transcript_id: str):
    """
    Analyze a transcript for sales intelligence using LLM
    
    Args:
        transcript_id: ID of the transcript to analyze
        
    Returns:
        JSON with structured sales intelligence data
    """
    try:
        # Check if transcript exists
        transcript = supabase.get_transcript(transcript_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
            
        # Run the analysis pipeline
        result = await run_analysis_pipeline(transcript_id)
        
        # Return the analysis results
        return {
            "transcript_id": transcript_id,
            "sales_data": result.get("sales_data", {})
        }
    except ValueError as e:
        # Handle validation errors
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Error analyzing transcript: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True) 