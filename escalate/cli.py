"""Command-line interface for the escalate tool."""
import sys
import argparse
import logging
import json
from typing import Dict, Any, Optional

from escalate.config import Config
from escalate.escalator import Escalator
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
    
    return parser.parse_args()

def list_rules(config: Config) -> None:
    """Print all rules in the config file."""
    print(f"Found {len(config.rules)} rules:")
    for i, rule in enumerate(config.rules, 1):
        name = rule.get("name", f"Rule {i}")
        jql = rule.get("jql", "No JQL specified")
        max_time = rule.get("max_time_in_status_minutes", "Not specified")
        
        print(f"\n{i}. {name}")
        print(f"   JQL: {jql}")
        print(f"   Max time in status: {max_time} minutes")
        
        paths = rule.get("escalation_paths", [])
        print(f"   Escalation paths ({len(paths)}):")
        
        for j, path in enumerate(paths, 1):
            path_type = path.get("type", "Unknown")
            recipient = path.get("recipient", "Not specified")
            print(f"     {j}. {path_type} -> {recipient}")

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
        
        # Validate configuration
        if not config.validate():
            logger.error("Invalid configuration. Please check your config file and environment variables.")
            return 1
        
        # Create escalator
        escalator = Escalator(config)
        
        if args.dry_run:
            logger.info("Performing dry run...")
            # TODO: Implement dry run logic
            return 0
        
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