import os
import platform
import subprocess
import glob

import pytest
import settings

from allure_commons.types import LabelType
from helpers.pginstall import (setup_repo,
                               install_package,
                               install_postgres_win,
                               remove_package,
                               install_perl_win,
                               exec_psql,
                               get_server_version,
                               get_psql_version,
                               get_initdb_props,
                               get_pg_setting,
                               restart_service)

PRELOAD_LIBRARIES = ['auth_delay', 'auto_explain', 'pg_pathman',
                     'plantuner', 'shared_ispell']


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
        build = request.config.getoption('--product_build')
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
        edtn = ''
        if edition:
            if edition == 'standard':
                edtn = 'std'
            else:
                raise Exception('Edition %s is not supported.' % edition)
        print("Running on %s." % target)
        if self.os != 'Windows':
            install_package('%s-%s-%s' % (name, edtn, version))
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
                  ','.join(PRELOAD_LIBRARIES))
        data_directory = get_pg_setting('data_directory')
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
            # TODO: Remove
            if self.os == 'Windows' and extension == 'test_ext7':
                print("CREATE EXTENSION %s skipped (PGPRO-1256)" % extension)
                continue
            # TODO: Remove
            if self.os == 'Windows' and \
               extension.startswith('test_ext_cyclic'):
                print("CREATE EXTENSION %s skipped (PGPRO-1257)" % extension)
                continue
            # TODO: Remove
            if self.os == 'Windows' and extension == 'test_pg_dump':
                print("CREATE EXTENSION %s skipped (PGPRO-1258)" % extension)
                continue
            # TODO: Remove
            if self.os == 'Windows' and extension == 'test_rls_hooks':
                print("CREATE EXTENSION %s skipped (PGPRO-1260)" % extension)
                continue
            # TODO: Remove
            if self.os != 'Windows' and (extension.endswith('_plperl') or
                                         extension.endswith('_plperlu') or
                                         extension.endswith('_plpythonu') or
                                         extension.endswith('_plpython2u')):
                print("CREATE EXTENSION %s skipped (PGPRO-1253)" % extension)
                continue
            print("CREATE EXTENSION %s" % extension)
            exec_psql("CREATE EXTENSION IF NOT EXISTS \\\"%s\\\" CASCADE" %
                      extension)

    @pytest.mark.test_full_remove
    def test_full_remove(self, request):
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        edtn = ''
        if edition:
            if edition == 'standard':
                edtn = 'std'
            else:
                raise Exception('Edition %s is not supported.' % edition)
        remove_package('%s-%s-%s*' % (name, edtn, version))
