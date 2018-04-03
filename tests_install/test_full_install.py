import os
import platform
import glob

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall
from helpers.os_helpers import get_directory_size
from helpers.os_helpers import get_process_pids

PRELOAD_LIBRARIES = {
    'standard-10':
        ['auth_delay', 'auto_explain', 'pg_pathman', 'plantuner',
         'shared_ispell'],
    'ee-10':
        ['auth_delay', 'auto_explain', 'in_memory', 'pg_pathman',
         'pg_shardman', 'pgpro_scheduler', 'plantuner', 'shared_ispell'],
    'ee-9.6':
        ['auth_delay', 'auto_explain', 'pg_pathman',
         'pgpro_scheduler', 'plantuner', 'shared_ispell'],
    'cert-enterprise-9.6':
        ['auth_delay', 'auto_explain', 'passwordcheck', 'pg_pathman',
         'pgaudit', 'pgpro_scheduler', 'plantuner',
         'shared_ispell'],
    'cert-enterprise-10':
        ['auth_delay', 'auto_explain', 'passwordcheck', 'pg_pathman',
         'pgaudit', 'pgpro_scheduler', 'plantuner',
         'shared_ispell'],
    '1c-10':
        ['auth_delay', 'auto_explain', 'plantuner'],
}


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
            pginst.install_full()
            pginst.initdb_start()
        else:
            pginst.install_perl_win()
            pginst.install_postgres_win()
        server_version = pginst.get_server_version()
        client_version = pginst.get_psql_version()
        print("Server version:\n%s\nClient version:\n%s" %
              (server_version, client_version))
        if name == 'postgrespro' and edition != '1c':
            ppversion = pginst.exec_psql_select("SELECT pgpro_version()")
            assert ppversion.startswith('PostgresPro ' + version)
            ppedition = pginst.exec_psql_select("SELECT pgpro_edition()")
            if edition == 'ee':
                assert ppedition == 'enterprise'
            elif edition == 'cert-enterprise':
                assert ppedition == 'enterprise'
            else:
                assert ppedition == 'standard'
        print("OK")

    @pytest.mark.test_all_extensions
    def test_all_extensions(self, request):
        pginst = request.cls.pginst
        iprops = pginst.get_initdb_props()
        pginst.exec_psql(
            "ALTER SYSTEM SET shared_preload_libraries = %s" %
            ','.join(PRELOAD_LIBRARIES[request.cls.pgid]))
        pginst.restart_service()
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
return "python test function"
$$ LANGUAGE plpython2u;"""
        pginst.exec_psql_script(func)
        # Step 2
        result = pginst.exec_psql_select("SELECT py_test_function()")
        # Step 3
        assert result == "python test function"
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
        # Step 1
        func = """CREATE FUNCTION plperl_test_function()
RETURNS text
AS $$
return "plperl test function"
$$ LANGUAGE plperl;"""
        pginst.exec_psql_script(func)
        # Step 2
        result = pginst.exec_psql_select("SELECT plperl_test_function()")
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
        if request.config.getoption('--product_edition') != "cert-enterprise":
            pytest.skip("This test only for certified enterprise version.")

        result = pginst.exec_psql_select("SHOW password_min_unique_chars")
        assert result == "8"

        result = pginst.exec_psql_select("SHOW password_min_pass_len")
        assert result == "8"

        result = pginst.exec_psql_select("SHOW password_with_nonletters")
        assert result == "on"

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
        assert not(os.path.exists(pginst.get_default_bin_path()))
