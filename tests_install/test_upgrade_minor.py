import os
import platform
import subprocess
import urllib
import re
import tempfile
import time
import pytest
from allure_commons.types import LabelType
from helpers.pginstall import PgInstall, PRELOAD_LIBRARIES,\
    PGPRO_ARCHIVE_STANDARD, PGPRO_ARCHIVE_ENTERPRISE,\
    DEBIAN_BASED, SUSE_BASED, REDHAT_BASED
from helpers.constants import FIRST_RELEASE
from BeautifulSoup import BeautifulSoup
from helpers.utils import diff_dbs, download_dump

tempdir = tempfile.gettempdir()
client_dir = os.path.join(tempdir, 'client')

# 9.6 stable, 10 stable, 11std stable does not contains pg_pageprep
PRELOAD_LIBRARIES['std-9.6'].remove('pg_pageprep')
PRELOAD_LIBRARIES['ent-9.6'].remove('pg_pageprep')
PRELOAD_LIBRARIES['std-10'].remove('pg_pageprep')
PRELOAD_LIBRARIES['ent-10'].remove('pg_pageprep')
PRELOAD_LIBRARIES['std-11'].remove('pg_pageprep')

ARCHIVE_VERSIONS = {
    'ALT Linux  7.0.5': {
        'postgrespro-std-9.6': '9.6.9.1',
        'postgrespro-ent-9.6': None,
        'postgrespro-ent-10': None
    },
    'ALT Linux  6.0.1': {
        'postgrespro-ent-9.6': None,
        'postgrespro-ent-10': None
    },
    'ALT  8.0': {
        'postgrespro-std-9.6': '9.6.13.1',
        'postgrespro-ent-9.6': '9.6.13.1',
        'postgrespro-std-10': '10.6.1',
        'postgrespro-ent-10': '10.6.1'
    },
    'ALT Linux  7.0.4': {
        'postgrespro-ent-9.6': None,
        'postgrespro-ent-10': '10.6.1'
    },
    '"AstraLinuxSE" 1.5': {
        'postgrespro-ent-9.6': None
    },
    '"AstraLinuxSE" 1.5.28': {
        'postgrespro-std-9.6': '9.6.11.1',
        'postgrespro-std-10': '10.7.1',
        'postgrespro-ent-10': '10.6.2'
    },
    'CentOS 6.7': {
        'postgrespro-ent-9.6': '9.6.8.1',
        'postgrespro-ent-10': '10.2.1'
    },
    'CentOS Linux 7.2.1511': {
        'postgrespro-ent-9.6': '9.6.9.1'
    },
    'debian 9.0': {
        'postgrespro-std-9.6': '9.6.10.2',
        'postgrespro-ent-9.6': '9.6.12.1'
    },
    'debian 8.4': {
        'postgrespro-ent-9.6': '9.6.7.1'
    },
    'GosLinux 6.4': {
        'postgrespro-std-9.6': None,
        'postgrespro-ent-9.6': None,
        'postgrespro-ent-10': None
    },
    'GosLinux 7.08': {
        'postgrespro-std-9.6': None,
        'postgrespro-std-10': '10.6.1',
        'postgrespro-ent-9.6': None,
        'postgrespro-ent-10': None
    },
    'Oracle Linux Server 6.7': {
        'postgrespro-ent-9.6': None,
        'postgrespro-ent-10': None
    },
    'Oracle Linux Server 7.2': {
        'postgrespro-ent-9.6': '9.6.8.1',
        'postgrespro-ent-10': '10.2.1'
    },
    'RED OS release MUROM ( 7.1': {
        'postgrespro-std-9.6': '9.6.11.1',
        'postgrespro-std-10': '10.6.1',
        'postgrespro-ent-9.6': None,
        'postgrespro-ent-10': None
    },
    'Red Hat Enterprise Linux Server 6.7': {
        'postgrespro-ent-9.6': None,
        'postgrespro-ent-10': None
    },
    'Red Hat Enterprise Linux Server 7.5': {
        'postgrespro-ent-9.6': '9.6.8.1',
        'postgrespro-ent-10': '10.3.1'
    },
    'ROSA Enterprise Linux Server 6.6': {
        'postgrespro-ent-10': '10.2.1'
    },
    'ROSA Enterprise Linux Server 7.3': {
        'postgrespro-std-9.6': '9.6.13.1',
        'postgrespro-std-10': '10.8.1',
        'postgrespro-std-11': '11.3.1',
        'postgrespro-ent-9.6': '9.6.13.1',
        'postgrespro-ent-10': '10.8.1',
        'postgrespro-ent-11': '11.3.1'
    },
    'ROSA Enterprise Linux Cobalt 7.3': {
        'postgrespro-std-9.6': '9.6.10.1',
        'postgrespro-ent-9.6': '9.6.9.1',
        'postgrespro-ent-10': '10.6.1'
    },
    'SUSE Linux Enterprise Server  11': {
        'postgrespro-ent-9.6': '9.6.10.1',
        'postgrespro-ent-10': None
    },
    'SUSE Linux Enterprise Server  12': {
        'postgrespro-std-9.6': '9.6.13.1',
        'postgrespro-ent-9.6': '9.6.13.1',
        'postgrespro-ent-10': None
    },
    'Ubuntu 16.04': {
        'postgrespro-ent-9.6': '9.6.7.1'
    },
    'Ubuntu 18.10': {
        'postgrespro-std-9.6': '9.6.11.1',
        'postgrespro-std-10': '10.7.1',
        'postgrespro-std-11': '11.2.1',
        'postgrespro-ent-9.6': None,
        'postgrespro-ent-10': None
    },
    'Ubuntu 18.04': {
        'postgrespro-std-9.6': '9.6.10.2',
        'postgrespro-std-10': '10.2.1',
        'postgrespro-ent-9.6': '9.6.11.1'
    },
    'Ubuntu 19.04': {
        'postgrespro-std-9.6': '9.6.15.1',
        'postgrespro-std-10': '10.8.1',
        'postgrespro-std-11': '11.5.4'
    },
    'AlterOS 7.5': {
        'postgrespro-std-9.6': None,
        'postgrespro-std-10': '10.8.1',
        'postgrespro-std-11': '11.3.1',
        'postgrespro-ent-9.6': None,
        'postgrespro-ent-10': '10.8.1',
        'postgrespro-ent-11': '11.3.1'
    },
    'SUSE Linux Enterprise Server  15': {
        'postgrespro-std-9.6': None,
        'postgrespro-std-10': '10.8.1',
        'postgrespro-std-11': '11.3.1',
        'postgrespro-ent-9.6': None,
        'postgrespro-ent-10': '10.8.1',
        'postgrespro-ent-11': '11.3.1'
    },
}

