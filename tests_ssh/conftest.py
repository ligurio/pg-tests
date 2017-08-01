import platform
import pytest

from allure_commons.types import LabelType

from helpers.utils import create_env_info_from_config
from helpers.utils import MySuites
from helpers.environment_manager import Environment
from helpers.pginstance import PgInstance

if platform.system() == 'Linux':
    dist = " ".join(platform.linux_distribution()[0:2])
elif platform.system() == 'Windows':
    dist = 'Windows'
else:
    print("Unknown Distro")


def pytest_addoption(parser):
    """Option for pytest run, list of images for test

    :param parser pytest default param for command line args:
    :return:
    """
    parser.addoption("--target", dest="target", help='system(s) under test (image(s))')
    parser.addoption("--product_version", action="store", default='9.6',
                     help="Specify product version. Available values: 9.5, 9.6")
    parser.addoption("--product_name", action="store", default='postgrespro',
                     help="Specify product name. Available values: postgrespro, postresql")
    parser.addoption("--product_edition", action="store", default='ee',
                     help="Specify product edition. Available values: ee, standard")
    parser.addoption("--product_milestone", action="store", default='beta',
                     help="Specify product milestone. Available values: beta")
    parser.addoption("--product_build", action="store",
                     help="Specify product build.")
    parser.addoption("--sqlsmith-queries", action="store", default=10000,
                     help="Number of sqlsmith queries.")
    parser.addoption("--config", dest="config", action="store",
                     help="Path to config file")


@pytest.fixture(scope='function')
def environment(request):
        name = request.node.name.split('.')[0]
        return Environment(name)


@pytest.mark.usefixtures('environment')
@pytest.fixture(scope='function')
def create_environment(request, environment):
    if request.config.getoption('--config'):
        print('Environment will be use from config')
    else:
        nodes_count = request.param
        return environment.create_environment(request.node.name, nodes_count, request.config.getoption("--target"))


@pytest.mark.usefixtures('environment')
@pytest.fixture(scope='function')
def install_postgres(request, environment):
    version = request.config.getoption('--product_version')
    name = request.config.getoption('--product_name')
    edition = request.config.getoption('--product_edition')
    product_info = " ".join([dist, name, edition, version])
    tag_mark = pytest.allure.label(LabelType.TAG, dist)
    request.node.add_marker(tag_mark)
    tag_mark = pytest.allure.label(MySuites.PARENT_SUITE, product_info)
    request.node.add_marker(tag_mark)
    tag_mark = pytest.allure.label(MySuites.EPIC, product_info)
    request.node.add_marker(tag_mark)
    if request.config.getoption('--config'):
        environment_info = create_env_info_from_config(request.node.name, request.config.getoption('--config'))
        cluster_name = request.node.name
    else:
        environment_info = environment.get_cluster_config()
        cluster_name = "%s_%s" % (request.node.name, request.config.getoption('--target'))
    pginstance = PgInstance(version=request.config.getoption('--product_version'),
                            milestone=request.config.getoption('--product_milestone'),
                            name=request.config.getoption('--product_name'),
                            edition=request.config.getoption('--product_edition'),
                            build=request.config.getoption('--product_build'),
                            skip_install=False,
                            environment_info=environment_info,
                            cluster_name=cluster_name)

    return pginstance
