import platform
import os
import allure
from allure_commons.types import LabelType
from helpers.pginstall import PgInstall, PGPRO_ARCHIVE_ENTERPRISE,\
    PGPRO_ARCHIVE_STANDARD
from helpers.os_helpers import ALT_BASED, DEBIAN_BASED
from helpers.constants import FIRST_RELEASE, UPGRADE_ROUTES,\
    DUMP_RESTORE_ROUTES
from helpers.utils import diff_dbs, download_dump, get_distro, \
    compare_versions, extend_ver, get_soup
import time
import subprocess
import shutil
import re

system = platform.system()
tempdir = os.path.join(os.path.abspath(os.getcwd()), 'tmp')
tablespacedir = os.path.join(tempdir, 'ts')

upgrade_dir = os.path.join(tempdir, 'upgrade')
amcheck_sql = """
create extension if not exists amcheck;
alter extension amcheck update;
create extension if not exists pageinspect;
alter extension pageinspect update;
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
        case when ae.default_version = '1.0' then
          bt_index_parent_check(i.indexrelid)
        else
          bt_index_full_check(i.indexrelid,
                              (bt_metap(indexrelid::regclass::varchar)).version)
        end
    from
        pg_index i
        join pg_opclass op ON i.indclass[0] = op.oid
        join pg_am am ON op.opcmethod = am.oid
        join pg_class c ON i.indexrelid = c.oid
        join pg_namespace n ON c.relnamespace = n.oid
        join pg_available_extensions ae ON ae.name='amcheck'
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
    DROP VIEW IF EXISTS my_locks;
END;
$$;
"""
prepare_for_12_plus_sql = """
DO $$
DECLARE
    table_name TEXT;
    attname TEXT;
    typname TEXT;
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
    FOR table_name, attname, typname IN
        SELECT
            '"' || n.nspname || '"."' || c.relname || '"' AS tab,
            pa.attname as col,
            pt.typname as typname
        FROM
            pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
            JOIN pg_catalog.pg_attribute pa ON pa.attrelid=c.oid
            JOIN pg_catalog.pg_type pt ON pa.atttypid=pt.oid
        WHERE
            n.nspname NOT IN ('pg_catalog')
            AND pt.typname IN ('abstime','reltime','tinterval','smgr',
                '_abstime','_reltime','_tinterval','_smgr')
        ORDER BY c.oid
    LOOP
        EXECUTE 'ALTER TABLE ' || table_name || ' ALTER COLUMN ' || attname ||
         ' TYPE VARCHAR';
    END LOOP;
END;
$$;
"""
prepare_for_13_plus_sql = """
DO $$
DECLARE
    con_name TEXT;
BEGIN
    FOR con_name IN
        SELECT
            '"' || n.nspname || '"."' || pc.conname || '"' AS cname
        FROM pg_catalog.pg_conversion pc
            JOIN pg_catalog.pg_namespace n ON pc.connamespace = n.oid
        WHERE
            n.nspname NOT IN ('pg_catalog')
            AND 'SQL_ASCII' IN (pg_encoding_to_char(pc.conforencoding),
                                pg_encoding_to_char(pc.contoencoding))
    LOOP
        EXECUTE 'DROP CONVERSION ' || con_name || ';';
    END LOOP;
    EXECUTE 'DROP EXTENSION IF EXISTS hunspell_ne_np CASCADE';
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
    if pg.os.is_altlinux() and pg.os.os_arch == 'aarch64':
        os.environ['LANG'] = 'en_US.UTF-8'
    if not windows:
        if old and pg.os_name == 'SLES' and pg.os_version.startswith('12.'):
            for pkg in pg.all_packages_in_repo[:]:
                if ('libzstd' in pkg):
                    pg.all_packages_in_repo.remove(pkg)
        # PGPRO-3889
        if (pg.os_name.startswith('CentOS') or
            pg.os_name.startswith('Red Hat') or
            pg.os_name.startswith('Oracle Linux')) and \
                pg.os_version.startswith('8'):
            for pkg in pg.all_packages_in_repo[:]:
                if ('jit' in pkg):
                    pg.all_packages_in_repo.remove(pkg)
        pg.install_full_topless()
        # PGPRO-2136
        if pg.os_name in ALT_BASED:
            with open('/etc/sysconfig/i18n', 'r') as file:
                for line in file:
                    kv = line.split('=')
                    if len(kv) == 2:
                        os.environ[kv[0]] = kv[1].strip()
    else:
        pg.install_postgres_win()
        pg.client_path_needed = True
        pg.server_path_needed = True
        pg.install_default_config()
        pg.load_shared_libraries()
    return pg


def prepare_ts_dir(pg):
    if os.path.exists(tablespacedir):
        shutil.rmtree(tablespacedir)
    pg.exec_psql("COPY (SELECT 1) TO PROGRAM 'mkdir %s';" %
                 tablespacedir)


def generate_db(pg, pgnew, custom_dump=None, on_error_stop=True):
    key = "-".join([pg.product, pg.edition, pg.version])
    dump_file_name = download_dump(pg.product, pg.edition, pg.version,
                                   tempdir, custom_dump)
    with open(os.path.join(tempdir, 'load-%s.log' % key), 'wb') as out:
        pg.exec_psql_file(dump_file_name, '-q%s' %
                          (' -v ON_ERROR_STOP=1' if on_error_stop else ''),
                          stdout=out)
    if pg.edition in ['ent', 'ent-cert']:
        # TEST-162
        prepare_ts_dir(pg)
        pg.exec_psql('CREATE TABLESPACE ts '
                     'LOCATION \'%s\' WITH(compression = true);' %
                     tablespacedir)
        pg.exec_psql(
            "CREATE TABLESPACE ts"
            " LOCATION \'%s\' WITH(compression = true); "
            "CREATE TABLE tbl TABLESPACE ts"
            " AS SELECT i, rpad('',30,'a')"
            " FROM generate_series(0,10000) AS i;" % tablespacedir)

    if compare_versions(pg.version, '12') < 0 and \
            compare_versions(pgnew.version, '12') >= 0:
        pg.do_in_all_dbs(prepare_for_12_plus_sql, 'prepare_for_12_plus')
    if compare_versions(pg.version, '13') < 0 and \
            compare_versions(pgnew.version, '13') >= 0:
        pg.do_in_all_dbs(prepare_for_13_plus_sql, 'prepare_for_13_plus')
    # wait for 12.5
    if pg.version == '12':
        pg.exec_psql('DROP TABLE IF EXISTS test_like_5c CASCADE',
                     '-d regression')
    if pgnew.edition in ['ent', 'ent-cert'] and \
            pg.edition not in ['ent', 'ent-cert']:
        pg.do_in_all_dbs(remove_xid_type_columns_sql, 'remove_xid_type_cols')
    expected_file_name = os.path.join(tempdir,
                                      "%s-expected.sql" % key)
    dumpall(pgnew, expected_file_name)


def dump_and_diff_dbs(oldKey, pgNew, prefix):
    result_file_name = "%s-%s-result.sql" % (prefix, oldKey)
    dumpall(pgNew, result_file_name)
    file1 = os.path.join(tempdir, result_file_name)
    file2 = os.path.join(tempdir, '%s-expected.sql' % oldKey)
    diff_file = os.path.join(tempdir, "%s-%s.sql.diff" % (prefix, oldKey))
    diff_dbs(file2, file1, diff_file)

    # PGPRO-4882
    if pgNew.version == '13' and pgNew.edition in ['ent', 'ent-cert']:
        crpi = pgNew.exec_psql_select(
            "SELECT COUNT(*) FROM pg_database WHERE "
            "datname='contrib_regression_pageinspect'")
        if crpi == '1':
            pgNew.exec_psql('DROP EXTENSION IF EXISTS pageinspect',
                            '-d contrib_regression_pageinspect')
    pgNew.do_in_all_dbs(amcheck_sql, 'amcheck')


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
    subprocess.check_call(cmd, shell=True, cwd=tempdir)


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
                pg.exec_psql_file(file_name, ' -v ON_ERROR_STOP=1',
                                  stdout=out)
    print("after_upgrade complete in %s sec" % (time.time()-start_time))


def init_cluster(pg, force_remove=True, initdb_params='',
                 stopped=None, load_libs=True):
    if system == 'Windows':
        restore_datadir_win(pg)
    else:
        stop(pg, stopped)
        pg.init_cluster(force_remove, '-k ' + initdb_params)
        pg.install_default_config()
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
    elif edition in ["std", "1c"]:
        archive_url = PGPRO_ARCHIVE_STANDARD
    else:
        raise Exception("Unsupported postgrespro edition (%s)." % edition)

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
                    ver = vere.group(1)
                    if version == '9.6':
                        # Due to CATALOG_VERSION_NO change
                        # we don't support lower 9.6 versions
                        if compare_versions(ver, '9.6.4.1') < 0:
                            ver = None
                    if ver:
                        arcversions.append(ver)
    arcversions.sort(key=extend_ver)
    return arcversions[-1]


class TestUpgrade():
    system = system

    def test_upgrade(self, request):
        """
        Scenario:
        1. Install testible version
        2. if route install upgradeable version
        3. Create DB with covering dump
        4. Upgrade by pg_upgrade
        5. Check that upgrade successfull (calculate diff between dump)
        :return:
        """
        distro = get_distro()
        if distro[2] == 'x86_64' or self.system == 'Windows':
            distro = distro[:-1]
        dist = " ".join(distro)
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
                if compare_versions(
                        FIRST_RELEASE[dist][old_key],
                        get_last_version(old_edition, old_version)) > 0:
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

            generate_db(
                pgold, pg,
                on_error_stop=False if pgold.os_arch == 'x86' else True
            )
            dumpall(pgold,
                    os.path.join(tempdir, "%s.sql" % old_key))
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
                    old_name == "postgrespro" and old_version == "9.6" and \
                    old_edition != '1c':
                subprocess.check_call("apt-get purge -y postgrespro-common "
                                      "postgrespro-client-common", shell=True)

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
                if compare_versions(
                        FIRST_RELEASE[dist][old_key],
                        get_last_version(old_edition, old_version)) > 0:
                    print("Wait for %s" % FIRST_RELEASE[dist][old_key])
                    continue

            print("=====Check dump-restore from %s" % old_key)

            file_name = os.path.join(tempdir, "%s.sql" % old_key)

            if (os.path.isfile(file_name)):
                start(pg)
                prepare_ts_dir(pg)
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

                generate_db(
                    pgold, pg,
                    on_error_stop=False if pgold.os_arch == 'x86' else True
                )
                dumpall(pgold, file_name)
                stop(pgold)

                start(pg)
                with open(os.path.join(tempdir, 'load-dr-%s.log' % old_key),
                          'wb') as out:
                    pg.exec_psql_file(file_name, '-q', stdout=out)
                dump_and_diff_dbs(old_key, pg, 'dump-restore')
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
