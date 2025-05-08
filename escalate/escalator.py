"""Main escalation logic."""
import logging
import os
from typing import Dict, List, Any, Set, Optional
from datetime import datetime, timedelta

from escalate.config import Config
from escalate.jira_client import JiraClient
from escalate.models import Rule, EscalationEvent, EscalationPathConfig, EscalationPathType, EscalationHistory
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
        
        # Initialize escalation history tracker
        history_path = config.get_history_file_path()
        self.history = EscalationHistory(history_path)
    
    def load_rules(self) -> List[Rule]:
        """Load rules from configuration."""
        return [Rule.from_dict(rule_data) for rule_data in self.config.rules]
    
    def process_rules(self) -> int:
        """
        Process all rules and escalate issues as needed.
        
        Returns the number of issues escalated.
        """
        # Group rules by level for later use
        rules_by_level = {}
        for rule in self.load_rules():
            if rule.level not in rules_by_level:
                rules_by_level[rule.level] = []
            rules_by_level[rule.level].append(rule)
        
        total_escalated = 0
        
        # Process each level of rules
        for level in sorted(rules_by_level.keys()):
            rules = rules_by_level[level]
            for rule in rules:
                logger.info(f"Processing rule: {rule.name or rule.jql} (Level {rule.level})")
                
                # Find issues matching the rule
                issues = self.jira_client.find_issues_for_rule(rule)
                
                if not issues:
                    logger.info(f"No issues found matching rule: {rule.name or rule.jql}")
                    continue
                
                logger.info(f"Found {len(issues)} potential issues for rule: {rule.name or rule.jql}")
                
                # Filter issues based on days_to_activate and escalation history
                eligible_issues = self.filter_eligible_issues(issues, rule)
                
                if not eligible_issues:
                    logger.info(f"No eligible issues to escalate for rule: {rule.name or rule.jql}")
                    continue
                
                logger.info(f"Found {len(eligible_issues)} eligible issues to escalate for rule: {rule.name or rule.jql}")
                
                # Escalate each eligible issue
                for issue in eligible_issues:
                    escalated = self.escalate_issue(issue, rule)
                    if escalated:
                        total_escalated += 1
                        # Record this escalation in history to prevent duplicates
                        self.history.record_escalation(issue["key"], rule.level)
        
        return total_escalated
    
    def filter_eligible_issues(self, issues: List[Dict[str, Any]], rule: Rule) -> List[Dict[str, Any]]:
        """
        Filter issues based on escalation history and days_to_activate rules.
        
        Args:
            issues: List of issues from JIRA
            rule: The rule being processed
            
        Returns:
            List of issues eligible for escalation
        """
        eligible_issues = []
        cooldown_hours = self.config.escalation_cooldown_hours
        
        for issue in issues:
            issue_key = issue["key"]
            
            # Check if this issue was recently escalated at this level
            if self.history.was_recently_escalated(issue_key, rule.level, cooldown_hours):
                logger.info(f"Issue {issue_key} recently escalated at level {rule.level}, skipping")
                continue
            
            # If this is not the first level, check previous levels have been escalated
            if rule.level > 1:
                # Check if previous level was escalated
                prev_level_escalated = False
                for prev_level in range(1, rule.level):
                    if not self.history.was_recently_escalated(issue_key, prev_level, 24*365):  # Check if ever escalated at prev level
                        break
                else:
                    prev_level_escalated = True
                
                if not prev_level_escalated:
                    logger.info(f"Issue {issue_key} has not been escalated at all previous levels, skipping")
                    continue
            
            # Check days_to_activate rule
            if rule.days_to_activate > 0:
                days_since_first = self.history.get_days_since_first_escalation(issue_key)
                
                # If never escalated before or not enough days have passed
                if days_since_first is None or days_since_first < rule.days_to_activate:
                    logger.info(f"Issue {issue_key} not ready for level {rule.level} (needs {rule.days_to_activate} days, has {days_since_first or 0})")
                    continue
            
            # If we got here, the issue is eligible
            eligible_issues.append(issue)
        
        return eligible_issues
    
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
                escalation_path=path_config,
                level=rule.level  # Set the escalation level
            )
            
            # Execute the escalation
            try:
                path_handler = self.escalation_paths[path_config.type]
                success = path_handler.escalate(event)
                event.successful = success
                
                if success:
                    any_successful = True
                    logger.info(f"Successfully escalated {issue['key']} via {path_config.type.value} at level {rule.level}")
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