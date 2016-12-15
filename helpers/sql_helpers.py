import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


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


def get_data_directory():
    """
    Get data directory
    :return: string with path to data directory
    """
    conn_string = "host='localhost' user='postgres' "
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    cursor.execute('show data_directory')
    return cursor.fetchall()[0][0]


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