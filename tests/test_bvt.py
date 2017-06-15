import allure
import platform
import psycopg2
import pytest
import settings

from helpers.sql_helpers import get_pgpro_info

if platform.system() == 'Linux':
    dist = platform.linux_distribution()
elif platform.system() == 'Windows':
    dist = 'Windows'
else:
    print("Unknown Distro")


@allure.feature('BVT Tests {}'.format(dist))
@allure.testcase('http://my.tms.org/browse/TESTCASE-2')
@pytest.mark.bvt
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
    if install_postgres.version == '9.5':
        pass
    else:
        cursor.execute("SELECT pgpro_build()")
        pgpro_info["last_commit"] = cursor.fetchall()[0][0]
    print("What must be installed:", request.config.getoption('--product_name'),
          request.config.getoption('--product_version'))
    print("Information about installed PostgresPro ", pgpro_info)
    assert install_postgres.name == pgpro_info['name'].lower()
    assert install_postgres.version == pgpro_info['version']


@allure.feature('BVT Tests {}'.format(platform.linux_distribution()))
@allure.testcase('http://my.tms.org/browse/TESTCASE-2')
@pytest.mark.bvt
@pytest.mark.usefixtures('install_postgres')
def test_extensions(install_postgres):
    """ Make sure all our extensions are available
    Scenario:
    1. Check postgrespro edition
    2. Check that extension for right edition available
    3. Try to load extension
    4. Check that every extension write information about self in table pg_catalog.pg_extension
    5. Drop extension
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

    if "standard" in edition:
        extensions = settings.EXTENSIONS_OS + settings.EXTENSIONS_POSTGRES
    elif edition == "enterprise":
        extensions = settings.EXTENSIONS_EE + settings.EXTENSIONS_OS + settings.EXTENSIONS_POSTGRES
    else:
        pytest.fail("Unknown PostgresPro edition: %s" % edition)

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
