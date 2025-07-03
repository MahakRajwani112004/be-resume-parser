# app/routers/status.py

from fastapi import APIRouter
import json
import os
import logging # Import logging to see errors

router = APIRouter()

PROCESSED_DATA_FILE = "processed_resume_data.json"

@router.get("/status", tags=["Database Info"])
async def get_database_status():
    """
    Provides a quick, non-destructive status check of the current vector database.
    Now with robust type checking to prevent errors.
    """
    if not os.path.exists(PROCESSED_DATA_FILE):
        return {"db_exists": False, "total_resumes": 0, "total_chunks": 0}
        
    try:
        with open(PROCESSED_DATA_FILE, "r") as f:
            db = json.load(f)
        
        # --- NEW: Type and structure validation ---
        if not isinstance(db, list):
            logging.error(f"Database file '{PROCESSED_DATA_FILE}' is not a JSON list. Content type: {type(db)}")
            raise ValueError("Invalid database format: not a list.")

        total_chunks = len(db)
        if total_chunks == 0:
            return {"db_exists": True, "total_resumes": 0, "total_chunks": 0}
            
        # --- Check the structure of the first item to be safe ---
        first_item = db[0]
        if not isinstance(first_item, dict) or 'metadata' not in first_item or 'resume_filename' not in first_item.get('metadata', {}):
             logging.error(f"Database file '{PROCESSED_DATA_FILE}' has an invalid item structure.")
             raise ValueError("Invalid item structure in database.")

        # If validation passes, proceed with the calculation
        total_resumes = len(set(item['metadata']['resume_filename'] for item in db))

        return {
            "db_exists": True,
            "total_resumes": total_resumes,
            "chunks": total_chunks
        }
    except json.JSONDecodeError as e:
        # This catches errors if the file is not valid JSON
        logging.error(f"Failed to parse '{PROCESSED_DATA_FILE}': {e}")
        return {"db_exists": True, "error": "Database file is corrupted (not valid JSON)."}
    except (ValueError, TypeError) as e:
        # This catches our custom validation errors and unexpected TypeErrors
        logging.error(f"Invalid data structure in '{PROCESSED_DATA_FILE}': {e}")
        return {"db_exists": True, "error": f"Database file has an invalid data structure: {e}"}
    except Exception as e:
        # A general catch-all for any other unexpected errors
        logging.error(f"An unexpected error occurred while reading status: {e}", exc_info=True)
        return {"db_exists": True, "error": "An unexpected error occurred."}