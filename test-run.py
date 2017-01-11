#!/usr/bin/env python

import argparse
import os
import os.path
import paramiko
import random
import re
import socket
import shutil
import subprocess
import sys
import time
import urllib
from subprocess import call
"""PostgresPro regression tests run script."""

__author__ = "Sergey Bronnikov <sergeyb@postgrespro.ru>"


IMAGE_BASE_URL = 'http://webdav.l.postgrespro.ru/DIST/vm-images/test/'
TEMPLATE_DIR = '/pgpro/templates/'
WORK_DIR = '/pgpro/test-envs/'
ANSIBLE_CMD = "ansible-playbook %s -i static/inventory -c paramiko --limit %s"
ANSIBLE_PLAYBOOK = 'static/playbook-prepare-env.yml'
ANSIBLE_INVENTORY = "%s ansible_host=%s \
                    ansible_become_pass=%s \
                    ansible_ssh_pass=%s \
                    ansible_user=%s \
                    ansible_become_user=root\n"
REPORT_SERVER_URL = 'http://testrep.l.postgrespro.ru/'

SSH_LOGIN = 'test'
SSH_ROOT = 'root'
SSH_PASSWORD = 'TestPass1'
SSH_ROOT_PASSWORD = 'TestRoot1'
SSH_PORT = 22
DEBUG = False


def list_images():
    names = []
    page = urllib.urlopen(IMAGE_BASE_URL).read()
    images = re.findall('href=[\'"]?([^\'" >]+)\.qcow2', page)
    for i in images:
        names.append(i)
    return names


def lookupIPbyMac(conn, mac):
    """Lookup IP adddress by MAC address using DHCP information

    :parameters: connection object, mac address
    :return: string: IP address
    """
    for net in conn.listNetworks():
        for lease in conn.networkLookupByName(net).DHCPLeases():
            if lease['mac'] == mac and lease['iaid'] is None:
                return lease['ipaddr']
    return None


# TODO: use Locally Administered Address Ranges
def mac_address_generator():
    """Generate random mac address

    :return: string: mac address
    """
    mac = [0x00, 0x16, 0x3e,
           random.randint(0x00, 0x7f),
           random.randint(0x00, 0xff),
           random.randint(0x00, 0xff)]
    return ':'.join(map(lambda x: "%02x" % x, mac))


def copy_file(local_path, remote_path, hostname):

    transport = paramiko.Transport((hostname, SSH_PORT))
    transport.connect(username=SSH_LOGIN, password=SSH_PASSWORD)
    sftp = paramiko.SFTPClient.from_transport(transport)
    print "Copying file '%s', remote host is '%s'" % (remote_path, hostname)
    sftp.get(remote_path, local_path)
    sftp.close()
    transport.close()

    # TODO: return exit code


def exec_command(cmd, hostname):

    buff_size = 1024
    stdout = ""
    stderr = ""

    known_hosts = os.path.expanduser(os.path.join("~", ".ssh", "known_hosts"))
    try:
        client = paramiko.SSHClient()
        if os.path.isfile(known_hosts):
            client.load_system_host_keys(known_hosts)
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=hostname, username=SSH_LOGIN,
                           password=SSH_PASSWORD, port=SSH_PORT,
                           look_for_keys=False)
    except paramiko.AuthenticationException, e:
        print 'Auth Error: ', e
        sys.exit(1)
    except paramiko.SSHException, e:
        print 'Connection Error: ', e
        sys.exit(1)
    except socket.error, e:
        print 'Timed Out', e
        sys.exit(1)

    chan = client.get_transport().open_session()
    print "Executing '%s' on '%s'" % (cmd, hostname)
    chan.exec_command(cmd)
    retcode = chan.recv_exit_status()
    while chan.recv_ready():
        stdout += chan.recv(buff_size)

    while chan.recv_stderr_ready():
        stderr += chan.recv_stderr(buff_size)

    client.close()

    return retcode, stdout, stderr


