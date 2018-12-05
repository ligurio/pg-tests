import os
import psycopg2
import subprocess


from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from helpers.os_helpers import create_tablespace_directory
from helpers.os_helpers import pg_bindir
from helpers.utils import (command_executor,
                           get_distro,
                           REMOTE_ROOT,
                           REMOTE_ROOT_PASSWORD)
from tests import settings

# TODO Change to class  all methods


def get_pgpro_info(pgpgro_version):
    """

    :param pgpgro_version: string like with PGPRO version
    :return: dict with parsed pgpro_version
    """
    name = pgpgro_version.split()[0]
    version = '.'.join(pgpgro_version.split()[1].split('.')[0:2])
    build = pgpgro_version.split()[1].split('.')[3]
    return {'version': version,
            'name': name,
            'build': build}


def create_test_database(db_name):
    """
    Create database
    :param db_name: string with db name
    :return:
    """
    conn_string = "host='localhost' user='postgres' "
    conn = psycopg2.connect(conn_string)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE {}".format(db_name))


def create_test_table(size, schema):
    """ This method needed for creating table with fake data.
    :param schema - SQL schema, the default schema includes
                     almost all available data types:
    :param size - number of rows to insert, default value is 10000:
    :return: string as exit code
    """

    if schema == "mixed":
        sqlschema = settings.MIXED_SCHEMA
    elif schema == "pgbench":
        sqlschema = settings.PGBENCH_SCHEMA
    else:
        sqlschema = schema

    datagen_cmd = ["python", "./helpers/datafiller.py", "--filter",
                   "--transaction", "--drop", "--size=%s" % size]

    p = subprocess.Popen(datagen_cmd, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE)
    p.stdin.write(sqlschema)
    p.stdin.close()

    psql = subprocess.Popen(["sudo", "-u", "postgres", "psql"],
                            stdin=p.stdout)
    psql.wait()

    return psql.returncode


def execute(conn, sql_query):
    """Execute sql query

    :param conn: psycopg2 connection object
    :param sql_query:
    :return: string
    """

    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    try:
        cursor.execute(sql_query)
    except psycopg2.Error as e:
        print e.pgerror
        raise Exception("SQL execution failed")
    conn.commit()

    response = None
    if cursor.description is not None:
        response = cursor.fetchall()
    cursor.close()

    return response


def drop_test_table(conn_string):
    """Drop tables from schema public
    :return: 0
    """
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 'DROP TABLE IF EXISTS \"\' || tablename ||"
        " \'\" CASCADE;\' FROM pg_tables WHERE schemaname = 'public';")
    for req in cursor.fetchall():
        cursor.execute("\n".join(req))
    conn.commit()
    conn.close()
    print("Test data was deleted")
    return 0


def pg_get_option(connstring, option):
    """ Get current value of a PostgreSQL option
    :param: connstring connection string
    :param: option name
    :return:
    """

    conn = psycopg2.connect(connstring)
    cursor = conn.cursor()
    if not pg_check_option(connstring, option):
        return None

    cursor.execute(
        "SELECT setting FROM pg_settings WHERE name = '%s'" % option)
    value = cursor.fetchall()[0][0]

    cursor.close()
    conn.close()

    return value


def pg_check_option(connstring, option):
    """ Check existence of a PostgreSQL option
    :param: connstring string for connect to postgres
    :param: option name
    :return: False or True
    """

    conn = psycopg2.connect(connstring)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT exists (SELECT 1 FROM pg_settings"
        " WHERE name = '%s' LIMIT 1)" % option)

    if not cursor.fetchall()[0][0]:
        return False

    cursor.close()
    conn.close()

    return True


def pg_set_option(connstring, option, value):
    """ Set a new value to a PostgreSQL option
    :param: option name and new value
    :return: False or True
    """

    conn = psycopg2.connect(connstring)
    cursor = conn.cursor()
    conn.set_session(autocommit=True)

    if not pg_check_option(connstring, option):
        return False

    cursor.execute(
        "SELECT context FROM pg_settings WHERE name = '%s'" % option)
    context = cursor.fetchall()[0][0]

    restart_contexts = ['superuser-backend',
                        'backend', 'user', 'postmaster', 'superuser']
    reload_contexts = ['sighup']

    if context in reload_contexts:
        cursor.execute("ALTER SYSTEM SET %s = '%s'" % (option, value))
        cursor.close()
        conn.close()
        return pg_manage_psql("reload",
                              pg_get_option(connstring, 'data_directory'))
    elif context in restart_contexts:
        cursor.execute("ALTER SYSTEM SET %s = '%s'" % (option, value))
        cursor.close()
        conn.close()
        return pg_manage_psql("restart",
                              pg_get_option(connstring, 'data_directory'))


def pg_manage_psql(action, data_dir, version="9.6", start_script=None,
                   remote=False, host=None):
        """ Manage Postgres instance
        :param action: start, restart, stop etc
        :param init: Initialization before a first start
        :return:
        """
        raise NotImplementedError()


def pg_start_script_name(name, edition, version, distro):
    """

    :param name:
    :param edition:
    :param version:
    :param distro:
    :return:
    """
    raise NotImplementedError()


def pg_initdb(connstring, *params):
    """

    :param connstring:
    :param params:
    :return:
    """
    raise NotImplementedError()


def create_tablespace(tablespace_name, compression=False):
    """ Create tablespace

    :return:
    """
    tablespace_location = create_tablespace_directory()
    conn_string = "host='localhost' user='postgres' "
    conn = psycopg2.connect(conn_string)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    # TODO add check that PGPRO edition is enterprise
    if compression:
        cursor.execute(
            'CREATE TABLESPACE {0}'
            ' LOCATION \'{1}\' WITH (compression=true);'.format(
                tablespace_name, tablespace_location))
    else:
        cursor.execute(
            'CREATE TABLESPACE {0}'
            ' LOCATION \'{1}\';'.format(
                tablespace_name, tablespace_location))
    return tablespace_location
