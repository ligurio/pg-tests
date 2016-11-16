#!/bin/env python

"""PostgresPro regression tests run script."""

__author__ = "Sergey Bronnikov <sergeyb@postgrespro.ru>"

import argparse
import json
import libvirt
import logging
import os
import os.path
import paramiko
import random
import re
import socket
import shutil
import sys
import time
import urllib
from subprocess import call

IMAGE_BASE_URL = 'http://webdav.l.postgrespro.ru/DIST/vm-images/test/'
TEMPLATE_DIR = '/home/sergeyb/original_vms/'
WORK_DIR = '/vz/working_vms/'
ANSIBLE_PLAYBOOK = 'static/playbook-prepare-env.yml'

SSH_LOGIN = 'test'
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
            if lease['mac'] == mac and lease['iaid'] == None:
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
    transport.connect(username = SSH_LOGIN, password = SSH_PASSWORD)
    sftp = paramiko.SFTPClient.from_transport(transport)
    print "Copying file '%s', remote host is '%s'" % (remote_path, hostname)
    sftp.get(remote_path, local_path)
    sftp.close()
    transport.close()
    client.close()

    # TODO: return exit code

def exec_command(cmd, hostname):

    known_hosts = os.path.expanduser(os.path.join("~", ".ssh", "known_hosts"))
    try:
       client = paramiko.SSHClient()
       if os.path.isfile(known_hosts):
          client.load_system_host_keys(known_hosts)
       client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
       client.connect(hostname=hostname, username=SSH_LOGIN, \
		      password=SSH_PASSWORD, port=SSH_PORT, look_for_keys=False)
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
    client.close()

    return retcode

#######################################################################
# Program body
#######################################################################

def main():

    names = list_images()
    actions = ['suspend', 'nothing', 'undefine']
    parser = argparse.ArgumentParser(description='PostgreSQL regression tests run script.')
    parser.add_argument('--target', dest = "target", choices=names, \
		        help='System under test (image)')
    parser.add_argument('--test', dest = "run_tests", help='Tests to run (default: all)')
    parser.add_argument('--action', dest = "action", choices=actions, \
                        help='What to do with instance in case of test fail (default: suspend)')

    args = parser.parse_args()

    if len(sys.argv) == 1:
       parser.print_help()
       sys.exit(0)

    name = None
    if args.target is not None:
       name = args.target
       if args.run_tests is None:
          tests = '*'
       tests = args.run_tests

    try:
       conn = libvirt.open(None)
    except libvirt.libvirtError, e:
       print 'LibVirt connect error: ', e
       sys.exit(1)

    domname = name + '-' + str(random.getrandbits(15))
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

    # FIXME: use linked clone qemu-img create -f qcow2 -b winxp.qcow2 winxp-clone.qcow2

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
    if dom == None:
       print "Failed to create a test domain"

    domipaddress = None
    timeout = 0
    while not domipaddress:
        timeout = timeout + 5
        print "Waiting for IP address...%d" % timeout
        time.sleep(timeout)
        domipaddress = lookupIPbyMac(conn, dommac)
        if timeout == 40:
           print "Failed to obtain an IP address inside domain"
           sys.exit(1)

    print "Domain name: %s\nIP address: %s" % (dom.name(), domipaddress)

    with open("/etc/hosts", "a") as hosts:
         hosts.write("{}	{}\n".format(domipaddress, dom.name()))

    with open("static/inventory", "a") as hosts:
	 inv = "%s ansible_host=%s ansible_become_pass=%s ansible_ssh_pass=%s \
		ansible_user=%s ansible_become_user=root\n" % \
		(dom.name(), domipaddress, SSH_ROOT_PASSWORD, SSH_PASSWORD, SSH_LOGIN)
         hosts.write(inv)

    os.environ['ANSIBLE_HOST_KEY_CHECKING'] = 'False'
    ansible_cmd = "ansible-playbook %s -i static/inventory -c paramiko --limit %s" % (ANSIBLE_PLAYBOOK, dom.name())
    if DEBUG:
       ansible_cmd = ansible_cmd + " -vvv"
    print ansible_cmd
    call(ansible_cmd.split(' '))

    cmd = 'cd pg-tests && pytest --self-contained-html --html=report-$(date "+%Y%m%d-%H%M.%S").html/ \
				 --failed-first --strict --junit-xml=report-$(date "+%Y%m%d-%H%M.%S").xml'

    if DEBUG:
       cmd = cmd + "--verbose --tb=long --full-trace"

    retcode = exec_command(cmd, domipaddress)

    exec_command("tar cvzf /home/test/archive.tgz /home/test/pg-tests", domipaddress)
    #copy_file("/home/test/archive.tgz", "/root/archive.tgz", domipaddress)
    save_image = os.path.join(WORK_DIR, dom.name() + ".img")

    if retcode <> 0:
       print "Return code is not zero."
       if (args.action == None) or (args.action == 'suspend'):
          if dom.save(save_image) < 0:
             print('Unable to save state of %s to %s' % (dom.name(), save_image))
          print('Domain %s state saved to %s' % (dom.name(), save_image))
       elif args.action == 'undefine':
          if dom.undefine() < 0:
             print('Unable to undefine of %s' % dom.name())
       elif args.action == 'nothing':
          print('Domain %s (IP address %s)' % (dom.name(), domipaddress))
    else:
       dom.undefine()

    conn.close()

if __name__ == "__main__":
    exit(main())
