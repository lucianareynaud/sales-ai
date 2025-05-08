from typing import Tuple, Optional

from db import supabase

def get_transcript_by_id(transcript_id: str) -> Tuple[str, str]:
    """
    Retrieve a transcript by its ID from the database.
    
    Args:
        transcript_id: The ID of the transcript to retrieve
        
    Returns:
        A tuple of (transcript_text, language)
        
    Raises:
        ValueError: If the transcript is not found
    """
    transcript = supabase.get_transcript(transcript_id)
    
    if not transcript:
        raise ValueError(f"Transcript with ID {transcript_id} not found")
        
    return transcript["transcript"], transcript["language"] 