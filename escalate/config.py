"""Configuration management for the escalate tool."""
import os
import json
from typing import Dict, List, Any, Optional
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
        
        # Escalation history storage
        self.history_file = os.getenv("ESCALATION_HISTORY_FILE", "escalation_history.json")
        
        # Hours between same level escalations (default: 24 hours)
        self.escalation_cooldown_hours = int(os.getenv("ESCALATION_COOLDOWN_HOURS", "24"))
        
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
    
    def get_rules_by_level(self) -> Dict[int, List[Dict[str, Any]]]:
        """Group rules by their escalation level."""
        rules_by_level = {}
        
        for rule in self.rules:
            level = rule.get("level", 1)
            if level not in rules_by_level:
                rules_by_level[level] = []
            rules_by_level[level].append(rule)
            
        return rules_by_level
        
    def get_history_file_path(self) -> str:
        """Get the full path to the escalation history file."""
        # If it's an absolute path, use it as is
        if os.path.isabs(self.history_file):
            return self.history_file
            
        # Otherwise, use a path relative to the config directory
        config_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(config_dir, self.history_file)