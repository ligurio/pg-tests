import platform
import os
import subprocess
import shutil
import time
import sys

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall
from helpers.utils import diff_dbs


class Pgbench(object):
    def __init__(self, pginst, number, host, port, dbuser, db, duration,
                 scale=1, type='tpc-b'):
        self.pginst = pginst
        self.number = number
        self.host = host
        self.port = port
        self.dbuser = dbuser
        self.db = db
        self.duration = duration
        self.scale = scale
        self.type = type
        self.process = None

    def init(self):
        return subprocess.check_output('%s -i -h %s -p %i -U %s -s %i %s' % (
            os.path.join(self.pginst.get_client_bin_path(), 'pgbench'),
            self.host, self.port, self.dbuser, self.scale, self.db),
                                       shell=True)

    def start(self):
        cmd = [os.path.join(
            self.pginst.get_client_bin_path(), 'pgbench'), self.db, '-p',
            str(self.port), '-h', self.host, '-U', self.dbuser, '-T',
            str(self.duration), '--max-tries', '0', '--latency-limit', '10000']
        if type == 'select':
            cmd.append('-S')
        print(cmd)
        self.process = subprocess.Popen(cmd, stderr=subprocess.STDOUT,
                                        stdout=subprocess.PIPE)
        return True

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.communicate()
            self.process.wait()
        return self.process.returncode

    def wait(self):
        self.process.wait()
        return self.process.communicate()


class Node(object):
    def __init__(self, pginst, datadir,
                 host, number, size, port=5432):
        self.host = host
        self.port = port
        self.datadir = datadir
        self.pginst = pginst
        self.pg_bin_path = self.pginst.get_client_bin_path()
        self.size = size
        host_base = '.'.join(self.host.split('.')[0:3])+'.'
        listen_ips = {}
        for i in range(1, self.size+1):
            listen_ips[i] = host_base+str(i)
        listen_ips[self.size+1] = self.host
        self.listen_ips = listen_ips
        self.number = number
        self.service_name = 'postgres-node%s' % self.number

    def init(self):
        self.pginst.datadir = self.datadir
        self.pginst.init_cluster(True)
        with open(os.path.join(self.datadir, 'postgresql.conf'), 'a') as conf:
            conf.write(
                'listen_addresses = \'%s\'\n' % ', '.join(
                    self.listen_ips.values()) +
                'unix_socket_directories = \'\'\n'
                   )
        if self.pginst.windows:
            subprocess.check_call(
                '%s register -D "%s" -N %s -U '
                '"NT Authority\\NetworkService"' % (
                    os.path.join(self.pginst.get_client_bin_path(),
                                 'pg_ctl.exe'), self.datadir,
                    self.service_name))

    def start(self):
        if self.pginst.windows:
            self.pginst.service_name = self.service_name
            self.pginst.srvhost = self.host
            self.pginst.service_action('start')
        else:
            self.pginst.pg_control('start', self.datadir)

    def stop(self):
        if self.pginst.windows:
            self.pginst.service_name = self.service_name
            self.pginst.srvhost = self.host
            self.pginst.service_action('stop')
        else:
            self.pginst.pg_control('stop', self.datadir)

    def add_config(self, *conf):
        for directive in conf:
            print(self.psql('ALTER SYSTEM SET %s' % directive))

    def psql(self, query, a_options=''):
        self.pginst.port = self.port
        self.pginst.srvhost = self.host
        return self.pginst.exec_psql(query,
                                     options=a_options)

    def pgbench(self, dbuser, db, duration, scale=1, type='tpc-b'):
        return Pgbench(self.pginst, self.number, self.host, self.port, dbuser,
                       db, duration, scale, type)

    def pg_dump(self, dbuser, db, table):
        while True:
            filename = '/tmp/pgd_node%i_%s.dmp' % (self.number, table[0])
            if not os.path.isfile(filename):
                break
        tbl = []
        for t in table:
            tbl.append('--table=%s' % t)
        cmd = [os.path.join(self.pginst.get_client_bin_path(), 'pg_dump'),
               '-h', self.host, '-p', str(self.port), '-U', dbuser, '-d',
               db, '-f', filename]+tbl
        print(cmd)
        subprocess.check_output(cmd)
        return filename

    def clean(self):
        if os.path.exists(self.datadir) and os.path.isdir(self.datadir):
            shutil.rmtree(self.datadir)

    def gethost(self):
        return self.host

    def getdatadir(self):
        return self.datadir


