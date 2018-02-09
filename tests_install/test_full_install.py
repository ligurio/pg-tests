import os
import platform
import subprocess
import glob

import pytest
import settings

from allure_commons.types import LabelType
from helpers.pginstall import (setup_repo,
                               get_all_packages_name,
                               install_package,
                               initdb_start,
                               install_postgres_win,
                               remove_package,
                               install_perl_win,
                               exec_psql,
                               get_server_version,
                               get_psql_version,
                               get_initdb_props,
                               restart_service)

PRELOAD_LIBRARIES = {
    'standard':
        ['auth_delay', 'auto_explain', 'pg_pathman', 'plantuner',
         'shared_ispell'],
    'ee':
        ['auth_delay', 'auto_explain', 'in_memory', 'pg_pathman',
         'pg_shardman', 'pgpro_scheduler', 'plantuner', 'shared_ispell'],
}


@pytest.mark.full_install
class TestFullInstall():

    os = platform.system()

    @pytest.mark.test_full_install
    def test_full_install(self, request):
        """
        Scenario:
        1. Install current version
        2. Check that setup successfull

        :return:
        """
        dist = ""
        if self.os == 'Linux':
            dist = " ".join(platform.linux_distribution()[0:2])
        elif self.os == 'Windows':
            dist = 'Windows'
            install_perl_win()
        else:
            raise Exception("OS %s is not supported." % self.os)
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

        # Step 1
        setup_repo(name=name, version=version, edition=edition,
                   milestone=milestone, branch=branch)
        print("Running on %s." % target)
        if self.os != 'Windows':
            package_name = get_all_packages_name(name, edition, version)
            install_package(package_name)
            initdb_start(name=name, version=version, edition=edition)
        else:
            install_postgres_win()
        server_version = get_server_version()
        client_version = get_psql_version()
        print("Server version:\n%s\nClient version:\n%s" %
              (server_version, client_version))
        print("OK")

    @pytest.mark.test_all_extensions
    def test_all_extensions(self, request):
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')

        iprops = get_initdb_props()
        exec_psql("ALTER SYSTEM SET shared_preload_libraries = %s" %
                  ','.join(PRELOAD_LIBRARIES[edition]))
        restart_service(name=name, version=version, edition=edition)
        share_path = iprops['share_path'].replace('/', os.sep)
        controls = glob.glob(os.path.join(share_path,
                                          'extension', '*.control'))
        for ctrl in sorted(controls):
            extension = os.path.splitext(os.path.basename(ctrl))[0]
            # TODO: Remove
            if self.os == 'Windows' and extension.endswith('plpython3u'):
                print("CREATE EXTENSION %s skipped (PGPRO-1252)" % extension)
                continue
            # multimaster requires a special setup
            if extension == 'multimaster':
                continue
            print("CREATE EXTENSION %s" % extension)
            exec_psql("CREATE EXTENSION IF NOT EXISTS \\\"%s\\\" CASCADE" %
                      extension)

    @pytest.mark.test_full_remove
    def test_full_remove(self, request):
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        version = request.config.getoption('--product_version')
        package_name = get_all_packages_name(name, edition, version)
        remove_package(package_name)
