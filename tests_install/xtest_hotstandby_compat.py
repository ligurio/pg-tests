import os
import platform
import distro
import subprocess
import re
import time
import shutil
import tempfile
import glob

import pytest
import allure

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall
from helpers.pginstall import PGPRO_ARCHIVE_STANDARD, PGPRO_ARCHIVE_ENTERPRISE
from helpers.utils import urlopen, get_distro, compare_versions, extend_ver, \
    get_soup
try:
    from bs4 import BeautifulSoup
except ImportError:  # py2compat
    from BeautifulSoup import BeautifulSoup

windows_os = False


def setup_pgpass(username, password):
    passline = "127.0.0.1:*:*:%s:%s" % (username, password)
    if windows_os:
        subprocess.check_call(
            'mkdir "%APPDATA%\\postgresql" & '
            'echo ' + passline + '>"%APPDATA%\\postgresql\\pgpass.conf"',
            shell=True)
    else:
        # chown is needed for 9.6
        # TODO: Report a bug
        subprocess.check_call(
            'chown postgres:postgres ~postgres && '
            'sudo -u postgres sh -c '
            '\'echo \"%s\" > ~postgres/.pgpass && '
            'chmod 600 ~postgres/.pgpass\'' % passline,
            shell=True)


def do_server_action(pginst, action):
    if windows_os:
        pginst.service_action(action)
    else:
        pginst.pg_control(action, pginst.get_datadir())


def setup_sender(pginst, waldir, backup_targetdir):
    do_server_action(pginst, "start")
    # Setup user and password
    pginst.exec_psql(
        "CREATE USER replicator WITH REPLICATION "
        "ENCRYPTED PASSWORD 'replicator'")

    if os.path.exists(waldir):
        shutil.rmtree(waldir)
    os.makedirs(waldir)
    os.chmod(waldir, 0o0777)
    pginst.exec_psql("ALTER SYSTEM SET logging_collector TO 'on'")
    pginst.exec_psql("ALTER SYSTEM SET wal_level TO 'hot_standby'")
    pginst.exec_psql("ALTER SYSTEM SET archive_mode TO 'on'")
    pginst.exec_psql("ALTER SYSTEM SET max_wal_senders TO '5'")
    pginst.exec_psql("ALTER SYSTEM SET wal_keep_segments TO '10'")
    pginst.exec_psql("ALTER SYSTEM SET listen_addresses TO '*'")
    pginst.exec_psql("ALTER SYSTEM SET hot_standby TO 'on'")
    if windows_os:
        arccom = 'copy "%p" "' + waldir + '\\%f"'
    else:
        arccom = 'test ! -f "' + waldir + '/%f" && cp "%p" "' + \
            waldir + '/%f"'
    pginst.exec_psql("ALTER SYSTEM SET archive_command TO '%s'" % arccom)
    with open(os.path.join(pginst.get_datadir(), "pg_hba.conf"), "a") as hba:
        hba.write("host replication replicator 127.0.0.1/32 md5")
    do_server_action(pginst, "restart")

    os.makedirs(backup_targetdir)
    if windows_os:
        # Grant Full Access to "Network Service" and Users
        subprocess.check_call(
            'icacls "%s" /grant *S-1-5-32-545:(OI)(CI)F /T' % backup_targetdir,
            shell=True)
        subprocess.check_call(
            'icacls "%s" /grant *S-1-5-20:(OI)(CI)F /T' % backup_targetdir,
            shell=True)
    else:
        subprocess.check_call(
            'chown postgres:postgres "%s" && chmod 700 "%s"' %
            (backup_targetdir, backup_targetdir),
            shell=True)

    pginst.exec_client_bin('pg_basebackup',
                           '-h 127.0.0.1 -p %d -U replicator '
                           '-D "%s" -P -Xs -R > "%s" 2>&1' %
                           (pginst.get_port(), backup_targetdir,
                            os.path.join(tempfile.gettempdir(),
                                         'pg_basebackup.log')))
    time.sleep(5)


