import hashlib
import platform
import pytest
import psycopg2
import random
import string

from allure.types import LabelType
from helpers.utils import MySuites

dist = ""
if platform.system() == 'Linux':
    dist = " ".join(platform.linux_distribution()[0:2])
elif platform.system() == 'Windows':
    dist = 'Windows'
else:
    print("Unknown Distro")

version = pytest.config.getoption('--product_version')
name = pytest.config.getoption('--product_name')
edition = pytest.config.getoption('--product_edition')
feature_name = "_".join(["Scram", dist, name, edition, version])


@pytest.allure.feature(feature_name)
@pytest.mark.core_functional
@pytest.mark.usefixtures('install_postgres')
class TestScram():
    """
    Only Enterprise Edition Feature
    """
    dist = ""
    if platform.system() == 'Linux':
        dist = " ".join(platform.linux_distribution()[0:2])
    elif platform.system() == 'Windows':
        dist = 'Windows'
    else:
        print("Unknown Distro")

    version = pytest.config.getoption('--product_version')
    name = pytest.config.getoption('--product_name')
    edition = pytest.config.getoption('--product_edition')
    feature_name = "_".join(["Scram", dist, name, edition, version])

    @staticmethod
    def random_password():
        return ''.join(random.choice(string.lowercase) for i in range(16))

    @staticmethod
    def create_hash_password(hash_type, password):
        if hash_type == 'md5':
            hash = hashlib.md5()
            hash.update(password)
            return 'md5' + hash.hexdigest()
        elif hash_type == 'sha256':
            hash = hashlib.sha256()
            hash.update(password)
            return 'AAAAAAAAAAAAAA==:4096:' + hash.hexdigest()
        else:
            print("Error. Bad hash type. Use md5 or sha256")
            return None

    @pytest.allure.feature(feature_name)
    @pytest.mark.test_scram_configuring
    def test_scram_configuring(self, request):
        """Check that we can set GUC variables via SET command,
         they saved and in pg_authid password saved in right format
        Scenario:
        1. Check that default password encryption is md5
        2. Set password encryption is plain
        3. Check that password encryption is plain
        4. Create role test_plain_user with password 'test_plain_password'
        5. Check from pg_authid that password for user test_plain_user in plain and equal 'test_plain_password'
        6. Set password encrytpion is md5
        7. Create role test_md5_user with password 'test_md5_password'
        8. Check from pg_authid that password for user test_md5_user in md5
        9. Set password encrytpion is scram
        10. Create role test_scram_user with password 'test_scram_password'
        11. Check from pg_authid that password for user test_scram_user in scram
        12. Set password encrytpion is on
        13. Create role test_on_user with password 'test_on_password'
        14. Check from pg_authid that password for user test_on_user in md5
        15. Set password encrytpion is off
        16. Create role test_off_user with password 'test_off_password'
        17. Check from pg_authid that password for user test_off_user in plain

        """
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        product_info = " ".join([self.dist, name, edition, version])
        tag_mark = pytest.allure.label(LabelType.TAG, self.dist)
        request.node.add_marker(tag_mark)
        tag_mark = pytest.allure.label(MySuites.PARENT_SUITE, product_info)
        request.node.add_marker(tag_mark)
        tag_mark = pytest.allure.label(MySuites.EPIC, product_info)
        request.node.add_marker(tag_mark)
        # Step 1
        conn_string = "host='localhost' user='postgres'"
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute("SHOW password_encryption")
        current_encryption = cursor.fetchall()[0][0]
        assert current_encryption == 'md5'
        # Step 2
        cursor.execute("SET password_encryption = 'plain'")
        # Step 3
        cursor.execute("SHOW password_encryption")
        current_encryption = cursor.fetchall()[0][0]
        assert current_encryption == 'plain'
        # Step 4
        cursor.execute("CREATE ROLE test_plain_user WITH PASSWORD 'test_plain_password' LOGIN")
        # Step 5
        cursor.execute("SELECT rolpassword FROM pg_authid where rolname = 'test_plain_user'")
        assert cursor.fetchall()[0][0] == 'test_plain_password'
        # Step 6
        cursor.execute("SET password_encryption = 'md5'")
        # Step 7
        cursor.execute("CREATE ROLE test_md5_user WITH PASSWORD 'test_md5_password' LOGIN")
        # Step 8
        cursor.execute("SELECT rolpassword FROM pg_authid where rolname = 'test_md5_user'")
        test_md5_user_pass = cursor.fetchall()[0][0]
        assert test_md5_user_pass[0:3] == 'md5'
        # Step 9
        cursor.execute("SET password_encryption = 'scram'")
        # Step 10
        cursor.execute("CREATE ROLE test_scram_user WITH PASSWORD 'test_scram_password' LOGIN")
        # Step 11
        cursor.execute("SELECT rolpassword FROM pg_authid where rolname = 'test_scram_user'")
        test_scram_user_pass = cursor.fetchall()[0][0]
        assert test_scram_user_pass[0:21] == 'AAAAAAAAAAAAAA==:4096'
        # Step 12
        cursor.execute("SET password_encryption = 'on'")
        # Step 13
        cursor.execute("CREATE ROLE test_on_user WITH PASSWORD 'test_on_password' LOGIN")
        # Step 14
        cursor.execute("SELECT rolpassword FROM pg_authid where rolname = 'test_on_user'")
        test_on_user_pass = cursor.fetchall()[0][0]
        assert test_on_user_pass[0:3] == 'md5'
        # Step 15
        cursor.execute("SET password_encryption = 'off'")
        # Step 16
        cursor.execute("CREATE ROLE test_off_user WITH PASSWORD 'test_off_password' LOGIN")
        # Step 17
        cursor.execute("SELECT rolpassword FROM pg_authid where rolname = 'test_off_user'")
        assert cursor.fetchall()[0][0] == 'test_off_password'
        cursor.close()
        conn.close()

    @pytest.allure.feature(feature_name)
    @pytest.mark.xfail
    @pytest.mark.test_authentication
    def test_authentication(self, request, install_postgres):
        """Check that we can authenticate user with different password types
        Scenario:
        1. Edit pg_hba conf for test and restart postgres
        2. Create roles for test
        3. Try to connect to db with hashed password
        4. Try to connect to db with password that stored in md5 hash
        5. Try to connect to db with password in scram format
        6. Try to connect with password in scram hash
        """
        version = request.config.getoption('--product_version')
        name = request.config.getoption('--product_name')
        edition = request.config.getoption('--product_edition')
        product_info = " ".join([self.dist, name, edition, version])
        tag_mark = pytest.allure.label(LabelType.TAG, self.dist)
        request.node.add_marker(tag_mark)
        tag_mark = pytest.allure.label(MySuites.PARENT_SUITE, product_info)
        request.node.add_marker(tag_mark)
        tag_mark = pytest.allure.label(MySuites.EPIC, product_info)
        request.node.add_marker(tag_mark)
        # Step 1
        hba_auth = """
            local   all             test_md5_hash_user                      md5
            local   all             test_md5_user_auth                      md5
            local   all             test_scram_hash_user                    scram
            local   all             test_scram_user_auth                    scram
            local   all             all                                     peer
            host    all             all             0.0.0.0/0               trust
            host    all             all             ::0/0                   trust"""
        install_postgres.edit_pg_hba_conf(hba_auth)
        install_postgres.manage_psql('restart')
        # Step 2
        conn_string = "host='localhost' user='postgres' dbname='postgres'"
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        md5_password = self.create_hash_password('md5', self.random_password())
        cursor.execute("CREATE ROLE test_md5_user_auth WITH PASSWORD 'test_md5_password' LOGIN")
        cursor.execute("CREATE ROLE test_md5_hash_user WITH PASSWORD '%s' LOGIN" % md5_password)
        scram_password = self.create_hash_password('sha256', self.random_password())
        conn.commit()
        cursor.close()
        conn.close()
        install_postgres.set_option('password_encryption', 'scram')
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        cursor.execute("CREATE ROLE test_scram_user_auth WITH PASSWORD 'test_scram_password' LOGIN")
        cursor.execute("CREATE ROLE test_scram_hash_user WITH PASSWORD ('%s' USING \'plain\') LOGIN" % scram_password)
        conn.commit()
        cursor.close()
        conn.close()
        # Step 3
        conn_string_md5_user =\
            "host='localhost' user='test_md5_user_auth' password='test_md5_password' dbname='postgres'"
        conn_md5_user = psycopg2.connect(conn_string_md5_user)
        assert conn_md5_user.status == 1
        conn_md5_user.close()
        # Step 4
        conn_string_test_md5_hash_user =\
            "host='localhost' user='test_md5_hash_user' password='%s' dbname='postgres'" % md5_password
        conn_md5_hash_user = psycopg2.connect(conn_string_test_md5_hash_user)
        assert conn_md5_hash_user.status == 1
        cursor = conn_md5_hash_user.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn_md5_hash_user.close()
        # Step 5
        conn_test_scram_user_auth = \
            "host='localhost' user='test_scram_user_auth' password='test_scram_password' dbname='postgres'"
        conn_test_scram_user_auth = psycopg2.connect(conn_test_scram_user_auth)
        assert conn_test_scram_user_auth.status == 1
        cursor = conn_test_scram_user_auth.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn_test_scram_user_auth.close()
        # Step 6
        conn_scram_hash_user = \
            "host='localhost' user='test_scram_hash_user' password=%s dbname='postgres'" % scram_password
        conn_scram_hash_user = psycopg2.connect(conn_scram_hash_user)
        assert conn_scram_hash_user.status == 1
        cursor = conn_scram_hash_user.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn_scram_hash_user.close()
