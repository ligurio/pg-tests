import pytest

from helpers.environment_manager import Environment
from helpers.pginstance import PgInstance


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
    parser.addoption("--sqlsmith-queries", action="store", default=10000,
                     help="Number of sqlsmith queries.")


@pytest.fixture(scope='function')
def environment(request):
    # TODO set here that if param == 'baremetal' provide config file with cluster_config or parse it from options
    if request.config.getoption('--config'):
        """Parse config """
        config = ""
        return config
    else:
        name = request.node.name.split('.')[0]
        return Environment(name)


@pytest.mark.usefixtures('environment')
@pytest.fixture(scope='function')
def create_environment(request, environment):
    if request.config.getoption('--config'):
        config = ""
        return config
    else:
        nodes_count = request.param
        return environment.create_environment(request.node.name, nodes_count, request.config.getoption("--target"))


@pytest.mark.usefixtures('environment')
@pytest.fixture(scope='function')
def install_postgres(request, environment):
    if request.config.getoption('--config'):
        environment_info = environment
        cluster_name = environment['env_name']
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