def create_image(domname, name):

    domimage = WORK_DIR + domname + '.qcow2'
    image_url = IMAGE_BASE_URL + domname + '.qcow2'
    image_original = TEMPLATE_DIR + name + '.qcow2'

    if not os.path.isfile(image_original):
        if not os.path.exists(TEMPLATE_DIR):
            os.makedirs(TEMPLATE_DIR)
        image = urllib.URLopener()
        image.retrieve(image_url, image_original)

    if not os.path.exists(WORK_DIR):
        os.makedirs(WORK_DIR)
    print "Copy an original image to %s" % domimage
    try:
        shutil.copy(image_original, domimage)
    except IOError as e:
        print "I/O error({0}): {1}".format(e.errno, e.strerror)

    # FIXME: use linked clone
    #  qemu-img create -f qcow2 -b winxp.qcow2 winxp-clone.qcow2

    return domimage


def gen_domname(name):
    return name + '-' + str(random.getrandbits(15))


def create_env(name, domname):
    try:
        import libvirt
        conn = libvirt.open(None)
    except libvirt.libvirtError, e:
        print 'LibVirt connect error: ', e
        sys.exit(1)

    domimage = create_image(domname, name)
    dommac = mac_address_generator()
    xmldesc = """<domain type='kvm'>
  <name>%s</name>
  <memory unit='GB'>1</memory>
  <vcpu>1</vcpu>
  <os>
    <type>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
  </features>
  <clock offset='utc'/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <devices>
    <emulator>/usr/libexec/qemu-kvm</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none'/>
      <source file='%s'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='bridge'>
      <mac address='%s'/>
      <source bridge='virbr0'/>
      <model type='virtio'/>
    </interface>
    <input type='tablet' bus='usb'/>
    <input type='mouse' bus='ps2'/>
    <graphics type='vnc' port='-1' listen='0.0.0.0'/>
  </devices>
</domain>
""" % (domname, domimage, dommac)

    dom = conn.createLinux(xmldesc, 0)
    if dom is None:
        print "Failed to create a test domain"

    domipaddress = None
    timeout = 0
    while not domipaddress:
        timeout += 5
        print "Waiting for IP address...%d" % timeout
        time.sleep(timeout)
        domipaddress = lookupIPbyMac(conn, dommac)
        if timeout == 40:
            print "Failed to obtain an IP address inside domain"
            sys.exit(1)

    print "Domain name: %s\nIP address: %s" % (dom.name(), domipaddress)
    conn.close()

    return domipaddress


def setup_env(domipaddress, domname):
    host_record = domipaddress + ' ' + domname + '\n'
    with open("/etc/hosts", "a") as hosts:
        hosts.write(host_record)

    inv = ANSIBLE_INVENTORY % (domname, domipaddress, SSH_ROOT_PASSWORD, SSH_PASSWORD, SSH_LOGIN)
    with open("static/inventory", "a") as hosts:
        hosts.write(inv)

    os.environ['ANSIBLE_HOST_KEY_CHECKING'] = 'False'
    ansible_cmd = ANSIBLE_CMD % (ANSIBLE_PLAYBOOK, domname)
    if DEBUG:
        ansible_cmd += " -vvv"
    print ansible_cmd
    time.sleep(5)    # GosLinux starts a bit slowly than other distros
    retcode = call(ansible_cmd.split(' '))
    if retcode != 0:
        print "Setup of the test environment %s is failed." % domname
        return 1
    return 0


def make_test_cmd(date, tests=None,
                  product_name=None,
                  product_version=None,
                  product_edition=None,
                  product_milestone=None,
                  product_build=None):

    pcmd = ""
    if product_name:
        pcmd = "%s --product_name %s " % (pcmd, product_name)
    if product_version:
        pcmd = "%s --product_version %s " % (pcmd, product_version)
    if product_edition:
        pcmd = "%s --product_edition %s " % (pcmd, product_edition)
    if product_milestone:
        pcmd = "%s --product_milestone %s " % (pcmd, product_milestone)
    if product_build:
        pcmd = "%s --product_build %s " % (pcmd, product_build)

    cmd = 'cd /home/test/pg-tests && sudo pytest \
                                    --self-contained-html \
                                    --html=report-%s.html \
                                    --junit-xml=report-%s.xml \
                                    --maxfail=1 %s %s' \
                                    % (date, date, pcmd, tests)

    if DEBUG:
        cmd = cmd + "--verbose --tb=long --full-trace"

    return cmd


