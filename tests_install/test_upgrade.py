import platform
import distro
import pytest
import os
import pytest
import allure
from allure_commons.types import LabelType
from helpers.pginstall import PgInstall, PGPRO_ARCHIVE_ENTERPRISE,\
    PGPRO_ARCHIVE_STANDARD, ALT_BASED, DEBIAN_BASED
from helpers.constants import FIRST_RELEASE
from helpers.utils import diff_dbs, download_dump, urlopen
import time
import tempfile
import subprocess
import shutil
try:
    from bs4 import BeautifulSoup
except ImportError:  # py2compat
    from BeautifulSoup import BeautifulSoup
import re

system = platform.system()
tempdir = tempfile.gettempdir()

UPGRADE_ROUTES = {

    'postgrespro-std-9.6': {
        'from': [
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            }
        ]
    },

    'postgrespro-std-10': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            },
        ]
    },

    'postgrespro-std-11': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '11',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            },
        ]
    },
    'postgrespro-std-12': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '11'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '11',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            },
        ]
    },
    'postgrespro-std-cert-11': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std-cert', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '11',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            },
        ]
    },

    'postgrespro-ent-10': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '9.6'
            }
        ]
    },

    'postgrespro-ent-11': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '9.6'
            },
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '10'
            }
        ]
    },

    'postgrespro-ent-12': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '12'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '11'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '11'
            },
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '9.6'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '12',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '11',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            },
        ]
    }

}

DUMP_RESTORE_ROUTES = {

    'postgrespro-std-9.6': {
        'from': [
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            }
        ]
    },

    'postgrespro-std-10': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            },
        ]
    },

    'postgrespro-std-11': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '11',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            },
        ]
    },
    'postgrespro-std-12': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '11'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '11',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            },
        ]
    },
    'postgrespro-std-cert-11': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'std-cert', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '11',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            },
        ]
    },

    'postgrespro-ent-10': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '9.6'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            }
        ]
    },

    'postgrespro-ent-11': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '9.6'
            },
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '11'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '11',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            }
        ]
    },

    'postgrespro-ent-12': {
        'from': [
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '9.6'
            },
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'ent', 'version': '11'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '9.6'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '10'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '11'
            },
            {
                'name': 'postgrespro', 'edition': 'std', 'version': '12'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '10',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '11',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '12',
                'initdb-params': '--locale=C'
            },
            {
                'name': 'postgresql', 'edition': '', 'version': '9.6',
                'initdb-params': '--locale=C'
            }
        ]
    }

}


upgrade_dir = os.path.join(tempfile.gettempdir(), 'upgrade')
amcheck_sql = """
create extension if not exists amcheck;
alter extension amcheck update;
create extension if not exists pageinspect;
create or replace function bt_index_full_check(indexrelid oid, version int)
returns void
as $$ begin
  if version = 4 then perform bt_index_parent_check(indexrelid, true, true);
  else perform bt_index_parent_check(indexrelid, true);
  end if;
end; $$ language plpgsql;

select count(*) from (
    select
        i.indexrelid::regclass,
        i.indexrelid,
        am.amname,
        bt_index_full_check(i.indexrelid,
                            (bt_metap(indexrelid::regclass::varchar)).version)
    from
        pg_index i
        join pg_opclass op ON i.indclass[0] = op.oid
        join pg_am am ON op.opcmethod = am.oid
        join pg_class c ON i.indexrelid = c.oid
        join pg_namespace n ON c.relnamespace = n.oid
    where
        am.amname='btree' and n.nspname != 'pg_catalog'
        and c.relpersistence != 't'
        and c.relkind = 'i'
        and i.indisready and i.indisvalid
) t;
"""
remove_xid_type_columns_sql = """
DO $$
DECLARE
    alter_command TEXT;
BEGIN
    FOR alter_command IN
        SELECT 'ALTER TABLE "' || table_schema || '"."' ||
            table_name || '" DROP COLUMN "' || column_name || '" CASCADE;'
            AS alter_command
        FROM information_schema.columns
        WHERE data_type = 'xid' and table_schema != 'pg_catalog'
    LOOP
        EXECUTE alter_command;
    END LOOP;
END;
$$;
"""
drop_oids_sql = """
DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOR table_name IN
        SELECT '"' || n.nspname || '"."' || c.relname || '"' AS tab
        FROM pg_catalog.pg_class c, pg_catalog.pg_namespace n
        WHERE
            c.relnamespace = n.oid AND c.relhasoids AND n.nspname
            NOT IN ('pg_catalog') order by c.oid
    LOOP
        EXECUTE 'ALTER TABLE ' || table_name || ' SET WITHOUT OIDS';
    END LOOP;
END;
$$;
"""


