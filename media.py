import subprocess
import os
import json
import re
from typing import Optional, Dict, Any, List, Tuple
import math
from pathlib import Path
import logging
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import python-magic, but provide fallback if not available
try:
    import magic
except ImportError:
    magic = None
    logger.warning("python-magic not installed. Using fallback mime type detection.")

def extract_high_quality_audio(input_file: str, output_file: str = None) -> str:
    """
    Extract high-quality audio from video or audio files with optimal settings for ASR
    
    Args:
        input_file: Path to input file (video or audio)
        output_file: Path to output audio file (if None, a temporary file will be created)
        
    Returns:
        Path to the extracted high-quality audio file
    """
    try:
        # If no output file specified, create a temporary WAV file
        if output_file is None:
            temp_dir = tempfile.gettempdir()
            output_file = os.path.join(temp_dir, f"extract_{os.path.basename(input_file)}.wav")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        
        logger.info(f"Extracting high-quality audio from: {input_file} to {output_file}")
        
        # Use FFmpeg to extract high-quality audio with optimal ASR settings
        # - Sample rate: 16kHz (what Whisper expects)
        # - Format: 16-bit PCM WAV (lossless)
        # - Channels: Mono (simplifies processing)
        cmd = [
            "ffmpeg",
            "-i", input_file,      # Input file
            "-vn",                 # No video
            "-ar", "16000",        # 16kHz sample rate (optimal for Whisper)
            "-ac", "1",            # Mono
            "-sample_fmt", "s16",  # 16-bit signed PCM
            "-acodec", "pcm_s16le", # PCM 16-bit little-endian codec (WAV)
            "-y",                  # Overwrite output file
            "-hide_banner",        # Hide banner
            "-loglevel", "error",  # Only show errors
            output_file
        ]
        
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Error extracting audio: {result.stderr}")
            raise RuntimeError(f"Audio extraction failed: {result.stderr}")
        
        # Verify the output file exists and has size > 0
        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            logger.error(f"Output file is empty or doesn't exist: {output_file}")
            raise RuntimeError("Audio extraction produced empty or missing file")
            
        logger.info(f"Successfully extracted high-quality audio: {output_file} ({os.path.getsize(output_file)/1024/1024:.2f} MB)")
        return output_file
        
    except Exception as e:
        logger.exception(f"Error in audio extraction: {str(e)}")
        raise

