import os
import platform
import subprocess
import glob

import pytest
import settings

from allure_commons.types import LabelType
from helpers.pginstall import setup_repo
from helpers.pginstall import install_package, remove_package
from helpers.pginstall import (exec_psql,
                               get_server_version,
                               get_psql_version,
                               get_initdb_props,
                               get_pg_setting,
                               pg_control)

PRELOAD_LIBRARIES = ['auth_delay', 'auto_explain', 'pg_pathman', 'plantuner', 'shared_ispell']


@pytest.mark.full_install
class TestFullInstall():

    os = ""

    @pytest.mark.test_full_install
    def test_full_install(self, request):
        """
        Scenario:
        1. Install current version
        2. Check that setup successfull

        :return:
        """
        dist = ""
        self.os = platform.system()
        if self.os == 'Linux':
            dist = " ".join(platform.linux_distribution()[0:2])
        elif self.os == 'Windows':
            dist = 'Windows'
        else:
            raise Exception("OS %s is not supported." % self.os)
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        build = request.config.getoption('--product_build')
        milestone = request.config.getoption('--product_milestone')
        target = request.config.getoption('--target')
        product_info = " ".join([dist, name, edition, version])
        tag_mark = pytest.allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        branch = request.config.getoption('--branch')

        # Step 1
        tag_mark = pytest.allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        setup_repo(name=name, version=version, edition=edition, milestone=milestone, branch=branch)
        edtn = ''
        if edition:
            if edition == 'standard':
                edtn = '-std'
            else:
                raise Exception('Edition %s is not supported.' % edition)
        print("Running on %s." % target)
        install_package('%s%s-%s*' % (name, edtn, version))
        server_version = get_server_version()
        client_version = get_psql_version()
        print("Server version:\n%s\nClient version:\n%s" % (server_version, client_version))
        print("OK")

    @pytest.mark.test_all_extensions
    def test_all_extensions(self, request):
        iprops = get_initdb_props()
        exec_psql("ALTER SYSTEM SET shared_preload_libraries = %s" %
                  ','.join(PRELOAD_LIBRARIES))
        data_directory = get_pg_setting('data_directory')
        pg_control("restart", data_directory)
        controls = glob.glob(os.path.join(iprops['share_path'], 'extension', '*.control'))
        for ctrl in sorted(controls):
            extension = os.path.splitext(os.path.basename(ctrl))[0]
            print("CREATE EXTENSION:", extension)
            exec_psql("CREATE EXTENSION IF NOT EXISTS \\\"%s\\\" CASCADE" % extension)
        #if self.os == 'Linux':
            #subprocess.check_call("/home/test/pg-tests/tests_install/test_extensions.sh",
                                  #cwd="/tmp", shell=True)

    @pytest.mark.test_full_remove
    def test_full_remove(self, request):
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        edtn = ''
        if edition:
            if edition == 'standard':
                edtn = '-std'
            else:
                raise Exception('Edition %s is not supported.' % edition)
        remove_package('%s%s-%s*' % (name, edtn, version))
