import pytest

from helpers.pginstall import install_product


@pytest.fixture(scope='session')
def install_postgres():
    install_product()