def normalize_audio(input_file: str, output_file: str = None) -> str:
    """
    Normalize audio volume for consistent levels using FFmpeg loudnorm filter
    
    Args:
        input_file: Path to input audio file 
        output_file: Path to output normalized audio file (if None, a temporary file will be created)
        
    Returns:
        Path to the normalized audio file
    """
    try:
        # If no output file specified, create a temporary WAV file
        if output_file is None:
            temp_dir = tempfile.gettempdir()
            output_file = os.path.join(temp_dir, f"norm_{os.path.basename(input_file)}")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        
        logger.info(f"Normalizing audio: {input_file} to {output_file}")
        
        # Use FFmpeg with the loudnorm filter to normalize audio levels
        # This is a two-pass process:
        # 1. First analyze the audio to get normalization parameters
        # 2. Then apply those parameters to normalize the audio
        
        # First pass - analyze
        cmd_analyze = [
            "ffmpeg",
            "-i", input_file,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f", "null",
            "-hide_banner",
            "-"
        ]
        
        logger.debug(f"Running analyze command: {' '.join(cmd_analyze)}")
        result_analyze = subprocess.run(cmd_analyze, capture_output=True, text=True)
        
        if result_analyze.returncode != 0:
            logger.error(f"Error analyzing audio for normalization: {result_analyze.stderr}")
            # If analysis fails, just copy the file
            cmd_copy = ["ffmpeg", "-i", input_file, "-y", output_file]
            subprocess.run(cmd_copy, capture_output=True)
            return output_file
        
        # Extract the normalization parameters from the JSON output
        stderr = result_analyze.stderr
        json_start = stderr.rfind('{')
        json_end = stderr.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = stderr[json_start:json_end]
            try:
                norm_data = json.loads(json_str)
                
                # Second pass - apply normalization
                loudnorm_filter = (
                    f"loudnorm=I=-16:TP=-1.5:LRA=11:"
                    f"measured_I={norm_data.get('input_i', '-16')}:"
                    f"measured_TP={norm_data.get('input_tp', '0')}:"
                    f"measured_LRA={norm_data.get('input_lra', '0')}:"
                    f"measured_thresh={norm_data.get('input_thresh', '-30')}:"
                    f"offset={norm_data.get('target_offset', '0')}:"
                    f"linear=true:print_format=json"
                )
                
                cmd_normalize = [
                    "ffmpeg",
                    "-i", input_file,
                    "-af", loudnorm_filter,
                    "-ar", "16000",  # Ensure 16kHz output
                    "-ac", "1",      # Ensure mono output
                    "-y",            # Overwrite output
                    output_file
                ]
                
                logger.debug(f"Running normalize command: {' '.join(cmd_normalize)}")
                result_normalize = subprocess.run(cmd_normalize, capture_output=True, text=True)
                
                if result_normalize.returncode != 0:
                    logger.error(f"Error normalizing audio: {result_normalize.stderr}")
                    # If normalization fails, just copy the file
                    cmd_copy = ["ffmpeg", "-i", input_file, "-y", output_file]
                    subprocess.run(cmd_copy, capture_output=True)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse normalization JSON data")
                # If JSON parsing fails, just copy the file
                cmd_copy = ["ffmpeg", "-i", input_file, "-y", output_file]
                subprocess.run(cmd_copy, capture_output=True)
        else:
            logger.error(f"Could not find JSON data in loudnorm output")
            # If no JSON data, just copy the file
            cmd_copy = ["ffmpeg", "-i", input_file, "-y", output_file]
            subprocess.run(cmd_copy, capture_output=True)
        
        # Verify the output file exists and has size > 0
        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            logger.error(f"Normalized output file is empty or doesn't exist: {output_file}")
            return input_file  # Return original file if normalization fails
            
        logger.info(f"Successfully normalized audio: {output_file} ({os.path.getsize(output_file)/1024/1024:.2f} MB)")
        return output_file
        
    except Exception as e:
        logger.exception(f"Error in audio normalization: {str(e)}")
        return input_file  # Return original file if normalization fails

