import pytest
import random

from helpers.sql_helpers import pg_initdb
from helpers.sql_helpers import execute
from helpers.os_helpers import pg_bindir
from helpers.os_helpers import parse_connstring
from helpers.os_helpers import load_pgbench

START_XID = 4294967296                  # 2^32
END_XID = 9223372036854775808           # 2^63


@pytest.skip(reason="PGPRO-501")
@pytest.mark.usefixtures('install_postgres')
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


@pytest.skip(reason="PGPRO-501")
@pytest.mark.usefixtures('install_postgres')
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
