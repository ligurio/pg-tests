import os
import platform
import psutil
import psycopg2
import subprocess
from subprocess import Popen

from helpers.pginstall import DEB_BASED
from helpers.pginstall import package_mgmt
from helpers.pginstall import RPM_BASED
from helpers.pginstall import setup_repo
from helpers.sql_helpers import pg_get_option
from helpers.sql_helpers import pg_set_option
from helpers.sql_helpers import pg_check_option
from helpers.sql_helpers import pg_manage_psql


class PgInstance:
    PG_PASSWORD = 'password'

    def __init__(self, version, milestone, name, edition, build, skip_install):
        self.version = version
        self.milestone = milestone
        self.name = name
        self.edition = edition
        self.build = build
        self.connstring = "host='localhost' user='postgres'"
        self.skip_install = True
        self.data_dir = self.get_option('data_directory')

        if not skip_install:
            self.skip_install = False
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

    def start_script_name(self, action):

        distro = platform.linux_distribution()[0]
        major = self.version.split(".")[0]
        minor = self.version.split(".")[1]

        service_name = ""
        if distro in RPM_BASED or distro == "ALT Linux ":
            if self.name == 'postgresql':
                service_name = "postgresql-%s.%s" % (major, minor)
            elif self.name == 'postgrespro' and self.edition == 'ee':
                service_name = "postgrespro-enterprise-%s.%s" % (major, minor)
            elif self.name == 'postgrespro' and self.edition == 'standard':
                service_name = "postgrespro-%s.%s" % (major, minor)
        elif distro in DEB_BASED:
            service_name = "postgresql"

        return service_name


    def manage_psql(self, action, init=False):
        """ Manage Postgres instance
        :param action: start, restart, stop etc
        :param init: Initialization before a first start
        :return:
        """

        data_dir = self.get_option('data_directory')
        if self.skip_install:
            ret = pg_manage_psql(action, data_dir)
        else:
            ret = pg_manage_psql(action, None, self.start_script_name, init)
            
        return ret

    def edit_pg_hba_conf(self, pg_hba_config):
        """Rewrite pg_hba.conf

        :param pg_hba_config: string with pg_hba.conf content
        """
        cmd = ["sudo", "-u", "postgres", "psql", "-t", "-P",
               "format=unaligned", "-c", "SHOW hba_file;"]
        p = Popen(cmd, stdout=subprocess.PIPE)
        response = p.communicate()
        if p.returncode != 0:
            print "Failed to find hba_file %s" % response[1]
            return 1

        hba_file = response[0].rstrip()
        print "Path to hba_file is", hba_file
        with open(hba_file, 'w') as hba:
            hba.write(pg_hba_config)

        subprocess.call(["chown", "postgres:postgres", hba_file])

    def setup_psql(self, name, version, edition, milestone, build):

        major = version.split(".")[0]
        minor = version.split(".")[1]

        print "Setup PostgreSQL service"
        self.manage_psql("start", True)

        os.environ['PATH'] += ":/usr/pgsql-%s.%s/bin/" % (major, minor)
        subprocess.call(["sudo", "-u", "postgres", "psql", "-c",
                         "ALTER USER postgres WITH PASSWORD '%s';"
                         % self.PG_PASSWORD])

        hba_auth = """
    local   all             all                                     peer
    host    all             all             0.0.0.0/0               trust
    host    all             all             ::0/0                   trust"""
        self.edit_pg_hba_conf(hba_auth)

        subprocess.call(["sudo", "-u", "postgres", "psql", "-c",
                         "ALTER SYSTEM SET listen_addresses to '*';"])
        self.manage_psql("restart")

    def get_postmaster_pid(self):
        """
        Method returns PID of the postmaster process.

        :returns: number with process identificator
        """

        conn = psycopg2.connect(self.connstring)
        pid = conn.get_backend_pid()
        ppid = psutil.Process(pid).ppid()
        conn.close()
        return ppid

    def get_option(self, option):
        """ Get current value of a PostgreSQL option
        :param: option name
        :return:
        """

        return pg_get_option(self.connstring, option)

    def check_option(self, option):
        """ Check existence of a PostgreSQL option
        :param: option name
        :return: False or True
        """

        return pg_check_option(self.connstring, option)

    def set_option(self, option, value):
        """ Set a new value to a PostgreSQL option
        :param: option name and new value
        :return: False or True
        """

        return pg_set_option(self.connstring, option, value)

    def load_extension(self, extension_name):
        """ Load PostgreSQL extension
        """

        loaded_extensions = self.get_option('shared_libraries')
        if loaded_extensions is None:
            extensions = extension_name
        else:
            extensions = loaded_extensions + ',' + extension_name
        self.set_option('shared_preload_libraries', extensions)

        conn = psycopg2.connect(self.connstring)
        cursor = conn.cursor()
        cursor.execute("CREATE EXTENSION IF NOT EXISTS %s" % extension_name)
        cursor.close()
        conn.close()
