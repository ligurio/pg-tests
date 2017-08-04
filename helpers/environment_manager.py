import logging
import json
import os
import sys

from helpers.utils import exec_command, gen_name
from helpers.utils import REMOTE_ROOT_PASSWORD
from helpers.utils import REMOTE_ROOT
from testrun import create_env
from testrun import list_images

from testrun import WORK_DIR


class Environment(object):
    CLUSTER_SETTING = WORK_DIR + gen_name("cluster") + ".json"

    def __init__(self, env_name):
        self.env = env_name
        try:
            import libvirt
            self.conn = libvirt.open(None)
        except libvirt.libvirtError, e:
            print 'LibVirt connect error: ', e
            sys.exit(1)

    def create_environment(self, name, node_count, image_name):
        """ Create cluster method

        :param node_count: int
        :param image_name: str
        :return:
        """
        env_info = {}
        if image_name in list_images():
            cluster_name = "%s_%s" % (name, image_name)
            env_info[cluster_name] = {}
            env_info[cluster_name]['nodes'] = []
            for node in (range(1, node_count + 1)):
                node_name = gen_name(image_name)
                node_info = create_env(image_name, node_name)
                env_info[cluster_name]['nodes'].append({"domname": node_name,
                                                        "ip": node_info[0],
                                                        "image_path": node_info[1],
                                                        "xml_desc": node_info[2]})
                host_record = node_info[0] + ' ' + node_name + '\n'
                with open("/etc/hosts", "a") as hosts:
                    hosts.write(host_record)
                cmd = 'echo \"%s %s\" >> /etc/hosts ' % (node_name, node_info[0])
                exec_command(cmd, node_info[0], REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                cmd = 'hostname %s' % node_name
                exec_command(cmd, node_info[0], REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                cmd = 'sed -i \'s/^Defaults    requiretty/#Defaults    requiretty/\' /etc/sudoers'
                exec_command(cmd, node_info[0], REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
                cmd = 'iptables -F'
                exec_command(cmd, node_info[0], REMOTE_ROOT, REMOTE_ROOT_PASSWORD)
            mode = 'a' if os.path.exists(self.CLUSTER_SETTING) else 'w'
            with open(self.CLUSTER_SETTING, mode) as f:
                json.dump(env_info, f, indent=4, sort_keys=True)

            logging.debug("Was created cluster with following nodes: %s" % env_info)
            return env_info
        else:
            logging.error("We haven't image with name %s" % image_name)

    def start_env(self):
        """
        Check that env not running and if not start vms from env
        """
        clusters = self.get_cluster_config()
        if self.env in clusters:
            for node in clusters[self.env]['nodes']:
                dom = self.conn.lookupByName(node['domname'])
                dom.resume()

    def suspend_env(self):
        """
        Check that env  running and if it is stop vms from env
        :return:
        """
        clusters = self.get_cluster_config()
        if self.env in clusters:
            for node in clusters[self.env]['nodes']:
                dom = self.conn.lookupByName(node['domname'])
                dom.suspend()

    def shutdown_env(self):
        """
        Check that env running and if it is shutdown vms
        :return:
        """
        clusters = self.get_cluster_config()
        if self.env in clusters:
            for node in clusters[self.env]['nodes']:
                dom = self.conn.lookupByName(node['domname'])
                dom.shutdown()

    def delete_env(self):
        """
        Check that env running and if it is shutdown vms
        :return:
        """
        clusters = self.get_cluster_config()
        if self.env in clusters:
            for node in clusters[self.env]['nodes']:
                dom = self.conn.lookupByName(node['domname'])
                dom.destroy()
        os.remove(self.CLUSTER_SETTING)

    def get_cluster_config(self):
        with open(self.CLUSTER_SETTING) as f:
            cluster_config = json.load(f)
            return cluster_config

    def get_cluster_config_from_file(self, file):
        with open(file) as f:
            cluster_config = json.load(f)
            return cluster_config
