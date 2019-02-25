import os
import platform
import glob
import time
import subprocess
import re

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall
from helpers.os_helpers import get_directory_size
from helpers.os_helpers import get_process_pids


SERVER_APPLICATIONS = {
    '1c-10':
        ['initdb', 'pg_archivecleanup', 'pg_controldata', 'pg_ctl',
         'pg_resetwal', 'pg_rewind', 'pg-setup', 'pg_test_fsync',
         'pg_test_timing', 'pg_upgrade', 'pg_waldump', 'postgres',
         'postmaster'],
    'std-10':
        ['initdb', 'pg_archivecleanup', 'pg_controldata', 'pg_ctl',
         'pg_resetwal', 'pg_rewind', 'pg-setup', 'pg_test_fsync',
         'pg_test_timing', 'pg_upgrade', 'pg_waldump', 'postgres',
         'postmaster'],
    'ent-10':
        ['initdb', 'pg_archivecleanup', 'pg_controldata', 'pg_ctl',
         'pg_resetwal', 'pg_rewind', 'pg-setup', 'pg_test_fsync',
         'pg_test_timing', 'pg_upgrade', 'pg_waldump', 'postgres',
         'postmaster'],
    '1c-11':
        ['initdb', 'pg_archivecleanup', 'pg_controldata', 'pg_ctl',
         'pg_resetwal', 'pg_rewind', 'pg-setup', 'pg_test_fsync',
         'pg_test_timing', 'pg_upgrade', 'pg_verify_checksums',
         'pg_waldump', 'postgres', 'postmaster'],
    'std-11':
        ['initdb', 'pg_archivecleanup', 'pg_controldata', 'pg_ctl',
         'pg_resetwal', 'pg_rewind', 'pg-setup', 'pg_test_fsync',
         'pg_test_timing', 'pg_upgrade', 'pg_verify_checksums',
         'pg_waldump', 'postgres', 'postmaster'],
    'ent-11':
        ['initdb', 'pg_archivecleanup', 'pg_controldata', 'pg_ctl',
         'pg_resetwal', 'pg_rewind', 'pg-setup', 'pg_test_fsync',
         'pg_test_timing', 'pg_upgrade', 'pg_verify_checksums',
         'pg_waldump', 'postgres', 'postmaster'],
}

CLIENT_APPLICATIONS = {
    '1c-10':
        ['clusterdb', 'createdb', 'createuser', 'dropdb', 'dropuser',
         'pg_basebackup', 'pgbench', 'pg_dump', 'pg_dumpall',
         'pg_isready', 'pg_receivewal', 'pg_recvlogical', 'pg_restore',
         'psql', 'reindexdb', 'vacuumdb'],
    'std-10':
        ['clusterdb', 'createdb', 'createuser', 'dropdb', 'dropuser',
         'pg_basebackup', 'pgbench', 'pg_dump', 'pg_dumpall',
         'pg_isready', 'pg_receivewal', 'pg_recvlogical', 'pg_restore',
         'psql', 'reindexdb', 'vacuumdb'],
    'ent-10':
        ['clusterdb', 'createdb', 'createuser', 'dropdb', 'dropuser',
         'pg_basebackup', 'pgbench', 'pg_dump', 'pg_dumpall',
         'pg_isready', 'pg_receivewal', 'pg_recvlogical', 'pg_restore',
         'psql', 'reindexdb', 'vacuumdb'],
    '1c-11':
        ['clusterdb', 'createdb', 'createuser', 'dropdb', 'dropuser',
         'pg_basebackup', 'pgbench', 'pg_dump', 'pg_dumpall',
         'pg_isready', 'pg_receivewal', 'pg_recvlogical', 'pg_restore',
         'psql', 'reindexdb', 'vacuumdb'],
    'std-11':
        ['clusterdb', 'createdb', 'createuser', 'dropdb', 'dropuser',
         'pg_basebackup', 'pgbench', 'pg_dump', 'pg_dumpall',
         'pg_isready', 'pg_receivewal', 'pg_recvlogical', 'pg_restore',
         'psql', 'reindexdb', 'vacuumdb'],
    'ent-11':
        ['clusterdb', 'createdb', 'createuser', 'dropdb', 'dropuser',
         'pg_basebackup', 'pgbench', 'pg_dump', 'pg_dumpall',
         'pg_isready', 'pg_receivewal', 'pg_recvlogical', 'pg_restore',
         'psql', 'reindexdb', 'vacuumdb'],
}

