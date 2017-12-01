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
import tempfile
import glob
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
ANSIBLE_PLAYBOOK = 'playbook-prepare-env.yml'
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
TESTS_PAYLOAD_TAR = '/tmp/pg-tests.tgz'
TESTS_PAYLOAD_ZIP = '/tmp/pg-tests.zip'


def list_images():
    names = []
    try:
        page = urllib.urlopen(IMAGE_BASE_URL).read()
    except IOError:
        for f in os.listdir(TEMPLATE_DIR):
            fp = os.path.splitext(f)
            if fp[1] == '.qcow2':
                names.append(fp[0])
        return sorted(names)
    images = re.findall('href=[\'"]?([^\'" >]+)\.qcow2', page)
    for i in images:
        names.append(i)
    return sorted(names)


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

    domimage = WORK_DIR + domname + '-overlay.qcow2'
    image_url = IMAGE_BASE_URL + name + '.qcow2'
    image_original = TEMPLATE_DIR + name + '.qcow2'

    if not os.path.isfile(image_original):
        if not os.path.exists(TEMPLATE_DIR):
            os.makedirs(TEMPLATE_DIR)
        image = urllib.URLopener()
        image.retrieve(image_url, image_original)

    if not os.path.exists(WORK_DIR):
        os.makedirs(WORK_DIR)

    retcode = call("qemu-img create -b %s -f qcow2 %s" %
                   (image_original, domimage), shell=True)
    if retcode != 0:
        raise Exception("Could not create qemu image.")

    return domimage


