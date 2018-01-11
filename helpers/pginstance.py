import os
import psutil
import psycopg2
import re
import sys
import urllib

from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from helpers.pginstall import package_mgmt
from helpers.pginstall import setup_repo
from helpers.sql_helpers import pg_get_option
from helpers.sql_helpers import pg_set_option
from helpers.sql_helpers import pg_check_option
from helpers.sql_helpers import pg_manage_psql
from helpers.sql_helpers import pg_start_script_name
from helpers.pginstall import (RPM_BASED,
                               PGPRO_ARCHIVE_STANDARD,
                               PGPRO_ARCHIVE_ENTERPRISE)

from helpers.utils import command_executor
from helpers.utils import get_distro
from helpers.utils import REMOTE_ROOT
from helpers.utils import REMOTE_ROOT_PASSWORD
from helpers.utils import write_file


class PgInstance:
    PG_PASSWORD = 'password'

    def __init__(self, version, milestone, name, edition,
                 skip_install, branch,
                 node_ip=None, cluster=False, windows=False):
        """

        :param version:
        :param milestone:
        :param name:
        :param edition:
        :param skip_install:
        :param branch:
        :param node_ip:
        :param cluster:
        :param windows:
        """
        self.version = version
        self.milestone = milestone
        self.name = name
        self.edition = edition
        self.skip_install = skip_install
        self.branch = branch
        self.connstring = "host=localhost user=postgres"
        self.windows = windows
        self.cluster = cluster
        self.node_ip = node_ip
        self.pgpro_version = None
        self.postgresql_version = None
        self.pgpro_edition = None
        self.available_minor_updates = None
        self.minor_version = None
        if cluster and not node_ip:
            print("You must provide ip address for node in cluster mode")
            sys.exit(1)
        if cluster and node_ip:
            self.connstring = "host=%s user=postgres" % node_ip

    def install_product(self, name, version, edition, milestone, branch,
                        windows=False, skip_install_psql=False):
        """ Install product
        Parameter: Product name: postgrespro, postgresql
        Parameter: Product version: 9.5, 9.6 etc
        Parameter: Product editions (postgrespro only): standard, ee
        Parameter: Product milestone (postgrespro only): beta
        """
        if windows:
            setup_repo(name=name, version=version, edition=edition,
                       milestone=milestone, branch=branch)
        else:
            if skip_install_psql:
                setup_repo(name=name, version=version, edition=edition,
                           milestone=milestone, branch=branch)
                package_mgmt(name=name, version=version, edition=edition,
                             milestone=milestone, branch=branch)
            else:
                setup_repo(name=name, version=version, edition=edition,
                           milestone=milestone, branch=branch)
                package_mgmt(name=name, version=version, edition=edition,
                             milestone=milestone, branch=branch)
                self.setup_psql(version)

        return {'name': name,
                'version': version,
                'edition': edition,
                'milestone': milestone}

    def install_product_cluster(self, node_ip, name, version, edition,
                                milestone, branch, skip_install_psql=False):
        """

        :param node_ip:
        :param name:
        :param version:
        :param edition:
        :param milestone:
        :param branch:
        :param skip_install_psql:
        :return:
        """
        if skip_install_psql:
            setup_repo(remote=True, host=node_ip, version=version,
                       milestone=milestone, name=name,
                       edition=edition, branch=branch)
            package_mgmt(remote=True, host=node_ip, version=version,
                         milestone=milestone, name=name,
                         edition=edition, branch=branch)
        else:
            setup_repo(remote=True, host=node_ip, version=version,
                       milestone=milestone, name=name,
                       edition=edition, branch=branch)
            package_mgmt(remote=True, host=node_ip, version=version,
                         milestone=milestone, name=name,
                         edition=edition, branch=branch)
            self.setup_psql(remote=True, host=node_ip, version=version)
        return {'name': name,
                'version': version,
                'edition': edition,
                'milestone': milestone}

    def start_script_name(self, remote=False, host=None):

        return pg_start_script_name(self.name,
                                    self.edition,
                                    self.version,
                                    distro=get_distro(remote, host)[0])

    def manage_psql(self, action, data_dir=None, remote=False, host=None):
        """ Manage Postgres instance
        :param action: start, restart, stop etc
        :param init: Initialization before a first start
        :return:
        """

        if self.skip_install:
            return pg_manage_psql(action, data_dir)
        else:
            return pg_manage_psql(action=action, data_dir=data_dir,
                                  start_script=self.start_script_name(
                                      remote, host),
                                  remote=remote, host=host)

    def edit_pg_hba_conf(self, pg_hba_config, remote=False, host=None):
        """Rewrite pg_hba.conf

        :param pg_hba_config: string with pg_hba.conf content
        """
        cmd = "sudo -u postgres psql -t -P format=unaligned -c " \
            "\"SHOW hba_file;\""
        hba_file = ""
        if remote:
            hba_file = command_executor(cmd, remote, host,
                                        REMOTE_ROOT,
                                        REMOTE_ROOT_PASSWORD)[1].strip()
        else:
            hba_file = command_executor(cmd, remote, host,
                                        REMOTE_ROOT,
                                        REMOTE_ROOT_PASSWORD,
                                        stdout=True).strip()
        print "Path to hba_file is", hba_file
        write_file(hba_file, pg_hba_config, remote, host)
        cmd = "chown postgres:postgres %s" % hba_file
        return command_executor(cmd, remote, host,
                                REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    def setup_psql(self, version, remote=False, host=None):
        """

        :param version:
        :param remote:
        :param host:
        :return:
        """

        major = version.split(".")[0]
        minor = version.split(".")[1]

        print "Setup PostgreSQL service"

        distro = get_distro(remote, host)[0]
        if distro in RPM_BASED or "ALT " in distro:
            self.manage_psql("initdb", remote=remote, host=host)
        self.manage_psql("start", remote=remote, host=host)

        if remote:
            cmd = "export PATH=$PATH:/usr/pgsql-%s.%s/bin/" % (major, minor)
            command_executor(cmd, remote, host,
                             login=REMOTE_ROOT, password=REMOTE_ROOT_PASSWORD)
        else:
            os.environ['PATH'] += ":/usr/pgsql-%s.%s/bin/" % (major, minor)
        cmd = "sudo -u postgres psql -c \"ALTER USER postgres" \
            " WITH PASSWORD \'%s\';\"" % self.PG_PASSWORD
        command_executor(cmd, remote, host,
                         login=REMOTE_ROOT, password=REMOTE_ROOT_PASSWORD)

        if self.cluster:
            hba_auth = """
    local   all             postgres                                trust
    local   all             all                                     peer
    host    all             all             0.0.0.0/0               trust
    host    all             all             ::0/0                   trust
    host    replication     postgres    0.0.0.0/0       trust"""
        else:
            hba_auth = """
    local   all             postgres                                trust
    local   all             all                                     peer
    host    all             all             0.0.0.0/0               trust
    host    all             all             ::0/0                   trust"""
        self.edit_pg_hba_conf(hba_auth, remote=remote, host=host)
        cmd = "sudo -u postgres psql -c " \
            "\"ALTER SYSTEM SET listen_addresses to \'*\';\""
        command_executor(cmd, remote, host,
                         login=REMOTE_ROOT, password=REMOTE_ROOT_PASSWORD)
        self.manage_psql("restart", remote=remote, host=host)

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
        :return: string
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
        # FIXME we need to change shared_libraries to
        # shared_preload libraries, and if we have
        # multiple extensions we need to write it
        # without quotes (for this situation
        # we need to change set_option() method
        loaded_extensions = self.get_option('shared_libraries')
        if extension_name not in ['plperlu', 'pltcl', 'plpython2u', 'plperl']:
            if loaded_extensions is None:
                extensions = extension_name
            else:
                extensions = loaded_extensions + ',' + extension_name
            self.set_option('shared_preload_libraries', extensions)

        conn = psycopg2.connect(self.connstring)
        cursor = conn.cursor()
        cursor.execute("CREATE EXTENSION IF NOT EXISTS %s" % extension_name)
        conn.commit()
        cursor.close()
        conn.close()

    def execute_sql(self, sql_query, conn="host=localhost user=postgres"):
        """Execute sql query

        :param conn: connection string
        :param sql_query: string sql query
        :return: list of tuples
        """
        conn = psycopg2.connect(conn)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        try:
            cursor.execute(sql_query)
        except psycopg2.Error as e:
            print e.pgerror
            raise Exception("SQL execution failed")
        conn.commit()

        response = None
        if cursor.description is not None:
            response = cursor.fetchall()
        cursor.close()

        return response

    def minor_upgrade(self, minor_version):
        """ Update to one version up
         Add check

        :param minor_version: version to upgrade
        :return:
        """
        if self.minor_version > minor_version:
            print("You try to downgrade. This action deprecated")
            sys.exit(1)

        # Delete old repo file
        # Add new repo file
        # Install new packages
        # Do initdb if needed
        pass

    def minor_upgrade_to_lates_version(self):
        """Upgrade to latest minor version.

        :return:
        """
        # Delete old repo file
        # Add new repo file
        # Install new packages
        # Do initdb if needed

    @property
    def get_current_minor_version(self):
        """ Get current minor version

        :return:
        """
        self.minor_version = self.execute_sql(
            "SELECT pgpro_version()")[0][0].split()[1]
        return self.minor_version

    # TODO add editing repo file for update

    def major_upgrade(self, name, version, edition, milestone,
                      branch, windows=False, skip_install_psql=False):
        """

        :param name: product name to upgrade
        :param version: version to upgrade
        :param edition: edition to upgrade
        :param milestone: milestone to upgrade can be beta or nothing
                           (release version)
        :param branch: string package branch
        :param windows: bool, if you need to install on windows set True
        :param skip_install_psql: bool, if you not install psql set to True
        :return:
        """
        pass

    @property
    def get_instance_ip(self):
        """Get instance ip

        :return: string
        """
        return self.node_ip

    @property
    def get_pgpro_version(self):
        """ Get pgpro_version

        :return: string with output of pgpro_version() output
        """
        if self.cluster:
            connstring = "host=%s user=postgres" % self.node_ip
        else:
            connstring = "host=localhost user=postgres"
        conn = psycopg2.connect(connstring)
        cursor = conn.cursor()
        cursor.execute("SELECT pgpro_version()")
        self.pgpro_version = cursor.fetchall()[0][0]
        return self.pgpro_version

    @property
    def get_version(self):
        """Get postgresql version for postgrespro instance.
         Postgrespro always inherited from postgresql
        :return: string
        """
        if self.cluster:
            connstring = "host=%s user=postgres" % self.node_ip
        else:
            connstring = "host=localhost user=postgres"
        conn = psycopg2.connect(connstring)
        cursor = conn.cursor()
        cursor.execute("SELECT version()")
        self.postgresql_version = cursor.fetchall()[0][0]
        return self.postgresql_version

    @property
    def get_edition(self):
        """Get postgrespro edition.
        It can be standard, enterprise, standard-certified and
         enterprise-certified

        :return: string
        """
        if self.cluster:
            connstring = "host=%s user=postgres" % self.node_ip
        else:
            connstring = "host=localhost user=postgres"
        conn = psycopg2.connect(connstring)
        cursor = conn.cursor()
        cursor.execute("SELECT pgpro_edition()")
        self.pgpro_edition = cursor.fetchall()[0][0]
        return self.pgpro_edition

    def get_available_minor_updates(self):
        """Check current minor version and get all available updates

        :return: list with minor version
        """
        current_minor_version = self.minor_version
        minor_versions = self.get_pgpro_minor_versions(
            self.version, self.edition)
        position = int
        for version in minor_versions:
            if current_minor_version in version:
                position = minor_versions.index(version)
        return minor_versions[position + 1:]

    def move_data_direcory(self, version, edition="standard",
                           remote=False, host=None):
        """Move data directory from one folder to another

        :return: int
        """
        major = "9"
        minor = version.split(".")[1]
        distro = get_distro()[0]
        self.kill_postgres_instance()
        if distro in RPM_BASED:
            if edition == "standard":
                cmd = "cp -r /var/lib/pgsql/%s.%s/data/" \
                    " /var/lib/pgpro/%s.%s/" % (major, minor, major, minor)
                command_executor(cmd)
                cmd = "chown -R postgres:postgres" \
                    " /var/lib/pgpro/%s.%s/data" % (major, minor)
                return command_executor(cmd, remote, host,
                                        REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            elif edition == "ee":
                cmd = "cp -r /var/lib/pgsql/%s.%s/data/" \
                    " /var/lib/pgproee/%s.%s/" % (major, minor, major, minor)
                command_executor(cmd)
                cmd = "chown -R postgres:postgres " \
                    "/var/lib/pgproee/%s.%s/data" % (major, minor)
                return command_executor(cmd, remote, host,
                                        REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    def kill_postgres_instance(self):
        """
        Method returns PID of the postmaster process.

        :return: int number with process identificator
        """
        conn = psycopg2.connect(self.connstring)
        pid = conn.get_backend_pid()
        ppid = psutil.Process(pid).ppid()
        conn.close()
        cmd = "kill -9 %s" % ppid
        return command_executor(cmd)

    def get_pgpro_minor_versions(self, major_version='9.6',
                                 edition='standard'):
        """ Get all minor versions of pgpro

        :return: list with minor version
        """
        # TODO add dependencie from distribution because
        #  not for all dists we have all updates
        minor_versions = []
        if edition == 'standard':
            page = urllib.urlopen(PGPRO_ARCHIVE_STANDARD).read()
        elif edition == 'ee':
            page = urllib.urlopen(PGPRO_ARCHIVE_ENTERPRISE).read()
        versions = re.findall('href=[\'"]?([^\'" >]+)/', page)
        for version in versions:
            if major_version in version and "9.6.4.1" not in version:
                minor_versions.append(version)
        return minor_versions

    def get_pgpro_earliest_minor_version(self,
                                         major_version='9.6',
                                         edition="standard"):
        """ Get earliest minor version
        :return string with earliest minor version
        """
        versions = self.get_pgpro_minor_versions(major_version, edition)
        versions.sort()
        return versions[0]
