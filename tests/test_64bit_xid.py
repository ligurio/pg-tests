import hashlib
import psycopg2
import pytest
import random
import time

from helpers.sql_helpers import execute
from helpers.sql_helpers import pg_initdb
from helpers.sql_helpers import create_test_table
from helpers.os_helpers import load_pgbench

START_XID = 4294967296                  # 2^32
END_XID = 4611686018427387904           # 2^62
PGBENCH_SCHEMA = """

CREATE TABLE pgbench_accounts (
aid bigint NOT NULL,
bid integer NOT NULL,
abalance integer NOT NULL,
filler character(84)
);

CREATE TABLE pgbench_branches (
bid integer NOT NULL,
bbalance integer NOT NULL,
filler character(88)
);

CREATE TABLE pgbench_history (
tid integer NOT NULL,
bid integer NOT NULL,
aid bigint NOT NULL,
delta integer NOT NULL,
mtime timestamp without time zone NOT NULL,
filler character(22)
);

CREATE TABLE pgbench_tellers (
tid integer NOT NULL,
bid integer NOT NULL,
tbalance integer NOT NULL,
filler character(84)
);
"""


def test_xid_boundary_values(install_postgres):

    connstring = install_postgres.connstring
    offset = random.randrange(START_XID, END_XID)
    pg_initdb(connstring, "-x", str(offset), "-m", str(offset))
    load_pgbench(connstring, ["-i", "-n", "-s", "100"])


testdata = [("autovacuum_freeze_max_age", 100000, 9223372036854775807),
            ("autovacuum_multixact_freeze_max_age", 10000, 9223372036854775807),
            ("vacuum_freeze_min_age", 0, 9223372036854775807),
            ("vacuum_freeze_table_age", 0, 9223372036854775807),
            ("vacuum_multixact_freeze_min_age", 0, 9223372036854775807),
            ("vacuum_multixact_freeze_table_age", 0, 9223372036854775807)]

gucs = [("autovacuum_freeze_max_age"),
        ("autovacuum_multixact_freeze_max_age"),
        ("vacuum_freeze_min_age"),
        ("vacuum_freeze_table_age"),
        ("vacuum_multixact_freeze_min_age"),
        ("vacuum_multixact_freeze_table_age")]


@pytest.mark.parametrize("guc, min, max", testdata, ids=gucs)
def test_guc_boundary_values(guc, min, max, install_postgres):
    """
    Testcase validates boundary values of GUCs specific for 64-bit XID's.
    """

    connstring = install_postgres.connstring
    pg_initdb(connstring, "-x", str(START_XID), "-m", str(START_XID))
    load_pgbench(connstring, ["--initialize", "--scale=100"])

    for value in [min, max, random.randrange(min, max)]:
        install_postgres.set_option(guc, value)
        load_pgbench(connstring, ["--progress=5", "--transactions=1000",
                                  "--jobs=5", "--client=5"])


def rel_checksum(fd):

    BUFSIZE = 4096
    m = hashlib.sha256()
    while True:
        data = fd.read(BUFSIZE)
        if not data:
            break
        m.update(data)

    return m.hexdigest()


def test_integrity(install_postgres):
    """
    Testcase checks data integrity with 64bit XID support.
    """

    pgbench_tables = {'pgbench_accounts': 0, 'pgbench_branches': 0,
                    'pgbench_history': 0, 'pgbench_tellers': 0}

    connstring = install_postgres.connstring
    load_pgbench(connstring, ["-i", "-s", "100"])

    conn = psycopg2.connect(connstring)
    cursor = conn.cursor()
    for key in pgbench_tables:
        filename = '%s.sql' % key
        with open(filename, 'w') as f:
            cursor.copy_to(f, key, sep=',')
        with open(filename, 'r') as f:
            pgbench_tables[key] = rel_checksum(f)
    cursor.close()
    conn.close()

    offset = random.randrange(START_XID, END_XID)
    pg_initdb(connstring, "-x", str(offset), "-m", str(offset))

    time.sleep(2)
    conn = psycopg2.connect(connstring)
    cursor = conn.cursor()
    execute(conn, PGBENCH_SCHEMA)
    for key in pgbench_tables:
        filename = '%s.sql' % key
        with open(filename, 'r') as f:
            cursor.copy_from(f, key, sep=',')
        with open(filename, 'w') as f:
            cursor.copy_to(f, key, sep=',')
        with open(filename, 'r') as f:
            assert pgbench_tables[key] == rel_checksum(f)
    cursor.close()
    conn.close()