def start(pg):
    if not pg.pg_isready():
        if not system == "Windows":
            pg.pg_control("start", pg.get_datadir())
        else:
            pg.start_service()
        for i in range(1, 100):
            if pg.pg_isready():
                break
            time.sleep(1)


def stop(pg, stopped=False):
    if stopped is None:
        if (pg.os_name in DEBIAN_BASED) and \
                (pg.version == '9.6' or pg.product == 'postgresql'):
            for i in range(1, 100):
                if pg.pg_isready():
                    break
                time.sleep(1)

    if not stopped and pg.pg_isready():
        if not system == "Windows":
            pg.pg_control("stop", pg.get_datadir())
        else:
            pg.stop_service()
        for i in range(1, 100):
            if not pg.pg_isready():
                break
            time.sleep(1)


def install_server(product, edition, version, milestone, branch, windows,
                   old=False):
    pg = PgInstall(product=product, edition=edition,
                   version=version, milestone=milestone,
                   branch=branch, windows=windows)
    pg.setup_repo()
    if not windows:
        if old and pg.os_name == 'SLES' and pg.os_version.startswith('12.'):
            for pkg in pg.all_packages_in_repo[:]:
                if ('libzstd' in pkg):
                    pg.all_packages_in_repo.remove(pkg)
        # PGPRO-3889
        if (pg.os_name.startswith('Centos') or
            pg.os_name.startswith('Red Hat') or
            pg.os_name.startswith('Oracle Linux')) and \
                pg.os_version.startswith('8'):
            for pkg in pg.all_packages_in_repo[:]:
                if ('jit' in pkg):
                    pg.all_packages_in_repo.remove(pkg)
        pg.install_full_topless()
        # PGPRO-2136
        if pg.os_name in ALT_BASED:
            subprocess.check_call(r"sudo sed -e 's/#\(Defaults:WHEEL_USERS"
                                  r"\s\+!env_reset\)/\1/' -i /etc/sudoers",
                                  shell=True)
            with open('/etc/sysconfig/i18n', 'r') as file:
                for line in file:
                    kv = line.split('=')
                    if len(kv) == 2:
                        os.environ[kv[0]] = kv[1].strip()
    else:
        pg.install_postgres_win()
        pg.client_path_needed = True
        pg.server_path_needed = True
        pg.load_shared_libraries()
    return pg


def do_in_all_dbs(pg, script):
    dbs = pg.exec_psql_select("SELECT datname FROM pg_database").\
        split(os.linesep)
    preoptions = os.environ['PGOPTIONS'] if 'PGOPTIONS' in os.environ else ''
    os.environ['PGOPTIONS'] = preoptions + ' --client-min-messages=warning'
    for db in dbs:
        if db != 'template0':
            os.environ['PGDATABASE'] = db
            pg.exec_psql_script(script, '-v ON_ERROR_STOP=1')
    del os.environ['PGDATABASE']
    os.environ['PGOPTIONS'] = preoptions


def generate_db(pg, pgnew, custom_dump=None):
    key = "-".join([pg.product, pg.edition, pg.version])
    dump_file_name = download_dump(pg.product, pg.edition, pg.version,
                                   tempdir, custom_dump)
    with open(os.path.join(tempdir, 'load-%s.log' % key), 'wb') as out:
        pg.exec_psql_file(dump_file_name, '-q',
                          stdout=out)
    if pgnew.version not in ["9.6", "10", "11"] and \
            pg.version in ["9.6", "10", "11"]:
        do_in_all_dbs(pg, drop_oids_sql)
    if pgnew.edition in ['ent', 'ent-cert'] and \
            pg.edition not in ['ent', 'ent-cert']:
        do_in_all_dbs(pg, remove_xid_type_columns_sql)
    expected_file_name = os.path.join(tempdir,
                                      "%s-expected.sql" % key)
    dumpall(pgnew, expected_file_name)


