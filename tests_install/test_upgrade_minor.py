import os
import platform
import subprocess
import urllib
import re
import tempfile
import pytest
from allure_commons.types import LabelType
from helpers.pginstall import PgInstall, PRELOAD_LIBRARIES, DEBIAN_BASED,\
    SUSE_BASED
from helpers.pginstall import PGPRO_ARCHIVE_STANDARD, PGPRO_ARCHIVE_ENTERPRISE
from BeautifulSoup import BeautifulSoup
from helpers.utils import diff_dbs, download_dump

tempdir = tempfile.gettempdir()

# 9.6 stable, 10 stable, 11std stable does not contains pg_pageprep
PRELOAD_LIBRARIES['std-9.6'].remove('pg_pageprep')
PRELOAD_LIBRARIES['ent-9.6'].remove('pg_pageprep')
PRELOAD_LIBRARIES['std-10'].remove('pg_pageprep')
PRELOAD_LIBRARIES['ent-10'].remove('pg_pageprep')
PRELOAD_LIBRARIES['std-11'].remove('pg_pageprep')

ARCHIVE_VERSIONS = {
    'ALT Linux  7.0.5': {
        'std-9.6': '9.6.9.1',
        'ent-9.6': None,
        'ent-10': None
    },
    'ALT Linux  6.0.1': {
        'ent-9.6': None,
        'ent-10': None
    },
    # Wait for 9.6.13 for ALT 8.0
    'ALT  8.0': {
        'std-9.6': None,
        'ent-9.6': None,
        'std-10': '10.6.1',
        'ent-10': '10.6.1'
    },
    'ALT Linux  7.0.4': {
        'ent-9.6': None,
        'ent-10': '10.6.1'
    },
    '"AstraLinuxSE" 1.5': {
        'ent-9.6': None
    },
    '"AstraLinuxSE" 1.5.28': {
        'std-9.6': '9.6.11.1',
        'std-10': None,
        'ent-9.6': '10.6.1',
        'ent-10': '10.6.2'
    },
    'CentOS 6.7': {
        'ent-9.6': '9.6.8.1',
        'ent-10': '10.2.1'
    },
    'CentOS Linux 7.2.1511': {
        'ent-9.6': '9.6.9.1'
    },
    'debian 9.0': {
        'std-9.6': '9.6.10.2'
    },
    'GosLinux 6.4': {
        'std-9.6': None,
        'ent-9.6': None,
        'ent-10': None
    },
    'GosLinux 7.08': {
        'std-9.6': None,
        'std-10': '10.6.1',
        'ent-9.6': None,
        'ent-10': None
    },
    'Oracle Linux Server 6.7': {
        'ent-9.6': None,
        'ent-10': None
    },
    'Oracle Linux Server 7.2': {
        'ent-9.6': '9.6.8.1',
        'ent-10': '10.2.1'
    },
    'RED OS release MUROM ( 7.1': {
        'std-9.6': '9.6.11.1',
        'std-10': '10.6.1',
        'ent-9.6': None,
        'ent-10': None
    },
    'Red Hat Enterprise Linux Server 6.7': {
        'ent-9.6': None,
        'ent-10': None
    },
    'Red Hat Enterprise Linux Server 7.5': {
        'ent-9.6': '9.6.8.1',
        'ent-10': '10.3.1'
    },
    'ROSA Enterprise Linux Server 6.6': {
        'ent-10': '10.2.1'
    },
    'ROSA Enterprise Linux Cobalt 7.3': {
        'ent-9.6': '9.6.9.1',
        'ent-10': '10.6.1'
    },
    'SUSE Linux Enterprise Server  11': {
        'ent-10': None
    },
    'SUSE Linux Enterprise Server  12': {
        'ent-10': None
    },
    'Ubuntu 18.10': {
        'std-9.6': '9.6.11.1',
        'std-10': None,
        'ent-9.6': None,
        'ent-10': None
    },
    'Ubuntu 18.04': {
        'std-9.6': '9.6.10.2',
        'std-10': '10.2.1',
        'ent-9.6': '9.6.7.1'
    },
    'Ubuntu 19.04': {
        'std-9.6': None,
        'std-10': None,
        'ent-9.6': None,
        'ent-10': None,
        'std-11': None
    },
    'AlterOS 7.5': {
        'std-9.6': None,
        'std-10': None,
        'ent-9.6': None,
        'ent-10': None,
        'std-11': None
    },
    'SUSE Linux Enterprise Server  15': {
        'std-9.6': None,
        'std-10': None,
        'ent-9.6': None,
        'ent-10': None,
        'std-11': None
    },
    '"AstraLinuxCE" 2.12.7': {
        'std-9.6': None,
        'std-10': None,
        'ent-9.6': None,
        'ent-10': None,
        'std-11': None
    }
}


