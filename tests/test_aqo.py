import psycopg2
import pytest
from helpers.sql_helpers import execute


def reset_aqo_stats(connstring, sql_query=None):

    conn = psycopg2.connect(connstring)

    if sql_query is not None:
        execute(conn, "DELETE FROM aqo_query_stat \
                WHERE query_hash = (SELECT query_hash from aqo_query_texts \
                WHERE query_text = '%s')" % sql_query)
        execute(conn, "DELETE FROM aqo_queries \
                WHERE query_hash = (SELECT query_hash from aqo_query_texts \
                WHERE query_text = '%s')" % sql_query)
        execute(conn, "DELETE FROM aqo_query_texts \
                WHERE query_text = '%s'" % sql_query)
    else:
        execute(conn, "TRUNCATE aqo_data CASCADE")
        execute(conn, "TRUNCATE aqo_queries CASCADE")
        execute(conn, "TRUNCATE aqo_query_stat CASCADE")
        execute(conn, "TRUNCATE aqo_query_texts CASCADE")
    conn.close()


@pytest.mark.usefixtures('install_postgres')
def test_available_modes(install_postgres):
    """
    Make sure aqo extension provides only known modes.
    """

    install_postgres.load_extension('aqo')
    known_modes = ['intelligent', 'forced', 'manual', 'disabled']

    conn = psycopg2.connect(install_postgres.connstring)
    SQL_QUERY = "SELECT enumvals FROM pg_settings WHERE name='aqo.mode';"
    actual_modes = execute(conn, SQL_QUERY)[0][0]
    conn.close()

    assert known_modes == actual_modes


@pytest.mark.usefixtures('install_postgres')
def test_default_aqo_mode(install_postgres):
    """
    Make sure default aqo mode stay without changes
    """

    install_postgres.load_extension('aqo')
    conn = psycopg2.connect(install_postgres.connstring)
    SQL_QUERY = "SELECT boot_val FROM pg_settings WHERE name='aqo.mode'"
    mode = execute(conn, SQL_QUERY)[0][0]
    conn.close()

    assert mode == "manual"


@pytest.mark.usefixtures('install_postgres')
def test_similar_queries(install_postgres):
    """
    Make sure AQO uses common statistic data for queries
    with the same constants in SQL clauses.
    """

    install_postgres.load_extension('aqo')
    reset_aqo_stats(install_postgres.connstring)

    conn = psycopg2.connect(install_postgres.connstring)
    execute(conn, 'SELECT 1')
    num1 = execute(conn, "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = 'SELECT 1'")[0][0]
    execute(conn, 'SELECT 2')
    num2 = execute(conn, "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = 'SELECT 2'")[0][0]
    conn.close()

    assert num1 == 1
    assert num2 == 0
