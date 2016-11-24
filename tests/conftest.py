import pytest

from helpers.pginstall import install_product


def pytest_addoption(parser):
    """This method needed for running pytest test with options
    Example: command "pytest --product_edition=opensource" will install
    postgrespro with opensource(standard) edition

    :param parser pytest default param for command line args:
    :return:
    """
    parser.addoption("--product_version", action="store", default='9.6',
                     help="Specify product version. Available values: 9.5, 9.6")
    parser.addoption("--product_name", action="store", default='postgrespro',
                     help="Specify product name. Available values: postgrespro, postresql")
    parser.addoption("--product_edition", action="store", default='ee',
                     help="Specify product edition. Available values: ee, opensource")
    parser.addoption("--product_milestone", action="store", default='beta',
                     help="Specify product milestone. Available values: beta, production")
    parser.addoption("--product_build", action="store", default='1',
                     help="Specify product build. Available values: 1, ")


@pytest.fixture(scope='session')
def install_postgres(request):
    """This fixture for postgres installation on different platforms

    :param request default param for pytest it helps us to pass
    command line variables from pytest_addoption() method
    :return:
    """
    return install_product(version=request.config.getoption('--product_version'),
                           milestone=request.config.getoption('--product_milestone'),
                           name=request.config.getoption('--product_name'),
                           edition=request.config.getoption('--product_edition'),
                           build=request.config.getoption('--product_build'))