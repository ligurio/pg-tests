import numpy
import psycopg2
import pytest
import re
from helpers.sql_helpers import execute


def parse_explain_stat(explain_output):

    dict = {'planning_time': '', 'execution_time': '', 'cardinality': ''}
    plan = explain_output[0][0][0]["Plan"]
    dict['cardinality'] = plan["Plan Rows"]

    return dict


def parse_explain_analyze_stat(explain_output):

    dict = {'planning_time': '',
            'execution_time': '',
            'planning_cardinality': '',
            'actual_cardinality': '',
            'cardinality_error': ''}

    # Like 'Seq Scan on pg_class  (cost=0.00..14.56 rows=356 width=228)
    #       (actual time=0.013..0.077 rows=356 loops=1)'
    REGEX_CARDINALITY = '.*\(cost.*rows=([0-9]*).*\)\s{1}\(actual\s{1}time.*rows=([0-9]*).*\)'
    REGEX_TIME = '\w+\s{1}time:\s{1}([0-9]+\.[0-9]+)\s{1}ms'

    try:
        dict['execution_time'] = re.search(REGEX_TIME, explain_output[-2][0]).group(1)
        dict['execution_time'] = float(dict['execution_time'])/1000
    except AttributeError:
        print 'Failed to extract numbers in %s' % dict['execution_time']
    except IndexError:
        print explain_output[-2][0]

    try:
        dict['planning_time'] = re.search(REGEX_TIME, explain_output[-1][0]).group(1)
        dict['planning_time'] = float(dict['planning_time'])/1000
    except AttributeError:
        print 'Failed to extract numbers in %s' % dict['planning_time']
    except IndexError:
        print explain_output[-2][0]

    log_rows_predicted = []
    log_rows_actual = []

    for line in explain_output:
        rows = re.search(REGEX_CARDINALITY, str(line))
        if rows is not None:
            predicted_rows = int(rows.group(1))
            actual_rows = int(rows.group(2))
            log_rows_predicted.append(numpy.log(predicted_rows))
            log_rows_actual.append(numpy.log(actual_rows))

    assert len(log_rows_predicted) == len(log_rows_actual)

    dict['cardinality_error'] = abs(numpy.mean(log_rows_predicted) - numpy.mean(log_rows_actual))

    return dict


def query_to_hash(sql_query, connstring):
    """
    Return query hash for specified SQL query.
    """

    conn = psycopg2.connect(connstring)
    query_hash_sql = execute(conn, "SELECT query_hash \
                            FROM aqo_query_texts \
                            WHERE query_text='%s'" % sql_query)
    conn.close()

    return query_hash_sql


def get_query_aqo_param(sql_query, param_name, connstring):
    """
    Return aqo parameter for specified SQL query.
    Possible parameters: learn_aqo, use_aqo, fspace_hash, auto_tuning
    """

    conn = psycopg2.connect(connstring)

    value = execute(conn, "SELECT %s FROM aqo_queries \
                       WHERE query_hash = \
                       (SELECT query_hash from aqo_query_texts \
                       WHERE query_text = '%s')" % (param_name, sql_query))
    conn.close()

    if len(value) is not 0:
        return value[0][0]
    else:
        return None


def set_query_aqo_param(sql_query, param_name, value, connstring):
    """
    Set aqo parameter for specified SQL query.
    Possible parameters: learn_aqo, use_aqo, fspace_hash, auto_tuning
    """

    conn = psycopg2.connect(connstring)

    execute(conn, "UPDATE aqo_queries SET %s = %s \
            WHERE query_hash = \
            (SELECT query_hash from aqo_query_texts \
            WHERE query_text = '%s')" % (param_name, value, sql_query))
    conn.close()

    assert get_query_aqo_param(sql_query, param_name, connstring) == value


def get_query_aqo_stat(sql_query, param_name, connstring):
    """
    Return aqo statistics for a specific query:
        - execution time with/without aqo
        - planning time with/without aqo
        - cardinality error with/without aqo
        - executions with/without aqo
    """

    conn = psycopg2.connect(connstring)

    response = execute(conn, "SELECT %s FROM aqo_query_stat \
                            WHERE query_hash = \
                            (SELECT query_hash from aqo_query_texts \
                            WHERE query_text = '%s')" % (param_name, sql_query))
    conn.close()

    return response


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