DEV_APPLICATIONS = {
    '1c-10':
        ['ecpg', 'pg_config'],
    'std-10':
        ['ecpg', 'pg_config'],
    'ent-10':
        ['ecpg', 'pg_config'],
    '1c-11':
        ['ecpg', 'pg_config'],
    'std-11':
        ['ecpg', 'pg_config'],
    'ent-11':
        ['ecpg', 'pg_config'],
}


def check_executables(pginst, packages):
    for package in packages:
        print('Analyzing package %s.' % package)
        pfiles = pginst.get_files_in_package(package)
        for f in pfiles:
            if f.startswith('/usr/lib/debug/'):
                continue
            fout = subprocess.check_output(
                'LANG=C file "%s"' % f, shell=True).strip()
            if fout.startswith(f + ': cannot open'):
                print fout
                raise Exception('Error opening file "%s".' % f)
            if not fout.startswith(f + ': ELF '):
                continue
            print "\tELF executable found:", f
            lddout = subprocess.check_output(
                'LANG=C ldd "%s"' % f, shell=True).split("\n")
            error = False
            for line in lddout:
                if line.strip() == "" or line.startswith("\tlinux") or \
                   line.startswith("\t/") or line == ("\tstatically linked"):
                    continue
                if not (' => ' in line) or ' not found' in line:
                    print "Invalid line: [%s]" % line
                    error = True
                    break
            if error:
                print 'ldd "%s":' % f, lddout
                raise Exception("Invalid dynamic dependencies")
            if f.endswith('.so') or '.so.' in os.path.basename(f):
                continue
            gdbout = subprocess.check_output(
                'gdb --batch -ex "b main" -ex run -ex next -ex bt -ex cont'
                ' --args  "%s" --version' % f,
                stderr=subprocess.STDOUT, shell=True).split("\n")
            good_lines = 0
            for line in gdbout:
                if re.match(r'Breakpoint 1, [a-z0-9_:]*main ', line):
                    good_lines += 1
                if re.match(r'#0\s+([a-z0-9_:]*main|get_progname)\s+\(', line):
                    good_lines += 1
            if good_lines != 2:
                if f in ['/usr/bin/pzstd', '/usr/bin/zstd']:
                    # a newer zstd can be installed from epel (on RH),
                    # but zstd-debuginfo will still be ours
                    continue
                print("gdb for %s output:" % f, gdbout)
                raise Exception("No valid backtrace for %s." % f)


def check_package_contents(pginst, packages):

    def check_contents(package, contents, must_present, must_absent):
        for pi in must_present:
            found = False
            for item in contents:
                if item.endswith(os.sep + pi):
                    found = True
            if not found:
                raise Exception(
                    "Application %s not found in package %s." % (pi, package))
        for item in contents:
            for ai in must_absent:
                if (package.endswith('-dev') or package.endswith('-devel')) \
                   and '/include/' in item:
                    continue
                if package.endswith('-jit') and '/bitcode/' in item:
                    continue
                if (re.search('/' + ai + '$', item) or
                   re.search('/man/.*/' + ai + r'\..*', item) or
                   re.search('/' + ai + r'\b.*\.mo$', item)):
                    raise Exception(
                        "Application %s found in package %s (file: %s)." %
                        (ai, package, item))

    if pginst.product != "postgrespro":
        return
    if pginst.milestone != "alpha":  # TODO: Remove before 2019.02 release
        return
    pgid = '%s-%s' % (pginst.edition, pginst.version)
    if (pgid not in SERVER_APPLICATIONS):
        return
    sapps = SERVER_APPLICATIONS[pgid]
    capps = CLIENT_APPLICATIONS[pgid]
    dapps = DEV_APPLICATIONS[pgid]
    for package in packages:
        if package.endswith('-debuginfo') or package.endswith('-dbg') or \
           package.endswith('-docs') or package.endswith('-docs-ru') or \
           package.endswith('-src'):
            continue
        pfiles = pginst.get_files_in_package(package)
        if package.endswith('-server'):
            check_contents(package, pfiles, sapps, capps + dapps)
        elif package.endswith('-client'):
            check_contents(package, pfiles, capps, sapps + dapps)
        elif package.startswith('postgrespro') and (
             package.endswith('-dev') or package.endswith('-devel')):
            check_contents(package, pfiles, dapps, sapps + capps)
        else:
            check_contents(package, pfiles, [], sapps + capps + dapps)


