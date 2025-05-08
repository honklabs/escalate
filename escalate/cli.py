"""Command-line interface for the escalate tool."""
import sys
import os
import argparse
import logging
import json
import datetime
from typing import Dict, Any, Optional, Tuple, List

from escalate.config import Config
from escalate.escalator import Escalator
from escalate.models import EscalationHistory
from escalate.logger import configure_logging

logger = logging.getLogger(__name__)

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Escalate JIRA issues based on rules")
    
    parser.add_argument(
        "-c", "--config",
        help="Path to config file",
        default="escalate.json"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        help="Enable verbose logging",
        action="store_true"
    )
    
    parser.add_argument(
        "--dry-run",
        help="Perform a dry run without actually escalating issues",
        action="store_true"
    )
    
    parser.add_argument(
        "--list-rules",
        help="List all rules in the config file",
        action="store_true"
    )
    
    parser.add_argument(
        "--show-history",
        help="Show escalation history",
        action="store_true"
    )
    
    parser.add_argument(
        "--clear-history",
        help="Clear escalation history",
        action="store_true"
    )
    
    parser.add_argument(
        "--clear-history-for",
        help="Clear escalation history for a specific issue",
        metavar="ISSUE_KEY"
    )
    
    parser.add_argument(
        "--list-active-escalations",
        help="List currently active escalations across all levels",
        action="store_true"
    )
    
    return parser.parse_args()

def list_rules(config: Config) -> None:
    """Print all rules in the config file."""
    rules_by_level = config.get_rules_by_level()
    levels = sorted(rules_by_level.keys())
    
    print(f"Found {len(config.rules)} rules across {len(levels)} levels:")
    
    for level in levels:
        rules = rules_by_level[level]
        print(f"\n=== LEVEL {level} Rules ({len(rules)}) ===")
        
        for i, rule in enumerate(rules, 1):
            name = rule.get("name", f"Rule {i}")
            jql = rule.get("jql", "No JQL specified")
            max_time = rule.get("max_time_in_status_minutes", "Not specified")
            days_to_activate = rule.get("days_to_activate", 0)
            
            print(f"\n{level}.{i}. {name}")
            print(f"   JQL: {jql}")
            print(f"   Max time in status: {max_time} minutes")
            if days_to_activate > 0:
                print(f"   Days to activate: {days_to_activate}")
            
            paths = rule.get("escalation_paths", [])
            print(f"   Escalation paths ({len(paths)}):")
            
            for j, path in enumerate(paths, 1):
                path_type = path.get("type", "Unknown")
                recipient = path.get("recipient", "Not specified")
                print(f"     {j}. {path_type} -> {recipient}")

def show_history(config: Config) -> None:
    """Show escalation history."""
    history_path = config.get_history_file_path()
    history = EscalationHistory(history_path)
    
    if not history.last_escalations:
        print("No escalation history found.")
        return
    
    # Group by issue key
    issues = {}
    for (issue_key, level), timestamp in history.last_escalations.items():
        if issue_key not in issues:
            issues[issue_key] = []
        issues[issue_key].append((level, timestamp))
    
    print(f"Escalation history for {len(issues)} issues:")
    
    for issue_key, escalations in sorted(issues.items()):
        # Sort by level
        escalations.sort(key=lambda x: x[0])
        
        first_seen = history.get_issue_first_seen(issue_key)
        days_since = (datetime.datetime.now() - first_seen).days if first_seen else 0
        
        print(f"\n{issue_key} (first seen {days_since} days ago):")
        
        for level, timestamp in escalations:
            time_ago = datetime.datetime.now() - timestamp
            if time_ago.total_seconds() < 60:
                time_str = f"{int(time_ago.total_seconds())} seconds ago"
            elif time_ago.total_seconds() < 3600:
                time_str = f"{int(time_ago.total_seconds() / 60)} minutes ago"
            elif time_ago.total_seconds() < 86400:
                time_str = f"{int(time_ago.total_seconds() / 3600)} hours ago"
            else:
                time_str = f"{int(time_ago.total_seconds() / 86400)} days ago"
            
            print(f"  Level {level}: {timestamp.strftime('%Y-%m-%d %H:%M:%S')} ({time_str})")

def clear_history(config: Config, issue_key: Optional[str] = None) -> None:
    """Clear escalation history."""
    history_path = config.get_history_file_path()
    
    if not os.path.exists(history_path):
        print("No escalation history found.")
        return
    
    if issue_key:
        # Only clear history for a specific issue
        history = EscalationHistory(history_path)
        to_remove = []
        
        # Find all entries for this issue
        for (key, level), _ in history.last_escalations.items():
            if key == issue_key:
                to_remove.append((key, level))
        
        # Remove entries
        for key in to_remove:
            del history.last_escalations[key]
        
        # Save
        history.save_history()
        print(f"Cleared escalation history for issue {issue_key}.")
    else:
        # Remove the entire history file
        os.remove(history_path)
        print("Cleared all escalation history.")

