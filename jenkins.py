#!/usr/bin/python

import base64
import datetime
import json
import re
import smtplib
import sys
import subprocess
import time
from helpers.utils import urlopen

MAIL_HOST = "postfix.l.postgrespro.ru"
MAIL_TO = ["m.samoylov@postgrespro.ru"]
MAIL_FROM = "m.samoylov@postgrespro.ru"
CHECK_TIMEOUT = 10
GITLAB_TOKEN = "8BZ5DaaLycAe5AGGTERb"
JENKINS_LOGIN = "jenkins"
JENKINS_PWORD = "jenkins"
JENKINS_URL = "http://bldfrm0.l.postgrespro.ru:8080/" \
    "view/%s/job/%s-hub/lastBuild/api/json"
TESTRUN_CMD = "./testrun.py --target %s --product_name postgrespro" \
    " --product_version %s --product_edition %s" \
    " --product_milestone beta --export"
DEBUG = False

if len(sys.argv) > 1:
    branch = sys.argv[1]
else:
    print("Usage: specify branch, like pgproee-9.6")
    sys.exit(1)

hubUrl = JENKINS_URL % (branch, branch)


def send_mail(text, subject):
    server = smtplib.SMTP(MAIL_HOST)
    server.ehlo()
    text = "Subject: %s\n%s" % (subject, text)
    if DEBUG:
        server.set_debuglevel(1)

    try:
        server.sendmail(MAIL_FROM, MAIL_TO, text)
    finally:
        server.quit()


def get_build_images(build_status):
    images = []
    for b in build_status["subBuilds"]:
        jobname = b["jobName"]
        if re.search('win', jobname):
            continue    # see PGPRO-153
        name = re.findall('%s-(.*)-amd64' % branch, jobname)[0]
        images.append(name)
    return images


def get_build_info(branch):
    request = urlopen(hubUrl)
    base64string = base64.b64encode(JENKINS_LOGIN + ':' + JENKINS_PWORD)
    request.add_header("Authorization", "Basic %s" % base64string)

    try:
        result = request.read().decode()
    except Exception as e:
        # pylint: disable=no-member
        print("URL Error: " + str(e.code))
        print("(branch name [" + branch + "] is probably wrong)")
        return e

    try:
        buildStatusJson = json.load(result)
    except ValueError as e:
        print("Failed to parse JSON")
        return e

    return buildStatusJson


def check_commits(last_commit):
    url = 'https://git.postgrespro.ru/api/v3/projects/193' \
        '/repository/commits?since=' + last_commit
    # pylint: disable=undefined-variable
    request = urllib2.Request(url, headers={"PRIVATE-TOKEN": GITLAB_TOKEN})

    try:
        # pylint: disable=undefined-variable
        result = urllib2.urlopen(request)
    # pylint: disable=undefined-variable
    except urllib2.HTTPError as e:
        print("URL Error: " + str(e.code))
        return False

    try:
        commits = json.load(result)
    except ValueError:
        print("Failed to parse JSON")
        return False

    if len(commits) > 0:
        return True
    else:
        return False


product_info = branch.split('-')
if product_info[0] == "pgproee":
    product_edition = "ent"
elif product_info[0] == "pgpro":
    product_edition = "std"
product_version = product_info[1]

print("Product version %s and edition %s" % (product_version, product_edition))

last_status = ""
last_timestamp = ""
last_commit = datetime.datetime.now().isoformat()
print("[" + branch + "] " + hubUrl)
while True:
    runtest = False
    build_status = get_build_info(branch)
    targets = get_build_images(build_status)

    last_status = build_status["result"]
    if last_status == "SUCCESS" and last_timestamp > build_status["timestamp"]:
        last_timestamp = build_status["timestamp"]
        print("[" + branch + "] New build - %s" % build_status["number"])
        runtest = True
    if check_commits(last_commit):
        last_commit = datetime.datetime.now().isoformat()
        print("[" + branch + "] New commit")
        runtest = True

    if runtest:
        for t in targets:
            print("[" + branch + "] Exec tests on %s" % t)
            cmd = TESTRUN_CMD % (t, product_version, product_edition)
            print(cmd)
            p = subprocess.Popen(
                cmd.split(' '), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = p.communicate()
            if p.returncode != 0:
                subject = "[FAIL]"
                if out != "":
                    print(" =================== stdout ======================")
                    print(out)
                if err != "":
                    print(" =================== stderr ======================")
                    print(err)
            else:
                subject = "[PASS]"
            output = "\n\nstdout\n\n%s\n\nstderr\n%s" % (out, err)
            subject += " %s build %s -- %s" % (branch,
                                               build_status["number"], t)
            send_mail(output, subject)
            print("[" + branch + "] Done %s" % t)

    time.sleep(CHECK_TIMEOUT)