@pytest.mark.full_install
class TestFullInstall():

    system = platform.system()

    @pytest.mark.test_full_install
    def test_full_install(self, request):
        """
        Scenario:
        1. Install current version
        2. Check that setup successfull

        :return:
        """
        dist = ""
        if self.system == 'Linux':
            dist = " ".join(platform.linux_distribution()[0:2])
        elif self.system == 'Windows':
            dist = 'Windows'
        else:
            raise Exception("OS %s is not supported." % self.system)
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        milestone = request.config.getoption('--product_milestone')
        request.cls.pgid = '%s-%s' % (edition, version)
        target = request.config.getoption('--target')
        product_info = " ".join([dist, name, edition, version])
        # pylint: disable=no-member
        tag_mark = pytest.allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        branch = request.config.getoption('--branch')

        # Step 1
        pginst = PgInstall(product=name, edition=edition,
                           version=version, milestone=milestone,
                           branch=branch, windows=(self.system == 'Windows'))
        request.cls.pginst = pginst
        pginst.setup_repo()
        print("Running on %s." % target)
        if self.system != 'Windows':
            all_available_packages = pginst.all_packages_in_repo
            print("All available packages in repo %s:\n" % pginst.reponame,
                  "\n".join(all_available_packages))
            pginst.install_full()
            pginst.install_package(" ".join(all_available_packages))
            check_package_contents(pginst, all_available_packages)
            check_executables(pginst, all_available_packages)
            pginst.initdb_start()
        else:
            pginst.install_perl_win()
            pginst.install_postgres_win()
        server_version = pginst.get_server_version()
        client_version = pginst.get_psql_version()
        print("Server version:\n%s\nClient version:\n%s" %
              (server_version, client_version))
        if name == 'postgrespro' and not (edition in ['1c', 'sql']):
            ppversion = pginst.exec_psql_select("SELECT pgpro_version()")
            assert ppversion.startswith('PostgresPro ' + version)
            ppedition = pginst.exec_psql_select("SELECT pgpro_edition()")
            if edition == 'ent':
                assert ppedition == 'enterprise'
            elif edition == 'ent-cert':
                assert ppedition == 'enterprise'
            else:
                assert ppedition == 'standard'
            print('pgpro_source_id:',
                  pginst.exec_psql_select("SELECT pgpro_build()"))
        print("OK")

    @pytest.mark.test_all_extensions
    def test_all_extensions(self, request):
        pginst = request.cls.pginst
        iprops = pginst.get_initdb_props()
        pginst.load_shared_libraries()
        share_path = iprops['share_path'].replace('/', os.sep)
        controls = glob.glob(os.path.join(share_path,
                                          'extension', '*.control'))
        for ctrl in sorted(controls):
            extension = os.path.splitext(os.path.basename(ctrl))[0]
            # multimaster requires a special setup
            if extension == 'multimaster':
                continue
            print("CREATE EXTENSION %s" % extension)
            pginst.exec_psql(
                "CREATE EXTENSION IF NOT EXISTS \\\"%s\\\" CASCADE" %
                extension)

    @pytest.mark.test_plpython
    def test_plpython(self, request):
        """Test for plpython language
        Scenario:
        1. Create function
        2. Execute function
        3. Check function result
        4. Drop function
        """
        pginst = request.cls.pginst
        # Step 1
        func = """CREATE FUNCTION py_test_function()
RETURNS text
AS $$
return "python2u test function"
$$ LANGUAGE plpython2u;"""
        pginst.exec_psql_script(func)
        # Step 2
        result = pginst.exec_psql_select("SELECT py_test_function()")
        print(result)
        # Step 3
        assert result == "python2u test function"
        # Step 4
        pginst.exec_psql("DROP FUNCTION py_test_function()")

    @pytest.mark.test_plpython
    def test_plpython3(self, request):
        """Test for plpython language
        Scenario:
        1. Create function
        2. Execute function
        3. Check function result
        4. Drop function
        """
        pginst = request.cls.pginst
        py3ext = pginst.exec_psql_select("SELECT extname FROM pg_extension "
                                         "WHERE extname='plpython3u'")
        if py3ext != "plpython3u":
            print("No plpython3u extension found. Test skipped.")
            return
        # Step 1
        func = """CREATE FUNCTION py_test_function()
RETURNS text
AS $$
return "python3u test function"
$$ LANGUAGE plpython3u;"""
        pginst.exec_psql_script(func)
        # Step 2
        result = pginst.exec_psql_select("SELECT py_test_function()")
        print(result)
        # Step 3
        assert result == "python3u test function"
        # Step 4
        pginst.exec_psql("DROP FUNCTION py_test_function()")

    @pytest.mark.skipif('platform.system() == "Windows"')
    @pytest.mark.test_pltcl
    def test_pltcl(self, request):
        """Test for pltcl language
        Scenario:
        1. Create function
        2. Execute function
        3. Check function result
        4. Drop function
        """
        pginst = request.cls.pginst
        # Step 1
        func = """CREATE FUNCTION pltcl_test_function()
RETURNS text
AS $$
return "pltcl test function"
$$ LANGUAGE pltcl;"""
        pginst.exec_psql_script(func)
        # Step 2
        result = pginst.exec_psql_select("SELECT pltcl_test_function()")
        print(result)
        # Step 3
        assert result == "pltcl test function"
        # Step 4
        pginst.exec_psql("DROP FUNCTION pltcl_test_function()")

    @pytest.mark.test_plperl
    def test_plperl(self, request):
        """Test for plperl language
        Scenario:
        1. Create function
        2. Execute function
        3. Check function result
        4. Drop function
        """
        pginst = request.cls.pginst
        if platform.system() == "Windows" and pginst.os_arch != 'AMD64':
            print "plperl is only supported on 64-bit Windows. Test skipped."
            return
        # Step 1
        func = """CREATE FUNCTION plperl_test_function()
RETURNS text
AS $$
return "plperl test function"
$$ LANGUAGE plperl;"""
        pginst.exec_psql_script(func)
        # Step 2
        result = pginst.exec_psql_select("SELECT plperl_test_function()")
        print(result)
        # Step 3
        assert result == "plperl test function"
        # Step 4
        pginst.exec_psql("DROP FUNCTION plperl_test_function()")

    @pytest.mark.test_plpgsql
    def test_plpgsql(self, request):
        """Test for plpgsql language
        Scenario:
        1. Create function
        2. Execute function
        3. Check function result
        4. Drop function
        """
        pginst = request.cls.pginst
        # Step 1
        func = """CREATE FUNCTION plpgsql_test_function()
RETURNS text
AS $$
DECLARE
    result text;
BEGIN
    result = 'plpgsql test function';
    RETURN result;
END;
$$ LANGUAGE plpgsql;"""
        pginst.exec_psql_script(func)
        # Step 2
        result = pginst.exec_psql_select("SELECT plpgsql_test_function()")
        print result
        # Step 3
        assert result == "plpgsql test function"
        # Step 4
        pginst.exec_psql("DROP FUNCTION plpgsql_test_function()")

    @pytest.mark.test_passwordcheck
    def test_passwordcheck(self, request):
        """Test for passwordcheck feature for certified enterprise version
        Scenario:
        1. Check default value for password_min_unique_chars variable
        2. Check default value for password_min_pass_len
        3. Check default value for password_with_nonletters
        :param install_postgres:
        :param request:
        :return:
        """

        pginst = request.cls.pginst
        if request.config.getoption('--product_edition') != "ent-cert":
            pytest.skip("This test only for certified enterprise version.")

        result = pginst.exec_psql_select("SHOW passwordcheck.min_unique_chars")
        assert result == "8"

        result = pginst.exec_psql_select("SHOW passwordcheck.min_len")
        assert result == "8"

        result = pginst.exec_psql_select("SHOW passwordcheck.with_nonletters")
        assert result == "on"

    @pytest.mark.test_src_debug
    def test_src_debug(self, request):
        if self.system == 'Windows':
            pytest.skip("This test is not for Windows.")
        pgsrcdirs = glob.glob('/usr/src/debug/postgrespro*')
        for pgsrcdir in pgsrcdirs:
            dircontents = os.listdir(pgsrcdir)
            if len(dircontents) > 0:
                print("List of directory %s:" % pgsrcdir)
                print("\n".join(dircontents))
                raise Exception(
                    "Directory /usr/src/debug/postgrespro* is not empty.")
            print("Directory %s is empty." % pgsrcdir)

    @pytest.mark.test_full_remove
    def test_full_remove(self, request):
        """Try to delete all installed packages for version under test
        Scenario:
        1. Delete packages
        2. Check that postgres instance was stopped
        3. Check that test data is not deleted

        """

        pginst = request.cls.pginst
        dirsize0 = get_directory_size(pginst.get_default_datadir())
        assert dirsize0 > 0
        pids0 = get_process_pids(
            ['postgres', 'postgres.exe', 'postmaster'])
        assert len(pids0) > 0
        pginst.remove_full()
        dirsize1 = get_directory_size(pginst.get_default_datadir())
        assert abs(dirsize0 - dirsize1) < (1024 * 1024)
        pids1 = get_process_pids(
            ['postgres', 'postgres.exe', 'postmaster'])
        assert len(pids1) == 0
        # TODO: Uncomment (PGPRO-1534)
        # assert not(os.path.exists(pginst.get_default_bin_path()))
