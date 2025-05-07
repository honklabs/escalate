"""Logging functionality for the escalate tool."""
import json
import logging
import requests
from typing import Dict, Any

from escalate.models import EscalationEvent

logger = logging.getLogger(__name__)

class SumoLogicHandler:
    """Handler for sending logs to Sumo Logic."""
    
    def __init__(self, endpoint_url: str):
        """Initialize with the Sumo Logic HTTP Source URL."""
        self.endpoint_url = endpoint_url
    
    def log_escalation(self, event: EscalationEvent) -> bool:
        """
        Log an escalation event to Sumo Logic.
        
        Returns True if logging was successful, False otherwise.
        """
        if not self.endpoint_url:
            logger.warning("Sumo Logic endpoint URL not configured, skipping logging")
            return False
        
        try:
            # Convert the event to a dictionary for logging
            log_data = event.to_dict()
            
            # Add timestamp
            log_data["timestamp"] = int(__import__("time").time())
            
            # Send to Sumo Logic
            response = requests.post(
                self.endpoint_url,
                data=json.dumps(log_data),
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code < 200 or response.status_code >= 300:
                logger.error(f"Sumo Logic API returned error: {response.status_code} {response.text}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending log to Sumo Logic: {str(e)}")
            return False


def configure_logging(log_level: str = "INFO") -> None:
    """Configure the Python logging."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure the root logger
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )