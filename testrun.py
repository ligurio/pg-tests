#!/usr/bin/env python
#    Copyright 2015 - 2017 Postgres Professional

import argparse
import os
import os.path
import platform
import random
import re
import shutil
import subprocess
import sys
import time
import urllib
import winrm
from subprocess import call

from helpers.utils import copy_file, copy_file_win, exec_command_win
from helpers.utils import REMOTE_LOGIN, REMOTE_PASSWORD, REMOTE_ROOT_PASSWORD
from helpers.utils import exec_command
from helpers.utils import gen_name

DEBUG = False

IMAGE_BASE_URL = 'http://webdav.l.postgrespro.ru/DIST/vm-images/test/'
TEMPLATE_DIR = '/pgpro/templates/'
WORK_DIR = '/pgpro/test-envs/'
ANSIBLE_CMD = "ansible-playbook %s -i static/inventory -c %s --limit %s"
ANSIBLE_PLAYBOOK = 'static/playbook-prepare-env.yml'
ANSIBLE_INVENTORY = "%s ansible_host=%s \
                    ansible_become_pass=%s \
                    ansible_ssh_pass=%s \
                    ansible_user=%s \
                    ansible_become_user=root\n"
ANSIBLE_INVENTORY_WIN = "%s ansible_host=%s \
                    ansible_user=%s  \
                    ansible_password=%s \
                    ansible_winrm_server_cert_validation=ignore  \
                    ansible_port=5985  \
                    ansible_connection=winrm \n"
REPORT_SERVER_URL = 'http://testrep.l.postgrespro.ru/'


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


def create_image(domname, name):

    domimage = WORK_DIR + domname + '.qcow2'
    image_url = IMAGE_BASE_URL + name + '.qcow2'
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

    return domimage