def start_receiver(pginst, waldir, pre12):
    # Remove custom configuration
    os.unlink(os.path.join(pginst.get_datadir(),
                           'postgresql.auto.conf'))
    recovery_params_conf = 'recovery.conf' if pre12 else 'postgresql.conf'
    with open(os.path.join(pginst.get_datadir(),
                           recovery_params_conf), "a") as conf:
        conf.write(
            "\nrestore_command = " +
            ("'copy \"" + waldir.replace("\\", "\\\\") + "\\\\%f\" \"%p\"'\n"
             if windows_os else
             "'cp \"" + waldir + "/%f\" \"%p\"'\n"))

    if not pre12:
        with open(os.path.join(pginst.get_datadir(),
                               'standby.signal'), "a") as signal:
            signal.write("")

    with open(os.path.join(pginst.get_datadir(),
                           'postgresql.conf'), "a") as conf:
        conf.write("\n"
                   "lc_messages = 'C'\n"
                   "hot_standby = on\n"
                   "port = %d\n" % pginst.get_port())
    do_server_action(pginst, "start")
    time.sleep(5)


def workaround_for_extra_libpq_options(pgold):
    confname = os.path.join(pgold.get_datadir(), 'recovery.conf')
    with open(confname, 'r') as conf:
        rec = conf.read()
    rec = re.sub(r"\Wreusepass=\w+", "", rec)
    rec = re.sub(r"\Wtarget_server_type=\w+", "", rec)
    rec = re.sub(r"\Whostorder=\w+", "", rec)
    with open(confname, 'w') as conf:
        rec = conf.write(rec)


def prepare_pg_regress(pginst, target_dir):
    pginst.download_source()
    pgsrc = None
    for tar in glob.glob("postgres*.tar*"):
        pgsrc = os.path.abspath(tar)
        break
    if not pgsrc:
        raise Exception("Source archive is not present.")
    if not os.path.isdir(target_dir):
        os.mkdir(target_dir)
    curpath = os.path.dirname(os.path.abspath(__file__))
    if windows_os:
        cmd = '"%s" "%s" "%s"' % (os.path.join(curpath,
                                               'prepare_for_build.cmd'),
                                  pgsrc, pginst.get_pg_prefix())
    else:
        cmd = '"%s" "%s" "%s"' % (os.path.join(curpath,
                                               'prepare_for_build.sh'),
                                  pgsrc, pginst.get_pg_prefix())
    subprocess.check_call(cmd, cwd=target_dir, shell=True)

    shutil.copytree(os.path.join(curpath, '..', 'patches'),
                    os.path.join(target_dir, 'patches'))
    pgsrcdir = None
    for pgi in glob.glob(os.path.join(target_dir, "postgres*")):
        if os.path.isdir(pgi):
            pgsrcdir = os.path.abspath(pgi)
            break
    if not pgsrcdir:
        raise Exception("Prepared build tree not found.")
    if windows_os:
        cmd = (r'c:\msys64\usr\bin\bash -c "'
               'source setenv.sh && '
               'patch -p1 -i ../patches/fix-pg_cancel_backend.patch && '
               'patch -p1 -i ../patches/hs_standby_allowed~e8ec19cd.patch && '
               'make -j4 -C src/common && '
               'make -j4 -C src/backend libpostgres.a && '
               'make -j4 -C src/test/regress"')
        subprocess.check_call(cmd, cwd=pgsrcdir, shell=True)
    else:
        cmd = ('sudo -u postgres sh -c "'
               'patch -p1 -i ../patches/fix-pg_cancel_backend.patch && '
               'patch -p1 -i ../patches/hs_standby_allowed~e8ec19cd.patch && '
               'make -C src/test/regress pg_regress"')
        subprocess.check_call(cmd, cwd=pgsrcdir, shell=True)
    return pgsrcdir