def list_active_escalations(config: Config) -> None:
    """List currently active escalations across all levels."""
    history_path = config.get_history_file_path()
    history = EscalationHistory(history_path)
    
    if not history.last_escalations:
        print("No escalation history found.")
        return
    
    now = datetime.datetime.now()
    cooldown_hours = config.escalation_cooldown_hours
    
    # Find active escalations (within cooldown period)
    active_escalations = {}
    for (issue_key, level), timestamp in history.last_escalations.items():
        time_diff = now - timestamp
        if time_diff.total_seconds() < cooldown_hours * 3600:
            if issue_key not in active_escalations:
                active_escalations[issue_key] = []
            active_escalations[issue_key].append((level, timestamp))
    
    if not active_escalations:
        print(f"No active escalations found (within {cooldown_hours} hour cooldown).")
        return
    
    print(f"Active escalations for {len(active_escalations)} issues:")
    
    for issue_key, escalations in sorted(active_escalations.items()):
        # Sort by level
        escalations.sort(key=lambda x: x[0])
        
        days_since = history.get_days_since_first_escalation(issue_key) or 0
        highest_level = max(level for level, _ in escalations)
        
        print(f"\n{issue_key} (Day {days_since}, highest level: {highest_level}):")
        
        for level, timestamp in escalations:
            time_ago = now - timestamp
            if time_ago.total_seconds() < 60:
                time_str = f"{int(time_ago.total_seconds())} seconds ago"
            elif time_ago.total_seconds() < 3600:
                time_str = f"{int(time_ago.total_seconds() / 60)} minutes ago"
            else:
                time_str = f"{int(time_ago.total_seconds() / 3600)} hours ago"
            
            # Calculate when this escalation expires
            expires_in = cooldown_hours - (time_ago.total_seconds() / 3600)
            if expires_in < 1:
                expires_str = f"{int(expires_in * 60)} minutes"
            else:
                expires_str = f"{int(expires_in)} hours"
            
            print(f"  Level {level}: {timestamp.strftime('%H:%M:%S')} ({time_str}, expires in {expires_str})")

def dry_run(config: Config) -> int:
    """Perform a dry run without actually escalating issues."""
    from escalate.models import Rule
    
    # Create the escalator
    escalator = Escalator(config)
    
    # Group rules by level
    rules_by_level = {}
    for rule in escalator.load_rules():
        if rule.level not in rules_by_level:
            rules_by_level[rule.level] = []
        rules_by_level[rule.level].append(rule)
    
    total_would_escalate = 0
    
    print("Dry run results:")
    
    # Process each level of rules
    for level in sorted(rules_by_level.keys()):
        print(f"\n=== LEVEL {level} Rules ===")
        rules = rules_by_level[level]
        
        for rule in rules:
            print(f"\nProcessing rule: {rule.name or rule.jql}")
            
            # Find issues matching the rule
            issues = escalator.jira_client.find_issues_for_rule(rule)
            
            if not issues:
                print(f"  No issues found matching rule")
                continue
            
            print(f"  Found {len(issues)} potential issues")
            
            # Filter issues based on days_to_activate and escalation history
            eligible_issues = escalator.filter_eligible_issues(issues, rule)
            
            if not eligible_issues:
                print(f"  No eligible issues to escalate")
                continue
            
            print(f"  Would escalate {len(eligible_issues)} issues:")
            
            for issue in eligible_issues:
                print(f"    - {issue['key']}: {issue['summary']}")
                print(f"      Status: {issue['status']} for {issue['time_in_status_minutes']:.1f} minutes")
                
                # If there are escalation paths, list them
                for path in rule.escalation_paths:
                    print(f"      Would send {path.type.value} to {path.recipient}")
                
                total_would_escalate += 1
    
    print(f"\nTotal: Would escalate {total_would_escalate} issues")
    return total_would_escalate

def main() -> int:
    """Main entry point for the command-line interface."""
    args = parse_args()
    
    # Configure logging
    log_level = "DEBUG" if args.verbose else "INFO"
    configure_logging(log_level)
    
    try:
        # Load configuration
        config = Config(args.config)
        
        # Just list rules if requested
        if args.list_rules:
            list_rules(config)
            return 0
        
        # Show history if requested
        if args.show_history:
            show_history(config)
            return 0
        
        # Clear history if requested
        if args.clear_history:
            clear_history(config)
            return 0
        
        # Clear history for specific issue if requested
        if args.clear_history_for:
            clear_history(config, args.clear_history_for)
            return 0
        
        # List active escalations if requested
        if args.list_active_escalations:
            list_active_escalations(config)
            return 0
        
        # Validate configuration
        if not config.validate():
            logger.error("Invalid configuration. Please check your config file and environment variables.")
            return 1
        
        # Create escalator
        escalator = Escalator(config)
        
        if args.dry_run:
            logger.info("Performing dry run...")
            return dry_run(config)
        
        # Process rules
        escalated_count = escalator.process_rules()
        
        logger.info(f"Escalated {escalated_count} issues")
        return 0
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        if args.verbose:
            logger.exception("Detailed error:")
        return 1

if __name__ == "__main__":
    sys.exit(main())