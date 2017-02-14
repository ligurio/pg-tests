import pytest

from helpers.pginstance import PgInstance
from helpers.sql_helpers import create_test_table


def pytest_addoption(parser):
    """This method needed for running pytest test with options
    Example: command "pytest --product_edition=standard" will install
    postgrespro with standard edition

    :param parser pytest default param for command line args:
    :return:
    """
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


@pytest.fixture(scope='session')
def install_postgres(request):
    """This fixture for postgres installation on different platforms

    :param request default param for pytest it helps us to pass
    command line variables from pytest_addoption() method
    :return:
    """
    skip_install = request.config.getoption("--skip_install")

    if skip_install:
        version = None
        milestone = None
        name = None
        edition = None
        build = None
        local = True
    else:
        version = request.config.getoption('--product_version')
        milestone = request.config.getoption('--product_milestone')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        build = request.config.getoption('--product_build')
        local = False

    pginstance = PgInstance(version, milestone, name, edition, build, local)

    return pginstance


@pytest.fixture(scope="session")
def create_table(request):
    """ This method needed for creating table with fake data.

    :param schema - SQL schema, the default schema includes almost all available data types:
    :param size - number of rows to insert, default value is 10000:
    :return:

    https://www.cri.ensmp.fr/people/coelho/datafiller.html#directives_and_data_generators
    """
    schema, size = request.param

    return create_test_table(size, schema)
