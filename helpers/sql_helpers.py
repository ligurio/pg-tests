import psycopg2
import subprocess

from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

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
    :param schema - SQL schema, the default schema includes almost all available data types:
    :param size - number of rows to insert, default value is 10000:
    :return: string as exit code
    """

    if schema == "mixed":
        sqlschema = settings.MIXED_SCHEMA
    elif schema == "pgbench":
        sqlschema = settings.PGBENCH_SCHEMA
    elif schema == "pgbench_unlogged":
        sqlschema = settings.PGBENCH_SCHEMA_UNLOGGED
    else:
        sqlschema = schema

    datagen_cmd = ["python", "./helpers/datafiller.py", "--filter",
                   "--transaction", "--drop", "--size=%s" % size]

    p = subprocess.Popen(datagen_cmd, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE)
    p.stdin.write(sqlschema)
    p.stdin.close()

    psql = subprocess.Popen(["sudo", "-u", "postgres", "psql"], stdin=p.stdout)
    psql.wait()

    return psql.returncode