class Multimaster(object):
    def __init__(self, size=3, dbuser='myuser', db='mydb',
                 ip_base='127.12.0.0', password='myuserpassword', pginst=None,
                 rootdir='/multimaster'):
        self.size = size
        self.pginst = pginst
        self.dbuser = dbuser
        self.db = db
        self.ip_base = ip_base
        self.password = password
        self.rootdir = rootdir
        if not os.path.isdir(self.rootdir):
            os.mkdir(self.rootdir, 0o755)
        host_base = '.'.join(ip_base.split('.')[0:2])+'.'
        hosts = {}
        for i in range(1, self.size+1):
            hosts[i] = host_base + str(i) + '.100'
        self.hosts = hosts
        nodes = {}
        for i in range(1, self.size+1):
            nodes[i] = Node(pginst=self.pginst,
                            datadir=os.path.join(self.rootdir,
                                                 'node%i' % i),
                            host=self.hosts[i], size=self.size,
                            number=i)
            nodes[i].clean()
            nodes[i].init()
            nodes[i].start()
            nodes[i].add_config(
                "shared_preload_libraries = 'multimaster'",
                "default_transaction_isolation = 'read committed'",
                "wal_level = 'logical'",
                "max_connections = 100",
                "max_prepared_transactions = 300",
                "max_wal_senders = 10",
                "max_replication_slots = 10",
                "max_worker_processes = 250",
            )
            nodes[i].psql(
                "CREATE USER %s WITH SUPERUSER PASSWORD '%s'" % (
                    self.dbuser, self.password))
            nodes[i].psql(
                "CREATE DATABASE %s OWNER %s" % (
                    self.db, self.dbuser))
            nodes[i].stop()

        host = '\nhost\treplication\t%s\t127.0.0.0/8\ttrust\n' % (
            self.dbuser)
        for i in range(1, self.size+1):
            with open(os.path.join(nodes[i].datadir, 'pg_hba.conf'), 'a'
                      ) as hba:
                hba.write(host)
        self.nodes = nodes

    def start(self):
        for i, node in self.nodes.items():
            node.start()
        for i, node in self.nodes.items():
            self.psql('CREATE EXTENSION multimaster', node=i)
            conn = []
            for j in range(1, self.size+1):
                conn.append("(%i, 'dbname=%s user=%s host=%s port=%i', %r)" % (
                    j, self.db, self.dbuser, self.nodes[j].listen_ips[i],
                    self.nodes[j].port, (i == j)))
            self.psql("INSERT INTO mtm.cluster_nodes VALUES %s" %
                      ', '.join(conn), node=i)
        for i in range(1, self.size+1):
            self.wait(i)

    def __link__(self, n1, n2, do_break=True):
        if do_break:
            mode = 'add'
        else:
            mode = 'delete'
        if self.pginst.windows:
            os.system(
                'route %s %s mask 255.255.255.255 192.168.0.1 if 1' % (
                    mode, self.nodes[n1].listen_ips[n2]))
            os.system(
                'route %s %s mask 255.255.255.255 192.168.0.1 if 1' % (
                    mode, self.nodes[n2].listen_ips[n1]))
        else:
            cmd = 'iptables %s INPUT -d %s/32 -j DROP' % (
                mode, self.nodes[n1].listen_ips[n2])
            subprocess.check_call(cmd, shell=True,
                                  stderr=subprocess.STDOUT,
                                  stdout=subprocess.PIPE)
            cmd = 'iptables %s INPUT -d %s/32 -j DROP' % (
                mode, self.nodes[n2].listen_ips[n1])
            subprocess.check_call(cmd, shell=True,
                                  stderr=subprocess.STDOUT,
                                  stdout=subprocess.PIPE)

    def break_link(self, n1, n2):
        self.__link__(n1, n2, True)

    def restore_link(self, n1, n2):
        self.__link__(n1, n2, False)

    def __isolate__(self, n, do_isolate=True):
        if self.pginst.windows:
            if do_isolate:
                mode = 'add'
            else:
                mode = 'delete'
        else:
            if do_isolate:
                mode = '-I'
            else:
                mode = '-D'
        ip = self.nodes[n].host
        net = '.'.join(ip.split('.')[0:3])+'.0/24'
        if self.pginst.windows:
            os.system('route %s %s mask 255.255.255.0 192.168.0.1 if 1' % (
                mode, net.split('/')[0]))
            for i in range(1, self.size+1):
                os.system(
                    'route %s %s mask 255.255.255.255 192.168.0.1 if 1' % (
                        mode, self.nodes[i].listen_ips[n]))
        else:
            cmd = 'iptables %s INPUT -d %s -j DROP' % (mode, net)
            subprocess.check_call(cmd, shell=True, stderr=subprocess.STDOUT,
                                  stdout=subprocess.PIPE)
            for i in range(1, self.size+1):
                cmd = 'iptables %s INPUT -d %s/32 -j DROP' % (
                    mode, self.nodes[i].listen_ips[n])
                subprocess.check_call(cmd, shell=True,
                                      stderr=subprocess.STDOUT,
                                      stdout=subprocess.PIPE)
            cmd = 'iptables %s INPUT -d %s -j ACCEPT' % (
                    mode, self.nodes[n].host)
            subprocess.check_call(cmd, shell=True, stderr=subprocess.STDOUT,
                                  stdout=subprocess.PIPE)

    def isolate(self, n):
        self.__isolate__(n, True)

    def deisolate(self, n):
        self.__isolate__(n, False)

    def psql(self, query, a_options='', node=1):
        return self.nodes[node].psql(
            query, '-d %s -U %s %s' % (self.db, self.dbuser, a_options))

    def check(self, node):
        try:
            self.psql('SELECT version()', node=node)
        except Exception:
            return False
        else:
            return True

    def wait(self, node, duration=60):
        fail = True
        for t in range(1, duration):
            if self.check(node):
                fail = False
                break
            else:
                time.sleep(1)
        if fail:
            raise Exception('Timeout %i seconds expired node: %i' % (
                duration, node))

    def pgbench(self, n, duration=60, scale=1, type='tpc-b'):
        return self.nodes[n].pgbench(self.dbuser, self.db, duration, scale,
                                     type)

    def pg_dump(self, n, table):
        return self.nodes[n].pg_dump(self.dbuser, self.db, table)

    def get_cluster_state(self, n, allow_fail=False):
        try:
            out = self.psql("select * from mtm.status()",
                            '-Aqt', n).split('|')
        except Exception:
            if allow_fail:
                return None
            else:
                raise Exception('Error get cluster state: node %i' % n)
        return out

    def get_cluster_state_all(self, allow_fail=False):
        all_states = {}
        for i in range(1, self.size+1):
            all_states[i] = self.get_cluster_state(i, allow_fail)
        return all_states

    def get_nodes_state(self, n, allow_fail=False):
        states = []
        try:
            s_states = self.psql(
                "SELECT id,enabled FROM mtm.nodes()", '-Aqt', n
                                 ).split('\n')
        except Exception:
            if allow_fail:
                return None
            else:
                raise Exception('Can not get nodes state on node %i' % n)
        else:
            for state in s_states:
                states.append(state.split('|'))
            return states

    def get_nodes_state_all(self, allow_fail=False):
        all_nodes_state = {}
        for i in range(1, self.size+1):
            all_nodes_state[i] = self.get_nodes_state(i, allow_fail)
        return all_nodes_state