def run_hs_test(primary, standby, pgsrcdir):
    # https://www.postgresql.org/docs/current/static/regress-run.html
    print("Prepare regression database...")
    primary.exec_psql("CREATE DATABASE regression")
    primary.exec_client_bin(
        "psql", '-p %d -f "%s" regression' %
        (primary.get_port(),
         os.path.join(pgsrcdir, 'src', 'test', 'regress',
                      'sql', 'hs_primary_setup.sql')))
    for i in range(30, 0, -1):
        try:
            standby.exec_psql("SELECT 1", "-d regression")
            break
        except Exception as ex:
            if i == 1:
                raise Exception(
                    "standby failed to replicate the regression database.")
            time.sleep(1)
    print("Performing pg_regress test...")
    comcmd = (r'''set -o pipefail &&
export PGPORT=%d && PATH=\"%s:$PATH\" &&
cd src/test/regress && make standbycheck | tee /tmp/standbycheck.log;
exitcode=$?; cd ../../..;
for df in $(find . -name *.diffs); do
 echo;echo \"    vvvv $df vvvv    \"; cat $df; echo \"    ^^^^^^^^\"; done;
exit $exitcode''' %
              (standby.get_port(), standby.get_bin_path())).replace("\n", " ")
    print("comcmd:", comcmd)
    if windows_os:
        cmd = r'c:\msys64\usr\bin\bash -c "source setenv.sh && %s"' % comcmd
    else:
        cmd = 'sudo -u postgres bash -c "%s"' % comcmd.replace('$', '\\$')
    print("cmd:", cmd)
    subprocess.check_call(cmd, cwd=pgsrcdir, shell=True)


