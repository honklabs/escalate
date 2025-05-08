"""Models for the escalate tool."""
from enum import Enum
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
import datetime


class EscalationPathType(Enum):
    """Types of escalation paths."""
    JIRA_COMMENT = "jira_comment"
    SLACK_DM = "slack_dm"
    PAGERDUTY = "pagerduty"
    EMAIL = "email"


@dataclass
class EscalationPathConfig:
    """Configuration for an escalation path."""
    type: EscalationPathType
    recipient: str  # User ID, email, etc.
    message_template: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EscalationPathConfig":
        """Create an EscalationPathConfig from a dictionary."""
        return cls(
            type=EscalationPathType(data["type"]),
            recipient=data["recipient"],
            message_template=data.get("message_template")
        )


@dataclass
class Rule:
    """A rule for when to escalate an issue."""
    jql: str
    max_time_in_status_minutes: int
    escalation_paths: List[EscalationPathConfig]
    name: Optional[str] = None
    description: Optional[str] = None
    level: int = 1  # Escalation level (1-based)
    days_to_activate: int = 0  # Number of days after issue matches criteria before this rule activates
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rule":
        """Create a Rule from a dictionary."""
        escalation_paths = [
            EscalationPathConfig.from_dict(path) for path in data["escalation_paths"]
        ]
        
        return cls(
            jql=data["jql"],
            max_time_in_status_minutes=data["max_time_in_status_minutes"],
            escalation_paths=escalation_paths,
            name=data.get("name"),
            description=data.get("description"),
            level=data.get("level", 1),
            days_to_activate=data.get("days_to_activate", 0)
        )


@dataclass
class EscalationEvent:
    """An event representing an escalation."""
    issue_key: str
    issue_summary: str
    issue_assignee: Optional[str]
    status: str
    time_in_status_minutes: float
    rule: Rule
    escalation_path: EscalationPathConfig
    level: int = 1
    timestamp: datetime.datetime = datetime.datetime.now()
    successful: bool = False
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the event to a dictionary for logging."""
        return {
            "issue_key": self.issue_key,
            "issue_summary": self.issue_summary,
            "issue_assignee": self.issue_assignee,
            "status": self.status,
            "time_in_status_minutes": self.time_in_status_minutes,
            "rule_name": self.rule.name,
            "rule_jql": self.rule.jql,
            "max_time_in_status_minutes": self.rule.max_time_in_status_minutes,
            "escalation_path_type": self.escalation_path.type.value,
            "escalation_path_recipient": self.escalation_path.recipient,
            "level": self.level,
            "timestamp": self.timestamp.isoformat(),
            "successful": self.successful,
            "error_message": self.error_message
        }


class EscalationHistory:
    """Tracks the history of escalations to prevent duplicates."""
    
    def __init__(self, storage_path: Optional[str] = None):
        """Initialize the escalation history."""
        self.storage_path = storage_path
        # Dictionary to track the last time an issue was escalated at each level
        # Key: (issue_key, level) tuple, Value: timestamp
        self.last_escalations: Dict[tuple, datetime.datetime] = {}
        
        # Load history from storage if available
        if storage_path:
            self.load_history()
    
    def was_recently_escalated(self, issue_key: str, level: int, hours: int = 24) -> bool:
        """
        Check if an issue was recently escalated at a specific level.
        
        Args:
            issue_key: The JIRA issue key
            level: The escalation level
            hours: Consider "recent" if within this many hours (default 24)
            
        Returns:
            True if the issue was escalated at this level within the time period
        """
        key = (issue_key, level)
        if key not in self.last_escalations:
            return False
            
        last_time = self.last_escalations[key]
        time_since = datetime.datetime.now() - last_time
        
        # Check if it's been less than the specified hours
        return time_since < datetime.timedelta(hours=hours)
    
    def record_escalation(self, issue_key: str, level: int) -> None:
        """
        Record that an issue was escalated at a specific level.
        
        Args:
            issue_key: The JIRA issue key
            level: The escalation level
        """
        key = (issue_key, level)
        self.last_escalations[key] = datetime.datetime.now()
        
        # Save to storage if configured
        if self.storage_path:
            self.save_history()
    
    def get_issue_first_seen(self, issue_key: str) -> Optional[datetime.datetime]:
        """
        Get the timestamp when the issue was first seen in any escalation.
        
        Args:
            issue_key: The JIRA issue key
            
        Returns:
            The datetime when the issue was first escalated, or None if never escalated
        """
        # Look for any keys with this issue
        timestamps = [
            timestamp for (key, _), timestamp in self.last_escalations.items()
            if key == issue_key
        ]
        
        if not timestamps:
            return None
            
        # Return the earliest timestamp
        return min(timestamps)
    
    def get_days_since_first_escalation(self, issue_key: str) -> Optional[int]:
        """
        Get the number of days since the issue was first escalated.
        
        Args:
            issue_key: The JIRA issue key
            
        Returns:
            The number of days since first escalation, or None if never escalated
        """
        first_seen = self.get_issue_first_seen(issue_key)
        if not first_seen:
            return None
            
        days = (datetime.datetime.now() - first_seen).days
        return days
    
    def save_history(self) -> None:
        """Save escalation history to disk."""
        try:
            import json
            import os
            
            # Convert data to serializable format
            data = {}
            for (issue_key, level), timestamp in self.last_escalations.items():
                key = f"{issue_key}:{level}"
                data[key] = timestamp.isoformat()
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            
            # Write to file
            with open(self.storage_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save escalation history: {str(e)}")
    
    def load_history(self) -> None:
        """Load escalation history from disk."""
        try:
            import json
            import os
            
            if not os.path.exists(self.storage_path):
                return
                
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            # Convert back to internal format
            for key_str, timestamp_str in data.items():
                issue_key, level_str = key_str.split(':', 1)
                level = int(level_str)
                timestamp = datetime.datetime.fromisoformat(timestamp_str)
                self.last_escalations[(issue_key, level)] = timestamp
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to load escalation history: {str(e)}")