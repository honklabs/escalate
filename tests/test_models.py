"""Tests for the models module."""
import pytest
from escalate.models import Rule, EscalationPathConfig, EscalationPathType, EscalationEvent

def test_escalation_path_config_from_dict():
    """Test creating an EscalationPathConfig from a dictionary."""
    data = {
        "type": "slack_dm",
        "recipient": "U12345678",
        "message_template": "Test message"
    }
    
    path = EscalationPathConfig.from_dict(data)
    
    assert path.type == EscalationPathType.SLACK_DM
    assert path.recipient == "U12345678"
    assert path.message_template == "Test message"

def test_rule_from_dict():
    """Test creating a Rule from a dictionary."""
    data = {
        "name": "Test Rule",
        "jql": "project = TEST",
        "max_time_in_status_minutes": 60,
        "description": "Test description",
        "escalation_paths": [
            {
                "type": "jira_comment",
                "recipient": "username"
            },
            {
                "type": "email",
                "recipient": "test@example.com"
            }
        ]
    }
    
    rule = Rule.from_dict(data)
    
    assert rule.name == "Test Rule"
    assert rule.jql == "project = TEST"
    assert rule.max_time_in_status_minutes == 60
    assert rule.description == "Test description"
    assert len(rule.escalation_paths) == 2
    assert rule.escalation_paths[0].type == EscalationPathType.JIRA_COMMENT
    assert rule.escalation_paths[0].recipient == "username"
    assert rule.escalation_paths[1].type == EscalationPathType.EMAIL
    assert rule.escalation_paths[1].recipient == "test@example.com"

def test_escalation_event_to_dict():
    """Test converting an EscalationEvent to a dictionary."""
    # Create a rule
    rule = Rule(
        name="Test Rule",
        jql="project = TEST",
        max_time_in_status_minutes=60,
        description="Test description",
        escalation_paths=[]
    )
    
    # Create an escalation path
    escalation_path = EscalationPathConfig(
        type=EscalationPathType.SLACK_DM,
        recipient="U12345678"
    )
    
    # Create an escalation event
    event = EscalationEvent(
        issue_key="TEST-123",
        issue_summary="Test issue",
        issue_assignee="username",
        status="In Progress",
        time_in_status_minutes=90.5,
        rule=rule,
        escalation_path=escalation_path,
        successful=True
    )
    
    # Convert to dictionary
    event_dict = event.to_dict()
    
    # Check values
    assert event_dict["issue_key"] == "TEST-123"
    assert event_dict["issue_summary"] == "Test issue"
    assert event_dict["issue_assignee"] == "username"
    assert event_dict["status"] == "In Progress"
    assert event_dict["time_in_status_minutes"] == 90.5
    assert event_dict["rule_name"] == "Test Rule"
    assert event_dict["rule_jql"] == "project = TEST"
    assert event_dict["max_time_in_status_minutes"] == 60
    assert event_dict["escalation_path_type"] == "slack_dm"
    assert event_dict["escalation_path_recipient"] == "U12345678"
    assert event_dict["successful"] is True
    assert event_dict["error_message"] is None