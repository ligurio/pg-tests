import fileinput
import fnmatch
import os
import platform
import psycopg2
import re
import subprocess
from subprocess import Popen

from helpers.pginstall import DEB_BASED
from helpers.pginstall import package_mgmt
from helpers.pginstall import RPM_BASED
from helpers.pginstall import setup_repo


class PgInstance:
    PG_PASSWORD = 'password'

    def __init__(self, version, milestone, name, edition, build):
        self.version = version
        self.milestone = milestone
        self.name = name
        self.edition = edition
        self.build = build
        self.install_product(name, version, edition, milestone, build)

    def install_product(self, name, version, edition, milestone, build):
        """ Install product
        Parameter: Product name: postgrespro, postgresql
        Parameter: Product version: 9.5, 9.6 etc
        Parameter: Product editions (postgrespro only): standard, ee
        Parameter: Product milestone (postgrespro only): beta
        """

        setup_repo(name, version, edition, milestone, build)
        package_mgmt(name, version, edition, milestone, build)
        self.setup_psql(name, version, edition, milestone, build)

        return {'name': name,
                'version': version,
                'edition': edition,
                'milestone': milestone}

    def manage_psql(self, version, action, init=False):
        """ Manage Postgres instance
        :param version 9.5, 9.6 etc
        :param action: start, restart, stop etc
        :param init: Initialization before a first start
        :return:
        """

        distro = platform.linux_distribution()[0]
        major = version.split(".")[0]
        minor = version.split(".")[1]

        if distro in RPM_BASED:
            service_name = "postgresql-%s.%s" % (major, minor)
        elif distro in DEB_BASED:
            service_name = "postgresql"

        if init:
            if distro in RPM_BASED:
                subprocess.call(["service", service_name, "initdb"])
                # subprocess.call(["chkconfig", service_name, "on"])
                # subprocess.call(["systemctl", "enable", "postgresql"])

        return subprocess.call(["service", service_name, action])

    def setup_psql(self, name, version, edition, milestone, build):

        distro = platform.linux_distribution()[0]
        major = version.split(".")[0]
        minor = version.split(".")[1]

        print "Setup PostgreSQL service"
        self.manage_psql(version, "start", True)

        os.environ['PATH'] += ":/usr/pgsql-%s.%s/bin/" % (major, minor)
        subprocess.call(["sudo", "-u", "postgres", "psql", "-c",
                         "ALTER USER postgres WITH PASSWORD '%s';" % self.PG_PASSWORD])

        hba_auth = """
    local   all             all                                     peer
    host    all             all             0.0.0.0/0               trust
    host    all             all             ::0/0                   trust"""

        cmd = ["sudo", "-u", "postgres", "psql", "-t", "-P",
               "format=unaligned", "-c", "SHOW hba_file;"]
        p = Popen(cmd, stdout=subprocess.PIPE)
        response = p.communicate()
        if p.returncode != 0:
            print "Failed to find hba_file %s" % response[1]
            return 1

        hba_file = response[0].rstrip()
        print "Path to hba_file is", hba_file
        hba = fileinput.FileInput(hba_file, inplace=True)
        for line in hba:
            if line[0] != '#':
                line = re.sub('^', '#', line.rstrip())
            print line.rstrip()

        with open(hba_file, 'a') as hba:
            hba.write(hba_auth)

        subprocess.call(["chown", "postgres:postgres", hba_file])
        subprocess.call(["sudo", "-u", "postgres", "psql", "-c",
                         "ALTER SYSTEM SET listen_addresses to '*';"])
        self.manage_psql(version, "restart")

    def get_option(self, option):
        """ Get current value of a PostgreSQL option
        :param: option name
        :return:
        """

        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        if not self.check_option(option):
            return None

        cursor.execute("SELECT setting FROM pg_settings WHERE name = '%s'" % option)
        value = cursor.fetchall()[0][0]

        cursor.close()
        conn.close()

        return value

    def check_option(self, option):
        """ Check existence of a PostgreSQL option
        :param: option name
        :return: False or True
        """

        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute("SELECT exists (SELECT 1 FROM pg_settings WHERE name = '%s' LIMIT 1)" % option)

        if not cursor.fetchall()[0][0]:
            return False

        cursor.close()
        conn.close()

        return True

    def set_option(self, option, value):
        """ Set a new value to a PostgreSQL option
        :param: option name and new value
        :return: False or True
        """

        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        conn.set_session(autocommit=True)

        if not self.check_option(option):
            return False

        cursor.execute("SELECT context FROM pg_settings WHERE name = '%s'" % option)
        context = cursor.fetchall()[0][0]

        restart_contexts = ['superuser-backend', 'backend', 'user', 'postmaster', 'superuser']
        reload_contexts = ['sighup']

        if context in reload_contexts:
            cursor.execute("ALTER SYSTEM SET %s = '%s'" % (option, value))
            cursor.close()
            conn.close()
            return self.manage_psql(self.version, "reload")
        elif context in restart_contexts:
            cursor.execute("ALTER SYSTEM SET %s = '%s'" % (option, value))
            cursor.close()
            conn.close()
            return self.manage_psql(self.version, "restart")
        else:
            return False