for distr in FIRST_RELEASE:
    if distr in ARCHIVE_VERSIONS:
        for product in FIRST_RELEASE[distr]:
            if product not in ARCHIVE_VERSIONS[distr]:
                ARCHIVE_VERSIONS[distr][product] = \
                    FIRST_RELEASE[distr][product]
    else:
        ARCHIVE_VERSIONS[distr] = FIRST_RELEASE[distr]


def get_test_versions(edition, version, specified_version, current_version):
    # Do not upgrade himself
    if specified_version and current_version:
        specified_ver = '.'.join([d.rjust(4)
                                  for d in specified_version.split('.')])
        if current_version <= specified_ver:
            return None
    if edition == "ent":
        archive_url = PGPRO_ARCHIVE_ENTERPRISE
    elif edition == "std":
        archive_url = PGPRO_ARCHIVE_STANDARD
    else:
        raise Exception("Unsupported postgrespro edition (%s)." % edition)

    # Choose two versions -- newest and oldest supported
    soup = BeautifulSoup(urllib.urlopen(archive_url))
    arcversions = []
    specified_version_found = False
    for link in soup.findAll('a'):
        href = link.get('href')
        if href.startswith('pgpro') and href.endswith('/'):
            vere = re.search(r'\w+-([0-9.]+)/', href)
            if vere:
                if vere.group(1).startswith(version):
                    ver = vere.group(1)
                    arcvers = ver.split('.')
                    if not specified_version_found and \
                            ver == specified_version:
                        specified_version_found = True

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
    if specified_version and not specified_version_found:
        print "Specified first version is not present in archive yet."
        return None
    n = len(arcversions) - 1
    while n >= 0 and current_version <= arcversions[n]:
        n = n - 1
    if n < 0:
        return None
    res = [specified_version if
           specified_version else arcversions[0].replace(' ', ''),
           arcversions[n].replace(' ', '')]
    if res[0] == res[1]:
        return [res[0]]
    else:
        return res


