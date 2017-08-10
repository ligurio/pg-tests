import psycopg2
import pytest
import time

from helpers.sql_helpers import drop_test_table
from helpers.utils import command_executor


@pytest.mark.test_multimaster
class TestMultimaster():

    MMR_POSTGRESQLCONF = ""
    MMR_PGHBACONF = ""

    def backp_postgresqlconf(self, node, data_dir):
        """Copy old postgresql.conf file to postgresql.conf.bckp and edit with new config and edit postggresql.conf
        :param node: node ip address
        :param conf_options: list with postgresql.conf options
        :return:
        """
        postgresql_conf_file = '/'.join([data_dir, 'postgresql.conf'])
        cmd = "cp -n %s %s/postgresql.conf_bckp" % (postgresql_conf_file, data_dir)
        command_executor(cmd, remote=True, host=node, login='root', password='TestRoot1')

    def edit_pghbaconf(self, data_dir):
        """

        :param data_dir:
        :return:
        """
        pass

    def delete_data(self, conn_string):
        """

        :param conn_string:
        :return:
        """
        drop_test_table(conn_string)

    @pytest.mark.usefixtures('install_postgres')
    @pytest.mark.parametrize("create_environment", [2, 3, 4, 5], indirect=True)
    @pytest.mark.usefixtures('create_environment')
    @pytest.mark.usefixtures('environment')
    def test_create_multimaster_cluster(self, create_environment, install_postgres):
        """Create cluster with simple configuration and 3 nodes
        Scenario:
        1. Edit replication settings
        2. Add multimaster settings
        3. Create extension multimaster
        4. Restart all nodes in cluster
        5. Check that cluster in online state
        6. Check that nodes in online state
        """
        # Step 1
        cluster_name = create_environment.keys()[0]
        multimaster_conn_string = "'dbname=postgres user=postgres host=%s," \
                                  " dbname=postgres user=postgres host=%s, " \
                                  "dbname=postgres user=postgres host=%s'" % (
            create_environment[cluster_name]['nodes'][0]['ip'],
            create_environment[cluster_name]['nodes'][1]['ip'],
            create_environment[cluster_name]['nodes'][2]['ip'])
        node_id = 1
        for node in create_environment[cluster_name]['nodes']:

            install_postgres.connstring = "host=%s user=postgres" % node['ip']
            self.backp_postgresqlconf(node['ip'], install_postgres.get_option('data_directory'))
            postgresql_conf_file = '/'.join([install_postgres.get_option('data_directory'), 'postgresql.conf'])
            cmd = "echo \'shared_preload_libraries = \'multimaster\'\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'multimaster.conn_strings = \'\\\'%s\\\'\'\' >> %s" % (multimaster_conn_string,
                                                                                postgresql_conf_file)
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'wal_level = logical\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'max_prepared_transactions = 300\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'max_wal_senders = 10\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'max_replication_slots = 10\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'max_worker_processes = 250\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'multimaster.max_nodes = 3\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'multimaster.node_id = %s\' >> %s " % (str(node_id), postgresql_conf_file)
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            node_id += 1
            cmd = "echo \'log_min_messages = log\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'log_min_error_statement = log\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            install_postgres.manage_psql("restart", remote=True, host=node['ip'])

        time.sleep(30)
        install_postgres.connstring = "host=%s user=postgres" % create_environment[cluster_name]['nodes'][0]['ip']
        conn = psycopg2.connect(install_postgres.connstring)
        cursor = conn.cursor()
        cursor.execute("CREATE EXTENSION multimaster")
        cursor.close()
        conn.commit()
        conn.close()

        for node in create_environment[cluster_name]['nodes']:
            install_postgres.connstring = "host=%s user=postgres" % node['ip']
            conn = psycopg2.connect(install_postgres.connstring)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT connected FROM mtm.get_nodes_state()")
            state = cursor.fetchall()[0][0]
            assert state is True
            cursor.execute(
                "SELECT status FROM mtm.get_cluster_state()")
            status = cursor.fetchall()[0][0]
            cursor.close()
            conn.close()
            assert status == 'Online'

    @pytest.mark.usefixtures('install_postgres')
    @pytest.mark.parametrize("create_environment", [3, 5], indirect=True)
    @pytest.mark.usefixtures('create_environment')
    @pytest.mark.usefixtures('environment')
    def test_upload_data_to_cluster(self, create_environment, install_postgres):
        """Scenario

        :param create_environment:
        :param install_postgres:
        :return:
        """
        # Step 1
        cluster_name = create_environment.keys()[0]
        multimaster_conn_string = "'dbname=postgres user=postgres host=%s," \
                                  " dbname=postgres user=postgres host=%s, " \
                                  "dbname=postgres user=postgres host=%s'" % (
                                      create_environment[cluster_name]['nodes'][0]['ip'],
                                      create_environment[cluster_name]['nodes'][1]['ip'],
                                      create_environment[cluster_name]['nodes'][2]['ip'])
        node_id = 1
        for node in create_environment[cluster_name]['nodes']:
            install_postgres.connstring = "host=%s user=postgres" % node['ip']
            self.backp_postgresqlconf(node['ip'], install_postgres.get_option('data_directory'))
            postgresql_conf_file = '/'.join([install_postgres.get_option('data_directory'), 'postgresql.conf'])
            cmd = "echo \'shared_preload_libraries = \'multimaster\'\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'multimaster.conn_strings = \'\\\'%s\\\'\'\' >> %s" % (multimaster_conn_string,
                                                                                postgresql_conf_file)
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'wal_level = logical\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'max_prepared_transactions = 300\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'max_wal_senders = 10\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'max_replication_slots = 10\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'max_worker_processes = 250\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'multimaster.max_nodes = 3\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'multimaster.node_id = %s\' >> %s " % (str(node_id), postgresql_conf_file)
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            node_id += 1
            cmd = "echo \'log_min_messages = log\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            cmd = "echo \'log_min_error_statement = log\' >> %s " % postgresql_conf_file
            command_executor(cmd, remote=True, host=node['ip'], login='root', password='TestRoot1')
            install_postgres.manage_psql("restart", remote=True, host=node['ip'])

        time.sleep(30)
        install_postgres.connstring = "host=%s user=postgres" % create_environment[cluster_name]['nodes'][0]['ip']
        conn = psycopg2.connect(install_postgres.connstring)
        cursor = conn.cursor()
        cursor.execute("CREATE EXTENSION multimaster")
        cursor.close()
        conn.commit()
        conn.close()

    @pytest.mark.usefixtures('install_postgres')
    @pytest.mark.parametrize("create_environment", [3], indirect=True)
    @pytest.mark.usefixtures('create_environment')
    @pytest.mark.usefixtures('environment')
    def test_multimaster_functions(self, create_environment, install_postgres):
        """Test multimaster functions working correctly
        1. Create multimaster cluster with 3 nodes
        2. Check function  mtm.get_nodes_state()
        3. Check function  mtm.collect_cluster_state()
        4. Check function  mtm.get_cluster_state()

        :param create_environment:
        :param install_postgres:
        :return:
        """

    @pytest.mark.usefixtures('install_postgres')
    @pytest.mark.parametrize("create_environment", [5], indirect=True)
    @pytest.mark.usefixtures('create_environment')
    @pytest.mark.usefixtures('environment')
    def test_multimaster_add_nodes(self, create_environment, install_postgres):
        """Test multimaster functions working correctly
        1. Create multimaster cluster with 3 nodes, but 2 nodes not add to cluster
        2. Upload data to cluster
        3. Add 2 nodes to cluster
        4. Check that added nodes was added to cluster
        5. Check that added nodes has all data
        6. Upload data to cluster
        7. Check that data added to all nodes in cluster

        :param create_environment:
        :param install_postgres:
        :return:
        """

    @pytest.mark.usefixtures('install_postgres')
    @pytest.mark.parametrize("create_environment", [5], indirect=True)
    @pytest.mark.usefixtures('create_environment')
    @pytest.mark.usefixtures('environment')
    def test_multimaster_drop_nodes(self, create_environment, install_postgres):
        """Test multimaster functions working correctly
        1. Create multimaster cluster with 5 nodes
        2. Upload data to cluster
        3. Drop  node from cluster
        4. Check that node was deleted
        5. Check that cluster still working
        6. Drop node wit option from cluster
        6. Upload data to cluster
        7. Check that data added to all nodes in cluster

        :param create_environment:
        :param install_postgres:
        :return:
        """

    @pytest.mark.usefixtures('install_postgres')
    @pytest.mark.parametrize("create_environment", [3], indirect=True)
    @pytest.mark.usefixtures('create_environment')
    @pytest.mark.usefixtures('environment')
    def test_multimaster_recover_node(self, create_environment, install_postgres):
        """Test multimaster functions working correctly
        1. Create multimaster cluster with 5 nodes
        2. Upload data to cluster
        3. Drop  node from cluster
        4. Check that node was deleted
        5. Check that cluster still working
        6. Drop node wit option from cluster
        6. Upload data to cluster
        7. Check that data added to all nodes in cluster

        :param create_environment:
        :param install_postgres:
        :return:
        """

    @pytest.mark.usefixtures('install_postgres')
    @pytest.mark.parametrize("create_environment", [3], indirect=True)
    @pytest.mark.usefixtures('create_environment')
    @pytest.mark.usefixtures('environment')
    def test_multimaster_check_make_table_local(self, create_environment, install_postgres):
        """Test multimaster functions working correctly
        1. Create multimaster cluster with 5 nodes
        2. Upload data to cluster
        3. Drop  node from cluster
        4. Check that node was deleted
        5. Check that cluster still working
        6. Drop node wit option from cluster
        6. Upload data to cluster
        7. Check that data added to all nodes in cluster

        :param create_environment:
        :param install_postgres:
        :return:
        """