class TestHotStandbyCompatibility():

    system = platform.system()

    def test_hotstandby_compat(self, request):
        """
        Scenario:
        1. Install current version
        2. Check that setup successfull (select version)

        :return:
        """
        global windows_os
        if self.system == 'Linux':
            dist = " ".join(get_distro()[0:2])
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
        tag_mark = allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        branch = request.config.getoption('--branch')

        if name != 'postgrespro':
            print("Hot Standby compatibility test is only for postgrespro.")
            return
        if edition == "ent":
            archive_url = PGPRO_ARCHIVE_ENTERPRISE
        elif edition == "std":
            archive_url = PGPRO_ARCHIVE_STANDARD
        else:
            raise Exception("Unsupported postgrespro edition (%s)." % edition)
        print("Running on %s." % target)

        # Choose two versions -- newest and oldest supported
        soup = get_soup(archive_url)
        arcversions = []
        startswith = 'pgproee-' if edition == 'ent' else \
            ('pgpro-' if edition == 'std' else 'pg1c-')
        for link in soup.findAll('a'):
            href = link.get('href')
            if href.startswith(startswith) and href.endswith('/'):
                vere = re.search(r'\w+-([0-9.]+)/', href)
                if vere:
                    if vere.group(1).startswith(version):
                        arcvers = vere.group(1)
                        if version == '9.6':
                            # Due to CATALOG_VERSION_NO change
                            # we don't support lower 9.6 versions
                            if compare_versions(arcvers, '9.6.4.1') < 0:
                                arcvers = None
                        # PGPRO-3227, PGPRO-3834
                        if windows_os and version == '10':
                            if compare_versions(arcvers, '10.11.1'):
                                arcvers = None
                        if windows_os and version == '11':
                            if compare_versions(arcvers, '11.6.1') < 0:
                                arcvers = None
                        if arcvers:
                            arcversions.append(arcvers)
        arcversions.sort(key=extend_ver)
        if not arcversions:
            print("No previous minor versions found. Test skipped.")
            return
        # Choose first and last versions
        testversions = [arcversions[0], arcversions[-1]]
        if testversions[0] == testversions[1]:
            testversions = [testversions[0]]
        # Workaround for unsupported libpq options
        fix_extra_libpq_options = False
        if edition == 'ent' and version == '10':
            if compare_versions(arcversions[0], '10.4.1') < 0:
                fix_extra_libpq_options = True
        pre12version = version in ['9.6', '10', '11']

        if windows_os:
            waldir = r'C:\tmp\pgwal'
            srcdir = r'C:\tmp'
        else:
            waldir = os.path.join(tempfile.gettempdir(), 'pgwal')
            srcdir = '/var/src'

        pgsrcdir = None

        for oldversion in testversions:
            print("Installing", oldversion)
            pgold = PgInstall(product=name, edition=edition,
                              version=oldversion, milestone='archive',
                              branch=None, windows=windows_os)

            pgold.setup_repo()
            if not windows_os:
                pgold.install_base()
                pgold.initdb_start()
            else:
                pgold.install_postgres_win()

            setup_pgpass('replicator', 'replicator')

            server_version = pgold.get_server_version()
            client_version = pgold.get_psql_version()
            print("Old server version:\n%s\nOld client version:\n%s" %
                  (server_version, client_version))
            pgold.exec_psql('ALTER SYSTEM SET port=15432')
            oldpgprefix = pgold.get_pg_prefix()
            olddatadir = pgold.get_datadir()
            if oldpgprefix == '/usr':
                raise Exception("/usr as postgres prefix is not supported.")
            if pgold.get_configdir() != pgold.get_datadir():
                raise Exception("Separate config dir is not supported.")
            pgold.stop_service()
            time.sleep(5)
            if not windows_os:
                subprocess.check_call('cp -a "%s" "%s.old"' %
                                      (oldpgprefix, oldpgprefix), shell=True)
                subprocess.check_call('cp -a "%s" "%s.old"' %
                                      (olddatadir, olddatadir), shell=True)
                oldpgprefix += ".old"
                olddatadir += ".old"
            else:
                print('xcopy /S /E /O /X /I /Q "%s" "%s.old"' %
                      (oldpgprefix, oldpgprefix))
                subprocess.check_call('xcopy /S /E /O /X /I /Q "%s" "%s.old"' %
                                      (oldpgprefix, oldpgprefix), shell=True)
                oldpgprefix += ".old"
                olddatadir = os.path.join(oldpgprefix, 'data')
                if os.path.exists(os.path.join(olddatadir,
                                               'postgresql.conf.old')):
                    os.remove(os.path.join(olddatadir, 'postgresql.conf.old'))

            pgold.remove_full(remove_data=True)

            pgold.pg_prefix = oldpgprefix
            pgold.datadir = olddatadir
            pgold.configdir = olddatadir
            pgold.port = 15432
            if not windows_os:
                pgold.pg_preexec = 'sudo -u postgres ' \
                                   'LD_LIBRARY_PATH=${LD_LIBRARY_PATH} '
                old_env = os.environ.copy()
                old_env["LD_LIBRARY_PATH"] = os.path.join(oldpgprefix, 'lib')
                pgold.env = old_env
            else:
                subprocess.check_call(
                    'sc create postgres-old binpath= '
                    '"\\"%s\\" runservice -N postgres-old -D \\"%s\\" -w"'
                    ' start= demand obj= "NT Authority\\NetworkService" ' %
                    (os.path.join(oldpgprefix, 'bin', 'pg_ctl'), olddatadir),
                    shell=True)
                pgold.service_name = 'postgres-old'

            pgnew = PgInstall(product=name, edition=edition,
                              version=version, milestone=milestone,
                              branch=branch, windows=windows_os)
            pgnew.setup_repo()
            if not windows_os:
                pgnew.install_base()
                pgnew.initdb_start()
            else:
                pgnew.install_postgres_win()
            if not pgsrcdir:
                pgsrcdir = prepare_pg_regress(pgnew, srcdir)
            pgnew.stop_service()
            pgnew.remove_data()

            # Test replication from old to new
            setup_sender(pgold, waldir, pgnew.get_datadir())
            start_receiver(pgnew, waldir, pre12version)

            run_hs_test(pgold, pgnew, pgsrcdir)

            do_server_action(pgnew, "stop")
            do_server_action(pgold, "stop")

            # Test replication from new to old
            pgnew.init_cluster(force_remove=True)
            pgold.remove_data()
            setup_sender(pgnew, waldir, pgold.get_datadir())
            if fix_extra_libpq_options:
                workaround_for_extra_libpq_options(pgold)
            start_receiver(pgold, waldir, pre12version)

            run_hs_test(pgnew, pgold, pgsrcdir)

            do_server_action(pgnew, "stop")
            do_server_action(pgold, "stop")

            pgnew.remove_full(remove_data=True)
            shutil.rmtree(olddatadir)
            shutil.rmtree(oldpgprefix)
            if windows_os:
                subprocess.check_call('sc delete postgres-old', shell=True)
        print("OK")
