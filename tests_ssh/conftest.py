import platform
import distro
import pytest

from allure_commons.types import LabelType

from helpers.utils import create_env_info_from_config
from helpers.environment_manager import Environment

if platform.system() == 'Linux':
    dist = " ".join(distro.linux_distribution()[0:2])
elif platform.system() == 'Windows':
    dist = 'Windows'
else:
    print("Unknown Distro")


def pytest_addoption(parser):
    """Option for pytest run, list of images for test

    :param parser pytest default param for command line args:
    :return:
    """
    parser.addoption(
        "--target", dest="target",
        help='system(s) under test (image(s))')
    parser.addoption(
        "--product_version", action="store", default='9.6',
        help="Specify product version. Available values: 9.5, 9.6")
    parser.addoption(
        "--product_name", action="store", default='postgrespro',
        help="Specify product name. Available values: postgrespro, postresql")
    parser.addoption(
        "--product_edition", action="store", default='ent',
        help="Specify product edition. Available values: ent, std")
    parser.addoption(
        "--product_milestone", action="store", default='beta',
        help="Specify product milestone. Available values: beta")
    parser.addoption(
        "--branch", action="store",
        help="Specify branch")
    parser.addoption(
        "--sqlsmith-queries", action="store", default=10000,
        help="Number of sqlsmith queries.")
    parser.addoption(
        "--config", dest="config", action="store",
        help="Path to config file")
    parser.addoption("--skip_install", action="store_true")


@pytest.fixture(scope='function')
def create_environment(request):
    if request.config.getoption('--config'):
        print('Environment will be use from config')
    else:
        name = request.node.name
        os = request.config.getoption('--target')
        if request.param:
            environment = Environment(name, os, nodes_count=request.param)
        else:
            environment = Environment(name, os)
        environment.create_environment()
        yield environment
        if request.config.getoption('--config'):
            print("Cluster was deployed from config."
                  " No teardown actions for this type of cluster deploy")
        else:
            environment.delete_env()


@pytest.mark.usefixtures('create_environment')
@pytest.fixture(scope='function')
def install_postgres(request, create_environment):
    """Install postgres

    :param request:
    :param create_environment: object with Environment class
    :return:
    """
    from helpers.pginstance import PgInstance
    if request.config.getoption('--config'):
        environment_info = create_env_info_from_config(
            request.node.name, request.config.getoption('--config'))
        cluster_name = request.node.name
    else:
        environment_info = create_environment.env_info
        cluster_name = "%s_%s" % (
            request.node.name, request.config.getoption('--target'))
    cluster_nodes = []
    for node in environment_info[cluster_name]['nodes']:
        cluster_node = PgInstance(
            version=request.config.getoption('--product_version'),
            milestone=request.config.getoption('--product_milestone'),
            name=request.config.getoption('--product_name'),
            edition=request.config.getoption('--product_edition'),
            branch=request.config.getoption('--branch'),
            skip_install=False,
            node_ip=node['ip'],
            cluster=True)
        cluster_node.install_product_cluster(
            version=request.config.getoption('--product_version'),
            milestone=request.config.getoption('--product_milestone'),
            name=request.config.getoption('--product_name'),
            edition=request.config.getoption('--product_edition'),
            branch=request.config.getoption('--branch'),
            node_ip=node['ip'])
        cluster_nodes.append(cluster_node)
    yield cluster_nodes
    if request.config.getoption('--config'):
        print("Cluster was deployed from config."
              " No teardown actions for this type of cluster deploy")
    else:
        create_environment.delete_env()

# TODO create different behaviour for multimaster and replica,
# TODO example here: https://docs.pytest.org/en/latest/
#                     proposals/parametrize_with_fixtures.html
# @pytest.fixture(params=['multimaster', 'replica'])
# def deploy_cluster(request):
#     if request.param == 'multimaster':
#         return request.getfuncargvalue('default_context')
#     elif request.param == 'replica':
#         return request.getfuncargvalue('extra_context')


@pytest.fixture()
def create_multimaster_cluster(request):
    pass


@pytest.fixture()
def create_replica(request):
    pass


def pytest_runtest_logreport(report):
    if report.when == 'call' and report.failed:
        pass
