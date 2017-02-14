import psycopg2
import pytest
import settings

from helpers.sql_helpers import get_pgpro_info


@pytest.mark.usefixtures('install_postgres')
def test_version(request, install_postgres):
    """ This is BVT test for all PostgreSQL version
    Scenario:
    1. Check PGPRO version
    2. Check PGPRO edition
    3. Check system default tables
    """
    conn_string = "host='localhost' user='postgres' "
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    cursor.execute("SELECT pgpro_version()")
    pgpro_info = get_pgpro_info(cursor.fetchall()[0][0])
    print("What must be installed:", request.config.getoption('--product_name'),
          request.config.getoption('--product_version'))
    print("Information about installed PostgresPro ", pgpro_info)
    assert install_postgres.name == pgpro_info['name'].lower()
    assert install_postgres.version == pgpro_info['version']


@pytest.mark.usefixtures('install_postgres')
def test_extensions(install_postgres):
    """ Make sure all our extensions are available
    """

    conn_string = "host='localhost' user='postgres' "
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT pgpro_edition()")
    except psycopg2.ProgrammingError:
        pytest.skip("pgpro_version() is not available in PostgreSQL")

    edition = cursor.fetchall()[0][0]
    cursor.execute("SELECT name FROM pg_catalog.pg_available_extensions")
    available_extensions = [e[0] for e in cursor]

    if edition == "standard":
        extensions = settings.EXTENSIONS_OS
    elif edition == "enterprise":
        extensions = settings.EXTENSIONS_EE
    else:
        pytest.fail("Unknown PostgresPro edition")

    for e in extensions:
        assert e in available_extensions