def dumpall(pg, file):
    cmd = '%s"%s" -f "%s"' % \
          (
              pg.pg_preexec,
              os.path.join(client_dir, 'bin', 'pg_dumpall'),
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
        if edition not in ['std', 'ent']:
            print "Minor upgrade only for std and ent"
            return
        if name != 'postgrespro':
            print("Minor upgrade test is only for postgrespro.")
            return

        small_key = "-".join([name, edition, version])
        specified_version = False
        if dist in ARCHIVE_VERSIONS \
                and small_key in ARCHIVE_VERSIONS[dist]:
            specified_version = ARCHIVE_VERSIONS[dist][small_key]

        if specified_version is None:
            return "%s %s %s does not support archived versions on %s." % \
                (name, edition, version, dist)
        print("specified version is %s" % specified_version)
        print("Running on %s." % target)
        pgnew = PgInstall(product=name, edition=edition,
                          version=version, milestone=milestone,
                          branch=branch, windows=windows_os)
        pgnew.setup_repo()
        if not windows_os:
            pgnew.install_client_only()
            pgnew.install_package(pgnew.get_dev_package_name())
            subprocess.check_call('cp -a "%s" "%s"' %
                                  (pgnew.get_pg_prefix(),
                                   client_dir),
                                  shell=True)
            pgnew.remove_full()
        else:
            pgnew.install_postgres_win()
            pgnew.stop_service()
            subprocess.check_call('xcopy /S /E /O /X /I /Q "%s" "%s"' %
                                  (pgnew.get_pg_prefix(),
                                   client_dir),
                                  shell=True)
            pgnew.remove_full(True)
        pgconfig = subprocess.check_output('"%s"' %
                                           os.path.join(client_dir, 'bin',
                                                        'pg_config'),
                                           shell=True)
        vere = re.search(r'PGPRO\_VERSION\s=\s([0-9.]+)', pgconfig)
        if (vere):
            current_ver = vere.group(1)
        else:
            vere = re.search(r'VERSION\s=\s\w+\s([0-9.]+)', pgconfig)
            current_ver = vere.group(1)
        print("Current version is %s" % current_ver)
        current_ver = '.'.join([d.rjust(4) for d in current_ver.split('.')])
        test_versions = get_test_versions(edition, version,
                                          specified_version, current_ver)

        if test_versions is None:
            print("No archive versions found.")
            return

        print test_versions

        dump_file_name = download_dump(name, edition, version, tempdir)

        for oldversion in test_versions:
            print("Installing", oldversion)
            key = "-".join([name, edition, oldversion])
            pgold = PgInstall(product=name, edition=edition,
                              version=oldversion,
                              milestone='archive',
                              branch=None, windows=windows_os)

            pgold.setup_repo()
            old_ver = '.'.join([d.rjust(4) for d in oldversion.split('.')])
            if not windows_os:
                # PGPRO-2954
                for pkg in pgold.all_packages_in_repo[:]:
                    if 'bouncer' in pkg or 'badger' in pkg:
                        pgold.all_packages_in_repo.remove(pkg)
                # PGPRO-2874
                if ((version == '11' and old_ver < '  11.   4.   2') or
                    (version == '10' and old_ver < '  10.  10.   1') or
                    (version == '9.6' and old_ver < '   9.   6.  15.   1')) \
                        and pgnew.os_name in REDHAT_BASED:
                    for pkg in pgold.all_packages_in_repo[:]:
                        if 'filedump' in pkg:
                            pgold.all_packages_in_repo.remove(pkg)
                if pgnew.os_name == 'ROSA Enterprise Linux Server' \
                        and pgnew.os_version.startswith('7.3') \
                        and edition == 'std' \
                        and version == '9.6' \
                        and old_ver == '   9.   6.  13.   1':
                    for pkg in pgold.all_packages_in_repo[:]:
                        if 'probackup' in pkg:
                            pgold.all_packages_in_repo.remove(pkg)
                pgold.install_full()
                pgold.initdb_start()
            else:
                pgold.install_postgres_win()
            pgold.load_shared_libraries()
            with open(os.path.join(tempdir, 'load-%s.log' % oldversion),
                      'wb') as out:
                pgold.exec_psql_file(dump_file_name, '-q',
                                     stdout=out)

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

            repo_diff = list(set(pgold.all_packages_in_repo)
                             - set(pgnew.all_packages_in_repo))
            print "repo diff is %s" % repo_diff
            for package in repo_diff:
                try:
                    pgold.remove_package(package)
                except Exception:
                    pass

            pgnew.remove_full(True)
            if pgold.os_name in DEBIAN_BASED and version == '9.6':
                try:
                    subprocess.check_call("apt-get purge -y 'postgres*'",
                                          shell=True)
                except Exception:
                    pass
            # PGPRO-2563
            if pgold.os_name == 'Ubuntu' and version == '9.6' and \
                    edition == 'ent':
                time.sleep(20)
