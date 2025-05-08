# Escalate

A Python tool for escalating JIRA issues based on rules with progressive, time-based escalation levels.

## Features

- Monitor JIRA issues using JQL queries
- Escalate issues when they're stuck in a status for too long
- Progressive escalation levels that activate on subsequent days
- Each level only triggers once per 24-hour period (configurable)
- Track escalation history to prevent duplicates
- Multiple escalation paths:
  - JIRA comments
  - Slack DMs
  - PagerDuty incidents
  - Email notifications
- Log all escalations to Sumo Logic for monitoring

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/escalate.git
cd escalate

# Install the package
pip install -e .
```

## Configuration

The tool is configured using a JSON file. Here's an example of progressive escalation configuration:

```json
{
  "escalation_cooldown_hours": 24,
  "history_file": "escalation_history.json",
  "rules": [
    {
      "name": "P1 Issues - Initial Alert",
      "jql": "project = MYPROJECT AND priority = P1 AND status != Done",
      "max_time_in_status_minutes": 30,
      "level": 1,
      "days_to_activate": 0,
      "description": "First escalation for P1 issues that haven't moved status in 30 minutes",
      "escalation_paths": [
        {
          "type": "jira_comment",
          "recipient": "assignee",
          "message_template": "⚠️ This P1 issue has been in {status} status for more than {time_in_status_minutes:.0f} minutes. Please update the status or add a comment."
        },
        {
          "type": "slack_dm",
          "recipient": "U12345678",
          "message_template": "⚠️ *Initial Alert*: P1 issue {issue_key} ({issue_summary}) has been in {status} for {time_in_status_minutes:.0f} minutes!"
        }
      ]
    },
    {
      "name": "P1 Issues - Day 1 Escalation",
      "jql": "project = MYPROJECT AND priority = P1 AND status != Done",
      "max_time_in_status_minutes": 30,
      "level": 2,
      "days_to_activate": 1,
      "description": "Second escalation for P1 issues, active after 1 day",
      "escalation_paths": [
        {
          "type": "jira_comment",
          "recipient": "manager_username",
          "message_template": "🔔 **Manager Alert**: This P1 issue has been in {status} status for more than 1 day. Please ensure this is being worked on."
        },
        {
          "type": "email",
          "recipient": "team-lead@example.com",
          "message_template": "🔔 ALERT: P1 issue {issue_key} ({issue_summary}) has been in {status} for more than 1 day!"
        }
      ]
    },
    {
      "name": "P1 Issues - Day 2 Escalation",
      "jql": "project = MYPROJECT AND priority = P1 AND status != Done",
      "max_time_in_status_minutes": 30,
      "level": 3,
      "days_to_activate": 2,
      "description": "Third escalation for P1 issues, active after 2 days",
      "escalation_paths": [
        {
          "type": "slack_dm",
          "recipient": "U87654321",
          "message_template": "🚨 **Director Alert**: P1 issue {issue_key} has been stuck for 2+ days. This requires immediate attention."
        },
        {
          "type": "email",
          "recipient": "director@example.com",
          "message_template": "🚨 URGENT: P1 issue {issue_key} ({issue_summary}) has been in {status} for more than 2 days without resolution."
        }
      ]
    },
    {
      "name": "P1 Issues - Day 3 Escalation",
      "jql": "project = MYPROJECT AND priority = P1 AND status != Done",
      "max_time_in_status_minutes": 30,
      "level": 4,
      "days_to_activate": 3,
      "description": "Final escalation for P1 issues, active after 3 days",
      "escalation_paths": [
        {
          "type": "pagerduty",
          "recipient": "on-call@example.com"
        },
        {
          "type": "email",
          "recipient": "vp@example.com",
          "message_template": "🔥 CRITICAL ALERT: P1 issue {issue_key} ({issue_summary}) has been in {status} for MORE THAN 3 DAYS without resolution. This requires IMMEDIATE executive attention."
        }
      ]
    }
  ]
}
```

### Configuration Parameters

- `escalation_cooldown_hours`: Number of hours before the same level can trigger again (default: 24)
- `history_file`: Path to store escalation history (default: "escalation_history.json")
- `rules`: Array of rule objects

### Rule Parameters

- `name`: Descriptive name for the rule
- `jql`: JIRA query to find matching issues
- `max_time_in_status_minutes`: Minimum time an issue must be in the current status
- `level`: Escalation level (1-based, with higher numbers being more severe)
- `days_to_activate`: Days after first escalation before this rule activates
- `description`: Human-readable description of the rule
- `escalation_paths`: Array of notification methods

### Environment Variables

```
# JIRA credentials (required)
JIRA_URL=https://your-jira.atlassian.net
JIRA_USERNAME=your-email@example.com
JIRA_API_TOKEN=your-api-token

# Escalation settings (optional)
ESCALATION_HISTORY_FILE=path/to/history.json
ESCALATION_COOLDOWN_HOURS=24

# Slack (optional, for Slack DM escalation)
SLACK_TOKEN=xoxb-your-slack-token

# PagerDuty (optional, for PagerDuty escalation)
PAGERDUTY_API_KEY=your-pagerduty-api-key
PAGERDUTY_SERVICE_ID=your-pagerduty-service-id

# Email (optional, for email escalation)
EMAIL_SENDER=sender@example.com
EMAIL_PASSWORD=your-email-password
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587

# Sumo Logic (optional, for logging)
SUMO_ENDPOINT_URL=https://collectors.sumologic.com/receiver/v1/http/your-endpoint
```

## Usage

```bash
# Run with default config file (escalate.json)
escalate

# Specify a config file
escalate -c /path/to/config.json

# Enable verbose logging
escalate -v

# List all rules in the config file (now grouped by level)
escalate --list-rules

# Perform a dry run (doesn't actually escalate issues)
escalate --dry-run

# Show escalation history (all recorded escalations)
escalate --show-history

# List only active escalations (within the cooldown period)
escalate --list-active-escalations

# Clear all escalation history
escalate --clear-history

# Clear history for a specific issue
escalate --clear-history-for PROJ-123
```

### Progressive Escalation Process

1. When an issue first matches a rule condition, the Level 1 escalation is triggered
2. The escalation is recorded in the history file
3. Each rule can only trigger once per cooldown period (default: 24 hours)
4. Higher-level rules will only trigger after:
   - The `days_to_activate` number of days have passed since the first escalation
   - All previous levels have been triggered at least once
   - The issue still matches the rule's JQL and status conditions
   
This ensures that escalations follow a logical progression up the chain of command, with each level only triggering once per day.

## Running as a Scheduled Job

You should set up the tool to run periodically (e.g., every 5-15 minutes) using a scheduler like cron or systemd timers.

Example crontab entry to run every 10 minutes:

```
*/10 * * * * /path/to/escalate -c /path/to/config.json >> /path/to/escalate.log 2>&1
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
flake8 escalate
```

## License

MIT