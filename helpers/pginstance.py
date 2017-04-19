import os
import psutil
import psycopg2

from helpers.pginstall import package_mgmt
from helpers.pginstall import setup_repo
from helpers.sql_helpers import pg_get_option
from helpers.sql_helpers import pg_set_option
from helpers.sql_helpers import pg_check_option
from helpers.sql_helpers import pg_manage_psql
from helpers.sql_helpers import pg_start_script_name
from helpers.pginstall import RPM_BASED

from helpers.utils import command_executor
from helpers.utils import get_distro
from helpers.utils import REMOTE_ROOT
from helpers.utils import REMOTE_ROOT_PASSWORD
from helpers.utils import write_file


class PgInstance:
    PG_PASSWORD = 'password'

    def __init__(self, version, milestone, name, edition, build, skip_install,
                 environment_info=None, cluster_name=None, windows=False):
        self.version = version
        self.milestone = milestone
        self.name = name
        self.edition = edition
        self.build = build
        self.skip_install = skip_install
        self.connstring = "host=localhost user=postgres"
        self.windows = windows
        if cluster_name is None and not skip_install:
            self.skip_install = False
            self.install_product(name, version, edition, milestone, build)
        elif not skip_install and windows:
            self.skip_install = False
            self.install_product(name, version, edition, milestone, build, windows=self.windows)
        elif not skip_install:
            self.environment_info = environment_info
            self.cluster_name = cluster_name
            self.install_product_cluster(environment_info, cluster_name, name=name,
                                         version=version, edition=edition, milestone=milestone,
                                         build=build)

    def install_product(self, name, version, edition, milestone, build, windows=False):
        """ Install product
        Parameter: Product name: postgrespro, postgresql
        Parameter: Product version: 9.5, 9.6 etc
        Parameter: Product editions (postgrespro only): standard, ee
        Parameter: Product milestone (postgrespro only): beta
        """
        if windows:
            setup_repo(name=name, version=version, edition=edition, milestone=milestone, build=build)
            package_mgmt(name=name, version=version, edition=edition, milestone=milestone, build=build)
        else:
            setup_repo(name=name, version=version, edition=edition, milestone=milestone, build=build)
            package_mgmt(name=name, version=version, edition=edition, milestone=milestone, build=build)
            self.setup_psql(name, version, edition, milestone, build)

        return {'name': name,
                'version': version,
                'edition': edition,
                'milestone': milestone}

    def install_product_cluster(self, cluster_info, cluster_name, name, version, edition, milestone, build):
        if cluster_name in cluster_info.keys():
            for node in cluster_info[cluster_name]['nodes']:
                setup_repo(remote=True, host=node['ip'], version=version, milestone=milestone, name=name,
                           edition=edition, build=build)
                package_mgmt(remote=True, host=node['ip'], version=version, milestone=milestone, name=name,
                             edition=edition, build=build)
                self.setup_psql(remote=True, host=node['ip'], name=name, version=version, edition=edition,
                                milestone=milestone, build=build)
        return {'name': name,
                'version': version,
                'edition': edition,
                'milestone': milestone}

    def start_script_name(self, remote=False, host=None):

        return pg_start_script_name(self.name, self.edition, self.version, distro=get_distro(remote, host)[0])

    def manage_psql(self, action, data_dir=None, remote=False, host=None):
        """ Manage Postgres instance
        :param action: start, restart, stop etc
        :param init: Initialization before a first start
        :return:
        """

        if self.skip_install:
            return pg_manage_psql(action, data_dir)
        else:
            return pg_manage_psql(action, data_dir, self.start_script_name(remote, host), remote, host)

    def edit_pg_hba_conf(self, pg_hba_config, remote=False, host=None):
        """Rewrite pg_hba.conf

        :param pg_hba_config: string with pg_hba.conf content
        """
        cmd = "sudo -u postgres psql -t -P format=unaligned -c \"SHOW hba_file;\""
        hba_file = ""
        if remote:
            hba_file = command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)[1]
        else:
            hba_file = command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD, stdout=True)
        print "Path to hba_file is", hba_file
        write_file(hba_file, pg_hba_config, remote, host)
        cmd = "chown postgres:postgres %s" % hba_file
        return command_executor(cmd, remote, host, REMOTE_ROOT, REMOTE_ROOT_PASSWORD)

    def setup_psql(self, name, version, edition, milestone, build, remote=False, host=None):

        major = version.split(".")[0]
        minor = version.split(".")[1]

        print "Setup PostgreSQL service"

        distro = get_distro(remote, host)[0]
        if distro in RPM_BASED or distro == "ALT Linux ":
            self.manage_psql("initdb", remote=remote, host=host)
        self.manage_psql("start", remote=remote, host=host)

        if remote:
            cmd = "export PATH=$PATH:/usr/pgsql-%s.%s/bin/" % (major, minor)
            command_executor(cmd, remote, host, login=REMOTE_ROOT, password=REMOTE_ROOT_PASSWORD)
        else:
            os.environ['PATH'] += ":/usr/pgsql-%s.%s/bin/" % (major, minor)
        cmd = "sudo -u postgres psql -c \"ALTER USER postgres WITH PASSWORD \'%s\';\"" % self.PG_PASSWORD
        command_executor(cmd, remote, host, login=REMOTE_ROOT, password=REMOTE_ROOT_PASSWORD)

        hba_auth = """
    local   all             all                                     peer
    host    all             all             0.0.0.0/0               trust
    host    all             all             ::0/0                   trust"""
        self.edit_pg_hba_conf(hba_auth, remote=remote, host=host)
        cmd = "sudo -u postgres psql -c \"ALTER SYSTEM SET listen_addresses to \'*\';\""
        command_executor(cmd, remote, host, login=REMOTE_ROOT, password=REMOTE_ROOT_PASSWORD)
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
