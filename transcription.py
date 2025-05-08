from dotenv import load_dotenv
import os
import uuid
import time
import tempfile
import traceback
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from openai import OpenAI, OpenAIError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure environment variables are loaded
load_dotenv()

from config import OPENAI_API_KEY, SUPPORTED_FORMATS, SUPABASE_STORAGE_BUCKET
from db import supabase
from media import get_media_duration, preprocess_audio, chunk_audio, merge_transcripts, optimize_audio_for_transcription, extract_high_quality_audio

# Whisper API constraints
MAX_WHISPER_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25MB
MAX_WHISPER_DURATION_SECONDS = 600  # 10 minutes (recommended safe limit)

# Initialize OpenAI client
client = None
if OPENAI_API_KEY and OPENAI_API_KEY != "demo_mode":
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("OpenAI client initialized with API key")
else:
    logger.warning("OPENAI_API_KEY not set or in demo mode. Using mock transcriptions.")

class TranscriptionService:
    """Service to handle audio/video transcription and storage"""
    
    def __init__(self):
        self.demo_mode = not bool(OPENAI_API_KEY) or OPENAI_API_KEY == "demo_mode"
        logger.info(f"Transcription Service initialized: Demo mode = {self.demo_mode}")
        logger.info(f"Supabase Demo Mode = {supabase.is_demo_mode}")
    
    def validate_file(self, filename: str) -> bool:
        """
        Validate if file format is supported
        
        Args:
            filename: Original filename
            
        Returns:
            True if supported, False otherwise
        """
        if not filename:
            return False
        
        # Extract extension and normalize
        file_ext = os.path.splitext(filename)[1].lower()
        
        # Check against supported formats
        if file_ext in SUPPORTED_FORMATS:
            logger.info(f"File validated by supported format: {file_ext}")
            return True
            
        # Special handling for common formats with potential case issues
        special_formats = ['.m4a', '.mp3', '.mp4', '.wav']
        for fmt in special_formats:
            if file_ext.lower() == fmt:
                logger.info(f"File validated by special format: {fmt}")
                return True
                
        logger.warning(f"File validation failed: {filename}")
        return False
    
    def transcribe_file_with_retries(self, file_path: str, language: str = "pt", max_retries: int = 3) -> Tuple[str, bool]:
        """
        Transcribe an audio/video file using OpenAI Whisper with retries
        
        Args:
            file_path: Path to the audio/video file
            language: Language code for transcription
            max_retries: Maximum number of retry attempts
            
        Returns:
            Tuple of (transcript_text, success_flag)
        """
        if self.demo_mode:
            # Simulate a small delay to make the demo more realistic
            time.sleep(1.5)
            return ("This is a demo transcription. Configure your OpenAI API key in the .env file for actual transcriptions.", True)
        
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Verify file size before attempting transcription
        if file_size > MAX_WHISPER_FILE_SIZE_BYTES:
            logger.error(f"File too large for direct transcription: {file_size_mb:.2f}MB > 25MB limit")
            return (f"File too large for transcription: {file_size_mb:.2f}MB exceeds 25MB limit", False)
            
        # Attempt transcription with retries
        retries = 0
        while retries <= max_retries:
            try:
                logger.info(f"Transcription attempt {retries+1} of {max_retries+1}")
                logger.info(f"Transcribing file: {file_path} ({file_size_mb:.2f}MB)")
                
                with open(file_path, "rb") as audio_file:
                    transcript_response = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=language
                    )
                
                transcript_text = transcript_response.text
                logger.info(f"Transcription successful: {len(transcript_text)} characters")
                return (transcript_text, True)
                
            except OpenAIError as oe:
                error_message = str(oe)
                retries += 1
                
                # Check for specific API errors
                if "content size limit" in error_message.lower():
                    logger.error(f"File exceeds OpenAI size limits: {error_message}")
                    return (f"File too large for transcription: {error_message}", False)
                elif "rate limit" in error_message.lower() or "429" in error_message:
                    # Rate limit error, wait longer and retry
                    wait_time = min(retries * 5, 30)  # Progressive backoff: 5s, 10s, 15s...
                    logger.warning(f"Rate limit hit, waiting {wait_time}s before retry")
                    time.sleep(wait_time)
                elif retries >= max_retries:
                    logger.error(f"All transcription attempts failed: {error_message}")
                    return (f"Transcription error after {max_retries} attempts: {error_message}", False)
                else:
                    # Other API error, wait a bit and retry
                    logger.warning(f"Transcription attempt {retries} failed: {error_message}")
                    time.sleep(2)
            
            except Exception as e:
                logger.exception(f"Unexpected error in transcription: {str(e)}")
                return (f"Transcription error: {str(e)}", False)
        
        # This should not be reached due to the return in the loop, but just in case
        return (f"Transcription failed after {max_retries} attempts", False)
    
    def transcribe_large_file(self, file_path: str, language: str = "pt") -> str:
        """
        Transcribe a potentially large audio/video file by chunking if necessary
        
        Args:
            file_path: Path to the audio/video file
            language: Language code for transcription
            
        Returns:
            Transcription text
        """
        if self.demo_mode:
            return self.transcribe_file_with_retries(file_path, language)[0]
        
        try:
            # First, detect if this is a video file and extract audio if needed
            is_video = False
            file_ext = os.path.splitext(file_path)[1].lower()
            video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.mpg', '.mpeg']
            
            if file_ext in video_extensions:
                is_video = True
                logger.info(f"Detected video file: {file_path}")
            
            with tempfile.TemporaryDirectory() as temp_dir:
                audio_path = file_path
                
                # Extract high-quality audio from video as first step
                if is_video:
                    logger.info(f"Extracting audio from video before further processing")
                    extracted_audio = os.path.join(temp_dir, "extracted_audio.wav")
                    try:
                        audio_path = extract_high_quality_audio(file_path, extracted_audio)
                        logger.info(f"Successfully extracted audio: {audio_path}")
                        
                        # Check if the extracted audio is small enough for direct transcription
                        extracted_size = os.path.getsize(audio_path)
                        extracted_size_mb = extracted_size / (1024 * 1024)
                        logger.info(f"Extracted audio size: {extracted_size_mb:.2f}MB")
                        
                        # If extracted audio is small enough, we might be able to skip optimization
                        if extracted_size < MAX_WHISPER_FILE_SIZE_BYTES:
                            logger.info("Extracted audio is under 25MB - attempting direct transcription")
                            extracted_duration = get_media_duration(audio_path)
                            
                            # Only try direct transcription if duration is also within limits
                            if extracted_duration <= MAX_WHISPER_DURATION_SECONDS:
                                logger.info(f"Extracted audio duration ({extracted_duration}s) is within limits")
                                transcript, success = self.transcribe_file_with_retries(audio_path, language)
                                if success:
                                    logger.info("Successfully transcribed extracted audio directly")
                                    return transcript
                                logger.warning(f"Direct transcription of extracted audio failed, will try optimizing")
                            else:
                                logger.info(f"Extracted audio is too long ({extracted_duration}s), will optimize")
                        else:
                            logger.info("Extracted audio is over 25MB, will optimize")
                    except Exception as extract_error:
                        logger.warning(f"Error extracting audio from video: {str(extract_error)}")
                        # Continue with original file if extraction fails
                        audio_path = file_path
                
                # Now optimize the audio (already extracted if it was a video)
                logger.info(f"Optimizing audio for transcription: {audio_path}")
                optimized_audio = optimize_audio_for_transcription(audio_path, temp_dir)
                
                logger.info(f"Using optimized audio for transcription: {optimized_audio}")
                
                file_size = os.path.getsize(optimized_audio)
                file_size_mb = file_size / (1024 * 1024)
                
                logger.info(f"Processing optimized audio of size {file_size_mb:.2f}MB")
                
                # Get duration of the optimized audio
                try:
                    duration = get_media_duration(optimized_audio)
                    logger.info(f"Optimized audio duration: {duration} seconds")
                except Exception as e:
                    logger.warning(f"Could not determine audio duration: {str(e)}")
                    duration = 0
                
                # For safety, always use chunking for files larger than 20MB or longer than 10 minutes
                # This ensures we're well below the 25MB API limit
                force_chunking = file_size > (20 * 1024 * 1024) or duration > 600
                
                # If file is small enough AND we're not forcing chunking, try direct transcription
                if file_size < MAX_WHISPER_FILE_SIZE_BYTES and not force_chunking:
                    logger.info("Optimized file is within Whisper size limits, attempting direct transcription")
                    transcript, success = self.transcribe_file_with_retries(optimized_audio, language)
                    if success:
                        return transcript
                        
                    # If direct transcription fails, proceed with chunking
                    logger.warning("Direct transcription failed, using chunking instead")
                else:
                    if force_chunking:
                        logger.info("Forcing chunking for large file to ensure reliable processing")
                
                # Create chunks directory within the temporary directory
                chunks_dir = os.path.join(temp_dir, "chunks")
                os.makedirs(chunks_dir, exist_ok=True)
                
                # For very large files, use smaller chunk sizes to ensure they stay well below limits
                max_chunk_size_mb = 15 if file_size_mb > 50 else 20
                
                # Create chunks with size and duration constraints
                chunks = chunk_audio(
                    optimized_audio, 
                    chunks_dir, 
                    max_size_mb=max_chunk_size_mb,  # Reduced size target for safety
                    max_chunk_duration=540  # 9 minutes (reduced from 10 minutes for safety)
                )
                
                if not chunks:
                    logger.error("Chunking failed, attempting emergency single-chunk approach")
                    # Emergency fallback: Try to create a single minimally-encoded chunk
                    emergency_path = os.path.join(temp_dir, "emergency.mp3")
                    cmd = [
                        "ffmpeg", "-i", optimized_audio, 
                        "-vn", "-map_metadata", "-1", 
                        "-ac", "1", "-ar", "8000", 
                        "-c:a", "libmp3lame", "-b:a", "8k", 
                        "-q:a", "9", 
                        emergency_path, "-y"
                    ]
                    try:
                        import subprocess
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode == 0 and os.path.exists(emergency_path):
                            emergency_size = os.path.getsize(emergency_path) / (1024 * 1024)
                            logger.info(f"Created emergency file ({emergency_size:.2f}MB), attempting transcription")
                            
                            if emergency_size < 20:  # Only try if emergency file is small enough
                                transcript, success = self.transcribe_file_with_retries(emergency_path, language)
                                if success:
                                    return transcript
                    except Exception as e:
                        logger.exception(f"Emergency encoding failed: {str(e)}")
                    
                    # If emergency approach fails, try extreme chunking
                    try:
                        logger.info("Attempting extreme chunking as last resort")
                        extreme_chunks_dir = os.path.join(temp_dir, "extreme_chunks")
                        os.makedirs(extreme_chunks_dir, exist_ok=True)
                        
                        # Use very aggressive compression for extreme case
                        extreme_audio = os.path.join(temp_dir, "extreme_compressed.mp3")
                        compress_cmd = [
                            "ffmpeg", "-i", optimized_audio,
                            "-vn", "-ac", "1", "-ar", "8000",
                            "-c:a", "libmp3lame", "-b:a", "8k",
                            "-q:a", "9",
                            extreme_audio, "-y"
                        ]
                        subprocess.run(compress_cmd, capture_output=True)
                        
                        # Try with much smaller chunks (5 minute max)
                        extreme_chunks = chunk_audio(
                            extreme_audio,
                            extreme_chunks_dir,
                            max_size_mb=10,
                            max_chunk_duration=300  # 5 minutes
                        )
                        
                        if extreme_chunks:
                            logger.info(f"Created {len(extreme_chunks)} extreme chunks as last resort")
                            chunks = extreme_chunks
                        else:
                            return "Transcription failed: Unable to process the file. The file may be too large or corrupted."
                    except Exception as extreme_error:
                        logger.exception(f"Extreme chunking failed: {str(extreme_error)}")
                        return "Transcription failed: Unable to process the file. The file may be too large or corrupted."
                
                # Transcribe each chunk
                logger.info(f"Transcribing {len(chunks)} chunks")
                transcripts = []
                failed_chunks = []
                
                for i, (chunk_path, start_time) in enumerate(chunks):
                    try:
                        logger.info(f"Transcribing chunk {i+1}/{len(chunks)} starting at {start_time:.1f}s")
                        chunk_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)
                        logger.info(f"Chunk size: {chunk_size_mb:.2f}MB")
                        
                        # Double-check this chunk isn't still too large
                        if chunk_size_mb > 20:
                            logger.warning(f"Chunk {i+1} is still too large ({chunk_size_mb:.2f}MB), trying extreme compression")
                            small_chunk = os.path.join(os.path.dirname(chunk_path), f"small_{os.path.basename(chunk_path)}")
                            compress_cmd = [
                                "ffmpeg", "-i", chunk_path,
                                "-vn", "-ac", "1", "-ar", "8000",
                                "-c:a", "libmp3lame", "-b:a", "8k",
                                "-q:a", "9",
                                small_chunk, "-y"
                            ]
                            subprocess.run(compress_cmd, capture_output=True)
                            if os.path.exists(small_chunk) and os.path.getsize(small_chunk) < (20 * 1024 * 1024):
                                chunk_path = small_chunk
                                chunk_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)
                                logger.info(f"Reduced chunk size to {chunk_size_mb:.2f}MB")
                        
                        transcript, success = self.transcribe_file_with_retries(chunk_path, language)
                        
                        if success:
                            transcripts.append(transcript)
                        else:
                            logger.error(f"Failed to transcribe chunk {i+1}: {transcript}")
                            failed_chunks.append(i+1)
                    except Exception as chunk_error:
                        logger.exception(f"Error processing chunk {i+1}: {str(chunk_error)}")
                        failed_chunks.append(i+1)
                
                # Combine the transcripts
                if not transcripts:
                    return "Transcription failed: No chunks could be transcribed. The file may be corrupted or unsupported."
                
                if failed_chunks:
                    logger.warning(f"Some chunks failed transcription: {failed_chunks}")
                
                # Merge all successful transcripts
                result = merge_transcripts(transcripts)
                
                if failed_chunks:
                    # Add a note about failed chunks
                    note = f"\n\n[Note: Some parts of the audio (chunks {', '.join(map(str, failed_chunks))}) could not be transcribed.]"
                    result += note
                
                return result
                
        except Exception as e:
            logger.exception(f"Error in large file transcription: {str(e)}")
            return f"Transcription error: {str(e)}. Please try again with a smaller file or in a different format."
    
    def process_and_store(self,
                         file_path: str,
                         original_filename: str,
                         language: str = None) -> Dict[str, Any]:
        """
        Process an audio/video file and store only the transcript in Supabase
        
        Args:
            file_path: Path to local file
            original_filename: Original filename
            language: Language code
            
        Returns:
            Dict with transcription details
        """
        try:
            # Log the start of processing
            logger.info(f"Processing file: {original_filename} (size: {os.path.getsize(file_path)} bytes)")
            
            # Get file duration
            try:
                duration = get_media_duration(file_path)
                logger.info(f"File duration: {duration} seconds")
            except Exception as e:
                logger.warning(f"Could not determine file duration: {str(e)}")
                duration = 0
            
            # Generate storage reference (we won't actually store the file)
            storage_path = f"{uuid.uuid4()}{os.path.splitext(original_filename)[1]}"
            logger.info(f"Reference ID: {storage_path}")
            
            # Determine if we need to use large file processing
            file_size = os.path.getsize(file_path)
            is_large_file = file_size > MAX_WHISPER_FILE_SIZE_BYTES or (duration > 0 and duration > MAX_WHISPER_DURATION_SECONDS)
            
            # Transcribe the file
            logger.info(f"Starting transcription of {file_path} with language {language}")
            
            # Use appropriate transcription method based on file size
            if is_large_file:
                logger.info(f"File is large ({file_size / (1024*1024):.2f} MB, {duration} seconds) - using chunked processing")
                transcript = self.transcribe_large_file(file_path, language)
            else:
                logger.info(f"File is within size limits - using standard processing")
                transcript_result, success = self.transcribe_file_with_retries(file_path, language)
                transcript = transcript_result
            
            logger.info(f"Transcription complete: {len(transcript)} characters")
            
            # Store transcript in database without uploading file
            logger.info("Storing transcript in database (skipping file upload)")
            transcript_record = supabase.store_transcript(
                transcript_text=transcript,
                storage_path=storage_path,
                duration_seconds=duration,
                language=language or "auto"
            )
            
            # Prepare response (no file_url since we're not uploading)
            result = {
                "transcript_id": transcript_record["id"],
                "filename": original_filename,
                "transcript": transcript,
                "duration_seconds": duration,
                "language": language or "auto",
                "file_url": f"local://{file_path}",  # Use local reference
                "upload_success": False  # Indicate we're not uploading
            }
            
            logger.info(f"Transcription process complete. ID: {result['transcript_id']}")
            return result
        except Exception as e:
            logger.exception(f"Error in process_and_store: {str(e)}")
            raise

# Initialize singleton service
transcription_service = TranscriptionService() 