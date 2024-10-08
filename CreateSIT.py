"""
    This is a script generating creating EPICS and Stories under SAFe Features for ST Team integration
"""

# coding=utf-8
import sys
import json
import logging
import colorlog
import urllib3
import argparse
import re

from atlassian import Jira

# disabling the warning on no/expired SSL certificate
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
            print("Error fetching JQL.")
            logging.error("Error fetching JQL.")
            exit(1)

        for value in values:
            self.issues.append(value)

        i = 0
        prefix = create_fields['summary']

        for value in values:
            i += 1

            issue_key = value['key']
            issue_summary = value['fields']['summary']

            if suffix:
                suffix_str = re.sub("[\(\[].*?[\)\]]", "", value['fields']['summary'])
                suffix_str = re.sub("ST: SIT -", "", suffix_str)
                create_fields['summary'] = prefix + suffix_str
                if create_fields['issuetype']['name'] == "Epic":
                    create_fields["customfield_11502"] = prefix + suffix_str

            print(i, ": ", issue_key, issue_summary)
            print("Creating: ", create_fields)

            # Check if the issue is already linked by comparing summaries (names)
            linked_issues = value['fields'].get('issuelinks', [])
            issue_exists = False

            # Iterate through linked issues and check if any have the same summary (name)
            for link in linked_issues:
                # Different links have different structures, check both inward and outward links
                if 'inwardIssue' in link:
                    linked_issue_summary = link['inwardIssue']['fields']['summary']
                elif 'outwardIssue' in link:
                    linked_issue_summary = link['outwardIssue']['fields']['summary']
                else:
                    continue

                if linked_issue_summary == create_fields['summary']:
                    issue_exists = True
                    logging.warning("\"" + create_fields['summary'] + "\"" + " already exists as a linked issue.")
                    break

            if issue_exists:
                continue  # Skip creating the issue if it already exists as a linked issue

            # Proceed with issue creation if it does not exist
            try:
                created_issue = self.jira.issue_create(fields=create_fields)
                logging.info("Created: " + created_issue['key'])
            except Exception as e:
                logging.error("Error creating issue:" + str(e))
                return  # Exit if issue creation fails

            # After issue creation, add the issue link
            if create_fields['issuetype']['name'] == "Epic":
                try:
                    link_payload = {
                        "type": {"id": "10502"},
                        "inwardIssue": {"key": created_issue['key'], },
                        "outwardIssue": {"key": issue_key}
                    }
                    self.jira.create_issue_link(link_payload)
                    logging.info("Linked: " + created_issue['key'] + " to " + issue_key)
                except Exception as e:
                    logging.error("Error creating issue link:" + str(e))
                # After issue creation, add the issue link

            elif create_fields['issuetype']['name'] == "Story":
                try:
                    # Update the 'Epic Link' field to associate the Story with the Epic
                    epic_link_payload = {
                        "customfield_11501": issue_key  # Replace with the correct Epic Link field ID
                        }
                    self.jira.issue_update(created_issue['key'], epic_link_payload)
                    logging.info(f"Updated Story: {created_issue['key']} with Epic Link: {issue_key}")

                except Exception as e:
                    logging.error("Error creating issue link:" + str(e))



def main():

    parser = argparse.ArgumentParser(description="Just a wrapper to prepare arguments")
    parser.add_argument("--jql", type=str, action="store", required=True, help="Path to the JQL file")
    parser.add_argument("--fields", type=str, action="store", required=True, help="Path to the fields JSON file")
    parser.add_argument("-suffix", action="store_true", help="Add a parent suffix to the summary of the created issues")
    parser.add_argument("--debug", type=str, action="store", default="INFO", help="Logging level (e.g., DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    args = parser.parse_args()

    log_format = "%(log_color)s%(asctime)s - %(levelname)s - %(message)s"
    log_colors = {
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
    handler = colorlog.StreamHandler(sys.stdout)
    handler.setFormatter(colorlog.ColoredFormatter(log_format, log_colors=log_colors))


    # Initialize Jira object
    jira = Jira(url="http://jira.frequentis.frq", token="ODAxNTEzNzg5NTMyOgRAZYeOvlN/hLHS0ahGpafxDrPI", verify_ssl=False)

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

    report = ReportGenerator(jira=jira)
    report._fetch_SAFe(jql, create_fields, args.suffix)
    print("\n")

if __name__ == "__main__":
    main()