@pytest.mark.multimaster_install
class TestMultimasterInstall():

    system = platform.system()
    def route_print(self):
        if self.system == 'Linux':
            os.system('ip route')
        elif self.system == 'Windows':
            os.system('route print')

    @pytest.mark.test_clean_install
    def test_multimaster_install(self, request):
        """
        Scenario:
        1. Install current version
        2. Check that setup successfull (select version)

        :return:
        """
        if self.system == 'Linux':
            dist = " ".join(platform.linux_distribution()[0:2])
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
        # pylint: disable=no-member
        tag_mark = pytest.allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        branch = request.config.getoption('--branch')

        if version.startswith('9.') or version.startswith('10'):
            print('Version %s is not supported' % version)
            sys.exit()

        # Step 1
        pginst = PgInstall(product=name, edition=edition,
                           version=version, milestone=milestone,
                           branch=branch, windows=(self.system == 'Windows'))
        request.cls.pginst = pginst
        pginst.setup_repo()
        print("Running on %s." % target)
        if self.system != 'Windows':
            pginst.install_full_topless()
        else:
            pginst.install_postgres_win()
            pginst.stop_service()
        mm = Multimaster(size=3, pginst=pginst,
                         rootdir=os.path.abspath(
                             os.path.join(pginst.get_datadir(), os.pardir)))
        mm.start()
        for i, cl_state in mm.get_cluster_state_all().items():
            if int(cl_state[0]) != i:
                raise Exception('Wrong ID on node %i! %i != %i' % (
                    i, i, cl_state[0]))
            if cl_state[1].lower() != 'online':
                print(cl_state)
                raise Exception('Node %i is not online!' % i)

        print(mm.get_nodes_state_all())
        for i, ns_all in mm.get_nodes_state_all().items():
            for node_state in ns_all:
                if node_state[1] != 't':
                    raise Exception('Node %s is not enabled! (on node %i)' % (
                        node_state[0], i))

        pgbench = {}
        for i, node in mm.nodes.items():
            pgbench[i] = mm.pgbench(i)
            pgbench[i].init()
        for i in range(1, mm.size+1):
            print('Running pgbench on node%i' % i)
            pgbench[i].start()

        time.sleep(15)
        print('Cluster state:')
        print(mm.get_cluster_state_all())
        print(mm.get_nodes_state_all())
        print('Isolating node 2...')
        mm.isolate(2)
        time.sleep(15)
        print('Cluster state:')
        print(mm.get_cluster_state_all(allow_fail=True))
        print(mm.get_nodes_state_all(allow_fail=True))
        print('De-isolating node 2...')
        mm.deisolate(2)
        time.sleep(15)
        if not mm.check(2):
            print('Try to recover node 2')
            mm.wait(2, 30)
        print('Cluster state:')
        print(mm.get_cluster_state_all(allow_fail=True))
        print(mm.get_nodes_state_all(allow_fail=True))
        for i in range(1, mm.size+1):
            print('Pgbench %i terminated rc=%i' % (i, pgbench[i].stop()))

        pgbench_tables = ('pgbench_branches', 'pgbench_tellers',
                          'pgbench_accounts', 'pgbench_history')
        for table in pgbench_tables:
            result = {}
            for i in range(1, mm.size+1):
                result[i] = mm.pg_dump(i, [table])
            for i in range(2, mm.size+1):
                diff_dbs(result[1], result[i], '%s_1_%i.diff' % (table, i))
