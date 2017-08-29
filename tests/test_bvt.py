import os
import platform
import psycopg2
import pytest
import settings

from allure_commons.types import LabelType

from helpers.os_helpers import get_directory_size
from helpers.os_helpers import get_postgres_process_pids
from helpers.pginstall import delete_packages
from helpers.sql_helpers import get_pgpro_info

dist = ""
if platform.system() == 'Linux':
    dist = " ".join(platform.linux_distribution()[0:2])
elif platform.system() == 'Windows':
    dist = 'Windows'
else:
    print("Unknown Distro")

version = pytest.config.getoption('--product_version')
name = pytest.config.getoption('--product_name')
edition = pytest.config.getoption('--product_edition')
feature_name = "_".join(["BVT", dist, name, edition, version])


@pytest.allure.feature(feature_name)
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
    version = request.config.getoption('--product_version')
    name = request.config.getoption('--product_name')
    edition = request.config.getoption('--product_edition')
    product_info = " ".join([dist, name, edition, version])
    tag_mark = pytest.allure.label(LabelType.TAG, product_info)
    request.node.add_marker(tag_mark)
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
        cursor.execute("SELECT pgpro_build()")
        pgpro_info["edition"] = cursor.fetchall()[0][0]
        # if edition == "ee":
        #     assert pgpro_info["edition"] == "enterprise"
        # elif edition == "standard":
        #     assert pgpro_info["edition"] == "standard"
        # elif edition == "cert":
        #     assert pgpro_info["edition"] == "standard-certification"
        # elif edition == "cert-enterprise":
        #     assert pgpro_info["edition"] == "enterprise-certification"
    print("What must be installed:", request.config.getoption('--product_name'),
          request.config.getoption('--product_version'))
    print("Information about installed PostgresPro ", pgpro_info)
    assert install_postgres.name == pgpro_info['name'].lower()
    assert install_postgres.version == pgpro_info['version']
    # TODO add check pgpro_edition()


@pytest.allure.feature(feature_name)
@pytest.mark.bvt
@pytest.mark.test_extensions
@pytest.mark.usefixtures('install_postgres')
def test_extensions(request, install_postgres):
    """ Make sure all our extensions are available
    Scenario:
    1. Check postgrespro edition
    2. Check that extension for right edition available
    3. Try to load extension
    4. Check that every extension write information about self in table pg_catalog.pg_extension
    5. Drop extension
    """
    version = request.config.getoption('--product_version')
    name = request.config.getoption('--product_name')
    edition = request.config.getoption('--product_edition')
    product_info = " ".join([dist, name, edition, version])
    tag_mark = pytest.allure.label(LabelType.TAG, product_info)
    request.node.add_marker(tag_mark)
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
    elif edition == "enterprise-certified":
        extensions = settings.EXTENSIONS_EE + settings.EXTENSIONS_OS + settings.EXTENSIONS_POSTGRES + ["pgaudit"]
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


@pytest.allure.feature(feature_name)
@pytest.mark.bvt
@pytest.mark.test_plpython
@pytest.mark.usefixtures('install_postgres')
def test_plpython(request, install_postgres):
    """Test for plpython language
    Scenario:
    1. Create extension plpython2u
    2. Create function
    3. Execute function
    4. Check function result
    5. Drop function
    6. Drop extension
    """
    version = request.config.getoption('--product_version')
    name = request.config.getoption('--product_name')
    edition = request.config.getoption('--product_edition')
    product_info = " ".join([dist, name, edition, version])
    tag_mark = pytest.allure.label(LabelType.TAG, product_info)
    request.node.add_marker(tag_mark)
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


@pytest.allure.feature(feature_name)
@pytest.mark.bvt
@pytest.mark.test_pltcl
@pytest.mark.usefixtures('install_postgres')
def test_pltcl(request, install_postgres):
    """Test for pltcl language
        Scenario:
        1. Create extension pltcl
        2. Create function
        3. Execute function
        4. Check function result
        5. Drop function
        6. Drop extension
        """
    version = request.config.getoption('--product_version')
    name = request.config.getoption('--product_name')
    edition = request.config.getoption('--product_edition')
    product_info = " ".join([dist, name, edition, version])
    tag_mark = pytest.allure.label(LabelType.TAG, product_info)
    request.node.add_marker(tag_mark)
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


