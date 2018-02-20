import os
import platform
import glob

import pytest

from allure_commons.types import LabelType
from helpers.pginstall import PgInstall

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
        print("OK")

    # pylint: disable=unused-argument
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
        result = pginst.exec_psql("SELECT py_test_function()",
                                  "-t -P format=unaligned")
        # Step 3
        assert result == "python test function"
        # Step 4
        pginst.exec_psql("DROP FUNCTION py_test_function()")

    # pylint: disable=unused-argument
    @pytest.mark.test_full_remove
    def test_full_remove(self, request):
        pginst = request.cls.pginst
        pginst.remove_full()