def export_results(domipaddress, date):
    if not os.path.exists('reports'):
        os.makedirs('reports')
    copy_file("reports/report-%s.html" % date,
              "/home/test/pg-tests/report-%s.html" % date, domipaddress)
    copy_file("reports/report-%s.xml" % date,
              "/home/test/pg-tests/report-%s.xml" % date, domipaddress)

    subprocess.Popen(
        ['curl', '-T', 'reports/report-%s.html' % date, REPORT_SERVER_URL])
    subprocess.Popen(['curl', '-T', 'reports/report-%s.xml' %
                      date, REPORT_SERVER_URL])


def keep_env(domname, keep):
    try:
        import libvirt
        conn = libvirt.open(None)
    except libvirt.libvirtError, e:
        print 'LibVirt connect error: ', e
        sys.exit(1)

    try:
        dom = conn.lookupByName(domname)
    except:
        print 'Failed to find the domain %s' % domname

    if keep:
        save_image = os.path.join(WORK_DIR, domname + ".img")
        if dom.save(save_image) < 0:
            print('Unable to save state of %s to %s' % (domname, save_image))
        else:
            print('Domain %s state saved to %s' % (domname, save_image))
    else:
        if dom.destroy() < 0:
            print('Unable to destroy of %s' % domname)
        domimage = WORK_DIR + domname + '.qcow2'
        if os.path.exists(domimage):
            os.remove(domimage)

    conn.close()


def main():

    names = list_images()
    parser = argparse.ArgumentParser(
        description='PostgreSQL regression tests run script.',
        epilog='Possible operating systems (images): %s' % ' '.join(names))
    parser.add_argument('--target', dest="target",
                        help='system(s) under test (image(s))')
    parser.add_argument('--test', dest="run_tests", default="",
                        help='tests to run (default: all)')
    parser.add_argument("--product_name", dest="product_name",
                        help="specify product name", action="store")
    parser.add_argument("--product_version", dest="product_version",
                        help="specify product version", action="store")
    parser.add_argument("--product_edition", dest="product_edition",
                        help="specify product edition", action="store")
    parser.add_argument("--product_milestone", dest="product_milestone",
                        help="specify target milestone", action="store")
    parser.add_argument("--product_build", dest="product_build",
                        help="specify product build", action="store")
    parser.add_argument('--keep', dest="keep", action='store_true',
                        help='what to do with env after testing')
    parser.add_argument('--export', dest="export",
                        help='export results', action='store_true')

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.target is not None:
        target = args.target
    else:
        print "No target name"
        sys.exit(1)

    targets = target.split(',')
    for t in targets:
        domname = gen_domname(t)
        date = time.strftime('%Y-%b-%d-%H-%M-%S')
        domipaddress = create_env(t, domname)
        setup_env(domipaddress, domname)
        cmd = make_test_cmd(date, args.run_tests,
                            args.product_name,
                            args.product_version,
                            args.product_edition,
                            args.product_milestone,
                            args.product_build)
        retcode, stdout, stderr = exec_command(cmd, domipaddress)
        if retcode != 0:
            print "Test return code is not zero - %s." % retcode
            print retcode, stdout, stderr

        if args.export:
            export_results(domipaddress, date)

        if args.keep:
            print('Domain %s (IP address %s)' % (domname, domipaddress))
        else:
            if retcode != 0:
                keep_env(domname, True)
            else:
                keep_env(domname, False)

if __name__ == "__main__":
    exit(main())