@pytest.allure.feature(feature_name)
@pytest.mark.bvt
@pytest.mark.test_plperl
@pytest.mark.usefixtures('install_postgres')
def test_plperl(request, install_postgres):
    """Test for plperl language
        Scenario:
        1. Create extension plperl
        2. Create function
        3. Execute function
        4. Check function result
        5. Drop function
        6. Drop extension
        """
    version = request.config.getoption('--product_version')
    name = request.config.getoption('--product_name')
    edition = request.config.getoption('--product_edition')
    product_info = " ".join([dist, name, edition, version])
    tag_mark = pytest.allure.label(LabelType.TAG, product_info)
    request.node.add_marker(tag_mark)
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


@pytest.allure.feature(feature_name)
@pytest.mark.bvt
@pytest.mark.test_plpgsql
@pytest.mark.usefixtures('install_postgres')
def test_plpgsql(request, install_postgres):
    """Test for plperl language
        Scenario:
        1. Create  plpgsql function
        2. Execute  plpgsql function
        3. Check plpgsql function result
        4. Drop  plpgsql function
        """
    version = request.config.getoption('--product_version')
    name = request.config.getoption('--product_name')
    edition = request.config.getoption('--product_edition')
    product_info = " ".join([dist, name, edition, version])
    tag_mark = pytest.allure.label(LabelType.TAG, product_info)
    request.node.add_marker(tag_mark)
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


@pytest.allure.feature(feature_name)
@pytest.mark.bvt
@pytest.mark.test_passwordcheck
@pytest.mark.usefixtures('install_postgres')
def test_passwordcheck(install_postgres, request):
    """Test for passwordcheck feature for certified enterprise version
    Scenario:
    1. Add passwordcheck lib
    2. Check default value for password_min_unique_chars variable
    3. Check default value for password_min_pass_len
    4. Check default value for password_with_nonletters
    :param install_postgres:
    :param request:
    :return:
    """
    version = request.config.getoption('--product_version')
    name = request.config.getoption('--product_name')
    edition = request.config.getoption('--product_edition')
    product_info = " ".join([dist, name, edition, version])
    tag_mark = pytest.allure.label(LabelType.TAG, product_info)
    request.node.add_marker(tag_mark)
    if request.config.getoption('--product_edition') != "cert-enterprise":
        pytest.skip("This test only for certified enterprise version.")
    # Step 1
    install_postgres.set_option('shared_preload_libraries', 'passwordcheck')
    # Step 2
    conn_string = "host='localhost' user='postgres' "
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    cursor.execute("SHOW password_min_unique_chars")
    assert cursor.fetchall()[0][0] == "8"
    # Step 3
    cursor.execute("SHOW password_min_pass_len")
    assert cursor.fetchall()[0][0] == "8"
    # Step 4
    cursor.execute("SHOW password_with_nonletters")
    assert cursor.fetchall()[0][0] == "on"
    conn.commit()
    conn.close()


@pytest.allure.feature(feature_name)
@pytest.mark.bvt
@pytest.mark.test_delete_packages
@pytest.mark.usefixtures('install_postgres')
def test_delete_packages(request, install_postgres):
    """Try to delete all installed packages for version under test
    Scenario:
    1. Delete packages
    2. Check that postgres instance was stopped
    3. Check that test data is not deleted

    """
    print(request.node.name)
    version = request.config.getoption('--product_version')
    name = request.config.getoption('--product_name')
    edition = request.config.getoption('--product_edition')
    product_info = " ".join([dist, name, edition, version])
    tag_mark = pytest.allure.label(LabelType.TAG, product_info)
    request.node.add_marker(tag_mark)
    data_directory = install_postgres.get_option('data_directory')
    data_dir_size_before_delete_packages = get_directory_size(data_directory)
    pids = get_postgres_process_pids()
    # Step 1
    delete_packages(remote=False, host=None, name=name, version=version, edition=edition)
    data_dir_size_after_delete_packages = get_directory_size(data_directory)
    # Step 2
    # assert data_dir_size_before_delete_packages == data_dir_size_after_delete_packages
    # Step 3
    for pid in pids:
        assert os.path.exists("/proc/%s") % str(pid) is False