def dump_and_diff_dbs(oldKey, pgNew, prefix):
    result_file_name = "%s-%s-result.sql" % (prefix, oldKey)
    tempdir = tempfile.gettempdir()
    dumpall(pgNew, result_file_name)
    file1 = os.path.join(tempdir, result_file_name)
    file2 = os.path.join(tempdir, '%s-expected.sql' % oldKey)
    diff_file = os.path.join(tempdir, "%s-%s.sql.diff" % (prefix, oldKey))
    diff_dbs(file1, file2, diff_file)
    # PGPRO-3679
    if not (pgNew.edition == 'ent' and pgNew.version == '11'):
        do_in_all_dbs(pgNew, amcheck_sql)


def upgrade(pg, pgOld):
    # type: (PgInstall, PgInstall) -> str
    start_time = time.time()
    stop(pg)
    stop(pgOld)
    if os.path.exists(upgrade_dir):
        shutil.rmtree(upgrade_dir)
    os.makedirs(upgrade_dir)
    if not system == "Windows":
        subprocess.check_call('chown postgres:postgres "%s"' % upgrade_dir,
                              shell=True)

    cmd = '%s"%spg_upgrade" -d "%s" -b "%s" -D "%s" -B "%s"' % \
          (
              pg.pg_sudo_cmd,
              pg.get_server_bin_path(),
              pgOld.get_datadir(),
              pgOld.get_default_bin_path(),
              pg.get_datadir(),
              pg.get_default_bin_path()
          )

    with open(os.path.join(tempdir,
                           'pg_upgrade-%s.log' %
                           "-".join([pgOld.product, pgOld.edition,
                                     pgOld.version])),
              'wb') as out:
        subprocess.check_call(cmd, shell=True, cwd=upgrade_dir, stdout=out)
    print("upgrade complete in %s sec" % (time.time()-start_time))


def dumpall(pg, file):
    cmd = '%s"%spg_dumpall" -h localhost -f "%s"' % \
          (
              pg.pg_sudo_cmd,
              pg.get_server_bin_path(),
              file
          )
    subprocess.check_call(cmd, shell=True, cwd=tempfile.gettempdir())


def after_upgrade(pg, pgOld):
    start_time = time.time()
    if not system == "Windows":
        subprocess.check_call('sudo -u postgres ./analyze_new_cluster.sh',
                              shell=True, cwd=upgrade_dir)
        subprocess.check_call('./delete_old_cluster.sh',
                              shell=True, cwd=upgrade_dir)
    else:
        subprocess.check_call('analyze_new_cluster.bat',
                              shell=True, cwd=upgrade_dir)
        subprocess.check_call('delete_old_cluster.bat',
                              shell=True, cwd=upgrade_dir)
    # Find any sql's after upgrade
    for file in os.listdir(upgrade_dir):
        if ".sql" in file:
            file_name = os.path.join(upgrade_dir, file)
            with open(os.path.join(tempdir,
                                   'after-%s.log' %
                                   '-'.join([pgOld.product, pgOld.edition,
                                             pgOld.version])),
                      'wb') as out:
                pg.exec_psql_file(file_name, stdout=out)
    print("after_upgrade complete in %s sec" % (time.time()-start_time))


def init_cluster(pg, force_remove=True, initdb_params='',
                 stopped=None, load_libs=True):
    if system == 'Windows':
        restore_datadir_win(pg)
    else:
        stop(pg, stopped)
        pg.init_cluster(force_remove, '-k ' + initdb_params)
        start(pg)
        if load_libs:
            pg.load_shared_libraries(restart_service=False)
        stop(pg)
    start(pg)


def backup_datadir_win(pg):
    cmd = 'xcopy /S /E /O /X /I /Q "%s" "%s.bak"' %\
          (pg.get_datadir(), pg.get_datadir())
    subprocess.check_call(cmd, shell=True)


