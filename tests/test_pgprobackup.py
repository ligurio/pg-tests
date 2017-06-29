import datetime
import grp
import os
import platform
import psycopg2
import pytest
import pwd
import subprocess

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
    def test_install_pgprobackup(self):
        """ Install pg_probackup utility and configure postgresql for running pg_probackup.
        Scenario:
        1. Check version function
        2. Check help function
        """
        # Step 1
        assert self.execute_pg_probackup("--version") is not None
        # Step 2
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

    @pytest.mark.test_pgprobackup_retention_policy_options
    def test_pgprobackup_retention_policy_options(self):
        """Scenario
        1. Create 3 backups
        2. Set option redundancy to 1 backup and run purge
        3. Check that only one backup must saved after purge
        4. Up system date for 3 days
        5. Create 2 backups
        6. Set option window to 1 and run purge
        7. Check that only one backup was saved
        8. Create 2 backups
        9. Up time for 2 days
        10. Run purge with redundancy=2 and window=1
        11. Check that saved 2 backups
        """
        # Step 1
        for i in range(3):
            self.execute_pg_probackup("-d", "postgres", "-b", "full", "backup", "-U", "postgres")
        # Step 2
        self.execute_pg_probackup("retention", "--redundancy=1", "purge")
        # Step 3
        pgprobackup_show = subprocess.Popen(["%s/pg_probackup" % pg_bindir(), "show", "-U", "postgres"],
                                            stdout=subprocess.PIPE)
        awk_backup_ids = subprocess.Popen(["awk", "NR > 3 {print $1}"], stdin=pgprobackup_show.stdout,
                                          stdout=subprocess.PIPE)
        assert len(awk_backup_ids.communicate()[0].strip().split()) == 1
        # Step 4
        for i in range(2):
            self.execute_pg_probackup("-d", "postgres", "-b", "full", "backup", "-U", "postgres")
        # Step 5
        new_time = datetime.datetime.now() + datetime.timedelta(days=3)
        subprocess.check_output(["sudo", "date", "-s", str(new_time)])
        # Step 6
        self.execute_pg_probackup("retention", "--window=1", "purge")
        # Step 7
        pgprobackup_show = subprocess.Popen(["%s/pg_probackup" % pg_bindir(), "show", "-U", "postgres"],
                                            stdout=subprocess.PIPE)
        awk_backup_ids = subprocess.Popen(["awk", "NR > 3 {print $1}"], stdin=pgprobackup_show.stdout,
                                          stdout=subprocess.PIPE)
        assert len(awk_backup_ids.communicate()[0].strip().split()) == 1
        # Step 8
        for i in range(2):
            self.execute_pg_probackup("-d", "postgres", "-b", "full", "backup", "-U", "postgres")
        # Step 9
        new_time = datetime.datetime.now() + datetime.timedelta(days=3)
        subprocess.check_output(["sudo", "date", "-s", str(new_time)])

        # Step 10
        self.execute_pg_probackup("retention", "--window=1", "--redundancy=2", "purge")
        # Step 11
        pgprobackup_show = subprocess.Popen(["%s/pg_probackup" % pg_bindir(), "show", "-U", "postgres"],
                                            stdout=subprocess.PIPE)
        awk_backup_ids = subprocess.Popen(["awk", "NR > 3 {print $1}"], stdin=pgprobackup_show.stdout,
                                          stdout=subprocess.PIPE)
        assert len(awk_backup_ids.communicate()[0].strip().split()) == 2
