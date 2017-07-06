import psycopg2
import glob
import pytest
import os
import shutil
import subprocess

from helpers.pginstall import delete_packages
from helpers.pginstall import delete_repo
from helpers.pginstance import PgInstance
from helpers.sql_helpers import drop_test_table
from helpers.sql_helpers import create_test_table
from helpers.sql_helpers import execute
from helpers.os_helpers import download_file
from tests.settings import TMP_DIR


def pytest_addoption(parser):
    """This method needed for running pytest test with options
    Example: command "pytest --product_edition=standard" will install
    postgrespro with standard edition

    :param parser pytest default param for command line args:
    :return:
    """
    parser.addoption("--target", action="store", default='linux',
                     help="Operating system")
    parser.addoption("--product_version", action="store", default='9.6',
                     help="Specify product version. Available values: 9.5, 9.6")
    parser.addoption("--product_name", action="store", default='postgrespro',
                     help="Specify product name. Available values: postgrespro, postresql")
    parser.addoption("--product_edition", action="store", default='ee',
                     help="Specify product edition. Available values: ee, standard")
    parser.addoption("--product_milestone", action="store",
                     help="Specify product milestone. Available values: beta")
    parser.addoption("--product_build", action="store",
                     help="Specify product build.")
    parser.addoption("--sqlsmith-queries", action="store", default=10000,
                     help="Number of sqlsmith queries.")
    parser.addoption("--skip_install", action="store_true")


@pytest.fixture
def sqlsmith_queries(request):
    return request.config.getoption("--sqlsmith-queries")


@pytest.fixture(scope='module')
def install_postgres(request):
    """This fixture for postgres installation on different platforms

    :param request default param for pytest it helps us to pass
    command line variables from pytest_addoption() method
    :return:
    """
    skip_install = request.config.getoption("--skip_install")
    version = request.config.getoption('--product_version')
    milestone = request.config.getoption('--product_milestone')
    name = request.config.getoption('--product_name')
    edition = request.config.getoption('--product_edition')
    build = request.config.getoption('--product_build')
    if skip_install:
        local = True
        windows = False
        yield PgInstance(version, milestone, name, edition, build, local, windows=windows)
        drop_test_table("host='localhost' user='postgres'")
    else:
        if request.config.getoption('--target')[0:3] == 'win':
            local = False
            windows = True
            yield PgInstance(version, milestone, name, edition, build, local, windows=windows)
            drop_test_table("host='localhost' user='postgres'")
            # delete_packages(remote=False, host=None, name=name, version=version, edition=edition)
            # delete_repo(remote=False, host=None, name=name, version=version)
        else:
            local = False
            windows = False
            yield PgInstance(version, milestone, name, edition, build, local, windows=windows)
            drop_test_table("host='localhost' user='postgres'")
            # delete_packages(remote=False, host=None, name=name, version=version, edition=edition)
            # delete_repo(remote=False, host=None, name=name, version=version)


@pytest.fixture
def create_table(request):
    """ This method needed for creating table with fake data. After test execution all test data will be droped

    :param schema - SQL schema, the default schema includes almost all available data types:
    :param size - number of rows to insert, default value is 10000:
    :return:

    https://www.cri.ensmp.fr/people/coelho/datafiller.html#directives_and_data_generators
    """
    schema, size = request.param

    def delete_tables():
        drop_test_table("host='localhost' user='postgres'")

    request.addfinalizer(delete_tables)

    return create_test_table(size, schema)


@pytest.fixture(scope="module")
def populate_imdb(request):
    """ This method needed for creating tables and populate them with IMDb dataset.

    http://www.imdb.com/interfaces
    """

    CONN_STRING = "host='localhost' user='postgres'"

    job_file = os.path.join(TMP_DIR, "join-order-benchmark.tar.gz")
    job_dir = os.path.join(TMP_DIR, "join-order-benchmark-0.1")
    job_url = "https://codeload.github.com/ligurio/join-order-benchmark/tar.gz/0.1"
    if not os.path.exists(job_file):
        download_file(job_url, job_file)

    subprocess.check_output(["tar", "xvzf", job_file, "-C", TMP_DIR])

    # CUSTOM METHOD OF DATABASE SETUP

    imdb_tgz = os.path.join(TMP_DIR, "imdb.tgz")
    if not os.path.exists(imdb_tgz):
        download_file("http://homepages.cwi.nl/~boncz/job/imdb.tgz", imdb_tgz)

    imdb_csv = os.path.join(TMP_DIR, "imdb_csv")
    if not os.path.exists(imdb_csv):
        os.mkdir(imdb_csv)
    subprocess.check_output(["tar", "xvzf", imdb_tgz, "-C", imdb_csv])

    os.chdir(imdb_csv)
    for csv in glob.glob('*.csv'):
        csv_file = os.path.join(imdb_csv, csv)
        data = open(csv_file).read().split('\n')
        for i in range(len(data)):
            data[i] = data[i].replace(r'\\', '').replace(r'\"', '')
            print data[i]
        with open(csv_file, 'w') as f:
            f.write('\n'.join(data))

    assert TMP_DIR == '/tmp'
    sql_files = ["schema", "imdb_load", "fkindexes", "imdb_analyse"]
    conn = psycopg2.connect(CONN_STRING)
    for f in sql_files:
        sql_path = os.path.join(job_dir, f + '.sql')
        with open(sql_path, 'r') as file:
            execute(conn, file.read())
    conn.close()