def get_test_versions(edition, version):

    if edition == "ent":
        archive_url = PGPRO_ARCHIVE_ENTERPRISE
    elif edition == "std":
        archive_url = PGPRO_ARCHIVE_STANDARD
    else:
        raise Exception("Unsupported postgrespro edition (%s)." % edition)

    # Choose two versions -- newest and oldest supported
    soup = BeautifulSoup(urllib.urlopen(archive_url))
    arcversions = []
    for link in soup.findAll('a'):
        href = link.get('href')
        if href.startswith('pgpro') and href.endswith('/'):
            vere = re.search(r'\w+-([0-9.]+)/', href)
            if vere:
                if vere.group(1).startswith(version):
                    arcvers = vere.group(1).split('.')
                    arcversion = '.'.join([d.rjust(4) for d in arcvers])
                    if version == '9.6':
                        # Due to CATALOG_VERSION_NO change
                        # we don't support lower 9.6 versions
                        if arcversion < '   9.   6.   4.   1':
                            arcversion = None
                    if arcversion:
                        arcversions.append(arcversion)
    arcversions.sort()
    if not arcversions:
        return None

    # Choose first and last versions
    if len(arcversions) > 2:
        return [arcversions[0].replace(' ', ''),
                arcversions[-2].replace(' ', '')]
    else:
        return [arcversions[0].replace(' ', '')]


def dumpall(pg, file):
    cmd = '%s"%spg_dumpall" -f "%s"' % \
          (
              pg.pg_preexec,
              os.path.join(tempdir, "client", "bin", ""),
              file
          )
    subprocess.check_call(cmd, shell=True)


@pytest.mark.upgrade_minor
class TestUpgradeMinor():

    system = platform.system()

    @pytest.mark.upgrade_minor
    def test_upgrade_minor(self, request):
        """
        Scenario:
        1. Install current version
        2. Check that setup successfull (select version)

        :return:
        """
        global windows_os
        if self.system == 'Linux':
            dist = " ".join(platform.linux_distribution()[0:2])
            windows_os = False
        elif self.system == 'Windows':
            dist = 'Windows'
            windows_os = True
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

        if name != 'postgrespro':
            print("Minor upgrade test is only for postgrespro.")
            return

        small_key = "-".join([edition, version])
        test_versions = get_test_versions(edition, version)
        if test_versions is None:
            print("No previous versions found.")
            return

        if dist in ARCHIVE_VERSIONS \
                and small_key in ARCHIVE_VERSIONS[dist]:
            first = ARCHIVE_VERSIONS[dist][small_key]
            if first is None:
                return "%s %s %s does not support archived versions on %s." % \
                    (name, edition, version, dist)
            elif len(test_versions) > 1 and first == test_versions[1]:
                test_versions = [first]
            elif len(test_versions) > 0 and first != test_versions[0]:
                test_versions[0] = first

        dump_file_name = download_dump(name, edition, version, tempdir)

        print test_versions
        print("Running on %s." % target)
        pgnew = PgInstall(product=name, edition=edition,
                          version=version, milestone=milestone,
                          branch=branch, windows=windows_os)
        pgnew.setup_repo()
        if not windows_os:
            pgnew.install_client_only()
            subprocess.check_call('cp -a "%s" "%s"' %
                                  (pgnew.get_pg_prefix(),
                                   os.path.join(tempdir, 'client')),
                                  shell=True)
            pgnew.remove_full()
        else:
            pgnew.install_postgres_win()
            pgnew.stop_service()
            subprocess.check_call('xcopy /S /E /O /X /I /Q "%s" "%s"' %
                                  (pgnew.get_pg_prefix(),
                                   os.path.join(tempdir, 'client')),
                                  shell=True)
            pgnew.remove_full(True)

        for oldversion in test_versions:
            if pgnew.os_name in SUSE_BASED and version == '10' \
                    and oldversion == '10.6.1':
                continue
            print("Installing", oldversion)
            key = "-".join([name, edition, oldversion])
            pgold = PgInstall(product=name, edition=edition,
                              version=oldversion,
                              milestone='archive',
                              branch=None, windows=windows_os)

            pgold.setup_repo()
            if not windows_os:
                if pgnew.os_name in SUSE_BASED and version == '11' \
                        and oldversion == '11.1.1':
                    for pkg in pgold.all_packages_in_repo[:]:
                        if 'bouncer' in pkg:
                            pgold.all_packages_in_repo.remove(pkg)
                pgold.install_full()
                pgold.initdb_start()
            else:
                pgold.install_postgres_win()
            pgold.load_shared_libraries()
            pgold.exec_psql_file(dump_file_name, '-q')
            expected_file_name = os.path.join(tempdir,
                                              "%s-expected.sql" % key)
            dumpall(pgold, expected_file_name)
            pgnew = PgInstall(product=name, edition=edition,
                              version=version, milestone=milestone,
                              branch=None, windows=windows_os)
            pgnew.setup_repo()
            pgold.stop_service()
            if not windows_os:
                pgnew.update_all_packages()
                pgnew.start_service()
            else:
                pgnew.install_postgres_win()

            result_file_name = os.path.join(tempdir,
                                            "%s-result.sql" % key)
            dumpall(pgnew, result_file_name)
            diff_dbs(expected_file_name, result_file_name,
                     os.path.join(tempdir, "%s.sql.diff" % key))
            pgnew.stop_service()
            pgnew.remove_full(True)
            if pgold.os_name in DEBIAN_BASED and version == '9.6':
                try:
                    subprocess.check_call("apt-get purge -y 'postgres*'",
                                          shell=True)
                except Exception:
                    pass
