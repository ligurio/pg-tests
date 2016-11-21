import pytest

from helpers.pginstall import install_product


@pytest.fixture(scope='session')
def install_postgres():
    return install_product()