def apply_noise_reduction(input_file: str, output_file: str = None) -> str:
    """
    Apply noise reduction to audio file using FFmpeg's arnndn filter if available
    Falls back to simple highpass filter if arnndn is not available
    
    Args:
        input_file: Path to input audio file
        output_file: Path to output denoised audio file (if None, a temporary file will be created)
        
    Returns:
        Path to the denoised audio file
    """
    try:
        # If no output file specified, create a temporary file
        if output_file is None:
            temp_dir = tempfile.gettempdir()
            output_file = os.path.join(temp_dir, f"denoise_{os.path.basename(input_file)}")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        
        logger.info(f"Applying noise reduction to: {input_file} -> {output_file}")
        
        # First check if input has significant noise level
        # This requires sox/ffmpeg with volumedetect filter
        has_noise = False
        
        try:
            # Check noise floor using volumedetect
            cmd_noise = [
                "ffmpeg",
                "-i", input_file,
                "-af", "volumedetect",
                "-f", "null",
                "-hide_banner",
                "-"
            ]
            
            noise_result = subprocess.run(cmd_noise, capture_output=True, text=True)
            
            if noise_result.returncode == 0:
                # Look for the noise floor in the output
                noise_output = noise_result.stderr
                noise_floor_match = re.search(r'mean_volume: ([-\d.]+) dB', noise_output)
                
                if noise_floor_match:
                    noise_floor = float(noise_floor_match.group(1))
                    logger.info(f"Detected noise floor: {noise_floor} dB")
                    
                    # If noise floor is too high (less negative), apply noise reduction
                    # Typical speech has a noise floor around -30 to -40 dB
                    # If it's higher than -25dB, we likely have background noise
                    if noise_floor > -25:
                        has_noise = True
                        logger.info(f"High noise floor detected ({noise_floor} dB), applying noise reduction")
        except Exception as noise_check_error:
            logger.warning(f"Error checking noise floor: {str(noise_check_error)}")
            # If we can't check noise, assume no significant noise
            has_noise = False
        
        if not has_noise:
            # If no significant noise, just copy the file
            logger.info("No significant noise detected, skipping noise reduction")
            cmd_copy = ["ffmpeg", "-i", input_file, "-y", output_file]
            copy_result = subprocess.run(cmd_copy, capture_output=True)
            return output_file
        
        # Try noise reduction with RNNoise - first check if arnndn filter is available
        has_arnndn = False
        
        try:
            # Check if FFmpeg has arnndn filter
            cmd_check = ["ffmpeg", "-filters"]
            check_result = subprocess.run(cmd_check, capture_output=True, text=True)
            
            if check_result.returncode == 0 and "arnndn" in check_result.stdout:
                has_arnndn = True
                logger.info("FFmpeg has arnndn filter available")
        except Exception:
            has_arnndn = False
        
        if has_arnndn:
            # Use RNNoise-based noise reduction (higher quality)
            cmd = [
                "ffmpeg",
                "-i", input_file,
                "-af", "arnndn=m=./rnnoise-models/bd.rnnn",  # Use RNNoise model
                "-y",
                output_file
            ]
        else:
            # Fallback to simpler noise reduction technique using highpass filter
            # This removes low-frequency noise and applies subtle noise gate
            cmd = [
                "ffmpeg",
                "-i", input_file,
                "-af", "highpass=f=200,anlmdn",  # Highpass filter at 200Hz, plus non-local means denoiser
                "-y",
                output_file
            ]
        
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Error applying noise reduction: {result.stderr}")
            # If noise reduction fails, just copy the file
            cmd_copy = ["ffmpeg", "-i", input_file, "-y", output_file]
            subprocess.run(cmd_copy, capture_output=True)
        
        # Verify the output file exists and has size > 0
        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            logger.error(f"Denoised output file is empty or doesn't exist: {output_file}")
            return input_file  # Return original file if denoising fails
            
        logger.info(f"Successfully applied noise reduction: {output_file} ({os.path.getsize(output_file)/1024/1024:.2f} MB)")
        return output_file
        
    except Exception as e:
        logger.exception(f"Error in noise reduction: {str(e)}")
        return input_file  # Return original file if denoising fails

def optimize_audio_for_transcription(input_file: str, output_dir: str = None) -> str:
    """
    Complete pipeline to optimize audio for transcription:
    1. Extract high-quality audio from video/audio
    2. Normalize volume levels
    3. Apply noise reduction if needed
    
    Args:
        input_file: Path to input file (video or audio)
        output_dir: Directory to store the optimized file (temporary dir if None)
        
    Returns:
        Path to the optimized audio file ready for transcription
    """
    try:
        # Create temporary directory for processing files if not provided
        temp_dir = output_dir or tempfile.mkdtemp()
        os.makedirs(temp_dir, exist_ok=True)
        
        # Final output file
        filename = os.path.splitext(os.path.basename(input_file))[0]
        final_output = os.path.join(temp_dir, f"{filename}_optimized.wav")
        
        logger.info(f"Starting audio optimization pipeline for: {input_file}")
        
        # Step 1: Extract high-quality audio
        hq_audio = extract_high_quality_audio(
            input_file, 
            os.path.join(temp_dir, f"{filename}_extracted.wav")
        )
        
        # Step 2: Normalize volume levels
        normalized_audio = normalize_audio(
            hq_audio,
            os.path.join(temp_dir, f"{filename}_normalized.wav")
        )
        
        # Step 3: Apply noise reduction
        final_audio = apply_noise_reduction(
            normalized_audio,
            final_output
        )
        
        # Clean up intermediate files
        if os.path.exists(hq_audio) and hq_audio != input_file and hq_audio != final_output:
            try:
                os.remove(hq_audio)
            except:
                pass
                
        if os.path.exists(normalized_audio) and normalized_audio != input_file and normalized_audio != final_output:
            try:
                os.remove(normalized_audio)
            except:
                pass
        
        logger.info(f"Audio optimization complete: {final_audio}")
        return final_audio
        
    except Exception as e:
        logger.exception(f"Error in audio optimization pipeline: {str(e)}")
        # Return the original file if anything fails
        return input_file

