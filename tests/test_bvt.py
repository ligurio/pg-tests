import psycopg2
import pytest

from helpers.sql_helpers import get_pgpro_info

@pytest.mark.usefixtures('install_postgres')
def test_bvt(install_postgres):
    # TODO add additional checks for test: pgpro edition check, system default settings and other
    """ This is BVT test for all PostgreSQL version
    Scenario:
    1. Check PGPRO version
    2. Check PGPRO edition
    3. Check system default tables
    """
    conn_string = "host='localhost' user='postgres' "
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    cursor.execute("select pgpro_version()")
    pgpro_info = get_pgpro_info(cursor.fetchall()[0][0])
    print("What must be installed", install_product)
    print("Information about installed PostgresPro ", pgpro_info)
    assert install_product['name'] == pgpro_info['name'].lower()
    assert install_product['version'] == pgpro_info['version']
    assert install_product['build'] == pgpro_info['build']
