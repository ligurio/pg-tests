import shutil
import json
import os
import tempfile
import pytest
import platform
import subprocess
import re
import sys
import allure
from helpers.utils import urlretrieve
import distro
try:
    from bs4 import BeautifulSoup
except ImportError:  # py2compat
    from BeautifulSoup import BeautifulSoup
import tarfile

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall, PGPRO_DEV_SOURCES_BASE,\
    PGPRO_ARCHIVE_SOURCES_BASE, PGPRO_STABLE_SOURCES_BASE
from helpers.utils import download_dump, diff_dbs

tempdir = tempfile.gettempdir()


truncate_unlogged_sql = """
DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOR table_name IN
        SELECT '"' || n.nspname || '"."' || c.relname || '"' AS tab
        FROM pg_catalog.pg_class c, pg_catalog.pg_namespace n
        WHERE
            c.relnamespace = n.oid AND c.relpersistence = 'u'
            AND c.relkind='r' order by c.oid
    LOOP
        EXECUTE 'TRUNCATE TABLE ' || table_name || ' CASCADE';
    END LOOP;
END;
$$;
"""


@pytest.mark.feature_pgprobackup
class TestPgprobackup():
    system = platform.system()

    bindir = ''

    def fix_permissions(self, dir):
        if self.system != 'Windows':
            import pwd
            import grp
            os.chown(dir,
                     pwd.getpwnam("postgres").pw_uid,
                     grp.getgrnam("postgres").gr_gid)
            for root, dirs, files in os.walk(dir):
                for d in dirs:
                    os.chown(os.path.join(root, d),
                             pwd.getpwnam("postgres").pw_uid,
                             grp.getgrnam("postgres").gr_gid)
                for f in files:
                    os.chown(os.path.join(root, f),
                             pwd.getpwnam("postgres").pw_uid,
                             grp.getgrnam("postgres").gr_gid)
        else:
            # Grant Full Access to "Network Service" and Users
            subprocess.check_call(
                'icacls "%s" /grant *S-1-5-32-545:(OI)(CI)F /T' % dir,
                shell=True)
            subprocess.check_call(
                'icacls "%s" /grant *S-1-5-20:(OI)(CI)F /T' % dir,
                shell=True)
            subprocess.check_call(
                r'icacls "%s\*" /grant *S-1-5-32-545:(OI)(CI)F /T' % dir,
                shell=True)
            subprocess.check_call(
                r'icacls "%s\*" /grant *S-1-5-20:(OI)(CI)F /T' % dir,
                shell=True)

    def execute_pg_probackup(self, *options):
        """
        :param options: strings with params for pg_probackup
        :return: output of command execution
        """
        cmd = '%s"%spg_probackup" %s' % (
            self.pginst.pg_sudo_cmd, self.bindir, " ".join(list(options)))
        ret = subprocess.check_output(cmd, shell=True).decode()
        return ret

    def download_source(self):
        if self.pginst.milestone == 'alpha':
            baseurl = PGPRO_DEV_SOURCES_BASE
        elif self.pginst.milestone == 'beta':
            baseurl = PGPRO_STABLE_SOURCES_BASE
        else:
            baseurl = PGPRO_ARCHIVE_SOURCES_BASE

        tar_href = 'pg_probackup-%s.tar.gz' % self.version
        tar_file = os.path.join(tempdir, tar_href)
        urlretrieve(baseurl + '/' + tar_href, tar_file)
        return tar_file

    @pytest.mark.test_install
    def test_install(self, request):
        """ Install pg_probackup utility and configure postgresql
             for running pg_probackup.
        Scenario:
        1. Install postgrespro version
        2. Check version function
        3. Check help function
        """
        if self.system == 'Linux':
            dist = " ".join(distro.linux_distribution()[0:2])
        elif self.system == 'Windows':
            dist = 'Windows'
        else:
            raise Exception("OS %s is not supported." % self.system)

        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        milestone = request.config.getoption('--product_milestone')
        target = request.config.getoption('--target')
        product_info = " ".join([dist, name, edition, version])
        tag_mark = allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        branch = request.config.getoption('--branch')

        if name != 'postgrespro' or edition == '1c':
            print("PgProBackup test is only for postgrespro std and ent.")
            return

        # Step 1
        self.pginst = PgInstall(product=name, edition=edition, version=version,
                                milestone=milestone, branch=branch,
                                windows=(self.system == 'Windows'))

        self.pginst.setup_repo()
        if self.system != 'Windows':
            self.pginst.install_full()
            self.pginst.initdb_start()
        else:
            self.pginst.install_postgres_win()

        self.bindir = self.pginst.get_bin_path() + os.sep
        print('Bindir is %s' % self.bindir)

        self.pginst.load_shared_libraries(restart_service=True)

        request.cls.pginst = self.pginst

        # Step 2
        assert self.execute_pg_probackup("--help")
        ver = self.execute_pg_probackup("--version")
        print('Version is %s' % ver)
        vere = re.search(r'[^(]+\s([0-9.]+)\s.*', ver)
        self.version = vere.group(1)
        assert self.version
        request.cls.version = self.version

    @pytest.mark.test_pgprobackup_internal
    def test_pgprobackup_internal(self, request):
        self.pginst = request.cls.pginst
        if self.pginst.product != 'postgrespro' or self.pginst.edition == '1c':
            print("PgProBackup test is only for postgrespro std and ent.")
            return
        # PBCKP-103
        if sys.version_info > (3, 0):
            print("Only 2 python temporary supported")
            return
        if self.system == 'Windows':
            print("Only linuxes temporary supported")
            return
        self.version = request.cls.version
        self.bindir = self.pginst.get_bin_path() + os.sep
        os.environ['PATH'] = os.environ['PATH'] + ':' + self.bindir
        tar_file = self.download_source()
        print(tar_file)
        tar = tarfile.open(tar_file, "r:gz")
        tar.extractall(tempdir)
        tar.close()
        dir = '.'.join(tar_file.split('.')[:-2])
        self.fix_permissions(dir)
        subprocess.check_call('pip install testgres==1.8.2')
        cmd = "%s sh -c 'PG_CONFIG=pg_config LANG=C" \
              " PG_PROBACKUP_TEST_BASIC=ON python -m unittest -v tests'" \
              % self.pginst.pg_sudo_cmd
        print(subprocess.check_output(cmd, cwd=dir, shell=True).decode())
        print("OK")

    @pytest.mark.test_pgprobackup_simple_backup_restore
    def test_pgprobackup_simple_backup_restore(self, request):
        """Test pg_probackup with compression feature
            and full continous backup
        Scenario:
        1. Create backup dir
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
        self.pginst = request.cls.pginst
        if self.pginst.product != 'postgrespro' or self.pginst.edition == '1c':
            print("PgProBackup test is only for postgrespro std and ent.")
            return
        self.bindir = self.pginst.get_bin_path() + os.sep
        # Step 1
        backup_dir = os.path.join(tempdir, 'backup')
        os.mkdir(backup_dir)
        self.fix_permissions(backup_dir)
        # Step 3
        self.execute_pg_probackup("init", "-B", '"%s"' % backup_dir)
        self.execute_pg_probackup("add-instance", "-B", '"%s"' % backup_dir,
                                  "-D", '"%s"' %
                                  self.pginst.get_default_datadir(),
                                  "--instance", "main")
        # Step 5
        if self.pginst.edition == 'ent':
            self.pginst.exec_psql("ALTER SYSTEM SET cfs_gc_workers TO '0'")
        self.pginst.exec_psql("ALTER SYSTEM SET wal_level TO 'replica'")
        dump_file_name = download_dump(self.pginst.product,
                                       self.pginst.edition,
                                       self.pginst.version, tempdir)
        with open(os.path.join(tempdir, 'load-dump.log'), 'wb') as out:
            self.pginst.exec_psql_file(dump_file_name, '-q',
                                       stdout=out)
        # Step 6
        tablespace_path = os.path.join(tempdir, 'pgprobackup')
        os.mkdir(tablespace_path)
        self.fix_permissions(tablespace_path)
        create_command = 'CREATE TABLESPACE pgprobackup ' \
                         'LOCATION \'%s\'%s;' % \
                         (tablespace_path,
                          ' WITH(compression = true)' if
                          self.pginst.edition == 'ent' else '')

        self.pginst.exec_psql(create_command)
        # Step 7
        self.pginst.exec_psql(
            "CREATE TABLE tbl TABLESPACE pgprobackup"
            " AS SELECT i, rpad('',30,'a')"
            " FROM generate_series(0,1000000) AS i;")

        before_backup_file = os.path.join(tempdir, 'before.sql')
        self.pginst.do_in_all_dbs(truncate_unlogged_sql)
        self.pginst.exec_client_bin('pg_dumpall', '-f "%s"' %
                                    before_backup_file)

        # Step 8
        self.execute_pg_probackup("backup", "-b", "full", "-B",
                                  '"%s"' % backup_dir, "-d", "postgres",
                                  "-U", "postgres", "--instance",
                                  "main", "--stream")
        # Step 9
        # Get last backup id and get out for show command with this backup
        pgprobackup_show = json.loads(
            self.execute_pg_probackup("show", "-B", '"%s"' % backup_dir, "-U",
                                      "postgres", "--format=json"))
        backup_id = pgprobackup_show[0]['backups'][0]['id']
        # Step 10
        assert pgprobackup_show[0]['backups'][0]['status'] == 'OK'
        # Step 11
        print("Validating backup %s" % backup_id)
        self.execute_pg_probackup("validate", "-i", backup_id, "-B",
                                  '"%s"' % backup_dir, '--instance', 'main')

        # Step 12
        print("Drop data and restore backup")
        self.pginst.stop_service()
        self.pginst.remove_data()
        shutil.rmtree(tablespace_path)

        self.execute_pg_probackup("restore", "-i", backup_id, "-B",
                                  '"%s"' % backup_dir, '--instance', 'main')
        # PBCKP-91
        if self.system == 'Windows':
            self.fix_permissions(self.pginst.get_default_datadir())
            self.fix_permissions(tablespace_path)
        self.pginst.start_service()
        after_backup_file = os.path.join(tempdir, 'after.sql')
        self.pginst.exec_client_bin('pg_dumpall', '-f "%s"' %
                                    after_backup_file)
        diff_dbs(before_backup_file, after_backup_file,
                 os.path.join(tempdir, 'diff.sql'))
