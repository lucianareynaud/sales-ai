from typing import Dict, Any

from analysis_svc.nodes import extract_sales_data_node

async def run_analysis_pipeline(transcript_id: str) -> Dict[str, Any]:
    """
    Run the sales intelligence analysis pipeline on a transcript.
    
    Args:
        transcript_id: The ID of the transcript to analyze
        
    Returns:
        A dictionary containing the results of each step in the pipeline,
        including the final sales_data.
    """
    # Initialize state with transcript ID
    state = {"transcript_id": transcript_id}
    
    # Run the extraction node
    state = await extract_sales_data_node(state)
    
    # We could add more nodes here in the future:
    # state = await scrape_node(state)
    # state = await rag_personalization_node(state)
    # state = await generate_report_node(state)
    
    return state 