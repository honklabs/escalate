"""PagerDuty escalation path."""
import logging
from pdpyras import EventsAPISession, APISession

from escalate.models import EscalationEvent
from escalate.escalation_paths.base import EscalationPath

logger = logging.getLogger(__name__)

class PagerDutyEscalationPath(EscalationPath):
    """Escalation path that creates a PagerDuty incident."""
    
    def __init__(self, api_key: str, service_id: str):
        """Initialize with PagerDuty API credentials."""
        self.events_session = EventsAPISession(api_key)
        self.api_session = APISession(api_key)
        self.service_id = service_id
    
    def escalate(self, event: EscalationEvent) -> bool:
        """Create a PagerDuty incident."""
        message = self.format_message(event)
        
        try:
            # Create the incident in PagerDuty
            dedup_key = f"escalate-{event.issue_key}"
            
            response = self.events_session.trigger(
                summary=f"Escalation for {event.issue_key}: {event.issue_summary}",
                source="Escalate Tool",
                dedup_key=dedup_key,
                severity="warning",
                component="JIRA",
                group="Issue Escalation",
                class_type="issue",
                custom_details={
                    "issue_key": event.issue_key,
                    "issue_summary": event.issue_summary,
                    "status": event.status,
                    "time_in_status_minutes": event.time_in_status_minutes,
                    "max_time_allowed": event.rule.max_time_in_status_minutes,
                    "rule_name": event.rule.name or "Unnamed Rule",
                    "jql": event.rule.jql
                }
            )
            
            # If we have a specific recipient (user email), assign them
            if event.escalation_path.recipient:
                try:
                    # Find the incident that was just created using dedup_key
                    incidents = self.api_session.list_all(
                        "incidents", 
                        params={"statuses[]": ["triggered"], "service_ids[]": [self.service_id]}
                    )
                    
                    # Find the user by email
                    users = self.api_session.list_all(
                        "users", 
                        params={"query": event.escalation_path.recipient}
                    )
                    
                    if incidents and users:
                        incident_id = incidents[0]["id"]
                        user_id = users[0]["id"]
                        
                        # Assign the incident
                        self.api_session.put(
                            f"incidents/{incident_id}",
                            json={"incident": {"assignments": [{"assignee": {"id": user_id, "type": "user_reference"}}]}}
                        )
                        
                except Exception as assign_err:
                    logger.error(f"Failed to assign PagerDuty incident: {str(assign_err)}")
            
            logger.info(f"Created PagerDuty incident for {event.issue_key}")
            return True
            
        except Exception as e:
            error_message = f"Failed to create PagerDuty incident: {str(e)}"
            logger.error(error_message)
            event.error_message = error_message
            return False