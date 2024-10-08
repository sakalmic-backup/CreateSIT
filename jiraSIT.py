# coding=utf-8
import sys
import json
import logging
import colorlog
import urllib3
import argparse
import re
import getpass  # For secure password entry
from atlassian import Jira

# Disable warnings on expired SSL certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ReportGenerator:
    def __init__(self, jira):
        self.jira = jira
        self.issues = []

    def _fetch_SAFe(self, jql, create_fields, suffix):
        try:
            response = self.jira.jql(
                jql,
                fields=["issuetype", "summary", "status", 'issuekey', 'project', 'issuelinks'],
                limit=1000
            )
            values = response.get("issues") or []
        except ValueError:
            values = []
            logging.error("Error fetching JQL.")
            exit(1)

        # Collect issues for processing
        for value in values:
            self.issues.append(value)

        prefix = create_fields['summary']

        # Iterate over issues and create new Epics or Stories
        for i, value in enumerate(values, start=1):
            issue_key = value['key']
            issue_summary = value['fields']['summary']

            if suffix:
                suffix_str = re.sub(r"[\(\[].*?[\)\]]", "",
                                    issue_summary)  # Remove any text inside parentheses or brackets
                suffix_str = re.sub("ST: SIT -", "", suffix_str)  # Custom suffix formatting
                create_fields['summary'] = prefix + suffix_str
                if create_fields['issuetype']['name'] == "Epic":
                    create_fields["customfield_11502"] = prefix + suffix_str  # Epic Name field

            print(f"{i}: {issue_key} - {issue_summary}")
            print(f"Creating: {create_fields}")

            # Check if the issue is already linked or exists as a Story under an Epic
            if self._issue_already_exists(value, create_fields['summary']):
                logging.warning(f"Issue with summary '{create_fields['summary']}' already exists as a linked issue.")
                continue

            # Proceed with issue creation if it doesn't already exist
            try:
                created_issue = self.jira.issue_create(fields=create_fields)
                logging.info(f"Created: {created_issue['key']}")
            except Exception as e:
                logging.error(f"Error creating issue: {e}")
                return

            # Link newly created Epic or Story
            self._link_issue(value, created_issue, create_fields)

    def _issue_already_exists(self, parent_issue, summary):
        """ Check if the issue already exists by comparing summaries of linked issues. """
        linked_issues = parent_issue['fields'].get('issuelinks', [])
        for link in linked_issues:
            linked_summary = ""
            if 'inwardIssue' in link:
                linked_summary = link['inwardIssue']['fields']['summary']
            elif 'outwardIssue' in link:
                linked_summary = link['outwardIssue']['fields']['summary']

            if linked_summary == summary:
                return True
        return False

    def _link_issue(self, parent_issue, created_issue, create_fields):
        """ Link newly created Epics and Stories to their parent issues. """
        parent_key = parent_issue['key']

        if create_fields['issuetype']['name'] == "Epic":
            # Link the Epic to the parent issue
            self._link_epic_to_safe_feature(parent_key, created_issue['key'])

        elif create_fields['issuetype']['name'] == "Story":
            # Update the Story's Epic Link
            self._link_story_to_epic(parent_key, created_issue['key'])

    def _link_epic_to_safe_feature(self, safe_feature_key, epic_key):
        """ Link an Epic to a SAFe Feature (parent issue). """
        try:
            link_payload = {
                "type": {"id": "10502"},
                "inwardIssue": {"key": epic_key},
                "outwardIssue": {"key": safe_feature_key}
            }
            self.jira.create_issue_link(link_payload)
            logging.info(f"Linked Epic {epic_key} to SAFe Feature {safe_feature_key}")
        except Exception as e:
            logging.error(f"Error linking Epic to SAFe Feature: {e}")

    def _link_story_to_epic(self, epic_key, story_key):
        """ Link a Story to its Epic using the 'Epic Link' field. """
        try:
            epic_link_payload = {
                "customfield_11501": epic_key  # Replace with the correct Epic Link field ID
            }
            self.jira.issue_update(story_key, epic_link_payload)
            logging.info(f"Updated Story {story_key} with Epic Link {epic_key}")
        except Exception as e:
            logging.error(f"Error linking Story to Epic: {e}")


def main():
    parser = argparse.ArgumentParser(description="Jira Issue Creator for SAFe and Story Epics")
    parser.add_argument("--jql", type=str, required=True, help="JQL query to find SAFe Features or Epics")
    parser.add_argument("--fields", type=str, required=True, help="Path to JSON file with fields for issue creation")
    parser.add_argument("--suffix", action="store_true", help="Add parent suffix to the summary of the created issues")
    parser.add_argument("--debug", type=str, default="INFO",
                        help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    args = parser.parse_args()

    # Setup logging with colors
    log_format = "%(log_color)s%(asctime)s - %(levelname)s - %(message)s"
    '''
    log_colors = {
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }

    handler = colorlog.StreamHandler(sys.stdout)
    handler.setFormatter(colorlog.ColoredFormatter(log_format, log_colors=log_colors))
    logging.basicConfig(level=args.debug, handlers=[handler])
    '''

    # Setup logging without colors (remove colorlog to avoid interference)
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=args.debug, format=log_format)

    # Debug statement to check where the script might get stuck
    logging.debug("Starting Jira credentials prompt...")

    # Prompt for Jira credentials (username and password or API token)
    jira_url = input("Enter Jira URL (e.g., https://jiraclone.frequentis.frq): ")
    logging.debug(f"Jira URL entered: {jira_url}")  # Debugging line to ensure input is received
    username = input("Enter your Jira username: ")
    logging.debug(f"Username entered: {username}")  # Debugging line to ensure input is received
    password = getpass.getpass("Enter your Jira API token (or password): ")
    logging.debug("Password input completed.")  # Debugging line to confirm password entry

    # Initialize Jira object
    jira = Jira(url=jira_url, username=username, password=password, verify_ssl=False)

    # Load JQL and fields from files
    try:
        with open(args.jql, 'r') as jql_file:
            jql = jql_file.read()
            logging.info("JQL loaded successfully.")
    except FileNotFoundError:
        logging.error("JQL file not found.")
        return

    try:
        with open(args.fields, 'r') as fields_file:
            create_fields = json.load(fields_file)
            logging.info("Fields loaded successfully.")
    except json.JSONDecodeError:
        logging.error("Error parsing fields JSON.")
        return

    # Start the report generation process
    report = ReportGenerator(jira=jira)
    report._fetch_SAFe(jql, create_fields, args.suffix)


if __name__ == "__main__":
    main()