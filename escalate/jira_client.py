"""JIRA client for the escalate tool."""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
from jira import JIRA

from escalate.models import Rule, EscalationEvent, EscalationPathConfig, EscalationPathType

logger = logging.getLogger(__name__)

class JiraClient:
    """Client for interacting with JIRA."""
    
    def __init__(self, url: str, username: str, api_token: str):
        """Initialize the JIRA client."""
        self.jira = JIRA(server=url, basic_auth=(username, api_token))
    
    def find_issues_for_rule(self, rule: Rule) -> List[Dict[str, Any]]:
        """Find issues that match the JQL query in the rule."""
        issues = []
        
        try:
            jira_issues = self.jira.search_issues(rule.jql)
            
            for issue in jira_issues:
                # Get the current status
                status = issue.fields.status.name
                
                # Calculate time in status
                status_history = self._get_status_history(issue.key)
                time_in_status = self._calculate_time_in_status(status_history, status)
                
                # Convert to minutes
                time_in_status_minutes = time_in_status.total_seconds() / 60
                
                # Check if we need to escalate
                if time_in_status_minutes > rule.max_time_in_status_minutes:
                    assignee = getattr(issue.fields, 'assignee', None)
                    assignee_name = assignee.displayName if assignee else None
                    
                    issues.append({
                        "key": issue.key,
                        "summary": issue.fields.summary,
                        "assignee": assignee_name,
                        "status": status,
                        "time_in_status_minutes": time_in_status_minutes
                    })
            
            return issues
        
        except Exception as e:
            logger.error(f"Error searching for issues with JQL '{rule.jql}': {str(e)}")
            return []
    
    def _get_status_history(self, issue_key: str) -> List[Dict[str, Any]]:
        """Get the status change history for an issue."""
        history = []
        
        try:
            issue = self.jira.issue(issue_key, expand='changelog')
            changelog = issue.changelog
            
            for history_item in changelog.histories:
                for item in history_item.items:
                    if item.field == 'status':
                        history.append({
                            'from': item.fromString,
                            'to': item.toString,
                            'date': datetime.strptime(history_item.created[:19], "%Y-%m-%dT%H:%M:%S")
                        })
            
            # Add the current status entry if there's no history
            if not history:
                current_status = issue.fields.status.name
                created_date = datetime.strptime(issue.fields.created[:19], "%Y-%m-%dT%H:%M:%S")
                
                history.append({
                    'from': None,
                    'to': current_status,
                    'date': created_date
                })
                
            return history
        
        except Exception as e:
            logger.error(f"Error getting status history for issue {issue_key}: {str(e)}")
            return []
    
    def _calculate_time_in_status(self, status_history: List[Dict[str, Any]], current_status: str) -> timedelta:
        """Calculate how long the issue has been in the current status."""
        if not status_history:
            return timedelta(0)
        
        # Sort history by date
        sorted_history = sorted(status_history, key=lambda x: x['date'])
        
        # Find the most recent transition to the current status
        latest_transition = None
        
        for item in reversed(sorted_history):
            if item['to'] == current_status:
                latest_transition = item
                break
        
        if not latest_transition:
            # If we didn't find a transition to the current status, use the creation date
            return datetime.now() - sorted_history[0]['date']
        
        # Calculate time since the transition
        return datetime.now() - latest_transition['date']
    
    def add_comment(self, issue_key: str, comment: str) -> bool:
        """Add a comment to a JIRA issue."""
        try:
            self.jira.add_comment(issue_key, comment)
            return True
        except Exception as e:
            logger.error(f"Error adding comment to issue {issue_key}: {str(e)}")
            return False