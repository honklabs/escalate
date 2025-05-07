"""Models for the escalate tool."""
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


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
            description=data.get("description")
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
            "successful": self.successful,
            "error_message": self.error_message
        }