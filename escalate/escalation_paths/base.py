"""Base escalation path implementation."""
from abc import ABC, abstractmethod
from typing import Optional

from escalate.models import EscalationEvent


class EscalationPath(ABC):
    """Base class for escalation paths."""
    
    @abstractmethod
    def escalate(self, event: EscalationEvent) -> bool:
        """
        Escalate an issue using this path.
        
        Returns True if escalation was successful, False otherwise.
        """
        pass
    
    def format_message(self, event: EscalationEvent) -> str:
        """Format the escalation message using the template if provided."""
        template = event.escalation_path.message_template
        
        if not template:
            # Default template
            template = """
Issue {issue_key}: {issue_summary}
Status: {status}
Time in status: {time_in_status_minutes:.1f} minutes
Max time allowed: {max_time_in_status_minutes} minutes
            """
        
        # Format the template with issue data
        return template.format(
            issue_key=event.issue_key,
            issue_summary=event.issue_summary,
            issue_assignee=event.issue_assignee or "Unassigned",
            status=event.status,
            time_in_status_minutes=event.time_in_status_minutes,
            max_time_in_status_minutes=event.rule.max_time_in_status_minutes
        )