# CANONICAL METHOD OF DATABASE SETUP
#
# imdb_gz_files = ["actors", "actresses", "aka-names", "aka-titles",
#                  "alternate-versions", "biographies", "business",
#                  "certificates", "cinematographers", "color-info",
#                  "complete-cast", "complete-crew", "composers",
#                  "costume-designers", "countries", "crazy-credits",
#                  "directors", "distributors", "editors", "genres",
#                  "german-aka-titles", "goofs", "iso-aka-titles",
#                  "italian-aka-titles", "keywords", "language",
#                  "laserdisc", "literature", "locations",
#                  "miscellaneous-companies", "miscellaneous",
#                  "movie-links", "movies", "mpaa-ratings-reasons",
#                  "plot", "producers", "production-companies",
#                  "production-designers", "quotes", "ratings",
#                  "release-dates", "running-times", "sound-mix",
#                  "soundtracks", "special-effects-companies",
#                  "taglines", "technical", "trivia", "writers"]
#
# IMDB_BASE = "ftp://ftp.fu-berlin.de/pub/misc/movies/database/"
# imdb_gz_dir = os.path.join(TMP_DIR, "imdb_gz")
# if not os.path.exists(imdb_gz_dir):
#     os.mkdir(imdb_gz_dir)
#
# for a in imdb_gz_files:
#     archive_path = os.path.join(imdb_gz_dir, a + ".list.gz")
#     plain_path = os.path.join(imdb_gz_dir, a + ".list")
#     url = os.path.join(IMDB_BASE, a + ".list.gz")
#     if not os.path.exists(plain_path):
#         if not os.path.exists(archive_path):
#             download_file(url, archive_path)
#         subprocess.check_output(['gunzip', archive_path])
#
# psql_url = "postgres://postgres@localhost/imdbload"
# subprocess.check_output(["/usr/local/bin/imdbpy2sql.py",
#                         "-d", imdb_gz_dir, "-u", psql_url])


@pytest.fixture(scope="module")
def populate_tpch(request):
    """ This method setup tables for TPC-H benchmark.
    """

    CONN_STRING = "host='localhost' user='postgres'"

    # GETTING A BENCHMARK

    TPCH_SCALE = "1"    # 1, 10, 100, 300, 1000, 3000, 10000, 30000, 100000
    COMMIT_HASH = "c5cd7711cc35"
    TPCH_BENCHMARK = "https://bitbucket.org/tigvarts/tpch-dbgen/get/%s.zip" % COMMIT_HASH
    tbls = ["region.tbl", "nation.tbl", "customer.tbl", "supplier.tbl",
            "part.tbl", "partsupp.tbl", "orders.tbl", "lineitem.tbl"]
    sqls = ["postgres_dll.sql", "postgres_load.sql", "postgres_ri.sql"]

    tpch_archive = os.path.join(TMP_DIR, "tpch-benchmark-%s.zip" % COMMIT_HASH)
    if not os.path.exists(tpch_archive):
        download_file(TPCH_BENCHMARK, tpch_archive)

    tpch_dir = os.path.join(TMP_DIR, "tigvarts-tpch-dbgen-%s" % COMMIT_HASH)
    if not os.path.exists(tpch_dir):
        os.mkdir(tpch_dir)
        subprocess.check_output(["unzip", tpch_archive, "-d", TMP_DIR])
    os.chdir(tpch_dir)

    # SETUP DATABASE (see ./install.sh)
    subprocess.check_output(["make"])
    # TODO: run multiple parallel streams when generating large amounts of data
    subprocess.check_output(["./dbgen", "-s", TPCH_SCALE, "-vf"])

    assert TMP_DIR == '/tmp'
    for t in tbls:
        if os.path.exists(os.path.join(TMP_DIR, t)):
            os.remove(os.path.join(TMP_DIR, t))
        shutil.move(os.path.join(tpch_dir, t), TMP_DIR)

    conn = psycopg2.connect(CONN_STRING)
    for sql_file in sqls:
        execute(conn, open(os.path.join(tpch_dir, sql_file)).read())
    conn.close()

    for t in tbls:
        tbl_path = os.path.join(TMP_DIR, t)
        if os.path.exists(tbl_path):
            os.remove(tbl_path)