def prepare_payload(tests_dir):
    print("Preparing a payload for target VMs...")
    tempdir = tempfile.mkdtemp()
    pgtd = os.path.join(tempdir, 'pg-tests')
    shutil.copytree('.', pgtd, ignore=shutil.ignore_patterns(('^.git')))
    retcode = call("wget -q https://bootstrap.pypa.io/get-pip.py", cwd=pgtd, shell=True)
    if retcode != 0:
        raise Exception("Downloading get-pip failed.")
    pgtdpp = os.path.join(pgtd, 'pip-packages')
    os.makedirs(pgtdpp)
    retcode = call("pip download -q -r %s" %
                   os.path.abspath(os.path.join(tests_dir, "requirements.txt")),
                   cwd=pgtdpp, shell=True)
    if retcode != 0:
        raise Exception("Downloading pip-requirements failed.")

    retcode = call("pip download -q --no-deps --only-binary=:all:"
                   " --platform manylinux1_x86_64 --python-version 27"
                   " --implementation cp --abi cp27m  -r %s" %
                   os.path.abspath(os.path.join(tests_dir, "requirements-bin.txt")),
                   cwd=pgtdpp, shell=True)
    if retcode != 0:
        raise Exception("Downloading pip-requirements(27m) failed.")

    retcode = call("pip download -q --no-deps --only-binary=:all:"
                   " --platform manylinux1_x86_64 --python-version 27"
                   " --implementation cp --abi cp27mu  -r %s" %
                   os.path.abspath(os.path.join(tests_dir, "requirements-bin.txt")),
                   cwd=pgtdpp, shell=True)
    if retcode != 0:
        raise Exception("Downloading pip-requirements(27mu) failed.")

    if os.path.exists(TESTS_PAYLOAD_ZIP):
        os.remove(TESTS_PAYLOAD_ZIP)
    retcode = call("zip -q -r {0} pg-tests".format(TESTS_PAYLOAD_ZIP),
                   cwd=tempdir, shell=True)
    if retcode != 0:
        raise Exception("Preparing zip payload failed.")
    if os.path.exists(TESTS_PAYLOAD_TAR):
        os.remove(TESTS_PAYLOAD_TAR)
    retcode = call("tar -czf {0} pg-tests".format(TESTS_PAYLOAD_TAR),
                   cwd=tempdir, shell=True)
    if retcode != 0:
        raise Exception("Preparing tar payload failed.")
    shutil.rmtree(tempdir)


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
    domisos = glob.glob(TEMPLATE_DIR + name + '*.iso')
    cdroms = ""
    cdromletter = "c"
    for diso in sorted(domisos):
        cdroms += """
                    <disk type='file' device='cdrom'>
                       <driver name='qemu' type='raw'/>
                       <source file='%s'/>
                       <target dev='hd%s' bus='ide'/>
                    </disk>
                    """ % (diso, cdromletter)
        cdromletter = chr(ord(cdromletter) + 1)

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
                      <driver name='qemu' type='qcow2' cache='unsafe'/>
                      <source file='%s'/>
                      <target dev='vda' bus='virtio'/>
                    </disk>
                    %s
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
                """ % (domname, qemu_path, domimage,
                       cdroms, dommac, network_driver)

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


def setup_env(domipaddress, domname, tests_dir):
    """Create ansible cmd and run ansible on virtual machine

    :param domipaddress str: ip address of virtual machine
    :param domname str: virtual machine name
    :return: int: 0 if all OK and 1 if not
    """

    retcode = call("ssh-keygen -R " + domname, shell=True)
    if retcode != 0:
        print "Removing old ssh-key for %s failed." % domname
        return 1

    retcode = call("ssh-keygen -R " + domipaddress, shell=True)
    if retcode != 0:
        print "Removing old ssh-key for %s failed." % domipaddress
        return 1

    if domname[0:3] != 'win':
        inv = ANSIBLE_INVENTORY % (domname, domipaddress, REMOTE_ROOT_PASSWORD, REMOTE_PASSWORD, REMOTE_LOGIN)
        ansible_cmd = ANSIBLE_CMD % (os.path.join(tests_dir, ANSIBLE_PLAYBOOK), "paramiko", domname)
    else:
        inv = ANSIBLE_INVENTORY_WIN % (domname, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD)
        ansible_cmd = ANSIBLE_CMD % (os.path.join(tests_dir, ANSIBLE_PLAYBOOK), "winrm", domname)

    with open("static/inventory", "w") as hosts:
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
                  --maxfail=1 --alluredir=reports %s --target=%s' % (tests, reportname, reportname, pcmd, domname)
    else:
        cmd = 'cd /home/test/pg-tests && sudo pytest %s --self-contained-html --html=%s.html ' \
              '--junit-xml=%s.xml --json=%s.json --maxfail=1 --alluredir=reports %s --target=%s' % (tests,
                                                                                                    reportname,
                                                                                                    reportname,
                                                                                                    reportname,
                                                                                                    pcmd, domname)

    if DEBUG:
        cmd += " --verbose --tb=long --full-trace"

    return cmd


def export_results(domname, domipaddress, reportname, operating_system=None, product_name=None,
                   product_version=None, product_edition=None, tests=None):
    if not os.path.exists('reports'):
        os.makedirs('reports')
    allure_reports_dir = "reports/allure_reports/%s/%s/%s/%s/%s" % (time.strftime("/%Y/%m/%d"), product_name,
                                                           product_version, product_edition, operating_system)
    if not os.path.exists(allure_reports_dir):
        os.makedirs(allure_reports_dir)

    # if not os.path.exists('reports/allure_reports'):
    #     os.makedirs('reports/allure_reports')

    if domname[0:3] == 'win':
        copy_file_win(reportname, domipaddress)
    else:
        try:
            copy_file("/home/test/pg-tests/%s.html" % reportname, "reports/%s.html" % reportname, domipaddress)
            copy_file("/home/test/pg-tests/%s.xml" % reportname, "reports/%s.xml" % reportname, domipaddress)
            copy_file("/home/test/pg-tests/%s.json" % reportname, "reports/%s.json" % reportname, domipaddress)
            copy_file("/home/test/pg-tests/reports", allure_reports_dir, domipaddress, dir=True)
            # copy_file("/home/test/pg-tests/reports", "reports/allure_reports", domipaddress, dir=True)
            # copy_file("/home/test/pg-tests/reports", allure_reports_dir,
            #           domipaddress, dir=True, operating_system=operating_system,
            #           product_name=product_name, product_version=product_version,
            #           product_edition=product_edition, tests=tests)
        except IOError as e:
            print("Cannot copy report from virtual machine.")
            print(e)
            pass
        finally:
            subprocess.Popen(
                ['curl', '-T', 'reports/%s.html' % reportname, REPORT_SERVER_URL])
            subprocess.Popen(
                ['curl', '-T', 'reports/%s.xml' % reportname, REPORT_SERVER_URL])
            for file in os.listdir('reports'):
                if '.json' in file:
                    subprocess.Popen(['curl', '-T', os.path.join('reports', file), REPORT_SERVER_URL])
                else:
                    continue


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
        domimage = WORK_DIR + domname + '-overlay.qcow2'
        if os.path.exists(domimage):
            os.remove(domimage)

    conn.close()


def main():

    start = time.time()
    names = list_images()
    parser = argparse.ArgumentParser(
        description='PostgreSQL regression tests run script.',
        epilog='Possible operating systems (images): %s' % ' '.join(names))
    parser.add_argument('--target', dest="target",
                        help='system(s) under test (image(s))')
    parser.add_argument('--test', dest="run_tests", default="tests/",
                        help='tests to run (default: all in tests/)')
    parser.add_argument("--product_name", dest="product_name",
                        help="specify product name", action="store", default="postgrespro")
    parser.add_argument("--product_version", dest="product_version",
                        help="specify product version", action="store", default="9.6")
    parser.add_argument("--product_edition", dest="product_edition",
                        help="specify product edition", action="store")
    parser.add_argument("--product_milestone", dest="product_milestone",
                        help="specify target milestone", action="store", default="beta")
    parser.add_argument("--branch", dest="branch",
                        help="specify product branch for package", action="store")
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

    if not (os.path.exists(args.run_tests)):
        print "Test(s) '%s' is not found." % args.run_tests
        sys.exit(1)
    tests_dir = args.run_tests if os.path.isdir(args.run_tests) else os.path.dirname(args.run_tests)
    prepare_payload(tests_dir)

    targets = target.split(',')
    for t in targets:
        print("Starting target %s..." % t)
        target_start = time.time()
        domname = gen_name(t)
        reportname = "report-" + time.strftime('%Y-%b-%d-%H-%M-%S')
        domipaddress = create_env(t, domname)[0]
        setup_env_result = setup_env(domipaddress, domname, tests_dir)
        if setup_env_result == 0:
            print("Environment deployed without errors. Ready to run tests")
        else:
            sys.exit(1)
        cmd = make_test_cmd(domname, reportname, args.run_tests,
                            args.product_name,
                            args.product_version,
                            args.product_edition,
                            args.product_milestone,
                            args.branch)
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
            retcode, stdout, stderr = exec_command_win(cmd, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD,
                                                       skip_ret_code_check=True)
            # export_results(domname, domipaddress, reportname)
        else:
            retcode, stdout, stderr = exec_command(cmd, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD,
                                                   skip_ret_code_check=True)

        if args.export:
            test = args.run_tests.split('/')[1].split('.')[0]
            export_results(domname, domipaddress, reportname,
                           operating_system=args.target, product_name=args.product_name,
                           product_version=args.product_version, product_edition=args.product_edition,
                           tests=test)
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
            reporturl = os.path.join(REPORT_SERVER_URL, reportname)
            print("Test return code (for target %s) is not zero - %s. "
                  "Please check logs in report: %s" % (t, retcode, reporturl))
            print retcode, stdout, stderr
            sys.exit(1)
        print("Target %s done in %s." %
              (t, time.strftime("%H:%M:%S",
                  time.gmtime(time.time() - target_start))))

    print("Test execution for targets %s finished without errors in %s." %
          (targets, time.strftime("%H:%M:%S",
           time.gmtime(time.time() - start))))


if __name__ == "__main__":
    exit(main())
