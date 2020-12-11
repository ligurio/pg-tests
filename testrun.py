#!/usr/bin/env python3
""" Copyright 2015 - 2020 Postgres Professional """

import argparse
import os
import os.path
import distro
import random
import re
import shutil
import subprocess
import sys
import time
import tempfile
import glob
from multiprocessing import Pipe, Process
from subprocess import call

from helpers.utils import (copy_file, copy_reports_win,
                           exec_command, gen_name, exec_retry,
                           exec_command_win, wait_for_boot,
                           REMOTE_LOGIN, REMOTE_PASSWORD,
                           REMOTE_ROOT_PASSWORD, is_remote_file_differ,
                           urlcontent, urlretrieve)

# py2compat
if not sys.version_info > (3, 0):
    # pylint: disable = undefined-variable
    reload(sys)
    # pylint: disable = no-member
    sys.setdefaultencoding('utf8')

MAX_DURATION = 5 * 60 * 60
DEBUG = False

IMAGE_BASE_URL = 'http://dist.l.postgrespro.ru/vm-images/test/'
TEMPLATE_DIR = '/pgpro/templates/'
WORK_DIR = '/pgpro/test-envs/'
ANSIBLE_CMD = "ansible-playbook %s -i static/inventory -c %s --limit %s"
ANSIBLE_PLAYBOOK = 'playbook-prepare-env.yml'
ANSIBLE_INVENTORY = "%s ansible_host=%s \
                    ansible_become_pass=%s \
                    ansible_ssh_pass=%s \
                    ansible_user=%s \
                    ansible_become_user=root\n"
ANSIBLE_INVENTORY_SSH = "%s ansible_host=%s \
                    ansible_user=%s \
                    ansible_become_user=root\n"
ANSIBLE_INVENTORY_WIN = "%s ansible_host=%s \
                    ansible_user=%s  \
                    ansible_password=%s \
                    ansible_winrm_server_cert_validation=ignore  \
                    ansible_port=5985  \
                    ansible_connection=winrm \
                    ansible_winrm_read_timeout_sec=90 \
                    ansible_winrm_operation_timeout_sec=60 \
                    \n"

REPORT_SERVER_URL = 'http://testrep.l.postgrespro.ru/'
TESTS_PAYLOAD_DIR = 'resources'
TESTS_PAYLOAD_TAR = 'pg-tests.tgz'
TESTS_PAYLOAD_ZIP = 'pg-tests.zip'


def list_images():
    names = []
    page = ''
    try:
        page = urlcontent(IMAGE_BASE_URL, retry_cnt=1)
    except IOError:
        for f in os.listdir(TEMPLATE_DIR):
            fp = os.path.splitext(f)
            if fp[1] == '.qcow2':
                names.append(fp[0])
        return sorted(names)
    images = re.findall(r'''href=['"]?([^'" >]+)\.qcow2''', page)
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


def get_dom_disk(domname):
    return os.path.join(WORK_DIR, domname + '-overlay.qcow2')


def create_image(domname, name):

    domimage = get_dom_disk(domname)
    image_url = IMAGE_BASE_URL + name + '.qcow2'
    image_original = TEMPLATE_DIR + name + '.qcow2'

    if os.path.isfile(image_original) and \
            is_remote_file_differ(image_url, image_original):
        print('Remote image differs with local, erasing it...')
        os.remove(image_original)

    if not os.path.isfile(image_original):
        if not os.path.exists(TEMPLATE_DIR):
            os.makedirs(TEMPLATE_DIR)
        print("Downloading %s.qcow2..." % name)
        try:
            urlretrieve(image_url, image_original)
        except Exception as e:
            print("Could not retrieve %s." % image_url)
            raise e

    page = ''
    try:
        page = urlcontent(IMAGE_BASE_URL, retry_cnt=1)
    except IOError:
        print("%s is not available, no *.iso will be downloaded." %
              IMAGE_BASE_URL)
    isos = re.findall(r'''href=['"]?([^'" >]+)\.iso"''', page)
    for isoname in isos:
        if isoname.startswith(name):
            iso_url = IMAGE_BASE_URL + isoname + '.iso'
            target_iso = TEMPLATE_DIR + isoname + '.iso'
            if not os.path.isfile(target_iso):
                print("Downloading %s.iso..." % isoname)
                urlretrieve(iso_url, target_iso)

    if not os.path.exists(WORK_DIR):
        os.makedirs(WORK_DIR)

    retcode = call("qemu-img create -b %s -f qcow2 -F qcow2 %s" %
                   (image_original, domimage), shell=True)
    if retcode != 0:
        raise Exception("Could not create qemu image.")

    return domimage