def get_media_duration(file_path: str) -> int:
    """
    Get the duration of a media file in seconds
    
    Uses ffprobe if available, falls back to ffmpeg
    
    Args:
        file_path: Path to media file
        
    Returns:
        Duration in seconds (rounded to nearest second)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Media file not found: {file_path}")
        
    try:
        # Try with ffprobe first (more accurate and faster)
        duration = get_duration_with_ffprobe(file_path)
        if duration > 0:
            return duration
            
        # Fallback to ffmpeg
        duration = get_duration_with_ffmpeg(file_path)
        return duration
    except Exception as e:
        logger.warning(f"Could not get duration for {file_path}: {str(e)}")
        # Return a default duration of 10 seconds
        return 10
        
def get_duration_with_ffprobe(file_path: str) -> int:
    """
    Get media duration using ffprobe
    
    Args:
        file_path: Path to media file
        
    Returns:
        Duration in seconds or 0 if failed
    """
    try:
        # Command to get duration with ffprobe
        cmd = [
            "ffprobe", 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "json", 
            file_path
        ]
        
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Parse the JSON output
            data = json.loads(result.stdout)
            duration_str = data.get("format", {}).get("duration", "0")
            duration_sec = int(float(duration_str))
            return max(1, duration_sec)  # Ensure at least 1 second
        else:
            logger.error(f"ffprobe error: {result.stderr}")
            return 0
    except Exception as e:
        logger.error(f"ffprobe error: {str(e)}")
        return 0
        
def get_duration_with_ffmpeg(file_path: str) -> int:
    """
    Get media duration using ffmpeg
    
    Args:
        file_path: Path to media file
        
    Returns:
        Duration in seconds or 10 if failed
    """
    try:
        # Command to get duration with ffmpeg
        cmd = [
            "ffmpeg", 
            "-i", file_path,
            "-hide_banner"
        ]
        
        # Run the command, ignoring stdout as ffmpeg outputs to stderr
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Parse the duration from stderr output which looks like "Duration: 00:01:23.45"
        output = result.stderr
        duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2})\.(\d{2})", output)
        
        if duration_match:
            hours = int(duration_match.group(1))
            minutes = int(duration_match.group(2))
            seconds = int(duration_match.group(3))
            # Convert to total seconds
            duration_sec = hours * 3600 + minutes * 60 + seconds
            return max(1, duration_sec)  # Ensure at least 1 second
        else:
            logger.warning(f"Could not extract duration with ffmpeg: {output}")
            return 10
    except Exception as e:
        logger.error(f"ffmpeg error: {str(e)}")
        return 10 

def preprocess_audio(input_file: str, output_file: str) -> bool:
    """
    Preprocess audio file to optimize for transcription
    - Convert to mono
    - Resample to 16kHz
    - Encode with Opus at low bitrate
    
    Args:
        input_file: Path to input file
        output_file: Path to output file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Preprocessing audio: {input_file} -> {output_file}")
        
        cmd = [
            "ffmpeg",
            "-i", input_file,
            "-vn",                     # Remove video stream
            "-map_metadata", "-1",     # Remove metadata
            "-ac", "1",                # Convert to mono
            "-ar", "16000",            # Resample to 16kHz
            "-c:a", "libopus",         # Use Opus codec
            "-b:a", "12k",             # Low bitrate (12kbps)
            "-application", "voip",    # Optimize for voice
            output_file,
            "-y"                       # Overwrite output file if exists
        ]
        
        # Run the command with detailed logging
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Error preprocessing audio: {result.stderr}")
            return False
        
        # Verify the output file exists and has appropriate size
        if not os.path.exists(output_file):
            logger.error(f"Output file was not created: {output_file}")
            return False
            
        output_size = os.path.getsize(output_file)
        input_size = os.path.getsize(input_file)
        ratio = output_size / input_size
        
        logger.info(f"File size: {input_size / (1024*1024):.2f}MB -> {output_size / (1024*1024):.2f}MB (ratio: {ratio:.4f})")
        
        if output_size == 0:
            logger.error("Output file is empty")
            return False
            
        return True
    except Exception as e:
        logger.exception(f"Exception preprocessing audio: {str(e)}")
        return False

