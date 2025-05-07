"""Email escalation path."""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from escalate.models import EscalationEvent
from escalate.escalation_paths.base import EscalationPath

logger = logging.getLogger(__name__)

class EmailEscalationPath(EscalationPath):
    """Escalation path that sends an email."""
    
    def __init__(self, sender: str, password: str, smtp_server: str = "smtp.gmail.com", smtp_port: int = 587):
        """Initialize with email credentials."""
        self.sender = sender
        self.password = password
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
    
    def escalate(self, event: EscalationEvent) -> bool:
        """Send an email to the recipient."""
        message = self.format_message(event)
        recipient = event.escalation_path.recipient
        
        # Create email
        email = MIMEMultipart()
        email["From"] = self.sender
        email["To"] = recipient
        email["Subject"] = f"Issue Escalation: {event.issue_key} - {event.issue_summary}"
        
        # Attach message body
        email.attach(MIMEText(message, "plain"))
        
        try:
            # Connect to the SMTP server
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()  # Secure the connection
            server.login(self.sender, self.password)
            
            # Send email
            server.send_message(email)
            server.quit()
            
            logger.info(f"Sent email to {recipient} about {event.issue_key}")
            return True
            
        except Exception as e:
            error_message = f"Failed to send email to {recipient}: {str(e)}"
            logger.error(error_message)
            event.error_message = error_message
            return False