import grp
import os
import platform
import psycopg2
import pytest
import pwd
import subprocess

from helpers.pginstall import DEB_BASED
from helpers.pginstall import RPM_BASED
from helpers.os_helpers import pg_bindir
from helpers.sql_helpers import execute
from tests.settings import TMP_DIR


class TestPgprobackup():
    # TODO add restore from backup for all test cases

    DISTRO = platform.linux_distribution()[0]

    PG_HBA_CONFIG = """
local   replication     all                                     trust
local   all             all                                     trust
host    all             all             0.0.0.0/0               trust
host    all             all             ::0/0                   trust"""

    def parse_pgprobackup_show_command_out(self, out):
        """ Parse show command output for pgprobackup feature

        :param out:
        :return:
        """
        return dict(v.split("=") for v in out.replace('\t', ' ').strip().split('\n') if v.strip() and "=" in v)

    def install_pgprobackup(self, version, edition):
        """Install pgprobackup from  deb or rpm package

        :param version: postgrespro version
        :param edition: can be standard or ee
        :return:
        """

        major = version.split(".")[0]
        minor = version.split(".")[1]

        if self.DISTRO in RPM_BASED or self.DISTRO == "ALT Linux ":
            if edition == 'ee':
                service_name = "postgrespro-enterprise%s%s-pg_probackup" % (major, minor)
            elif edition == 'standard':
                service_name = "postgrespro%s%s-pg-probackup" % (major, minor)
            subprocess.call(['yum', 'install', service_name, '-y'])

        elif self.DISTRO in DEB_BASED:
            service_name = "postgrespro-pg-probackup-%s.%s" % (major, minor)
            subprocess.call(["apt-get", "update", "-y"])
            subprocess.call(["apt-get", "install", service_name, "libpq-dev", "-y"])

    @staticmethod
    def create_backup_directory():
        """Create new  directory for tablespace
        :return: str path to tablespace
        """
        backup_path = os.path.join(TMP_DIR, 'backup')
        os.mkdir(backup_path)
        os.chown(backup_path,
                 pwd.getpwnam("postgres").pw_uid,
                 grp.getgrnam("postgres").gr_gid)
        os.environ["BACKUP_PATH"] = backup_path
        return backup_path

    def execute_pg_probackup(self, *options):
        """

        :param options: strings with params for pg_probackup
        :return: output of command execution
        """
        cmd = ["%s/pg_probackup" % pg_bindir()] + list(options)
        return subprocess.check_output(cmd)

    @pytest.mark.test_install_pgprobackup
    def test_install_pgprobackup(self, install_postgres):
        """ Install pg_probackup utility and configure postgresql for running pg_probackup.
        Scenario:
        1. Install pg_probackup
        2. Check version function
        3. Check help function
        """

        # Step 1
        self.install_pgprobackup(install_postgres.version, install_postgres.edition)
        # Step 2
        assert self.execute_pg_probackup("--version") is not None
        # Step 3
        assert self.execute_pg_probackup("--help") is not None

    @pytest.mark.test_pgprobackup_compression_continious_backup
    def test_pgprobackup_compression_continious_backup(self, install_postgres):
        """Test pg_probackup with compression feature and full continious backup
        Scenario:
        1. Create backup dir
        2. Set data dir to environment variables
        3. Init backup dir
        4. Set options for pg_probackup
        5. Create tablespace with compression
        6. Create table in compression tablespace
        7. Edit pg_hba_config
        8. Make full backup
        9. Get backup id
        10. Check that backup status is OK
        11. Check that backup validation is OK

        """
        # Step 1
        backup_dir = self.create_backup_directory()
        # Step 2
        os.environ["PGDATA"] = install_postgres.get_option('data_directory')
        # Step 3
        install_postgres.edit_pg_hba_conf(self.PG_HBA_CONFIG)
        install_postgres.manage_psql('restart')
        # Step 4
        self.execute_pg_probackup("init")
        for root, dirs, files in os.walk(backup_dir):
            for d in dirs:
                os.chown(os.path.join(root, d), pwd.getpwnam("postgres").pw_uid, grp.getgrnam("postgres").gr_gid)
            for f in files:
                os.chown(os.path.join(root, f), pwd.getpwnam("postgres").pw_uid, grp.getgrnam("postgres").gr_gid)
        # Step 5
        install_postgres.set_option("ptrack_enable", "on")
        install_postgres.set_option("wal_level", "archive")
        install_postgres.set_option("archive_mode", "on")
        install_postgres.set_option("archive_command",
                                    "test ! -f {0}/wal/%f && cp %p {1}/wal/%f".format(backup_dir, backup_dir))
        install_postgres.set_option("cfs_gc_workers", "0")
        # Step 6
        tablespace_path = os.path.join(TMP_DIR, 'pgprobackup_compression')
        os.mkdir(tablespace_path)
        os.chown(tablespace_path,
                 pwd.getpwnam("postgres").pw_uid,
                 grp.getgrnam("postgres").gr_gid)
        conn = psycopg2.connect(install_postgres.connstring)
        execute(conn,
                'CREATE TABLESPACE pgprobackup_compression LOCATION \'%s\' WITH(compression = true);' % tablespace_path)
        # Step 7
        execute(conn,
                'CREATE TABLE tbl TABLESPACE pgprobackup_compression'
                ' AS SELECT i, md5(random()::text) FROM generate_series(0,1e05) AS i;')
        # Step 8
        self.execute_pg_probackup("-d", "postgres", "-b", "full", "backup", "-U", "postgres")
        # Step 9
        # Get last backup id and get out for show command with this backup
        pgprobackup_show = subprocess.Popen(["%s/pg_probackup" % pg_bindir(), "show", "-U", "postgres"],
                                            stdout=subprocess.PIPE)
        awk_backup_id = subprocess.Popen(["awk", "FNR == 4 {print $1}"], stdin=pgprobackup_show.stdout,
                                         stdout=subprocess.PIPE)
        backup_id = awk_backup_id.communicate()[0].strip()
        pgprobackup_show.stdout.close()
        # Step 10
        backup_info = self.parse_pgprobackup_show_command_out(self.execute_pg_probackup("show", backup_id))
        assert backup_info['STATUS'] == 'OK'
        # Step 11
        self.execute_pg_probackup("validate", backup_id)
