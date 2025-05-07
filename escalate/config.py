"""Configuration management for the escalate tool."""
import os
import json
from typing import Dict, List, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration class for the escalate tool."""
    
    def __init__(self, config_path: str = None):
        """Initialize the config from a file or environment variables."""
        self.jira_url = os.getenv("JIRA_URL")
        self.jira_username = os.getenv("JIRA_USERNAME")
        self.jira_api_token = os.getenv("JIRA_API_TOKEN")
        
        self.slack_token = os.getenv("SLACK_TOKEN")
        
        self.pagerduty_api_key = os.getenv("PAGERDUTY_API_KEY")
        self.pagerduty_service_id = os.getenv("PAGERDUTY_SERVICE_ID")
        
        self.email_sender = os.getenv("EMAIL_SENDER")
        self.email_password = os.getenv("EMAIL_PASSWORD")
        self.email_smtp_server = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
        self.email_smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        
        self.sumo_endpoint_url = os.getenv("SUMO_ENDPOINT_URL")
        
        # Rules configuration
        self.rules: List[Dict[str, Any]] = []
        
        # Load rules from config file if provided
        if config_path:
            self.load_config(config_path)
    
    def load_config(self, config_path: str) -> None:
        """Load configuration from a JSON file."""
        with open(config_path, 'r') as f:
            config_data = json.load(f)
            
        self.rules = config_data.get("rules", [])
        
        # Override env vars with config file values if they exist
        for key, value in config_data.items():
            if key != "rules" and value:
                setattr(self, key, value)
    
    def validate(self) -> bool:
        """Validate that the configuration has the required values."""
        # Check if we have Jira credentials
        if not all([self.jira_url, self.jira_username, self.jira_api_token]):
            return False
        
        # Check if rules are defined
        if not self.rules:
            return False
            
        return True