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
    cursor.execute("SELECT pgpro_build()")
    pgpro_info["last_commit"] = cursor.fetchall()[0][0]
    print("What must be installed:", request.config.getoption('--product_name'),
          request.config.getoption('--product_version'))
    print("Information about installed PostgresPro ", pgpro_info)
    assert install_postgres.name == pgpro_info['name'].lower()
    assert install_postgres.version == pgpro_info['version']


@pytest.mark.usefixtures('install_postgres')
def test_extensions(install_postgres):
    # TODO add check for extension step 1. Create extension
    # TODO add check for extensions, step 2. SELECT extname FROM pg_catalog.pg_extension WHERE extname = <ext_name>;
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
        extensions = settings.EXTENSIONS_EE + settings.EXTENSIONS_OS
    else:
        pytest.fail("Unknown PostgresPro edition")

    for e in extensions:
        print("Trying to check extension %s" % e)
        if e in ["aqo", "multimaster", "hunspell_en_us", "hunspell_nl_nl", "hunspell_fr", "hunspell_ru_ru"]:
            assert e in available_extensions
        else:
            assert e in available_extensions
            install_postgres.load_extension(e)
            conn = psycopg2.connect(conn_string)
            cursor = conn.cursor()
            cursor.execute("SELECT extname FROM pg_catalog.pg_extension WHERE extname = \'%s\';" % e)
            assert cursor.fetchall()[0][0] == e
            cursor.execute("DROP EXTENSION IF EXISTS %s" % e)
            conn.commit()
            conn.close()
