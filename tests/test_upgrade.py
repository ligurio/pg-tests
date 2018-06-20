import logging
import os
import platform
import psycopg2
import psutil
import pytest
import shlex
import subprocess
import re
import sys
import urllib

from allure_commons.types import LabelType
from time import sleep

from helpers.os_helpers import pg_bindir
from helpers.pginstance import PgInstance
from helpers.pginstall import (ALT_PACKAGES,
                               DEB_BASED,
                               DEB_PACKAGES,
                               RPM_BASED,
                               WIN_BASED,
                               PACKAGES,
                               dist)
from helpers.sql_helpers import create_tablespace
from helpers.utils import command_executor
from helpers.utils import get_distro
from helpers.utils import write_file


@pytest.mark.minor_updates
class TestMinorUpdates():
    """Test class for minor updates.
    It checks that minor package updates finished without errors.
    Basic description for scenarions in this test class -
     we need to check that we can update every package on every
    operating system from earliest minor version to beta package.
    If after update postgrespro instance cannot start
    we will do pg_upgrade for first scenario and dump_restore for second.
    This test for standard and enterprise versions.

    """
    PGPRO_ARCHIVE_STANDARD = "http://repo.postgrespro.ru/pgpro-archive/"
    PGPRO_ARCHIVE_ENTERPRISE = "http://repoee.l.postgrespro.ru/archive/"

    connstring = "host=localhost user=postgres"

    def get_pgpro_minor_versions(self, major_version='9.6',
                                 edition='std'):
        """ Get all minor versions of pgpro

        :return: list with minor version
        """
        minor_versions = []
        if edition == 'std':
            page = urllib.urlopen(self.PGPRO_ARCHIVE_STANDARD).read()
        elif edition == 'ent':
            page = urllib.urlopen(self.PGPRO_ARCHIVE_ENTERPRISE).read()
        versions = re.findall('href=[\'"]?([^\'" >]+)/', page)
        for version in versions:
            if major_version in version and "9.6.4.1" not in version:
                minor_versions.append(version)
        return minor_versions

    def get_pgpro_earliest_minor_version(self, major_version='9.6',
                                         edition="std"):
        """ Get earlies minor version
        :return string with earliest minor version
        """
        versions = self.get_pgpro_minor_versions(major_version, edition)
        versions.sort()
        return versions[0]

    def generate_repo_info(self, distro, osversion, version,
                           edition="std"):
        """

        :return:
        """

        if distro == "ALT Linux " and osversion in ["7.0.4", "6.0.1"]:
            distname = "altlinux-spt"
        elif distro == "ALT Linux " and osversion == "7.0.5":
            distname = "altlinux"
        elif distro == "ROSA Enterprise Linux Server" and osversion != "6.8":
            distname = "rosa-el"
        elif distro == "ROSA Enterprise Linux Server" and osversion == "6.8":
            distname = "rosa-chrome"
        elif distro == "ROSA SX \"COBALT\" ":
            distname = "rosa-sx"
        elif distro == "AstraLinuxSE" or distro == "Astra Linux SE":
            if osversion == "1.4":
                distname = "astra-smolensk/1.4"
            elif osversion == "1.5":
                distname = "astra-smolensk/1.5"
        elif distro == "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1" \
                       "\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ":
            distname = "msvsphere"
        elif distro in WIN_BASED:
            distname = "Windows"
        else:
            distname = dist[distro].lower()

        if edition == "ent":
            baseurl = os.path.join(self.PGPRO_ARCHIVE_ENTERPRISE,
                                   version, distname)
            gpg_key_url = self.PGPRO_ARCHIVE_ENTERPRISE + version
        elif edition == "std":
            baseurl = os.path.join(self.PGPRO_ARCHIVE_STANDARD,
                                   version, distname)
            gpg_key_url = self.PGPRO_ARCHIVE_STANDARD + version
        gpg_key_url += '/keys/GPG-KEY-POSTGRESPRO'
        logging.debug("Installation repo path: %s" % baseurl)
        logging.debug("GPG key url for installation: %s" % gpg_key_url)
        return baseurl, gpg_key_url

    def setup_repo(self, version, edition="std"):
        """
        Check that we already has repo file
        Delete old repo file if needed
        Create new repo file

        :return:
        """
        dist_info = get_distro()
        repo_info = self.generate_repo_info(dist_info[0], dist_info[1],
                                            version, edition)
        baseurl = repo_info[0]
        gpg_key_url = repo_info[1]
        if dist_info[0] in RPM_BASED:
            if dist_info[0] == "ROSA Enterprise Linux Server" and \
               dist_info[1] == "6.8":
                baseurl = os.path.join(baseurl, "6.8Server/os/$basearch/rpms")
            elif dist_info[0] == "\xd0\x9c\xd0\xa1\xd0\x92\xd0\xa1"\
                                 "\xd1\x84\xd0\xb5\xd1\x80\xd0\xb0 ":
                baseurl = os.path.join(baseurl,
                                       "6.3Server/os/$basearch/rpms")
            else:
                baseurl = os.path.join(baseurl,
                                       "$releasever/os/$basearch/rpms")

            repo = """
[%s]
name=%s
baseurl=%s
enabled=1
                """ % (version, version, baseurl)
            repofile = "/etc/yum.repos.d/%s.repo" % version
            write_file(repofile, repo)
            cmd = "rpm --import %s" % gpg_key_url
            command_executor(cmd)
            return repofile
        elif dist_info[0] in DEB_BASED or "ALT" in dist_info[0]:
            cmd = "apt-get install -y lsb-release"
            command_executor(cmd)
            cmd = "lsb_release -cs"
            codename = command_executor(cmd, stdout=True)
            repofile = "/etc/apt/sources.list.d/%s.list" % version
            repo = "deb %s %s main" % (baseurl, codename)
            if dist_info[0] == "ALT Linux " and \
               dist_info[1] in ["7.0.4", "7.0.5"]:
                repo = "rpm %s/7 x86_64 pgpro\n rpm %s/7 noarch pgpro\n" % (
                    baseurl, baseurl)
            elif dist_info[0] == "ALT Linux " and dist_info[1] == "6.0.1":
                repo = "rpm %s/6 x86_64 pgpro\n rpm %s/6 noarch pgpro\n" % (
                    baseurl, baseurl)
            elif dist_info[0] == "ALT ":
                repo = "rpm %s/8 x86_64 pgpro\n rpm %s/8 noarch pgpro\n" % (
                    baseurl, baseurl)

            write_file(repofile, repo)

            if "ALT " in dist_info[0]:
                cmd = "apt-get update -y"
                command_executor(cmd)
            else:
                cmd = "apt-get install -y wget ca-certificates"
                command_executor(cmd)
                cmd = "wget --quiet -O - %s | apt-key add -" % gpg_key_url
                command_executor(cmd)
                cmd = "apt-get update -y"
                command_executor(cmd)
            return repofile
        else:
            print "Unsupported distro %s" % dist_info[0]
            sys.exit(1)

    def package_mgmt(self, version, edition="std"):
        dist_info = get_distro()
        major = "9"
        minor = version.split(".")[1]
        pkg_name = ""
        if dist_info[0] in RPM_BASED:
            if edition == "ent":
                pkg_name = "postgrespro-enterprise%s%s" % (major, minor)
            elif edition == "std":
                pkg_name = "postgrespro%s%s" % (major, minor)

            for p in PACKAGES:
                cmd = "yum install -y %s-%s" % (pkg_name, p)
                command_executor(cmd)
            # if '9.5' not in version:
            #     cmd = "yum install -y %s-%s" % (pkg_name, "pg_probackup")
            #     command_executor(cmd)
        elif dist_info[0] in DEB_BASED and "ALT" not in dist_info[0]:
            cmd = "apt-get install -y %s-%s" % ("postgrespro", ".".join(
                [major, minor]))
            command_executor(cmd)
            cmd = "apt-get install -y libpq-dev"
            command_executor(cmd)
            # if '9.5' not in version:
            #     cmd = "apt-get install -y %s-pg-probackup-%s" %
            #       ("postgrespro",  ".".join([major, minor]))
            #     command_executor(cmd)
            for p in DEB_PACKAGES:
                cmd = "apt-get install -y %s-%s-%s" % (
                    "postgrespro", p, ".".join([major, minor]))
                command_executor(cmd)

        elif "ALT" in dist_info[0]:
            if edition == "std":
                pkg_name = "postgrespro%s.%s" % (major, minor)
            elif edition == "ent":
                pkg_name = "postgrespro-enterprise%s.%s" % (major, minor)
            for p in ALT_PACKAGES:
                cmd = "apt-get install -y %s-%s" % (pkg_name, p)
                command_executor(cmd)
            # if '9.5' not in version:
            #     cmd = "apt-get install -y %s-%s" % (
            #         pkg_name, "pg_probackup")
            #     command_executor(cmd)

    def delete_repo(self, version, edition="std"):
        """ Delete repo file
        """
        dist_info = get_distro()
        if dist_info[0] in RPM_BASED:
            repofile = "/etc/yum.repos.d/%s.repo" % version
            cmd = "rm -f %s" % repofile
            command_executor(cmd)
            cmd = "yum update -y && yum clean cache"
            command_executor(cmd)
        elif dist_info[0] in DEB_BASED or "ALT" in dist_info[0]:
            repofile = "/etc/apt/sources.list.d/%s.list" % version
            cmd = "rm -f %s" % repofile
            command_executor(cmd)
            cmd = "apt-get update"
            command_executor(cmd)
            cmd = "apt-get clean cache"
            command_executor(cmd)
        else:
            print "Unsupported distro %s" % dist_info[0]
            sys.exit(1)

    def setup_psql(self, version, edition="std"):
        """

        :return: None
        """
        major = "9"
        minor = version.split(".")[1]
        print "Setup PostgreSQL service"
        distro = get_distro()[0]
        if distro in RPM_BASED or "ALT " in distro:
            self.manage_psql("initdb", version=version, edition=edition)
        self.manage_psql("start", version=version, edition=edition)
        os.environ['PATH'] += ":/usr/pgsql-%s.%s/bin/" % (major, minor)
        cmd = "sudo -u postgres psql -c " \
            "\"ALTER USER postgres WITH PASSWORD \'postgres\';\""
        command_executor(cmd)
        hba_auth = """
local   all             postgres                                trust
local   all             all                                     peer
host    all             all             0.0.0.0/0               trust
host    all             all             ::0/0                   trust"""
        self.edit_pg_hba_conf(hba_auth)
        cmd = "sudo -u postgres psql -c " \
            "\"ALTER SYSTEM SET listen_addresses to \'*\';\""
        command_executor(cmd)
        self.manage_psql("restart", version=version, edition=edition)

    def edit_pg_hba_conf(self, pg_hba_config):
        """Rewrite pg_hba.conf
        :param pg_hba_config: string with pg_hba.conf content
        """
        cmd = "sudo -u postgres psql -t -P format=unaligned -c " \
            "\"SHOW hba_file;\""
        hba_file = command_executor(cmd, stdout=True).strip()
        print "Path to hba_file is", hba_file
        write_file(hba_file, pg_hba_config)
        cmd = "chown postgres:postgres %s" % hba_file
        return command_executor(cmd)

    def pg_start_script_name(self, version, distro, edition="std"):
        """

        :param version:
        :param distro:
        :return:
        """
        print(version)
        if edition == "std":
            version = version.strip("pgpro-")
        elif edition == "ent":
            version = version.strip("pgproee-")
        major = "9"
        minor = version.split(".")[1]
        if distro in RPM_BASED:
            if version < "9.6.2.1":
                service_name = "postgresql-%s.%s" % (major, minor)
                assert service_name is not None
                return service_name
            else:
                if edition == "std":
                    service_name = "postgrespro-%s.%s" % (major, minor)
                elif edition == "ent":
                    service_name = "postgrespro-enterprise-%s.%s" % (
                        major, minor)
                assert service_name is not None
                return service_name
        elif "ALT " in distro:
            service_name = "postgresql-%s.%s" % (major, minor)
            assert service_name is not None
            return service_name
        elif distro in DEB_BASED:
            service_name = "postgresql"
            assert service_name is not None
            return service_name

    def start_script_name(self, version, edition="std"):

        return self.pg_start_script_name(version, distro=get_distro()[0],
                                         edition=edition)

    def manage_psql(self, action, data_dir=None, version="9.6",
                    edition="std"):
        """ Manage Postgres instance
        :param action: start, restart, stop etc
        :param init: Initialization before a first start
        :return:
        """

        return self.pg_manage_psql(action, data_dir, version=version,
                                   start_script=self.start_script_name(
                                       version, edition))

    def pg_manage_psql(self, action, data_dir, version, start_script=None):
        """ Manage Postgres instance
        :param action: start, restart, stop etc
        :param init: Initialization before a first start
        :return:
        """
        version = version.strip("pgpro-")
        distro = get_distro()
        if start_script is None:
            pg_ctl = os.path.join(pg_bindir(), "pg_ctl")
            cmd = "sudo -u postgres %s -w -D %s %s" % (
                pg_ctl, data_dir, action)
            print(cmd)
            return command_executor(cmd)
        else:
            if distro[0] == "ALT ":
                cmd = "/etc/init.d/%s %s" % (start_script, action)
            elif version < "9.6.2.1" and distro[0] in RPM_BASED:
                cmd = "/etc/init.d/%s %s" % (start_script, action)
            else:
                cmd = "service %s %s" % (start_script, action)
            print(cmd)
            if "ALT" in distro[0]:
                return subprocess.call(shlex.split(cmd))
            else:
                return command_executor(cmd)

    def kill_postgres_instance(self):
        """
        Method returns PID of the postmaster process.

        :returns: number with process identificator
        """
        conn = psycopg2.connect(self.connstring)
        pid = conn.get_backend_pid()
        ppid = psutil.Process(pid).ppid()
        conn.close()
        cmd = "kill -9 %s" % ppid
        return command_executor(cmd)

    def move_data_direcory(self, version, edition="std"):
        """Move data directory from one folder to another

        :return:
        """
        major = "9"
        minor = version.split(".")[1]
        distro = get_distro()[0]
        self.kill_postgres_instance()
        if distro in RPM_BASED:
            if edition == "std":
                cmd = "cp -r /var/lib/pgsql/%s.%s/data/" \
                    " /var/lib/pgpro/%s.%s/" % (major, minor, major, minor)
                command_executor(cmd)
                cmd = "chown -R postgres:postgres" \
                    " /var/lib/pgpro/%s.%s/data" % (major, minor)
                return command_executor(cmd)
            elif edition == "ent":
                cmd = "cp -r /var/lib/pgsql/%s.%s/data/" \
                    " /var/lib/pgproee/%s.%s/" % (major, minor, major, minor)
                command_executor(cmd)
                cmd = "chown -R postgres:postgres" \
                    " /var/lib/pgproee/%s.%s/data" % (major, minor)
                return command_executor(cmd)

    def create_test_tablespace(self):
        """

        :return:
        """
        create_tablespace("tbs_upgrade_check")
        return "tbs_upgrade_check"

    def create_test_table(self):
        """

        :return:
        """
        tbs_name = self.create_test_tablespace()
        conn = psycopg2.connect(self.connstring)
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE test (id serial, name text)"
            " TABLESPACE %s" % tbs_name)
        cursor.execute("INSERT INTO  test VALUES (1, 'test_text')")
        conn.commit()
        conn.close()

    def select_from_test_table(self):
        connect_retry_count = 3
        for _ in range(connect_retry_count):
            try:
                conn = psycopg2.connect(self.connstring)
            except psycopg2.OperationalError:
                sleep(10)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM test")
        return cursor.fetchall()[0]

    def execute_pgpro_upgrade(self):
        """For CentOS based OS we need to do pgpro_upgrade

        :return:
        """
        pgbindir = pg_bindir()
        pgpro_upgrade_script = os.path.join(pgbindir, "pgpro_upgrade")
        cmd = "su - postgres -c \"%s\"" % pgpro_upgrade_script
        return command_executor(cmd)

    @pytest.mark.test_minor_updates
    def test_minor_updates(self, request):
        """
        Scenario:
        1. Install earliest minor version and configure it
        2. Check that setup successfull
             (postgres run and we can create test table)
        3. Create tablespace
        4. Rewrite repoinfo and update package
        5. Check that update was successfull
            (postgres run and we can execute select 1)
        6. Check that we can read information from tablespace
        7. Download and install beta version or version from branch
        8. Check that we can read information from tablespace

        :return:
        """
        dist = ""
        if platform.system() == 'Linux':
            dist = " ".join(platform.linux_distribution()[0:2])
        elif platform.system() == 'Windows':
            dist = 'Windows'
        else:
            print("Unknown Distro")
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        build = request.config.getoption('--product_build')
        milestone = request.config.getoption('--product_milestone')
        product_info = " ".join([dist, name, edition, version])
        # pylint: disable=no-member
        tag_mark = pytest.allure.label(LabelType.TAG, product_info)
        request.node.add_marker(tag_mark)
        branch = request.config.getoption('--branch')
        local = False
        # Step 1
        earliest_pgpro_version = self.get_pgpro_earliest_minor_version(
            request.config.getoption('--product_version'), edition)
        minor_versions = self.get_pgpro_minor_versions(
            request.config.getoption('--product_version'), edition)[1:]
        self.setup_repo(earliest_pgpro_version, edition)
        self.package_mgmt(earliest_pgpro_version, edition)
        self.setup_psql(earliest_pgpro_version, edition)
        self.delete_repo(earliest_pgpro_version, edition)
        # Step 2
        # Step 3
        self.create_test_table()
        # Steps 4-6
        for version in minor_versions:
            print("Trying to update to version: %s" % version)
            if edition == "std":
                version_for_check = version.strip("pgpro-")
            else:
                version_for_check = version.strip("pgproee-")
            if version_for_check in ["9.6.4.1", "9.6.4.2", "9.6.5.1"]:
                continue
            self.setup_repo(version, edition)
            self.package_mgmt(version, edition)
            if version_for_check == "9.6.2.1" or edition == "ent" \
               and version_for_check == "9.6.3.1":
                self.move_data_direcory(version_for_check, edition)
            self.manage_psql("restart", version=version, edition=edition)
            connect_retry_count = 3
            for _ in range(connect_retry_count):
                try:
                    conn = psycopg2.connect(self.connstring)
                except psycopg2.OperationalError:
                    sleep(10)
            cursor = conn.cursor()
            cursor.execute("SELECT pgpro_version()")
            assert version_for_check == cursor.fetchall()[0][0].split()[1]
            conn.close()
            assert self.select_from_test_table() == (1, 'test_text')
            self.delete_repo(version, edition)
        # Step 7
        version = request.config.getoption('--product_version')
        pginstance = PgInstance(version, milestone, name,
                                edition, build, local, branch)
        if get_distro()[0] in RPM_BASED:
            data_dir = pginstance.get_option("data_directory")
            pginstance.install_product(version=version, milestone=milestone,
                                       name=name, edition=edition,
                                       branch=branch,
                                       skip_install_psql=True)
            os.environ["PGDATA"] = data_dir
            pginstance.manage_psql("stop")
            self.execute_pgpro_upgrade()
            pginstance.manage_psql("start")
        else:
            pginstance.install_product(version=version, milestone=milestone,
                                       name=name, edition=edition,
                                       branch=branch,
                                       skip_install_psql=True)
            pginstance.manage_psql("restart")
        # Step 8
        assert self.select_from_test_table() == (1, 'test_text')
