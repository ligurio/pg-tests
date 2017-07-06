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


@pytest.allure.feature('BVT Tests {}'.format(dist))
@pytest.mark.bvt
@pytest.mark.test_version
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


@pytest.allure.feature('BVT Tests {}'.format(platform.linux_distribution()))
@pytest.mark.bvt
@pytest.mark.test_extensions
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
            # TODO add check that in pg_catalog extension was deleted
            conn.commit()
            conn.close()


@pytest.allure.feature('BVT Tests {}'.format(dist))
@pytest.mark.bvt
@pytest.mark.test_plpython
@pytest.mark.usefixtures('install_postgres')
def test_plpython(install_postgres):
    """Test for plpython language
    Scenario:
    1. Create extension plpython2u
    2. Create function
    3. Execute function
    4. Check function result
    5. Drop function
    6. Drop extension
    """
    # Step 1
    install_postgres.load_extension("plpython2u")
    fun = """CREATE FUNCTION py_test_function()
  RETURNS text
AS $$
  return "python test function"
$$ LANGUAGE plpython2u;"""
    conn_string = "host='localhost' user='postgres' "
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    # Step 2
    cursor.execute(fun)
    # Step 3
    cursor.execute("SELECT py_test_function()")
    # Step 4
    assert cursor.fetchall()[0][0] == "python test function"
    # Step 5
    cursor.execute("DROP FUNCTION IF EXISTS py_test_function()")
    # Step 6
    cursor.execute("DROP EXTENSION IF EXISTS plpython2u")
    conn.commit()
    conn.close()


@pytest.allure.feature('BVT Tests {}'.format(dist))
@pytest.mark.bvt
@pytest.mark.test_pltcl
@pytest.mark.usefixtures('install_postgres')
def test_pltcl(install_postgres):
    """Test for pltcl language
        Scenario:
        1. Create extension pltcl
        2. Create function
        3. Execute function
        4. Check function result
        5. Drop function
        6. Drop extension
        """
    install_postgres.load_extension("pltcl")
    fun = """CREATE FUNCTION pltcl_test_function()
      RETURNS text
    AS $$
      return "pltcl test function"
    $$ LANGUAGE pltcl;"""
    conn_string = "host='localhost' user='postgres' "
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    # Step 2
    cursor.execute(fun)
    # Step 3
    cursor.execute("SELECT pltcl_test_function()")
    # Step 4
    assert cursor.fetchall()[0][0] == "pltcl test function"
    # Step 5
    cursor.execute("DROP FUNCTION IF EXISTS pltcl_test_function()")
    # Step 6
    cursor.execute("DROP EXTENSION IF EXISTS pltcl")
    conn.commit()
    conn.close()


@pytest.allure.feature('BVT Tests {}'.format(dist))
@pytest.mark.bvt
@pytest.mark.test_plperl
@pytest.mark.usefixtures('install_postgres')
def test_plperl(install_postgres):
    """Test for plperl language
        Scenario:
        1. Create extension plperl
        2. Create function
        3. Execute function
        4. Check function result
        5. Drop function
        6. Drop extension
        """
    install_postgres.load_extension("plperl")
    fun = """CREATE FUNCTION plperl_test_function()
      RETURNS text
    AS $$
      return "plperl test function"
    $$ LANGUAGE plperl;"""
    conn_string = "host='localhost' user='postgres' "
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    # Step 2
    cursor.execute(fun)
    # Step 3
    cursor.execute("SELECT plperl_test_function()")
    # Step 4
    assert cursor.fetchall()[0][0] == "plperl test function"
    # Step 5
    cursor.execute("DROP FUNCTION IF EXISTS plperl_test_function()")
    # Step 6
    cursor.execute("DROP EXTENSION IF EXISTS plperl")
    conn.commit()
    conn.close()


@pytest.allure.feature('BVT Tests {}'.format(dist))
@pytest.mark.bvt
@pytest.mark.test_plpgsql
@pytest.mark.usefixtures('install_postgres')
def test_plpgsql(install_postgres):
    """Test for plperl language
        Scenario:
        1. Create  plpgsql function
        2. Execute  plpgsql function
        3. Check plpgsql function result
        4. Drop  plpgsql function
        """
    fun = """CREATE OR REPLACE FUNCTION plpgsql_test_function()
    RETURNS text AS
$$
DECLARE
    result text;
BEGIN
    result = 'plpgsql test function';
    RETURN result;
END;
$$
LANGUAGE plpgsql """
    conn_string = "host='localhost' user='postgres' "
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    # Step 1
    cursor.execute(fun)
    # Step 2
    cursor.execute("SELECT plpgsql_test_function()")
    # Step 3
    assert cursor.fetchall()[0][0] == "plpgsql test function"
    # Step 4
    cursor.execute("DROP FUNCTION IF EXISTS plpgsql_test_function()")
    conn.commit()
    conn.close()
