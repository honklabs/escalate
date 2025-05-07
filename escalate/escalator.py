"""Main escalation logic."""
import logging
from typing import Dict, List, Any

from escalate.config import Config
from escalate.jira_client import JiraClient
from escalate.models import Rule, EscalationEvent, EscalationPathConfig, EscalationPathType
from escalate.escalation_paths import (
    JiraCommentEscalationPath,
    SlackDMEscalationPath,
    PagerDutyEscalationPath,
    EmailEscalationPath
)
from escalate.logger import SumoLogicHandler

logger = logging.getLogger(__name__)

class Escalator:
    """Main class for escalating issues."""
    
    def __init__(self, config: Config):
        """Initialize with configuration."""
        self.config = config
        self.jira_client = JiraClient(
            url=config.jira_url,
            username=config.jira_username,
            api_token=config.jira_api_token
        )
        
        # Initialize escalation paths
        self.escalation_paths = {
            EscalationPathType.JIRA_COMMENT: JiraCommentEscalationPath(self.jira_client),
            EscalationPathType.SLACK_DM: SlackDMEscalationPath(config.slack_token) if config.slack_token else None,
            EscalationPathType.PAGERDUTY: PagerDutyEscalationPath(config.pagerduty_api_key, config.pagerduty_service_id) 
                if config.pagerduty_api_key and config.pagerduty_service_id else None,
            EscalationPathType.EMAIL: EmailEscalationPath(
                sender=config.email_sender,
                password=config.email_password,
                smtp_server=config.email_smtp_server,
                smtp_port=config.email_smtp_port
            ) if config.email_sender and config.email_password else None
        }
        
        # Initialize Sumo Logic logger
        self.sumo_logger = SumoLogicHandler(config.sumo_endpoint_url) if config.sumo_endpoint_url else None
    
    def load_rules(self) -> List[Rule]:
        """Load rules from configuration."""
        return [Rule.from_dict(rule_data) for rule_data in self.config.rules]
    
    def process_rules(self) -> int:
        """
        Process all rules and escalate issues as needed.
        
        Returns the number of issues escalated.
        """
        rules = self.load_rules()
        total_escalated = 0
        
        for rule in rules:
            logger.info(f"Processing rule: {rule.name or rule.jql}")
            
            # Find issues matching the rule
            issues = self.jira_client.find_issues_for_rule(rule)
            
            if not issues:
                logger.info(f"No issues found matching rule: {rule.name or rule.jql}")
                continue
            
            logger.info(f"Found {len(issues)} issues to escalate for rule: {rule.name or rule.jql}")
            
            # Escalate each issue
            for issue in issues:
                escalated = self.escalate_issue(issue, rule)
                if escalated:
                    total_escalated += 1
        
        return total_escalated
    
    def escalate_issue(self, issue: Dict[str, Any], rule: Rule) -> bool:
        """
        Escalate a single issue.
        
        Returns True if at least one escalation path was successful.
        """
        any_successful = False
        
        for path_config in rule.escalation_paths:
            # Skip if the escalation path is not configured
            if self.escalation_paths[path_config.type] is None:
                logger.warning(f"Escalation path {path_config.type.value} is not configured, skipping")
                continue
            
            # Create the escalation event
            event = EscalationEvent(
                issue_key=issue["key"],
                issue_summary=issue["summary"],
                issue_assignee=issue["assignee"],
                status=issue["status"],
                time_in_status_minutes=issue["time_in_status_minutes"],
                rule=rule,
                escalation_path=path_config
            )
            
            # Execute the escalation
            try:
                path_handler = self.escalation_paths[path_config.type]
                success = path_handler.escalate(event)
                event.successful = success
                
                if success:
                    any_successful = True
                    logger.info(f"Successfully escalated {issue['key']} via {path_config.type.value}")
                else:
                    logger.error(f"Failed to escalate {issue['key']} via {path_config.type.value}")
                
            except Exception as e:
                error_message = f"Error escalating {issue['key']} via {path_config.type.value}: {str(e)}"
                logger.error(error_message)
                event.error_message = error_message
                event.successful = False
            
            # Log to Sumo Logic if configured
            if self.sumo_logger:
                self.sumo_logger.log_escalation(event)
        
        return any_successful