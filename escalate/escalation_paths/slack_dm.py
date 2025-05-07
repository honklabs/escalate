"""Slack DM escalation path."""
import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from escalate.models import EscalationEvent
from escalate.escalation_paths.base import EscalationPath

logger = logging.getLogger(__name__)

class SlackDMEscalationPath(EscalationPath):
    """Escalation path that sends a Slack DM."""
    
    def __init__(self, slack_token: str):
        """Initialize with a Slack API token."""
        self.client = WebClient(token=slack_token)
    
    def escalate(self, event: EscalationEvent) -> bool:
        """Send a Slack DM to the recipient."""
        message = self.format_message(event)
        recipient = event.escalation_path.recipient
        
        try:
            # Open a DM channel
            response = self.client.conversations_open(users=recipient)
            channel_id = response["channel"]["id"]
            
            # Send the message
            self.client.chat_postMessage(
                channel=channel_id,
                text=message
            )
            
            logger.info(f"Sent Slack DM to {recipient} about {event.issue_key}")
            return True
            
        except SlackApiError as e:
            error_message = f"Failed to send Slack DM to {recipient}: {str(e)}"
            logger.error(error_message)
            event.error_message = error_message
            return False