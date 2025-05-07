"""Escalation path implementations."""
from escalate.escalation_paths.base import EscalationPath
from escalate.escalation_paths.jira_comment import JiraCommentEscalationPath
from escalate.escalation_paths.slack_dm import SlackDMEscalationPath
from escalate.escalation_paths.pagerduty import PagerDutyEscalationPath
from escalate.escalation_paths.email import EmailEscalationPath

# Export all escalation paths
__all__ = [
    'EscalationPath',
    'JiraCommentEscalationPath',
    'SlackDMEscalationPath',
    'PagerDutyEscalationPath',
    'EmailEscalationPath',
]