def create_env(name, domname):
    try:
        import libvirt
        conn = libvirt.open(None)
    except libvirt.libvirtError, e:
        print 'LibVirt connect error: ', e
        sys.exit(1)

    domimage = create_image(domname, name)
    dommac = mac_address_generator()
    qemu_path = ""
    if platform.linux_distribution()[0] == 'Ubuntu' or platform.linux_distribution()[0] == 'debian':
        qemu_path = """/usr/bin/qemu-system-x86_64"""
    elif platform.linux_distribution()[0] == 'CentOS Linux':
        qemu_path = """/usr/libexec/qemu-kvm"""
    if domname[0:3] == 'win':
        network_driver = "e1000"
    else:
        network_driver = "virtio"
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
                    <emulator>%s</emulator>
                    <disk type='file' device='disk'>
                      <driver name='qemu' type='qcow2' cache='none'/>
                      <source file='%s'/>
                      <target dev='vda' bus='virtio'/>
                    </disk>
                    <interface type='bridge'>
                      <mac address='%s'/>
                      <source bridge='virbr0'/>
                      <model type='%s'/>
                    </interface>
                    <input type='tablet' bus='usb'/>
                    <input type='mouse' bus='ps2'/>
                    <graphics type='vnc' port='-1' listen='0.0.0.0'/>
                  </devices>
                </domain>
                """ % (domname, qemu_path, domimage, dommac, network_driver)

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
        if timeout == 60:
            print "Failed to obtain an IP address inside domain"
            sys.exit(1)

    print "Domain name: %s\nIP address: %s" % (dom.name(), domipaddress)
    conn.close()

    return domipaddress, domimage, xmldesc


def setup_env(domipaddress, domname):
    """Create ansible cmd and run ansible on virtual machine

    :param domipaddress str: ip address of virtual machine
    :param domname str: virtual machine name
    :return: int: 0 if all OK and 1 if not
    """
    host_record = domipaddress + ' ' + domname + '\n'
    with open("/etc/hosts", "a") as hosts:
        hosts.write(host_record)

    if domname[0:3] != 'win':
        inv = ANSIBLE_INVENTORY % (domname, domipaddress, REMOTE_ROOT_PASSWORD, REMOTE_PASSWORD, REMOTE_LOGIN)
        ansible_cmd = ANSIBLE_CMD % (ANSIBLE_PLAYBOOK, "paramiko", domname)
    else:
        inv = ANSIBLE_INVENTORY_WIN % (domname, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD)
        ansible_cmd = ANSIBLE_CMD % (ANSIBLE_PLAYBOOK, "winrm", domname)

    with open("static/inventory", "a") as hosts:
        hosts.write(inv)

    os.environ['ANSIBLE_HOST_KEY_CHECKING'] = 'False'

    if DEBUG:
        ansible_cmd += " -vvv"
    print ansible_cmd
    time.sleep(5)    # GosLinux starts a bit slowly than other distros
    retcode = call(ansible_cmd.split(' '))
    if retcode != 0:
        print "Setup of the test environment %s is failed." % domname
        return 1
    return 0


def make_test_cmd(domname, reportname, tests=None,
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

    if domname[0:3] == 'win':
        cmd = r'cd C:\Users\test\pg-tests && pytest %s --self-contained-html --html=%s.html --junit-xml=%s.xml \
                  --maxfail=1 %s --target=%s' % (tests, reportname, reportname, pcmd, domname)
    else:
        cmd = 'cd /home/test/pg-tests && sudo pytest %s --self-contained-html --html=%s.html --junit-xml=%s.xml ' \
              '--maxfail=1 %s --target=%s' % (tests, reportname, reportname, pcmd, domname)

    if DEBUG:
        cmd += "--verbose --tb=long --full-trace"

    return cmd


def export_results(domname, domipaddress, reportname):
    if not os.path.exists('reports'):
        os.makedirs('reports')

    if domname[0:3] == 'win':
        copy_file_win(reportname, domipaddress)
    else:
        copy_file("reports/%s.html" % reportname,
                  "/home/test/pg-tests/%s.html" % reportname, domipaddress)
        copy_file("reports/%s.xml" % reportname,
                  "/home/test/pg-tests/%s.xml" % reportname, domipaddress)
    subprocess.Popen(
        ['curl', '-T', 'reports/%s.html' % reportname, REPORT_SERVER_URL])
    subprocess.Popen(
        ['curl', '-T', 'reports/%s.xml' % reportname, REPORT_SERVER_URL])


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
    parser.add_argument('--test', dest="run_tests", default="tests",
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
        domname = gen_name(t)
        reportname = "report-" + time.strftime('%Y-%b-%d-%H-%M-%S')
        domipaddress = create_env(t, domname)[0]
        setup_env(domipaddress, domname)
        cmd = make_test_cmd(domname, reportname, args.run_tests,
                            args.product_name,
                            args.product_version,
                            args.product_edition,
                            args.product_milestone,
                            args.product_build)
        if domname[0:3] == 'win':
            s = winrm.Session(domipaddress, auth=(REMOTE_LOGIN, REMOTE_PASSWORD))
            ps_script = """
                Set-ExecutionPolicy Unrestricted
                [Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Python27",
                [EnvironmentVariableTarget]::Machine)
                [Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Python27\Scripts",
                [EnvironmentVariableTarget]::Machine)
                """
            s.run_ps(ps_script)
            print "Added path for python and python scripts. \n"
            retcode, stdout, stderr = exec_command_win(cmd, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD)
            # export_results(domname, domipaddress, reportname)
        else:
            retcode, stdout, stderr = exec_command(cmd, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD)

        if args.export:
            export_results(domname, domipaddress, reportname)
            reporturl = os.path.join(REPORT_SERVER_URL, reportname)
            print "Link to the html report - %s.html" % reporturl
            print "Link to the xml report - %s.xml" % reporturl

        if args.keep:
            print('Domain %s (IP address %s)' % (domname, domipaddress))
        else:
            if retcode != 0:
                keep_env(domname, True)
            else:
                keep_env(domname, False)

        if retcode != 0:
            print("Test return code is not zero - %s. Please check logs in report: %s" % (retcode, reporturl))
            print retcode, stdout, stderr
            sys.exit(1)
        else:
            print("Test execution finished without errors")
            sys.exit(0)

        
if __name__ == "__main__":
    exit(main())
