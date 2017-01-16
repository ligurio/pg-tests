import grp
import os
import pwd
import random

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from helpers.sql_helpers import create_test_table
from helpers.sql_helpers import get_data_directory
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
        cursor.execute("ALTER DATABASE {} SET default_tablespace TO {}".format(db_name, tbs_name))

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
        file_names = []
        for root, directories, files in os.walk(directory):
            for filename in files:
                file_names.append(filename)
        return file_names

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
            cursor.execute('CREATE TABLESPACE {} LOCATION \'{}\' WITH (compression=true);'.format(tablespace_name,
                                                                                                  tablespace_location))
        else:
            cursor.execute('CREATE TABLESPACE {} LOCATION \'{}\';'.format(tablespace_name, tablespace_location))

    @pytest.mark.test_compression
    @pytest.mark.usefixtures('create_table')
    @pytest.mark.parametrize('create_table', [('pgbench', '20')], indirect=True)
    def test_compression_standalone_positive(self):
        #  TODO add check from step 5
        #  TODO add logging for checks and actions
        """ Test for compression feature.
        Scenario:
        1. Create tablespace with compression
        2. Save size of created table by fixture in file system (count and size of files)
        3. Create tablespace with compression
        4. Run data generator for tablespace with compression
        5. Check tablespace folder for files with *.shm extension (not implemented yet)
        6. Save count of files in directory with table
        7. Save size of table with compression
        8. Check that files for table in tablespace without compression > that files in tablespace with compression
        """
        self.create_tablespace('compression', compression=True)
        data_directory = get_data_directory()
        print(data_directory)
        #  Save db files size
        data_size_without_compression = self.get_directory_size(data_directory)
        print(data_size_without_compression)
        self.set_default_tablespace('postgres', 'compression')
        create_test_table(size='20', schema='pgbench')
        compression_data_directory = get_data_directory()
        print(compression_data_directory)
        data_size_with_compression = self.get_directory_size(compression_data_directory)
        print(data_size_with_compression)
        compression_files = self.get_filenames(compression_data_directory)
        assert data_size_with_compression < data_size_without_compression