def chunk_audio(input_file: str, chunks_dir: str, max_size_mb: int = 20, max_chunk_duration: int = 600) -> List[Tuple[str, float]]:
    """
    Split audio into chunks under max_size_mb
    
    Args:
        input_file: Path to input file
        chunks_dir: Directory to store chunks
        max_size_mb: Maximum chunk size in MB
        max_chunk_duration: Maximum chunk duration in seconds
        
    Returns:
        List of (chunk_path, start_time_seconds) tuples
    """
    try:
        logger.info(f"Chunking audio: {input_file} (max: {max_size_mb}MB / {max_chunk_duration}s)")
        
        # Create chunks directory if it doesn't exist
        os.makedirs(chunks_dir, exist_ok=True)
        
        # Get original file duration
        duration = get_media_duration(input_file)
        logger.info(f"File duration: {duration} seconds")
        
        # Estimate chunk duration based on file size and duration
        file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
        logger.info(f"File size: {file_size_mb:.2f}MB")
        
        # If file is already under max size, return it directly
        if file_size_mb <= max_size_mb and duration <= max_chunk_duration:
            logger.info("File is already under maximum size, no chunking needed")
            return [(input_file, 0)]
        
        # Calculate time per MB to estimate chunk duration
        time_per_mb = duration / max(1, file_size_mb)  # Avoid division by zero
        
        # Calculate target chunk duration based on desired file size
        # but limit to max_chunk_duration
        target_chunk_duration = min(max_chunk_duration, max_size_mb * time_per_mb * 0.9)  # 10% safety margin
        
        # If estimated chunk duration is too short, adjust bitrate instead of using tiny chunks
        if target_chunk_duration < 60 and duration > 180:  # If chunks would be less than 1 minute and audio is longer than 3 minutes
            logger.info(f"Estimated chunk duration would be too short ({target_chunk_duration:.1f}s), adjusting bitrate")
            
            # First try with lower bitrate to avoid too many tiny chunks
            lower_bitrate_file = os.path.join(chunks_dir, "lower_bitrate.mp3")
            
            # Calculate appropriate bitrate based on target size and duration
            # Formula: bitrate_kbps = (target_size_bytes * 8) / (duration_seconds * 1000)
            target_bitrate = int((max_size_mb * 1024 * 1024 * 8) / (max_chunk_duration * 1000) * 0.8)  # 20% safety margin
            
            # Ensure bitrate is reasonable (minimum 8kbps, maximum 128kbps for mp3)
            target_bitrate = max(8, min(target_bitrate, 128))
            
            logger.info(f"Using lower bitrate of {target_bitrate}kbps for chunking")
            
            lower_bitrate_cmd = [
                "ffmpeg",
                "-i", input_file,
                "-c:a", "libmp3lame",  # Use MP3 codec
                "-b:a", f"{target_bitrate}k",  # Lower bitrate
                "-ac", "1",           # Mono
                "-ar", "16000",       # 16kHz
                "-vn",                # No video
                "-y",                 # Overwrite
                lower_bitrate_file
            ]
            
            result = subprocess.run(lower_bitrate_cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and os.path.exists(lower_bitrate_file):
                # Use this lower bitrate file for chunking
                input_file = lower_bitrate_file
                
                # Recalculate size
                file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
                logger.info(f"Created lower bitrate version: {file_size_mb:.2f}MB")
                
                # Recalculate target duration
                time_per_mb = duration / max(1, file_size_mb)
                target_chunk_duration = min(max_chunk_duration, max_size_mb * time_per_mb * 0.9)
        
        # Calculate number of chunks needed
        chunk_count = math.ceil(duration / target_chunk_duration)
        
        # Add overlap to avoid cutting words
        overlap_seconds = 2  # 2 seconds overlap
        chunk_list = []
        
        logger.info(f"Creating {chunk_count} chunks with {overlap_seconds}s overlap")
        
        for i in range(chunk_count):
            # Calculate start and end times with overlap
            start_time = max(0, i * target_chunk_duration - (0 if i == 0 else overlap_seconds))
            end_time = min(duration, (i + 1) * target_chunk_duration + (0 if i == chunk_count - 1 else overlap_seconds))
            
            chunk_duration = end_time - start_time
            logger.info(f"Chunk {i+1}/{chunk_count}: {start_time:.1f}s to {end_time:.1f}s ({chunk_duration:.1f}s)")
            
            # Generate chunk filename - using .mp3 instead of .opus
            chunk_file = os.path.join(chunks_dir, f"chunk_{i:03d}.mp3")
            
            # Extract chunk using ffmpeg with appropriate bitrate
            # For longer chunks, use lower bitrate to ensure we stay under size limit
            bitrate = "24k"  # Default bitrate (higher than opus since mp3 is less efficient)
            
            # For chunks over 5 minutes, progressively decrease bitrate
            if chunk_duration > 300:
                bitrate = "16k"
            if chunk_duration > 450:
                bitrate = "12k"
            
            cmd = [
                "ffmpeg",
                "-i", input_file,
                "-ss", str(start_time),
                "-to", str(end_time),
                "-c:a", "libmp3lame",  # Use MP3 codec
                "-b:a", bitrate,      # Bitrate
                "-ac", "1",           # Mono
                "-ar", "16000",       # 16kHz
                "-vn",                # No video
                chunk_file,
                "-y"                  # Overwrite if exists
            ]
            
            logger.debug(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Error creating chunk {i}: {result.stderr}")
                continue
            
            # Verify chunk file size
            chunk_size_mb = os.path.getsize(chunk_file) / (1024 * 1024)
            logger.info(f"Chunk {i+1} size: {chunk_size_mb:.2f}MB")
            
            # If chunk is still too large, try with lower bitrate
            if chunk_size_mb > max_size_mb:
                logger.warning(f"Chunk {i+1} is still too large ({chunk_size_mb:.2f}MB > {max_size_mb}MB), recreating with lower bitrate")
                
                # Try again with progressive lower bitrate until acceptable size is reached
                for retry_bitrate in ["12k", "8k", "6k"]:
                    logger.info(f"Attempting with {retry_bitrate} bitrate")
                    retry_cmd = [
                        "ffmpeg",
                        "-i", input_file,
                        "-ss", str(start_time),
                        "-to", str(end_time),
                        "-c:a", "libmp3lame",  # Use MP3 codec
                        "-b:a", retry_bitrate,
                        "-ac", "1",
                        "-ar", "16000",
                        "-vn",
                        chunk_file,
                        "-y"
                    ]
                    
                    retry_result = subprocess.run(retry_cmd, capture_output=True, text=True)
                    
                    if retry_result.returncode != 0:
                        logger.error(f"Error recreating chunk {i} with lower bitrate: {retry_result.stderr}")
                        continue
                    
                    # Check if size is now acceptable
                    new_size_mb = os.path.getsize(chunk_file) / (1024 * 1024)
                    logger.info(f"Chunk {i+1} new size with {retry_bitrate}: {new_size_mb:.2f}MB")
                    
                    if new_size_mb <= max_size_mb:
                        logger.info(f"Successfully reduced chunk {i+1} size to {new_size_mb:.2f}MB")
                        break
                    elif retry_bitrate == "6k":  # If we've tried the lowest bitrate and it's still too large
                        logger.warning(f"Could not reduce chunk size below limit even with lowest bitrate. Proceeding anyway.")
            
            # Add chunk to list
            chunk_list.append((chunk_file, start_time))
        
        # Check if all chunks were created
        if len(chunk_list) != chunk_count:
            logger.warning(f"Expected {chunk_count} chunks but created {len(chunk_list)}")
            if not chunk_list:
                raise RuntimeError("No chunks were created successfully")
        
        logger.info(f"Created {len(chunk_list)} chunks successfully")
        return chunk_list
        
    except Exception as e:
        logger.exception(f"Error in chunking audio: {str(e)}")
        return []

def merge_transcripts(transcript_chunks: List[str]) -> str:
    """
    Merge multiple transcript chunks into a single transcript
    
    Args:
        transcript_chunks: List of transcript text chunks
        
    Returns:
        Merged transcript
    """
    if not transcript_chunks:
        logger.warning("No transcript chunks to merge")
        return ""
    
    logger.info(f"Merging {len(transcript_chunks)} transcript chunks")
    
    # Simple concatenation with spacing
    result = " ".join(transcript_chunks)
    
    # Remove multiple spaces
    result = re.sub(r'\s+', ' ', result).strip()
    
    logger.info(f"Merged transcript length: {len(result)} characters")
    return result 