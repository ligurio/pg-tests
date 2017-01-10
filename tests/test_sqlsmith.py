import platform
import pytest
import subprocess

from helpers.pginstall import setup_repo


@pytest.fixture(scope="session")
def install_sqlsmith(request):

    setup_repo("postgresql", "9.6")
    subprocess.call(["apt-get", "install", "-y", "sqlsmith"])
    return subprocess.call("type sqlsmith", shell=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.mark.slowtest
@pytest.mark.skipif('platform.linux_distribution()[0] != "Ubuntu"')
@pytest.mark.usefixtures('install_postgres')
@pytest.mark.usefixtures('install_sqlsmith')
@pytest.mark.usefixtures('sqlsmth_queries')
def test_sqlsmith(install_sqlsmith, sqlsmith_queries):

    sqlsmith_cmd = ["sudo", "-u", "postgres",
                    "sqlsmith", "--max-queries=%s" % sqlsmith_queries]
    sqlsmith = subprocess.Popen(sqlsmith_cmd)
    assert sqlsmith.wait() == 0