def prepare_payload(tests_dir, clean):
    rsrcdir = os.path.join(tests_dir, TESTS_PAYLOAD_DIR)
    tar_path = os.path.join(rsrcdir, TESTS_PAYLOAD_TAR)
    zip_path = os.path.join(rsrcdir, TESTS_PAYLOAD_ZIP)
    if clean:
        if os.path.isdir(rsrcdir):
            shutil.rmtree(rsrcdir)
    while True:
        if os.path.isdir(rsrcdir):
            timeout = 0
            while not os.path.exists(tar_path) or \
                    not os.path.exists(zip_path):
                timeout += 5
                if timeout == 60:
                    raise Exception('Could not find tar and zip in "%s".' %
                                    rsrcdir)
                print("Waiting for parallel tar and zip creation...%d" %
                      timeout)
                time.sleep(timeout)
            return
        try:
            os.makedirs(rsrcdir)
        except OSError as exc:
            if os.path.exists(rsrcdir):
                continue
            raise exc
        break

    print("Preparing a payload for target VMs...")
    tempdir = tempfile.mkdtemp()
    pgtd = os.path.join(tempdir, 'pg-tests')
    shutil.copytree('.', pgtd,
                    ignore=shutil.ignore_patterns('.git', 'reports'))
    exec_retry("wget -q https://bootstrap.pypa.io/get-pip.py", pgtd,
               'Downloading get-pip')

    exec_retry(
        "wget -T 60 -q https://codeload.github.com/postgrespro/"
        "pg_wait_sampling/tar.gz/master -O extras/pg_wait_sampling.tar.gz",
        pgtd, 'Downloading pg_wait_sampling')

    exec_retry(
        "wget -T 60 -q https://codeload.github.com/Test-More/"
        "test-more/tar.gz/v0.90 -O extras/test-more.tar.gz",
        pgtd, 'Downloading test-more')

    retcode = call("zip -q -x '*.pyc' -r _%s pg-tests" %
                   TESTS_PAYLOAD_ZIP, cwd=tempdir, shell=True)
    if retcode != 0:
        raise Exception("Preparing zip payload failed.")

    # Preparing pip packages for linux with 2 python
    pgtdpp = os.path.join(pgtd, 'pip-packages')
    os.makedirs(pgtdpp)
    exec_retry(
        "pip2 download -q -r %s" %
        os.path.abspath(os.path.join(tests_dir, "requirements2.txt")),
        pgtdpp, 'Download python2 requirements'
    )
    exec_retry(
        "pip2 download -q --no-deps --only-binary=:all:"
        " --platform manylinux1_x86_64 --python-version 27"
        " --implementation cp --abi cp27m  -r %s" %
        os.path.abspath(os.path.join(tests_dir, "requirements-bin.txt")),
        pgtdpp, "Downloading pip-requirements(27m)")
    exec_retry(
        "pip2 download -q --no-deps --only-binary=:all:"
        " --platform manylinux1_x86_64 --python-version 27"
        " --implementation cp --abi cp27mu  -r %s" %
        os.path.abspath(os.path.join(tests_dir, "requirements-bin.txt")),
        pgtdpp, "Downloading pip-requirements(27mu)")

    retcode = call("tar -czf _%s --exclude='*.pyc' pg-tests" %
                   TESTS_PAYLOAD_TAR, cwd=tempdir, shell=True)
    if retcode != 0:
        raise Exception("Preparing tar payload failed.")
    # First move to the target directory to prepare for atomic rename
    #  (if tempdir is on different filesystem)
    shutil.move(os.path.join(tempdir, '_' + TESTS_PAYLOAD_ZIP), rsrcdir)
    shutil.move(os.path.join(tempdir, '_' + TESTS_PAYLOAD_TAR), rsrcdir)

    # Atomic rename
    os.rename(os.path.join(rsrcdir, '_' + TESTS_PAYLOAD_ZIP), zip_path)
    os.rename(os.path.join(rsrcdir, '_' + TESTS_PAYLOAD_TAR), tar_path)
    shutil.rmtree(tempdir)

    # Clear inventory
    try:
        os.remove('static/inventory')
    except OSError:
        pass


