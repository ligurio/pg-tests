# -*- coding: utf-8 -*-

import platform
import subprocess
import os
import re
import tarfile
import allure

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall, PRELOAD_LIBRARIES
from helpers.os_helpers import DEBIAN_BASED
from helpers.utils import ConsoleEncoding, get_distro, refresh_env_win

PRELOAD_LIBRARIES['ent-cert-11'].remove('passwordcheck')


def get_pg_prefix(pginst):
    cmd = '"%s" --bindir' % os.path.join(pginst.get_default_bin_path(),
                                         'pg_config')
    binpath = subprocess.check_output(cmd, shell=True). \
        decode(ConsoleEncoding).strip()
    pg_prefix = re.sub('bin$', '', binpath)
    return pg_prefix


class TestMakeCheck(object):
    """
    Test that performs 'make installcheck' and 'make check'
    for the installed instance.
    """

    system = platform.system()

    def test_make_check(self, request):
        """
        Scenario:
        1. Install current version
        2. Check that setup successfull

        We need to perform the test on Windows in two stages:
        First we setup the server and prepare environment,
        then we exclude current user from the Administrators group.
        Second we execute `make installcheck` without admin rights.

        :return:
        """
        dist = ""
        if self.system == 'Linux':
            dist = " ".join(get_distro()[0:2])
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
        pgid = '%s-%s' % (edition, version)
        tag_mark = allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        branch = request.config.getoption('--branch')
        # Step 1
        pginst = PgInstall(product=name, edition=edition,
                           version=version, milestone=milestone,
                           branch=branch, windows=(self.system == 'Windows'))
        request.cls.pginst = pginst
        pginst.make_check_passed = False
        curpath = os.path.dirname(os.path.abspath(__file__))
        if pginst.os.is_altlinux() and pginst.os.os_arch == 'aarch64':
            os.environ['LANG'] = 'en_US.UTF-8'

        if self.system == 'Windows':
            if os.path.exists(pginst.get_default_bin_path()):
                # Refresh environment to get correct PYTHONHOME
                refresh_env_win()
                # The instance is already installed and
                # installcheck environment is presumably prepared,
                # so just run make_installcheck (once more)
                subprocess.check_call(
                    '"%s" "%s" "%s"' % (
                        os.path.join(curpath, 'make_installcheck.cmd'),
                        get_pg_prefix(pginst), pginst.service_name),
                    shell=True)
                pginst.make_check_passed = True
                return

        pginst.setup_repo()
        print("Running on %s." % target)
        tarball = pginst.download_source()
        tar = tarfile.open(tarball, 'r:bz2')
        tar.extractall()
        tar.close()
        for comp in ['orafce', 'plv8', 'pgpro-stats', 'pgpro-pwr',
                     'pgpro-controldata', 'pg-filedump', 'pg-portal-modify',
                     'pg-repack']:
            pkgname = '%s-%s-%s' % (comp, edition, version)
            if pkgname not in pginst.get_packages_in_repo():
                pkgname = comp
                if pkgname not in pginst.get_packages_in_repo():
                    continue
            pginst.download_source(
                comp.replace('-', '_'),
                pginst.get_package_version(pkgname), 'tar.gz')
        if self.system != 'Windows':
            pginst.install_full()
            pginst.initdb_start()
        else:
            pginst.install_perl_win()
            pginst.install_postgres_win(port=55432)
            try:
                pginst.exec_psql('CREATE EXTENSION plpython3u')
            except Exception:
                subprocess.check_call('SETX PYTHONHOME C:\\Python27 -m',
                                      shell=True)
        if version != "9.6" or self.system == 'Windows' or \
                (edition == '1c' and pginst.os_name not in DEBIAN_BASED):
            buildinfo = os.path.join(pginst.get_pg_prefix(),
                                     'doc', 'buildinfo.txt')
        else:
            buildinfo = subprocess.check_output(
                'ls /usr/share/doc/postgres*pro*/buildinfo.txt',
                shell=True).decode(ConsoleEncoding).strip()

        with open(buildinfo, 'r') as bi:
            bitxt = bi.read()
            assert(re.search(r'^Documentation translation', bitxt,
                             re.MULTILINE))
            assert(re.search(r'^Source', bitxt, re.MULTILINE))
            assert(re.search(r'^SPEC', bitxt, re.MULTILINE))
            print("The binary package buildinfo:\n%s\n" % bitxt)

        pginst.install_default_config()

        pginst.exec_psql("ALTER SYSTEM SET max_worker_processes = 16")
        pginst.exec_psql("ALTER SYSTEM SET lc_messages = 'C'")
        # Prepare pg_hba.conf for src/interfaces/ecpg/test/connect/test5
        with open(os.path.join(pginst.get_configdir(), 'pg_hba.conf'),
                  'r+') as conf:
            hba = re.sub(r'^(local\s+all\s+all\s+peer)$',
                         "local all regress_ecpg_user1  md5\n"
                         "local all regress_ecpg_user2  md5\n"
                         "local all regress_hacker trust\n"
                         "local all regress_superuser trust\n"
                         "local all nosuper trust\n"
                         r'\1', conf.read(), flags=re.MULTILINE)
            conf.seek(0)
            conf.write(hba)
        pginst.load_shared_libraries(restart_service=False)
        pginst.restart_service()
        if self.system != 'Windows':
            subprocess.check_call(
                '"%s" "%s" "%s"' % (
                    os.path.join(curpath, 'make_installcheck.sh'),
                    get_pg_prefix(pginst), pginst.service_name),
                shell=True)
            pginst.make_check_passed = True
        else:
            # First run is performed to setup the environment
            subprocess.check_call(
                '"%s" "%s" "%s"' % (
                    os.path.join(curpath, 'make_installcheck.cmd'),
                    get_pg_prefix(pginst), pginst.service_name),
                shell=True)
            request.session.customexitstatus = 222

    def test_sqlsmith(self, request):
        pginst = request.cls.pginst
        if not pginst.make_check_passed:
            return
        pginst.exec_psql("CREATE ROLE tester LOGIN PASSWORD 'test'")
        pginst.exec_psql("GRANT ALL ON DATABASE regression TO tester")
        pginst.exec_psql("REVOKE EXECUTE ON FUNCTION"
                         " pg_catalog.pg_terminate_backend(int) FROM PUBLIC",
                         "-d regression")
        pg_prefix = pginst.get_default_pg_prefix()
        curpath = os.path.dirname(os.path.abspath(__file__))
        if self.system == 'Windows':
            print("sqlsmith is not supported on Windows")
            return
        subprocess.check_call(
            '"%s" "%s"' % (os.path.join(curpath, 'sqlsmith.sh'),
                           pg_prefix),
            shell=True)