def restore_datadir_win(pg):
    pg.remove_data()
    cmd = 'xcopy /S /E /O /X /I /Q "%s" "%s"' %\
          (pg.get_datadir() + '.bak', pg.get_datadir())
    subprocess.check_call(cmd, shell=True)


def get_last_version(edition, version):

    if edition == "ent":
        archive_url = PGPRO_ARCHIVE_ENTERPRISE
    elif edition == "std":
        archive_url = PGPRO_ARCHIVE_STANDARD
    else:
        raise Exception("Unsupported postgrespro edition (%s)." % edition)

    # Choose two versions -- newest and oldest supported
    soup = BeautifulSoup(urlopen(archive_url))
    arcversions = []
    for link in soup.findAll('a'):
        href = link.get('href')
        if href.startswith('pgpro') and href.endswith('/'):
            vere = re.search(r'\w+-([0-9.]+)/', href)
            if vere:
                if vere.group(1).startswith(version):
                    ver = vere.group(1)
                    arcvers = ver.split('.')
                    arcversion = '.'.join([d.rjust(4) for d in arcvers])
                    if version == '9.6':
                        # Due to CATALOG_VERSION_NO change
                        # we don't support lower 9.6 versions
                        if arcversion < '   9.   6.   4.   1':
                            arcversion = None
                    if arcversion:
                        arcversions.append(arcversion)
    arcversions.sort()
    return arcversions[-1]