def create_env(name, domname, domimage=None, mac=None):
    import libvirt
    conn = libvirt.open(None)

    if not domimage:
        domimage = create_image(domname, name)
    dommac = mac if mac else mac_address_generator()
    qemu_path = ""
    if distro.linux_distribution()[0] == 'Ubuntu' or \
       distro.linux_distribution(False)[0] == 'debian':
        qemu_path = "/usr/bin/qemu-system-x86_64"
    elif distro.linux_distribution()[0] == 'CentOS Linux':
        qemu_path = "/usr/libexec/qemu-kvm"
    if name[0:3] == 'win':
        network_driver = "e1000"
        ram_size = 2048
        cpus = 4
        features = """
        <hyperv>
          <relaxed state='on'/>
          <vapic state='on'/>
          <spinlocks state='on' retries='8191'/>
        </hyperv>"""
        clock = """
        <clock offset='localtime'>
          <timer name='hypervclock' present='yes'/>
          <timer name='hpet' present='no'/>
        </clock>"""
    else:
        network_driver = "virtio"
        ram_size = 2048
        cpus = 2
        features = ""
        clock = "<clock offset='utc'/>"
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
                  <memory unit='MB'>%d</memory>
                  <vcpu>%d</vcpu>
                  <os>
                    <type>hvm</type>
                    <boot dev='hd'/>
                  </os>
                  <features>
                    <acpi/>
                    %s
                  </features>
                  <cpu mode='host-passthrough' check='none'>
                    <topology sockets='1' cores='%d' threads='1'/>
                  </cpu>
                  %s
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
                    <channel type='unix'>
                      <source mode="bind"/>
                      <target type='virtio' name='org.qemu.guest_agent.0'/>
                    </channel>
                    <!--rng model='virtio'>
                      <backend model='random'>/dev/random</backend>
                      <address type='pci' domain='0x0000'
                      bus='0x00' slot='0x06' function='0x0'/>
                    </rng-->
                  </devices>
                </domain>
                """ % (domname, ram_size, cpus, features, cpus, clock,
                       qemu_path, domimage, cdroms, dommac, network_driver)

    dom = conn.createLinux(xmldesc, 0)
    if dom is None:
        print("Failed to create a test domain")

    timeout = 0
    while True:
        domipaddress = lookupIPbyMac(conn, dommac)
        if domipaddress:
            break
        timeout += 5
        if timeout > 80:
            raise Exception(
                "Failed to obtain IP address (for MAC %s) in domain %s." %
                (dommac, domname))
        print("Waiting for IP address...%d" % timeout)
        time.sleep(timeout)

    print("Domain name: %s\nIP address: %s, MAC address: %s" % (dom.name(),
                                                                domipaddress,
                                                                dommac))
    conn.close()
    if name[0:3] != 'win':
        # We don't use SSH on Windows
        retcode = call("ssh-keygen -R " + domname,
                       stderr=subprocess.STDOUT, shell=True)
        if retcode != 0:
            raise Exception("Could not remove old ssh key for %s." %
                            domname)

        retcode = call("ssh-keygen -R " + domipaddress,
                       stderr=subprocess.STDOUT, shell=True)
        if retcode != 0:
            raise Exception("Could not remove old ssh key for %s." %
                            domipaddress)

    return domipaddress, domimage, xmldesc, dommac


def setup_env(domipaddress, domname, linux_os, tests_dir, target_ssh=False):
    """Create ansible cmd and run ansible on virtual machine

    :param domipaddress str: ip address of virtual machine
    :param domname str: virtual machine name
    :return: int: 0 if all OK and 1 if not
    """

    if target_ssh:
        inv = ANSIBLE_INVENTORY_SSH % (domname, domipaddress, REMOTE_LOGIN)
        ansible_cmd = ANSIBLE_CMD % (
            os.path.join(tests_dir, ANSIBLE_PLAYBOOK), "paramiko", domname)
        ansible_cmd += ' --extra-vars use_ssh=1'
    elif linux_os:
        inv = ANSIBLE_INVENTORY % (domname, domipaddress,
                                   REMOTE_ROOT_PASSWORD,
                                   REMOTE_PASSWORD,
                                   REMOTE_LOGIN)
        ansible_cmd = ANSIBLE_CMD % (
            os.path.join(tests_dir, ANSIBLE_PLAYBOOK), "paramiko", domname)
    else:
        inv = ANSIBLE_INVENTORY_WIN % (domname, domipaddress,
                                       REMOTE_LOGIN,
                                       REMOTE_PASSWORD)
        ansible_cmd = ANSIBLE_CMD % (
            os.path.join(tests_dir, ANSIBLE_PLAYBOOK), "winrm", domname)

    with open("static/inventory", "a") as hosts:
        hosts.write(inv)

    os.environ['ANSIBLE_HOST_KEY_CHECKING'] = 'False'

    if DEBUG:
        ansible_cmd += " -vvv"
    print(ansible_cmd)
    retcode = call(ansible_cmd.split(' '))
    if retcode != 0:
        raise Exception("Setup of the test environment %s failed." % domname)


def make_test_cmd(domname, linux_os, reportname, tests=None,
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

    pytest_cmd = 'pytest {0} --self-contained-html --html={1}.html ' \
                 '--junit-xml={1}.xml --json={1}.json --maxfail=1 ' \
                 '--alluredir=reports {2} --target={3}'.format(
                     tests, reportname, pcmd, domname)
    if not linux_os:
        cmd = r'cd C:\Users\test\pg-tests && ' + \
              r'set PYTHONHOME=C:\Python38&&' + \
              'set PYTHONIOENCODING=UTF-8 && ' + pytest_cmd
    else:
        cmd = "cd /home/test/pg-tests && " + \
            "sudo sh -c 'PYTHONIOENCODING=UTF-8 " + pytest_cmd + "'"

    if DEBUG:
        cmd += " --verbose --tb=long --full-trace"

    return cmd


def export_results(domname, linux_os, domipaddress, reportname,
                   operating_system=None,
                   product_name=None, product_version=None,
                   product_edition=None, tests=None):
    if not os.path.exists('reports'):
        os.makedirs('reports')
        subprocess.check_call('chmod 777 reports', shell=True)
    rel_allure_reports_dir = "allure_reports/%s/%s/%s/%s/%s" % (
        time.strftime("/%Y/%m/%d"), product_name,
        product_version, product_edition, operating_system)
    allure_reports_dir = 'reports/' + rel_allure_reports_dir
    if not os.path.exists(allure_reports_dir):
        os.makedirs(allure_reports_dir)
        subprocess.check_call('chmod 777 %s' % allure_reports_dir, shell=True)

    try:
        if not linux_os:
            copy_reports_win(reportname, rel_allure_reports_dir, 'reports',
                             domipaddress)
        else:
            copy_file("/home/test/pg-tests/%s.html" % reportname,
                      "reports/%s.html" % reportname, domipaddress)
            copy_file("/home/test/pg-tests/%s.xml" % reportname,
                      "reports/%s.xml" % reportname, domipaddress)
            copy_file("/home/test/pg-tests/%s.json" % reportname,
                      "reports/%s.json" % reportname, domipaddress)
            copy_file("/home/test/pg-tests/reports", allure_reports_dir,
                      domipaddress, dir=True)
    except IOError as e:
        print("Cannot copy report from virtual machine.")
        print(e)
        pass
    finally:
        reporturl = os.path.join(REPORT_SERVER_URL,
                                 reportname.replace('#', '%23'))
        if (os.path.exists('reports/%s.html' % reportname)):
            subprocess.call(
                ['curl', '-s', '-S', '-o', '/dev/null',
                 '-T', 'reports/%s.html' % reportname,
                 REPORT_SERVER_URL])
            print("Link to the html report: %s.html" % reporturl)
        if (os.path.exists('reports/%s.xml' % reportname)):
            subprocess.call(
                ['curl', '-s', '-S', '-o', '/dev/null',
                 '-T', 'reports/%s.xml' % reportname,
                 REPORT_SERVER_URL])
            print("Link to the xml report: %s.xml" % reporturl)
        if (os.path.exists('reports/%s.json' % reportname)):
            subprocess.call(
                ['curl', '-s', '-S', '-o', '/dev/null',
                 '-T', 'reports/%s.json' % reportname,
                 REPORT_SERVER_URL])
            print("Link to the json report: %s.json" % reporturl)
        sys.stdout.flush()


def save_env(domname):
    import libvirt
    conn = libvirt.open(None)
    dom = conn.lookupByName(domname)
    print('Shutting target down...')
    sdFlags = 2  # Preferred mode -- VIR_DOMAIN_SHUTDOWN_GUEST_AGENT
    try:
        if dom.shutdownFlags(sdFlags) < 0:
            raise Exception('Unable to shutdown %s.' % domname)
    except libvirt.libvirtError:
        sdFlags = 1  # Fallback mode -- VIR_DOMAIN_SHUTDOWN_ACPI_POWER_BTN
        if dom.shutdownFlags(sdFlags) < 0:
            raise Exception('Unable to shutdown %s.' % domname)
    timeout = 0
    while True:
        timeout += 5
        try:
            print("Waiting for domain shutdown...%d" % timeout)
            time.sleep(timeout)
            if not dom.isActive():
                break
            dom.shutdownFlags(sdFlags)
        except libvirt.libvirtError:
            break
        if timeout == 60:
            raise Exception('Could not shutdown domain %s.' % domname)
    conn.close()
    diskfile = get_dom_disk(domname)
    shutil.copy(diskfile, diskfile + '.s0')


def restore_env(domname):
    import libvirt
    conn = libvirt.open(None)
    try:
        dom = conn.lookupByName(domname)
        dom.destroy()
    except libvirt.libvirtError:
        pass
    conn.close()

    diskfile = get_dom_disk(domname)
    os.remove(diskfile)
    print('Restoring target...')
    shutil.copy(diskfile + '.s0', diskfile)


def close_env(domname, saveimg=False, destroys0=False):
    if domname.find('@') != -1:
        return
    import libvirt
    conn = libvirt.open(None)
    dom = conn.lookupByName(domname)
    imgfile = os.path.join(WORK_DIR, domname + '.img')

    if saveimg:
        if dom.save(imgfile) < 0:
            print('Unable to save state of %s to %s.' % (domname, imgfile))
        else:
            print('Domain %s state saved to %s.' % (domname, imgfile))
    else:
        timeout = 0
        print('Destroying domain...')
        while True:
            # To workaround: libvirt.libvirtError: Failed to terminate \
            #   process PID with SIGKILL: Device or resource busy
            try:
                if dom.destroy() == 0:
                    break
            except libvirt.libvirtError:
                pass
            timeout += 5
            if timeout == 60:
                raise Exception('Unable to destroy %s.' % domname)
            time.sleep(timeout)
            try:
                dom = conn.lookupByName(domname)
            except libvirt.libvirtError:
                break

        diskfile = get_dom_disk(domname)
        os.remove(diskfile)
        if destroys0:
            if os.path.exists(diskfile + '.s0'):
                os.remove(diskfile + '.s0')

    conn.close()


def log(s):
    print(time.strftime("%H:%M:%S: " + str(s)))


def main(conn):
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
                        help="specify product name", action="store",
                        default="postgrespro")
    parser.add_argument("--product_version", dest="product_version",
                        help="specify product version", action="store",
                        default="10")
    parser.add_argument("--product_edition", dest="product_edition",
                        help="specify product edition", action="store")
    parser.add_argument("--product_milestone", dest="product_milestone",
                        help="specify target milestone", action="store")
    parser.add_argument("--branch", dest="branch",
                        help="specify product branch for package",
                        action="store")
    parser.add_argument('--keep', dest="keep", action='store_true',
                        help='what to do with env after testing')
    parser.add_argument('--export', dest="export",
                        help='export results', action='store_true')
    parser.add_argument('--clean', dest="clean",
                        help='clean resources before run', action='store_true')
    parser.add_argument('--vm_prefix', dest="vm_prefix",
                        help='virtual machine prefix', action='store',
                        default="pgt")

    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.target is None:
        print("No target name")
        sys.exit(1)

    if not os.path.exists(args.run_tests):
        print("Test(s) '%s' is not found." % args.run_tests)
        sys.exit(1)
    tests = []
    for test in args.run_tests.split(','):
        if os.path.isdir(test):
            for tf in os.listdir(test):
                if tf.startswith('test') and tf.endswith('.py'):
                    tests.append(os.path.join(test, tf))
        else:
            tests.append(test)
    if not tests:
        print("No tests scripts found in %s." % args.run_tests)
        sys.exit(1)

    tests_dir = args.run_tests if os.path.isdir(args.run_tests) else \
        os.path.dirname(args.run_tests)
    prepare_payload(tests_dir, args.clean)

    targets = args.target.split(',')
    for target in targets:
        dommac = None
        target_ssh = "@" in target
        if target_ssh:
            print("Assuming target %s as ssh..." % target)
            domname, domipaddress = target.split('@')
            if domname == '':
                domname = 'remote-test'
            domname += '@ssh'
            linux_os = True
            target_start = time.time()
            setup_env(domipaddress, domname, linux_os, tests_dir, target_ssh)
        else:
            print("Starting target %s..." % target)
            linux_os = target[0:3] != 'win'
            target_start = time.time()
            domname = gen_name(target, args.vm_prefix)
            conn.send([domname, args.keep])
            try:
                dom = create_env(target, domname)
                domipaddress = dom[0]
                dommac = dom[3]
                setup_env(domipaddress, domname, linux_os, tests_dir)
            except Exception as e:
                # Don't leave a domain that is failed to setup running
                try:
                    close_env(domname, saveimg=False, destroys0=True)
                except Exception:
                    pass
                raise e
            print("Environment deployed without errors. Ready to run tests")
            if len(tests) > 1:
                save_env(domname)

        for test in sorted(tests):
            print("Performing test %s..." % test)
            testname = test.split('/')[1].split('.')[0]
            if len(tests) > 1 and not target_ssh:
                print("Restoring environment (%s)..." % domname)
                restore_env(domname)
                try:
                    print("Creating environment (%s, %s)..." %
                          (target, domname))
                    domipaddress = create_env(
                        target, domname, get_dom_disk(domname), dommac)[0]
                    print("Waiting for boot (%s)..." % domipaddress)
                    wait_for_boot(domipaddress, linux=linux_os)
                    print("Boot completed.")
                except Exception as e:
                    # Don't leave a domain that is failed to boot running
                    try:
                        close_env(domname, saveimg=False, destroys0=True)
                    except Exception:
                        pass
                    raise e
            stage = 0
            while True:
                reportname = "report-%s_%s%s_%s" % (
                    target,
                    testname,
                    '' if stage == 0 else ('#%d' % (stage + 1)),
                    time.strftime('%Y-%m-%d-%H-%M-%S'))
                cmd = make_test_cmd(
                    domname, linux_os, reportname, test,
                    args.product_name,
                    args.product_version,
                    args.product_edition,
                    args.product_milestone,
                    args.branch)
                if DEBUG:
                    print("Test command:\n%s" % cmd)
                log("Test %s%s started..." % (
                    testname,
                    '' if stage == 0 else ' (stage %d)' % (stage + 1)))
                sys.stdout.flush()
                try:
                    if not linux_os:
                        retcode, stdout, stderr = exec_command_win(
                            cmd, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD,
                            skip_ret_code_check=True)
                    else:
                        retcode, stdout, stderr = exec_command(
                            cmd, domipaddress, REMOTE_LOGIN, REMOTE_PASSWORD,
                            skip_ret_code_check=True)
                    if args.export:
                        export_results(
                            domname, linux_os, domipaddress, reportname,
                            operating_system=target,
                            product_name=args.product_name,
                            product_version=args.product_version,
                            product_edition=args.product_edition,
                            tests=testname)
                except Exception as ex:
                    log("Test execution failed.")
                    if not args.keep:
                        try:
                            close_env(domname, False, True)
                        except Exception:
                            pass
                    raise ex
                log("Test ended.")

                if retcode == 222:
                    stage += 1
                    continue

                if retcode != 0:
                    if not args.keep:
                        close_env(domname, saveimg=False, destroys0=True)
                    reporturl = os.path.join(REPORT_SERVER_URL, reportname)
                    print("Test (for target: %s, domain: %s,"
                          " IP address: %s) returned error: %d.\n" %
                          (target, domname, domipaddress, retcode))
                    print(stdout)
                    print(stderr)
                    sys.exit(1)
                break

        if not args.keep or len(tests) > 1:
            close_env(domname, saveimg=False, destroys0=True)

        print("Target %s done in %s." %
              (target, time.strftime(
                  "%H:%M:%S",
                  time.gmtime(time.time() - target_start))))

    print("Test execution for targets %s finished without errors in %s." %
          (targets, time.strftime("%H:%M:%S",
                                  time.gmtime(time.time() - start))))


if __name__ == "__main__":
    parent_conn, child_conn = Pipe()
    p = Process(target=main, args=(child_conn,))
    p.daemon = True
    p.start()
    start_time = time.time()
    while True:
        time.sleep(0.1)
        if p.is_alive():
            if time.time() - start_time >= MAX_DURATION:
                domname, keep = parent_conn.recv()
                p.terminate()
                if not keep:
                    try:
                        close_env(domname, False, True)
                    except Exception:
                        pass
                raise Exception('Timed out')
        else:
            exit(p.exitcode)
