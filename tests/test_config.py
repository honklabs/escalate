"""Tests for the config module."""
import os
import pytest
import tempfile
import json
from escalate.config import Config

@pytest.fixture
def config_file():
    """Create a temporary config file for testing."""
    config_data = {
        "rules": [
            {
                "name": "Test Rule",
                "jql": "project = TEST",
                "max_time_in_status_minutes": 60,
                "description": "Test description",
                "escalation_paths": [
                    {
                        "type": "jira_comment",
                        "recipient": "username"
                    }
                ]
            }
        ],
        "jira_url": "https://test-jira.example.com",
        "jira_username": "test_user",
        "jira_api_token": "test_token"
    }
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        json.dump(config_data, f)
        return f.name

def test_load_config(config_file):
    """Test loading configuration from a file."""
    config = Config(config_file)
    
    assert config.jira_url == "https://test-jira.example.com"
    assert config.jira_username == "test_user"
    assert config.jira_api_token == "test_token"
    assert len(config.rules) == 1
    
    rule = config.rules[0]
    assert rule["name"] == "Test Rule"
    assert rule["jql"] == "project = TEST"
    assert rule["max_time_in_status_minutes"] == 60
    assert rule["description"] == "Test description"
    assert len(rule["escalation_paths"]) == 1
    assert rule["escalation_paths"][0]["type"] == "jira_comment"
    assert rule["escalation_paths"][0]["recipient"] == "username"

def test_validate_valid_config(config_file):
    """Test validation with a valid configuration."""
    config = Config(config_file)
    assert config.validate() is True

def test_validate_missing_jira_credentials():
    """Test validation with missing JIRA credentials."""
    config = Config()
    config.jira_url = None
    config.rules = [{"jql": "project = TEST", "max_time_in_status_minutes": 60, "escalation_paths": []}]
    
    assert config.validate() is False

def test_validate_missing_rules():
    """Test validation with missing rules."""
    config = Config()
    config.jira_url = "https://test-jira.example.com"
    config.jira_username = "test_user"
    config.jira_api_token = "test_token"
    config.rules = []
    
    assert config.validate() is False