@pytest.mark.upgrade
class TestUpgrade():
    system = system

    @pytest.mark.test_upgrade
    def test_upgrade(self, request):
        """
        Scenario:
        1. Install testible version
        2. if route install upgradeble version
        3. Create DB with covering dump
        4. Upgrade by pg_upgrade
        5. Check that upgrade successfull (calculate diff between dump)
        :return:
        """
        dist = ""
        if self.system == 'Linux':
            dist = " ".join(distro.linux_distribution()[0:2])
        elif self.system == 'Windows':
            dist = " ".join(platform.win32_ver()[0:2])
        else:
            raise Exception("OS %s is not supported." % self.system)
        request.cls.dist = dist
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        milestone = request.config.getoption('--product_milestone')
        target = request.config.getoption('--target')
        product_info = " ".join([dist, name, edition, version])
        request.cls.product_info = product_info
        key = "-".join([name, edition, version])
        request.cls.key = key

        print("Running on %s." % target)

        if dist in FIRST_RELEASE and key in FIRST_RELEASE[dist] and \
                FIRST_RELEASE[dist][key] is None:
            print("Platform not supported")
            return

        if key not in UPGRADE_ROUTES:
            print('No routes for upgrade')
            return

        upgrade_route = UPGRADE_ROUTES[key]

        tag_mark = allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        # Install the tested version
        branch = request.config.getoption('--branch')
        pg = install_server(product=name, edition=edition,
                            version=version, milestone=milestone,
                            branch=branch, windows=(self.system == 'Windows'))
        request.cls.pg = pg
        stop(pg)

        if pg.os_name in DEBIAN_BASED and pg.version == '9.6':
            print("Two products 9.6 cannot be "
                  "installed simultaneously on debian-based OS")
            return

        if self.system == 'Windows':
            backup_datadir_win(pg)

        for route in upgrade_route['from']:
            initdb_params = route['initdb-params'] if \
                'initdb-params' in route else ''
            init_cluster(pg, True, initdb_params, True, False)
            stop(pg)
            old_name = route['name']
            old_edition = route['edition']
            old_version = route['version']
            old_key = "-".join([old_name, old_edition, old_version])
            if dist in FIRST_RELEASE and old_key in FIRST_RELEASE[dist]:
                if FIRST_RELEASE[dist][old_key] is None:
                    print("Distributive is not supported")
                    continue
                first_release = '.'.join(
                    [d.rjust(4) for d in FIRST_RELEASE[dist][old_key].
                        split('.')])
                if first_release > get_last_version(old_edition, old_version):
                    print("Wait for %s" % FIRST_RELEASE[dist][old_key])
                    continue

            print("=====Check upgrade from %s" % old_key)

            pgold = install_server(
                product=old_name, edition=old_edition,
                version=old_version, milestone=None,
                branch=None, windows=(self.system == 'Windows'), old=True
            )
            if self.system != 'Windows':
                init_cluster(pgold, True, initdb_params, None, True)

            generate_db(pgold, pg)
            dumpall(pgold,
                    os.path.join(tempfile.gettempdir(), "%s.sql" % old_key))
            stop(pgold)
            upgrade(pg, pgold)
            start(pg)
            after_upgrade(pg, pgold)
            dump_and_diff_dbs(old_key, pg, 'upgrade')
            stop(pg)
            pgold.remove_full(do_not_remove=[
                    r"^libc.*", r".*icu.*", r".*zstd.*", r"^llvm.*"
                ])
            # PGPRO-2459
            if pgold.os_name in DEBIAN_BASED and \
                    old_name == "postgrespro" and old_version == "9.6":
                subprocess.check_call("apt-get purge -y postgrespro-common "
                                      "postgrespro-client-common", shell=True)

    @pytest.mark.test_dump_restore
    def test_dump_restore(self, request):
        """
        Scenario:
        3. if route install upgradeble version
        7. Check that upgrade successfull (select from table)
        :return:
        """
        product_info = request.cls.product_info
        tag_mark = allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)

        key = request.cls.key
        dist = request.cls.dist

        print("Test dump-restore %s" % product_info)

        if dist in FIRST_RELEASE and key in FIRST_RELEASE[dist] and \
                FIRST_RELEASE[dist][key] is None:
            print("Platform not supported")
            return

        if key not in DUMP_RESTORE_ROUTES:
            print('No routes for dump-restore')
            return

        dump_restore_route = DUMP_RESTORE_ROUTES[key]

        pg = request.cls.pg

        if pg.os_name in DEBIAN_BASED and pg.version == '9.6':
            print("Two products 9.6 cannot be "
                  "installed simultaneously on debian-based")
            return

        for route in dump_restore_route['from']:
            initdb_params = route['initdb-params'] if \
                'initdb-params' in route else ''
            init_cluster(pg, True, initdb_params, True, False)
            stop(pg)

            old_name = route['name']
            old_edition = route['edition']
            old_version = route['version']
            old_key = "-".join([old_name, old_edition, old_version])
            if dist in FIRST_RELEASE and old_key in FIRST_RELEASE[dist]:
                if FIRST_RELEASE[dist][old_key] is None:
                    print("Distributive is not supported")
                    continue
                first_release = '.'.join(
                    [d.rjust(4) for d in FIRST_RELEASE[dist][old_key].
                        split('.')])
                if first_release > get_last_version(old_edition, old_version):
                    print("Wait for %s" % FIRST_RELEASE[dist][old_key])
                    continue

            print("=====Check dump-restore from %s" % old_key)

            file_name = os.path.join(tempfile.gettempdir(), "%s.sql" % old_key)

            if (os.path.isfile(file_name)):
                start(pg)
                with open(os.path.join(tempdir, 'load-dr-%s.log' % old_key),
                          'wb') as out:
                    pg.exec_psql_file(file_name, '-q', stdout=out)
                dump_and_diff_dbs(old_key, pg, 'dump-restore')
                stop(pg)
            else:
                pgold = install_server(
                    product=old_name, edition=old_edition,
                    version=old_version, milestone=None,
                    branch=None, windows=(self.system == 'Windows'), old=True
                )
                if self.system != 'Windows':
                    init_cluster(pgold, True, initdb_params, None, True)

                generate_db(pgold, pg)
                dumpall(pgold, file_name)
                stop(pgold)

                start(pg)
                with open(os.path.join(tempdir, 'load-dr-%s.log' % old_key),
                          'wb') as out:
                    pg.exec_psql_file(file_name, '-q', stdout=out)
                dump_and_diff_dbs(old_key, pg, 'upgrade')
                stop(pg)
                pgold.remove_full(True, do_not_remove=[
                    r"^libc.*", r".*icu.*", r".*zstd.*", r"^llvm.*"
                ])
                # PGPRO-2459
                if pgold.os_name in DEBIAN_BASED and \
                        old_name == "postgrespro" and old_version == "9.6":
                    subprocess.check_call("apt-get purge -y "
                                          "postgrespro-common "
                                          "postgrespro-client-common",
                                          shell=True)
