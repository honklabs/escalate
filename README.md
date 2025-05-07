# Escalate

A Python tool for escalating JIRA issues based on rules.

## Features

- Monitor JIRA issues using JQL queries
- Escalate issues when they're stuck in a status for too long
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

The tool is configured using a JSON file. Here's an example configuration:

```json
{
  "rules": [
    {
      "name": "Blocked Issues",
      "jql": "project = MYPROJECT AND status = Blocked AND assignee IS NOT EMPTY",
      "max_time_in_status_minutes": 120,
      "description": "Escalate issues that have been blocked for more than 2 hours",
      "escalation_paths": [
        {
          "type": "jira_comment",
          "recipient": "manager_username"
        },
        {
          "type": "slack_dm",
          "recipient": "U12345678"
        }
      ]
    },
    {
      "name": "P1 Issues",
      "jql": "project = MYPROJECT AND priority = P1 AND status != Done",
      "max_time_in_status_minutes": 30,
      "description": "Escalate P1 issues that haven't moved status in 30 minutes",
      "escalation_paths": [
        {
          "type": "pagerduty",
          "recipient": "on-call@example.com"
        },
        {
          "type": "email",
          "recipient": "team-lead@example.com",
          "message_template": "URGENT: P1 issue {issue_key} ({issue_summary}) has been in {status} for {time_in_status_minutes} minutes!"
        }
      ]
    }
  ]
}
```

You also need to set the following environment variables:

```
# JIRA credentials (required)
JIRA_URL=https://your-jira.atlassian.net
JIRA_USERNAME=your-email@example.com
JIRA_API_TOKEN=your-api-token

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

# List all rules in the config file
escalate --list-rules

# Perform a dry run (doesn't actually escalate issues)
escalate --dry-run
```

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