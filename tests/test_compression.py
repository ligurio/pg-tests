import grp
import os
import platform
import distro
import psutil
import pwd
import random
import time
import psycopg2
import pytest

from allure_commons.types import LabelType
from multiprocessing import Process
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from helpers.os_helpers import load_pgbench
from helpers.sql_helpers import drop_test_table
from helpers.sql_helpers import create_test_table
from tests.settings import TMP_DIR


@pytest.mark.core_functional
@pytest.mark.compression
class TestCompression():
    dist = ""
    if platform.system() == 'Linux':
        dist = " ".join(distro.linux_distribution()[0:2])
    elif platform.system() == 'Windows':
        dist = 'Windows'
    else:
        print("Unknown Distro")

    PGBENCH_SCHEMA_UNLOGGED = """

    CREATE UNLOGGED TABLE pgbench_branches_unlogged(
      bid SERIAL PRIMARY KEY,
      bbalance INTEGER NOT NULL,
      filler CHAR(88) NOT NULL
    );
    CREATE UNLOGGED TABLE pgbench_tellers_unlogged(
      tid SERIAL PRIMARY KEY,
      bid INTEGER NOT NULL REFERENCES pgbench_branches_unlogged,
      tbalance INTEGER NOT NULL,
      filler CHAR(84) NOT NULL
    );
    CREATE UNLOGGED TABLE pgbench_accounts_unlogged(
      aid BIGSERIAL PRIMARY KEY,
      bid INTEGER NOT NULL REFERENCES pgbench_branches_unlogged,
      abalance INTEGER NOT NULL,
      filler CHAR(84) NOT NULL
    );
    CREATE UNLOGGED TABLE pgbench_history_unlogged(
      tid INTEGER NOT NULL REFERENCES pgbench_tellers_unlogged,
      bid INTEGER NOT NULL REFERENCES pgbench_branches_unlogged,
      aid BIGINT NOT NULL REFERENCES pgbench_accounts_unlogged,
      delta INTEGER NOT NULL,
      mtime TIMESTAMP NOT NULL,
      filler CHAR(22)
      -- UNIQUE (tid, bid, aid, mtime)
    );
    """

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
            cursor.execute(
                'CREATE TABLESPACE {0} LOCATION \'{1}\''
                ' WITH (compression=true);'.format(
                    tablespace_name, tablespace_location))
        else:
            cursor.execute(
                'CREATE TABLESPACE {0} LOCATION \'{1}\';'.format(
                    tablespace_name, tablespace_location))
        return tablespace_location

    @pytest.mark.test_compression_standalone_positive
    def test_compression_standalone_positive(self, request, install_postgres):
        """ Test for compression feature.
        Scenario:
        1. Create test tables
        1. Create tablespace with compression
        2. Save size of created tables by fixture in file system
            (count and size of files)
        3. Run data generator for tablespace with compression
        4. Save size of table with compression
        5. Check that files for table in tablespace without compression >
            that files in tablespace with compression
        6. Check tablespace folder for files with *.cfm extension
        7. Check that tables has some data
        """
        # Step 1
        create_test_table('20', 'pgbench')
        # Step 2
        compression_files_directory = self.create_tablespace(
            'compression', compression=True)
        # Step 3
        data_size_without_compression = self.get_directory_size(
            install_postgres.get_option('data_directory'))
        # Step 4
        print(data_size_without_compression)
        install_postgres.set_option('default_tablespace', 'compression')
        create_test_table(size='20', schema='pgbench')
        # Step 5
        data_size_with_compression = self.get_directory_size(
            install_postgres.get_option('data_directory'))
        print(data_size_with_compression)
        print(compression_files_directory)
        # Step 6
        assert data_size_with_compression < data_size_without_compression
        # Step 7
        compression_files = self.get_filenames(
            compression_files_directory)
        assert '.cfm' in compression_files
        # Step 8
        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pgbench_tellers LIMIT 10;")
        result = cursor.fetchall()
        print(result)
        assert result != 0
        conn.close()
        drop_test_table(conn_string)

    @pytest.mark.test_compression_unlogged_tables
    def test_compression_unlogged_tables(self, request, install_postgres):
        """ Test for compression feature.
        Scenario:
        1. Create tablespace with compression
        2. Run pgbench (unlogged schema) for tablespace with compression
        3. Check tablespace folder for files with *.cfm extension
        """
        # Step 1
        compression_files_directory = self.create_tablespace(
            'compression_unlogged_tables', compression=True)
        print compression_files_directory
        # Step 2
        install_postgres.set_option(
            'default_tablespace', 'compression_unlogged_tables')
        create_test_table(size='20', schema=self.PGBENCH_SCHEMA_UNLOGGED)
        # Step 3
        compression_files = self.get_filenames(compression_files_directory)
        assert '.cfm' in compression_files
        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pgbench_tellers_unlogged LIMIT 10;")
        result = cursor.fetchall()
        print(result)
        assert result != 0
        conn.close()

    @pytest.mark.test_compression_negative
    def test_compression_negative(self, request, install_postgres):
        """ Test for compression feature.
        Scenario:
        1. Create tablespace with compression
        2. Run pgbench for tablespace with compression and
            kill postgres process
        3. Run postgres process and check that postgres is running
        4. Check that cfm files created
        5. Check that pgbench tables don't created
        """
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        product_info = " ".join([self.dist, name, edition, version])
        # pylint: disable=no-member
        tag_mark = pytest.allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        # Step 1
        compression_files_directory = self.create_tablespace(
            'compression_negative', compression=True)
        print(compression_files_directory)
        install_postgres.set_option(
            'default_tablespace', 'compression_negative')
        postgres_pid = install_postgres.get_postmaster_pid()
        print(postgres_pid)
        # Step 2
        create_table_process = Process(target=create_test_table,
                                       args=('20', 'pgbench',))
        create_table_process.start()
        time.sleep(10)
        # Step 3
        if create_table_process.is_alive():
            process = psutil.Process(postgres_pid)
            process.kill()
        compression_files = self.get_filenames(
            compression_files_directory)
        # Step 4
        # Files for tables created but no any table was created
        #  because transaction was corruped
        assert '.cfm' in compression_files
        install_postgres.manage_psql('start')
        # Step 5
        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM pg_tables"
            " WHERE tablespace=\'compression_negative\';")
        assert len(cursor.fetchall()) == 0
        drop_test_table(conn_string)

    @pytest.mark.test_compression_unlogged_tables_negative
    def test_compression_unlogged_tables_negative(self, request,
                                                  install_postgres):
        """ Test for compression feature.
        Scenario:
        1. Create tablespace with compression for test
        2. Run pgbench (unlogged schema) for tablespace with compression
        3. Kill postgres process
        4. Start postgres process
        5. Check that tables was created and readable
        6. Check tablespace folder for files with *.cfm extension
        """
        # Step 1
        compression_files_directory = self.create_tablespace(
            'compression_unlogged_tables_negative', compression=True)
        # Step 2
        install_postgres.set_option(
            'default_tablespace', 'compression_unlogged_tables_negative')
        create_test_table(size='20', schema=self.PGBENCH_SCHEMA_UNLOGGED)
        # Step 3
        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute("select * from pgbench_tellers_unlogged limit 10;")
        conn.close()
        process = psutil.Process(install_postgres.get_postmaster_pid())
        process.kill()
        # Step 4
        install_postgres.manage_psql('start')
        # Step 5
        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM pg_tables"
            " WHERE tablespace=\'compression_unlogged_tables_negative\';")
        assert len(cursor.fetchall()) != 0
        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pgbench_tellers_unlogged LIMIT 10;")
        result = cursor.fetchall()
        assert result != 0
        conn.close()
        # Step 6
        compression_files = self.get_filenames(compression_files_directory)
        assert '.cfm' in compression_files

    @pytest.mark.usefixtures('install_postgres')
    @pytest.mark.test_compression_alter_tablepsace_to_compression
    def test_compression_alter_tablepsace_to_compression(self, request):
        """Scenario:
        1. Create tablespace for test
        2. Create test data with pgbench
        3. Save rows count from pgbench_history
        4. Move table to branch with compression
        5. Check that rows count before and after moving the same
        """
        # Step 1
        self.create_tablespace(
            'compression_alter_tablepsace', compression=True)
        # Step 2
        conn_string = "host=localhost user=postgres"
        load_pgbench(conn_string, ["-i", "-s", "10"])
        load_pgbench(conn_string, ["-s", "10", "-t", "1000", "-c", "10"])
        # Step 3
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute("select count(*) from pgbench_history")
        rows_before_move = cursor.fetchall()[0][0]
        conn.commit()
        conn.close()
        # Step 4
        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute(
            "ALTER TABLE pgbench_history"
            " SET TABLESPACE compression_alter_tablepsace")
        cursor.execute("select count(*) from pgbench_history")
        rows_after_move = cursor.fetchall()[0][0]
        conn.commit()
        conn. close()
        # Step 5
        assert rows_before_move == rows_after_move

    @pytest.mark.usefixtures('install_postgres')
    @pytest.mark.test_compression_alter_tablepsace_from_compression
    def test_compression_alter_tablepsace_from_compression(self, request):
        """Scenario:
        1. Create tablespace for test
        2. Create test data with pgbench
        3. Save rows count from pgbench_history
        4. Move table to branch without compression
        5. Check that rows count before and after moving the same
        """
        # Step 1
        self.create_tablespace(
            'compression_alter_from_tablepsace', compression=True)
        # Step 2
        conn_string = "host=localhost user=postgres"
        load_pgbench(conn_string, ["-i", "-s", "10"])
        load_pgbench(conn_string, ["-s", "10", "-t", "1000", "-c", "10"])
        # Step 3
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute("select count(*) from pgbench_history")
        rows_before_move = cursor.fetchall()[0][0]
        conn.commit()
        conn.close()
        # Step 4
        conn_string = "host='localhost' user='postgres' "
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute(
            "ALTER TABLE pgbench_history"
            " SET TABLESPACE compression_alter_from_tablepsace")
        cursor.execute("select count(*) from pgbench_history")
        rows_after_move = cursor.fetchall()[0][0]
        conn.commit()
        conn.close()
        # Step 5
        assert rows_before_move == rows_after_move
