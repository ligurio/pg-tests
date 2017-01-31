import grp
import os
import psutil
import pwd
import random
import time


import psycopg2
import pytest
from multiprocessing import Process
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from helpers.sql_helpers import create_test_table
from tests.settings import TMP_DIR


class TestCompression():

    @staticmethod
    def set_default_tablespace(db_name, tbs_name):
        """

        :param tbs_name: string - tablespace name
        :param db_name: database name as string
        :return:
        """
        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        cursor.execute("ALTER DATABASE {0} SET default_tablespace TO {1}".format(db_name, tbs_name))

    @staticmethod
    def get_directory_size(start_path):
        """ Get directory size recursively

        :param start_path: directory for start
        :return: total size of directory in bytes
        """
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(start_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        #  TODO return in Mb
        return total_size

    @staticmethod
    def get_filenames(directory):
        """
        This function will return the file names in a directory
        tree by walking the tree either top-down or bottom-up. For each
        directory in the tree rooted at directory top (including top itself),
        it yields a 3-tuple (dirpath, dirnames, filenames).
        """
        for root, directories, files in os.walk(directory):
            for filename in files:
                fn, ext = os.path.splitext(filename)
                yield ext

    @staticmethod
    def create_tablespace_directory():
        """Create new  directory for tablespace
        :return: str path to tablespace
        """
        tablespace_catalog = 'tablespace-' + str(random.randint(0, 100))
        tablespace_path = os.path.join(TMP_DIR, tablespace_catalog)
        os.mkdir(tablespace_path)
        os.chown(tablespace_path,
                 pwd.getpwnam("postgres").pw_uid,
                 grp.getgrnam("postgres").gr_gid)
        return tablespace_path

    def create_tablespace(self, tablespace_name, compression=False):
        """ Create tablespace

        :return:
        """
        tablespace_location = self.create_tablespace_directory()
        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        # TODO add check that PGPRO edition is enterprise
        if compression:
            cursor.execute('CREATE TABLESPACE {0} LOCATION \'{1}\' WITH (compression=true);'.format(
                tablespace_name,
                tablespace_location))
        else:
            cursor.execute('CREATE TABLESPACE {0} LOCATION \'{1}\';'.format(tablespace_name, tablespace_location))
        return tablespace_location

    @pytest.mark.test_compression_standalone_positive
    @pytest.mark.usefixtures('create_table')
    @pytest.mark.parametrize('create_table', [('pgbench', '20')], indirect=True)
    def test_compression_standalone_positive(self, install_postgres):
        """ Test for compression feature.
        Scenario:
        1. Create tablespace with compression
        2. Save size of created tables by fixture in file system (count and size of files)
        3. Run data generator for tablespace with compression
        4. Save size of table with compression
        5. Check that files for table in tablespace without compression > that files in tablespace with compression
        6. Check tablespace folder for files with *.cfm extension
        """
        # Step 1
        compression_files_directory = self.create_tablespace('compression', compression=True)
        # Step 2
        data_size_without_compression = self.get_directory_size(install_postgres.get_option('data_directory'))
        # Step 3
        print(data_size_without_compression)
        self.set_default_tablespace('postgres', 'compression')
        install_postgres.manage_psql(install_postgres.version, 'restart')
        create_test_table(size='20', schema='pgbench')
        # Step 4
        data_size_with_compression = self.get_directory_size(install_postgres.get_option('data_directory'))
        print(data_size_with_compression)
        print(compression_files_directory)
        # Step 5
        assert data_size_with_compression < data_size_without_compression
        # Step 6
        compression_files = self.get_filenames(compression_files_directory)
        assert '.cfm' in compression_files

    @pytest.mark.test_compression_unlogged_tables
    def test_compression_unlogged_tables(self, install_postgres):
        """ Test for compression feature.
        Scenario:
        1. Create tablespace with compression
        2. Run pgbench (unlogged schema) for tablespace with compression
        3. Check tablespace folder for files with *.cfm extension
        """
        # Step 1
        compression_files_directory = self.create_tablespace('compression_unlogged_tables', compression=True)
        print compression_files_directory
        # Step 2
        self.set_default_tablespace('postgres', 'compression_unlogged_tables')
        install_postgres.manage_psql(install_postgres.version, 'restart')
        create_test_table(size='20', schema='pgbench_unlogged')
        # Step 3
        compression_files = self.get_filenames(compression_files_directory)
        assert '.cfm' in compression_files

    @pytest.mark.test_compression_negative
    def test_compression_negative(self, install_postgres):
        """ Test for compression feature.
        Scenario:
        1. Create tablespace with compression
        2. Run pgbench for tablespace with compression and kill postgres process
        3. Run postgres process and check that postgress is successfully runninng
        4. Check that cfm files created
        5. Check that pgbench tables don't created
        """
        # Step 1
        compression_files_directory = self.create_tablespace('compression_negative', compression=True)
        print(compression_files_directory)
        self.set_default_tablespace('postgres', 'compression_negative')
        postgres_pid = install_postgres.get_postmaster_pid()
        print(postgres_pid)
        # Step 2
        create_table_process = Process(target=create_test_table, args=('20', 'pgbench',))
        create_table_process.start()
        time.sleep(10)
        # Step 3
        if create_table_process.is_alive():
            process = psutil.Process(postgres_pid)
            process.kill()
        compression_files = self.get_filenames(compression_files_directory)
        # Step 4
        # Files for tables created but no any table was created because transaction was corruped
        assert '.cfm' in compression_files
        install_postgres.manage_psql(install_postgres.version, 'start')
        # Step 5
        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pg_tables WHERE tablespace=\'compression_negative\';")
        assert len(cursor.fetchall()) == 0
