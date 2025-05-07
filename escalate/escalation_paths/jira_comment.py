"""JIRA comment escalation path."""
import logging
from escalate.models import EscalationEvent
from escalate.escalation_paths.base import EscalationPath
from escalate.jira_client import JiraClient

logger = logging.getLogger(__name__)

class JiraCommentEscalationPath(EscalationPath):
    """Escalation path that adds a comment to a JIRA issue."""
    
    def __init__(self, jira_client: JiraClient):
        """Initialize with a JIRA client."""
        self.jira_client = jira_client
    
    def escalate(self, event: EscalationEvent) -> bool:
        """Add a comment to the JIRA issue."""
        message = self.format_message(event)
        
        # Add recipient mention if specified
        if event.escalation_path.recipient:
            message = f"[~{event.escalation_path.recipient}] {message}"
        
        successful = self.jira_client.add_comment(event.issue_key, message)
        
        if successful:
            logger.info(f"Added comment to {event.issue_key} escalating to {event.escalation_path.recipient}")
        else:
            logger.error(f"Failed to add comment to {event.issue_key}")
        
        return successful