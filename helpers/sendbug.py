#!/usr/bin/env python

# https://www.postgresql.org/docs/9.6/static/bug-reporting.html
# https://wiki.postgresql.org/wiki/Guide_to_reporting_problems

import argparse
import base64
import json
import platform
import subprocess
import sys
import urllib2


def getDistribution():

    if sys.platform == "win32":
        return win32_version()
    elif sys.platform == "linux" or sys.platform == "linux2":
        distname, version, id = platform.linux_distribution()
        return "%s %s" % (distname, version)
    elif sys.platform == "darwin":
        release, versioninfo, machine = platform.mac_ver()
        return "%s %s" % (release, versioninfo)
    else:
        return "Undefined"


def createDescription():

    description = """
>> Description

>> Steps to reproduce:

>> Actual results:

>> Expected results:

>> Environment:"""

    query = """
SELECT version();
SELECT pgpro_version();
SELECT pgpro_edition();
SELECT name, current_setting(name), SOURCE
FROM pg_settings WHERE SOURCE NOT IN ('default', 'override');"""

    process = subprocess.Popen(['psql', '-e'], shell=False,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    env, err = process.communicate(query)
    return description + "\n" + env


def createTask(server_base_url, user, password,
               project, task_summary, component):

    task_environment = getDistribution()
    task_description = createDescription()

    try:
        data = {
            "fields": {
                "project": {
                    "key": project
                },
                "summary": task_summary,
                "issuetype": {
                    "name": "Bug"
                },
                "environment": task_environment,
                "description": task_description,
                "components": [
                    {
                        "id": component
                    }
                ],
            }
        }

        server_base_url = 'https://jira.postgrespro.ru'
        complete_url = "%s/rest/api/2/issue" % server_base_url
        base64string = base64.encodestring('%s:%s' % (user, password))[:-1]
        request = urllib2.Request(complete_url, json.dumps(data),
                                  {'Content-Type': 'application/json'})
        request.add_header("Authorization", "Basic %s" % base64string)
        response = urllib2.urlopen(request)

    except Exception, ex:
        print "EXCEPTION: %s " % ex.msg
        return None

    if response.code / 100 != 2:
        print "ERROR: status %s" % response.code
        return None
    issue = json.loads(response.read())
    return issue

if __name__ == '__main__':

    server_url = 'https://jira.postgrespro.ru'
    project = 'PGPRO'
    component = '10211'  # QA

    desc = 'Script helps to submit a new Jira issue.'
    epilog = "Example: sendbug.py --summary 'XXX' --user " \
             "'s.bronnikov' --password 'GQoJrxl'"
    parser = argparse.ArgumentParser(description=desc, epilog=epilog)

    parser.add_argument('--project', dest="project",
                        help='Jira project ID (default: %s)' % project,
                        default=project)
    parser.add_argument('--url', dest="server_url",
                        help='Jira URL (default: %s)' % server_url,
                        default=server_url)
    parser.add_argument('--summary', dest="summary",
                        help='Summary', required=True)
    parser.add_argument('--user', dest="username",
                        help='Jira user', required=True)
    parser.add_argument('--password', dest="password",
                        help='Jira password', required=True)
    parser.add_argument('--dry-run', dest="dry_run",
                        help='Show description without'
                             ' submitting of new issue', action='store_true')

    args = parser.parse_args()

    summary = args.summary
    username = args.username
    password = args.password

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.dry_run:
        print createDescription()
        sys.exit(0)

    issue = createTask(server_url, username, password,
                       project, summary, component)
    issue_code = issue["key"]
    issue_url = "%s/browse/%s" % (server_url, issue_code)

    if (issue is not None):
        print issue_url
    else:
        sys.exit(2)
