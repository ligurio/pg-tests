import pytest
import psycopg2


class TestScram():
    """
    Only Enterprise Edition Feature
    """

    @pytest.mark.test_configuring
    def test_scram_configuring(self):
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
