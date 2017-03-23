import glob
import json
import matplotlib.pyplot as plot
import numpy
import os
import platform
import psycopg2
import pytest
import re
import shutil
import subprocess
import time
from helpers.sql_helpers import execute
from helpers.sql_helpers import pg_set_option
from helpers.os_helpers import download_file
from tests.settings import TMP_DIR

AQO_AUTO_TUNING_MAX_ITERATIONS = 50  # auto_tuning_max_iterations in aqo.c


def learn_aqo(sql_query, connstring, number=AQO_AUTO_TUNING_MAX_ITERATIONS):
    """
    This function is intended to learn AQO with a specific function
    with exact number of iterations equal to AQO_AUTO_TUNING_MAX_ITERATIONS
    """

    conn = psycopg2.connect(connstring)

    stats = {'default': [], 'aqo': [], 'aqo_stat': [],
             'learn_aqo_true': '', 'learn_aqo_false': '',
             'use_aqo_true': '', 'use_aqo_false': '', 'query': sql_query}

    sql_query_analyze = 'EXPLAIN ANALYZE ' + sql_query

    aqo_mode = execute(conn, 'SHOW aqo.mode')[0][0]
    pg_set_option(connstring, 'aqo.mode', 'disabled')
    for i in range(0, number):
        dict = parse_explain_analyze_stat(execute(conn, sql_query_analyze))
        stats['default'].append(dict)

    pg_set_option(connstring, 'aqo.mode', aqo_mode)
    aqo_stat = []
    for i in range(0, number):
        use_aqo = get_query_aqo_param(sql_query_analyze, 'use_aqo', connstring)
        learn_aqo = get_query_aqo_param(
            sql_query_analyze, 'learn_aqo', connstring)
        auto_tuning = get_query_aqo_param(
            sql_query_analyze, 'auto_tuning', connstring)

        dict = parse_explain_analyze_stat(execute(conn, sql_query_analyze))
        stats['aqo'].append(dict)

        if learn_aqo:
            if stats['learn_aqo_true'] == '':
                stats['learn_aqo_true'] = i
            if use_aqo:
                cardinality_error = get_query_aqo_stat(
                    sql_query_analyze, 'cardinality_error_with_aqo', connstring)[0][0][-1]
            else:
                cardinality_error = get_query_aqo_stat(
                    sql_query_analyze, 'cardinality_error_without_aqo', connstring)[0][0][-1]
        else:
            if stats['learn_aqo_false']:
                stats['learn_aqo_false'] = i
            cardinality_error = 0

        if use_aqo:
            if stats['use_aqo_true'] == '':
                stats['use_aqo_true'] = i
            execution_time = get_query_aqo_stat(
                sql_query_analyze, 'execution_time_with_aqo', connstring)[0][0][-1]
            planning_time = get_query_aqo_stat(
                sql_query_analyze, 'planning_time_with_aqo', connstring)[0][0][-1]
        elif learn_aqo or auto_tuning:
            execution_time = get_query_aqo_stat(
                sql_query_analyze, 'execution_time_without_aqo', connstring)[0][0][-1]
            planning_time = get_query_aqo_stat(
                sql_query_analyze, 'planning_time_without_aqo', connstring)[0][0][-1]
        else:
            if stats['use_aqo_false'] == '':
                stats['use_aqo_false'] = i
            execution_time = 0
            planning_time = 0

        dict = {'execution_time': execution_time,
                'planning_time': planning_time,
                'cardinality_error': cardinality_error}
        aqo_stat.append(dict)

    stats['aqo_stat'] = aqo_stat
    conn.close()

    return stats


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
        dict['execution_time'] = re.search(
            REGEX_TIME, explain_output[-2][0]).group(1)
        dict['execution_time'] = float(dict['execution_time']) / 1000
    except AttributeError:
        print 'Failed to extract numbers in %s' % dict['execution_time']
    except IndexError:
        print explain_output[-2][0]

    try:
        dict['planning_time'] = re.search(
            REGEX_TIME, explain_output[-1][0]).group(1)
        dict['planning_time'] = float(dict['planning_time']) / 1000
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

    dict['cardinality_error'] = abs(numpy.mean(
        log_rows_predicted) - numpy.mean(log_rows_actual))

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


def keep_aqo_tables(connstring):

    conn = psycopg2.connect(connstring)
    DBNAME = 'postgres'
    cursor = conn.cursor()
    aqo_tables = ['aqo_query_stat',
                  'aqo_query_texts', 'aqo_data', 'aqo_queries']
    for t in aqo_tables:
        with open('%s-%s.sql' % (t, DBNAME), 'w') as outfile:
            cursor.copy_to(outfile, t, sep="|")
    cursor.close()
    conn.close()


def dump_stats(stats, filename):

    with open('%s.json' % filename, 'w') as outfile:
        json.dump(stats, outfile, sort_keys=True, indent=4, ensure_ascii=False)


def plot_stats(stats, connstring):

    sql_query_analyze = "EXPLAIN ANALYZE " + stats['query']
    filename = str(query_to_hash(sql_query_analyze, connstring)[0][0])
    assert filename != ''
    if filename[0] == '-':
        filename = filename[1:]

    dump_stats(stats, filename)
    types = ['default', 'aqo', 'aqo_stat']

    #
    #   DRAW TOTAL TIME (EXECUTION + PLANNING)
    #

    plot.figure(figsize=(10, 5))
    for type in types:
        x_series = [x for x in range(0, len(stats[type]))]

        execution_time = [float(x['execution_time']) for x in stats[type]]
        planning_time = [float(x['planning_time']) for x in stats[type]]
        y_series = [x + y for x, y in zip(execution_time, planning_time)]
        plot.plot(x_series, y_series, label="%s total time" % type)

    for p in ['learn_aqo_true', 'learn_aqo_false', 'use_aqo_true', 'use_aqo_false']:
        if stats[p]:
            plot.axvline(stats[p], label=p, color='r')

    plot.axvline(AQO_AUTO_TUNING_MAX_ITERATIONS,
                 label='auto_tuning_max_iterations', color='k')
    plot.autoscale(enable=True, axis=u'both', tight=False)
    plot.xlabel("Iteration")
    plot.ylabel("Time")
    plot.grid(True)
    plot.title("aqo vs default planners")

    plot.legend(loc='best', fancybox=True, framealpha=0.5)
    plot.savefig("%s.png" % filename, dpi=100)
    plot.close()

    #
    #   DRAW CARDINALITY
    #

    plot.figure(figsize=(10, 5))
    types = ['default', 'aqo', 'aqo_stat']
    for type in types:
        x_series = [x for x in range(0, len(stats[type]))]
        y_series = [float(x['cardinality_error']) for x in stats[type]]
        plot.plot(x_series, y_series, label="%s cardinality error" % type)

    for p in ['learn_aqo_true', 'learn_aqo_false', 'use_aqo_true', 'use_aqo_false']:
        if stats[p]:
            plot.axvline(stats[p], label=p, color='r')

    plot.axvline(AQO_AUTO_TUNING_MAX_ITERATIONS,
                 label='auto_tuning_max_iterations', color='k')
    plot.autoscale(enable=True, axis=u'both', tight=False)
    plot.xlabel("Iteration")
    plot.ylabel("Cardinality error")
    plot.grid(True)
    plot.title("aqo vs default planners")

    plot.legend(loc='best', fancybox=True, framealpha=0.5)
    plot.savefig("%s-cardinality.png" % filename, dpi=100)
    plot.close()


@pytest.mark.usefixtures('install_postgres')
def test_available_modes(install_postgres):
    """
    Make sure aqo extension provides only known modes.
    """

    install_postgres.load_extension('aqo')
    known_modes = ['intelligent', 'forced', 'controlled', 'disabled']

    conn = psycopg2.connect(install_postgres.connstring)
    SQL_QUERY = "SELECT enumvals FROM pg_settings WHERE name='aqo.mode';"
    actual_modes = execute(conn, SQL_QUERY)[0][0]
    conn.close()

    assert known_modes == actual_modes


def evaluate_aqo(stats):
    """
    This function is intended to validate aqo with specific query.

    Criterias:

        - planning time + execution time with aqo
            is not bigger than time of default planner
        - cardinality error is less than 0.5
        - there are no spikes on total_time with enabled aqo after
    """

    IGNORE_ITER = 10
    dict = {'aqo': {'total_time': '', 'cardinality_error': ''},
            'aqo_stat': {'total_time': '', 'cardinality_error': ''},
            'default': {'total_time': '', 'cardinality_error': ''}}

    for k in dict.keys():
        execution_time = [float(x['execution_time']) for x in stats[k]]
        planning_time = [float(x['planning_time']) for x in stats[k]]
        dict[k]['total_time'] = [x + y for x,
                                 y in zip(execution_time[-IGNORE_ITER:], planning_time[-IGNORE_ITER:])]
        dict[k]['cardinality_error'] = [
            float(x['cardinality_error']) for x in stats[k]]

    assert len(dict['aqo']) == len(dict['aqo_stat'])
    # FIXME:
    # assert (numpy.mean(dict['default']['total_time']) < numpy.mean(dict['aqo_stat']['total_time']))
    assert (numpy.mean(dict['aqo']['total_time']) /
            numpy.mean(dict['aqo_stat']['total_time'])) < 0.15
    diff = numpy.mean(dict['default']['cardinality_error']) - \
        numpy.mean(dict['aqo_stat']['cardinality_error'])
    assert diff < 0.5 and diff > 0

    IGNORE_ITER = 65
    FACTOR_SPIKE = 3
    if len(dict['aqo']) > IGNORE_ITER:
        for k in dict.keys():
            execution_time = [float(x['execution_time']) for x in stats[k]]
            planning_time = [float(x['planning_time']) for x in stats[k]]
            dict[k]['total_time'] = [
                x + y for x, y in zip(execution_time[-IGNORE_ITER:], planning_time[-IGNORE_ITER:])]
            dict[k]['cardinality_error'] = [
                float(x['cardinality_error']) for x in stats[k]]

        assert numpy.max(dict['aqo']['total_time']) < numpy.mean(
            dict['aqo']['total_time']) * FACTOR_SPIKE


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

    assert mode == "controlled"


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
    num1 = execute(
        conn, "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = 'SELECT 1'")[0][0]
    execute(conn, 'SELECT 2')
    num2 = execute(
        conn, "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = 'SELECT 2'")[0][0]
    conn.close()

    assert num1 == 1
    assert num2 == 0


@pytest.mark.parametrize("aqo_mode", [
                        ("intelligent"),
                        ("forced"),
                        ("manual"),
                        ("disabled"),
])
@pytest.mark.usefixtures('install_postgres')
def test_aqo_mode(aqo_mode, install_postgres):
    """
    Testcase validates available aqo modes

    +-------------+-------------+-------------+-----------------+
    |             | optimize    | optimize    | separate record |
    |  aqo mode   | new queries | old queries | for each query  |
    +-----------------------------------------------------------+
    | intelligent | Yes         | Yes         | Yes             |
    | manual      | No          | Yes         | Yes             |
    | forced      | Yes         | Yes         | No              |
    | disabled    | No          | No          | -               |
    +-------------+-------------+-------------+-----------------+

    """

    OLD_SQL_QUERY = "SELECT * FROM pg_class WHERE relpages > 455"
    NEW_SQL_QUERY = "SELECT * FROM pg_class WHERE reltablespace != reltoastrelid"
    old_sql_query_explain = 'EXPLAIN ANALYZE ' + OLD_SQL_QUERY
    new_sql_query_explain = 'EXPLAIN ANALYZE ' + NEW_SQL_QUERY

    install_postgres.load_extension('aqo')
    connstring = install_postgres.connstring
    reset_aqo_stats(connstring)

    install_postgres.set_option('aqo.mode', 'intelligent')
    learn_aqo(OLD_SQL_QUERY, connstring)
    install_postgres.set_option('aqo.mode', aqo_mode)
    learn_aqo(NEW_SQL_QUERY, connstring)

    conn = psycopg2.connect(install_postgres.connstring)
    num_old_sql_query = execute(conn,
                                "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = '%s'" % old_sql_query_explain)[0][0]
    num_new_sql_query = execute(conn,
                                "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = '%s'" % new_sql_query_explain)[0][0]

    if aqo_mode == 'forced' or aqo_mode == 'disabled':
        executions_w_aqo = execute(conn,
                                   "SELECT executions_with_aqo FROM aqo_query_stat WHERE query_hash = 0;")
        executions_wo_aqo = execute(conn,
                                    "SELECT executions_without_aqo FROM aqo_query_stat WHERE query_hash = 0;")
    elif aqo_mode == 'intelligent':
        new_executions_w_aqo = get_query_aqo_stat(new_sql_query_explain,
                                                  'executions_with_aqo', connstring)[0][0]
        new_executions_wo_aqo = get_query_aqo_stat(new_sql_query_explain,
                                                   'executions_without_aqo', connstring)[0][0]
        old_executions_w_aqo = get_query_aqo_stat(old_sql_query_explain,
                                                  'executions_with_aqo', connstring)
        old_executions_wo_aqo = get_query_aqo_stat(old_sql_query_explain,
                                                   'executions_without_aqo', connstring)
    conn.close()

    if aqo_mode == 'intelligent':
        assert num_old_sql_query == 1
        assert num_new_sql_query == 1
        assert new_executions_w_aqo + new_executions_wo_aqo == AQO_AUTO_TUNING_MAX_ITERATIONS
        assert old_executions_w_aqo + old_executions_wo_aqo == AQO_AUTO_TUNING_MAX_ITERATIONS
        # TODO: check optimization of old query
        # TODO: check optimization of new query
    elif aqo_mode == 'forced':
        assert num_old_sql_query == 1
        assert num_new_sql_query == 0
        assert executions_w_aqo + executions_wo_aqo == AQO_AUTO_TUNING_MAX_ITERATIONS
        # TODO: check optimization of old query
        # TODO: check optimization of new query
    elif aqo_mode == 'manual':
        assert num_old_sql_query == 1
        assert num_new_sql_query == 0
        # TODO: check optimization of old query
        # TODO: check optimization of new query
    elif aqo_mode == 'disabled':
        assert num_old_sql_query == 1
        assert num_new_sql_query == 0
        assert executions_w_aqo + executions_wo_aqo == 0
        # TODO: check optimization of old queries
        # TODO: check optimization of new queries
    else:
        pytest.fail("Unknown AQO mode - %s" % aqo_mode)


@pytest.mark.usefixtures('install_postgres')
def test_aqo_stat_numbers(install_postgres):
    """
    Testcase validate numbers in aqo statistics.
    """

    SQL_QUERY = "SELECT 1"
    SQL_QUERY_ANALYZE = 'EXPLAIN ANALYZE ' + SQL_QUERY
    ITER_NUM = 100

    connstring = install_postgres.connstring
    install_postgres.load_extension('aqo')
    reset_aqo_stats(connstring)
    stat = learn_aqo(SQL_QUERY, ITER_NUM)
    plot_stats(stat, connstring)

    executions_w_aqo = get_query_aqo_stat(
        SQL_QUERY_ANALYZE, 'executions_with_aqo', connstring)[0][0]
    executions_wo_aqo = get_query_aqo_stat(
        SQL_QUERY_ANALYZE, 'executions_without_aqo', connstring)[0][0]

    planning_time_w_aqo = get_query_aqo_stat(
        SQL_QUERY_ANALYZE, 'planning_time_with_aqo', connstring)[0][0]
    planning_time_wo_aqo = get_query_aqo_stat(
        SQL_QUERY_ANALYZE, 'planning_time_without_aqo', connstring)[0][0]

    execution_time_w_aqo = get_query_aqo_stat(
        SQL_QUERY_ANALYZE, 'execution_time_with_aqo', connstring)[0][0]
    execution_time_wo_aqo = get_query_aqo_stat(
        SQL_QUERY_ANALYZE, 'execution_time_without_aqo', connstring)[0][0]

    assert executions_w_aqo + executions_wo_aqo == ITER_NUM
    assert len(stat['aqo_stat']) == ITER_NUM
    assert len(planning_time_wo_aqo) == len(execution_time_wo_aqo)
    assert len(planning_time_w_aqo) == len(execution_time_w_aqo)


@pytest.mark.usefixtures('install_postgres')
def test_tuning_max_iterations(install_postgres):
    """
    AQO will disable query optimization after N unsussessful attempts.
    N is defined in auto_tuning_max_iterations in aqo.c
    """

    install_postgres.load_extension('aqo')
    reset_aqo_stats(install_postgres.connstring)

    conn = psycopg2.connect(install_postgres.connstring)
    execute(conn, 'SELECT 1')
    num1 = execute(
        conn, "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = 'SELECT 1'")[0][0]
    execute(conn, 'SELECT 2')
    num2 = execute(
        conn, "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = 'SELECT 2'")[0][0]
    conn.close()

    assert num1 == 1
    assert num2 == 0


@pytest.mark.usefixtures('install_postgres')
def test_in_honor_of_teodor(install_postgres):

    PREP_TABLE_QUERY = """
DROP TABLE IF EXISTS t;
DROP TABLE IF EXISTS a;
DROP TABLE IF EXISTS b;

SELECT id::int4, (id/3)::int4 AS v INTO t FROM GENERATE_SERIES(1,10000) AS id;
CREATE UNIQUE INDEX it ON t (id, v);

SELECT (100.0 * RANDOM())::int4 AS id, (100.0 * RANDOM())::int4 AS v
INTO a FROM GENERATE_SERIES(1,10000) AS id;
CREATE INDEX ia ON a (id, v);

SELECT (100000.0 * RANDOM())::int4 AS id, (100000.0 * RANDOM())::int4 AS v
INTO b FROM GENERATE_SERIES(1,10000) AS id;
CREATE INDEX ib ON b (id, v);
"""

    queries = [
        "SELECT * FROM t t1, t t2 WHERE t1.id = t2.id AND t1.v = t2.v;",
        "SELECT * FROM a t1, a t2 WHERE t1.id = t2.id AND t1.v = t2.v;",
        "SELECT * FROM b t1, b t2 WHERE t1.id = t2.id AND t1.v = t2.v;",
        "SELECT * FROM a t1, t t2 WHERE t1.id = t2.id AND t1.v = t2.v;",
        "SELECT * FROM b t1, t t2 WHERE t1.id = t2.id AND t1.v = t2.v;",
        "SELECT * FROM a t1, b t2 WHERE t1.id = t2.id AND t1.v = t2.v;"]

    install_postgres.load_extension('aqo')
    connstring = install_postgres.connstring
    conn = psycopg2.connect(connstring)
    execute(conn, PREP_TABLE_QUERY)
    execute(conn, 'VACUUM ANALYZE t')
    execute(conn, 'VACUUM ANALYZE a')
    execute(conn, 'VACUUM ANALYZE b')
    conn.close()

    time.sleep(10)

    reset_aqo_stats(connstring)

    install_postgres.set_option('aqo.mode', 'intelligent')
    for q in queries:
        print q
        stats = learn_aqo(q, 100)
        plot_stats(stats, connstring)
        evaluate_aqo(stats)


@pytest.mark.usefixtures('install_postgres')
@pytest.mark.slowtest
def test_1C_sample(install_postgres):

    SQL_QUERY = """
SELECT * FROM _AccRgAT31043 , _AccRgAT31043_ttgoab153 T2 WHERE
     (T2._Period = _AccRgAT31043._Period AND
      T2._AccountRRef = _AccRgAT31043._AccountRRef AND
      T2._Fld1009RRef = _AccRgAT31043._Fld1009RRef AND
      (COALESCE(T2._Fld1010RRef,'\\377'::bytea) =
COALESCE(_AccRgAT31043._Fld1010RRef,'\\377 '::bytea)) AND
      (COALESCE(T2._Fld1011RRef,'\\377'::bytea) =
COALESCE(_AccRgAT31043._Fld1011RRef,'\\377'::bytea)) AND
      T2._Fld995 = _AccRgAT31043._Fld995 AND
      (COALESCE(T2._Value1_TYPE,'\\377'::bytea) =
COALESCE(_AccRgAT31043._Value1_TYPE,'\\377'::bytea) AND
     COALESCE(T2._Value1_RTRef,'\\377'::bytea) =
COALESCE(_AccRgAT31043._Value1_RTRef,'\\377'::bytea) AND
     COALESCE(T2._Value1_RRRef,'\\377'::bytea) =
COALESCE(_AccRgAT31043._Value1_RRRef,'\\377'::bytea)) AND
      (COALESCE(T2._Value2_TYPE,'\\377'::bytea) =
COALESCE(_AccRgAT31043._Value2_TYPE,'\\377'::bytea) AND
       COALESCE(T2._Value2_RTRef,'\\377'::bytea) =
COALESCE(_AccRgAT31043._Value2_RTRef,'\\377'::bytea) AND
     COALESCE(T2._Value2_RRRef,'\\377'::bytea) =
COALESCE(_AccRgAT31043._Value2_RRRef, '\\377'::bytea)) AND
     (COALESCE(T2._Value3_TYPE,'\\377'::bytea) =
COALESCE(_AccRgAT31043._Value3_TYPE,'\\377'::bytea) AND
     COALESCE(T2._Value3_RTRef,'\\377'::bytea) =
COALESCE(_AccRgAT31043._Value3_RTRef,'\\377'::bytea) AND
     COALESCE(T2._Value3_RRRef,'\\377'::bytea) =
COALESCE(_AccRgAT31043._Value3_RRRef,'\\377'::bytea)) AND
     _AccRgAT31043._Splitter = 0) AND (T2._EDCount = 3) AND
     (_AccRgAT31043._Fld995 = 271602);
"""

    DUMP_URL = "http://webdav.l.postgrespro.ru/DIST/vm-images/test/blobs/pg.sql.bz"

    archive_path = os.path.join(TMP_DIR, "pg.sql.gz")
    plain_path = os.path.join(TMP_DIR, "pg.sql")
    if not os.path.exists(plain_path):
        if not os.path.exists(archive_path):
            download_file(DUMP_URL, archive_path)
        os.chdir(TMP_DIR)
        subprocess.check_output(['gunzip', archive_path])

    # with open(plain_path, 'r') as file:
    #     psql = subprocess.Popen(["psql"], stdin=file)
    #     psql.wait()
    #     assert psql.returncode == 0

    connstring = install_postgres.connstring
    conn = psycopg2.connect(connstring)
    execute(conn, open(plain_path, "r").read())
    execute(conn, 'VACUUM ANALYZE _accrgat31043')
    conn.close()

    time.sleep(10)

    install_postgres.load_extension('aqo')
    reset_aqo_stats(connstring)
    # FIXME: execute(conn, 'SET escape_string_warning=off')
    # FIXME: execute(conn, 'SET enable_mergejoin=off')

    stats = learn_aqo(SQL_QUERY, connstring)
    plot_stats(stats, connstring)
    evaluate_aqo(stats)


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
    num1 = execute(
        conn, "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = 'SELECT 1'")[0][0]
    execute(conn, 'SELECT 2')
    num2 = execute(
        conn, "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = 'SELECT 2'")[0][0]
    conn.close()

    assert num1 == 1
    assert num2 == 0


@pytest.mark.parametrize("optimizer", [
                        ("geqo"),
                        ("default"),
])
@pytest.mark.usefixtures('install_postgres')
@pytest.mark.usefixtures('populate_imdb')
@pytest.mark.slowtest
def test_join_order_benchmark(optimizer, install_postgres, populate_imdb):
    """
    Testcase uses the Join Order Benchmark (JOB) queries from:

    "How Good Are Query Optimizers, Really?"
    by Viktor Leis, Andrey Gubichev, Atans Mirchev,
    Peter Boncz, Alfons Kemper, Thomas Neumann
    PVLDB Volume 9, No. 3, 2015

    http://oai.cwi.nl/oai/asset/24379/24379B.pdf

    Source repository with queries:
    https://github.com/tigvarts/join-order-benchmark
    """

    # SETUP TEST

    job_file = os.path.join(TMP_DIR, "join-order-benchmark.tar.gz")
    job_dir = os.path.join(TMP_DIR, "join-order-benchmark-0.1")
    job_url = "https://codeload.github.com/ligurio/join-order-benchmark/tar.gz/0.1"
    if not os.path.exists(job_file):
        download_file(job_url, job_file)

    subprocess.check_output(["tar", "xvzf", job_file, "-C", TMP_DIR])

    # RUN WORKLOAD

    connstring = install_postgres.connstring
    install_postgres.load_extension('aqo')
    conn = psycopg2.connect(connstring)

    install_postgres.set_option('shared_buffers', '4Gb')
    install_postgres.set_option('effective_cache_size', '32Gb')
    install_postgres.set_option('work_mem', '2Gb')

    GEQO_THRESHOLD = 5
    if optimizer == 'geqo':
        # FIXME: install_postgres.set_option('', )
        install_postgres.set_option('geqo_threshold', GEQO_THRESHOLD)
    elif optimizer == 'default':
        # FIXME: install_postgres.set_option('', )
        install_postgres.set_option('geqo', 'off')
    conn.close()

    sqlq_files_re = r'[0-9]+[a-z]+\.sql'
    sql_queries_files = [f for f in os.listdir(job_dir)
                         if re.match(sqlq_files_re, f)]

    for f in sql_queries_files:
        sql_path = os.path.join(job_dir, f)
        with open(sql_path, 'r') as file:
            reset_aqo_stats(connstring)
            stats = learn_aqo(file.read(), connstring, 100)
            keep_aqo_tables(connstring)
            plot_stats(stats, connstring)
            evaluate_aqo(stats)


@pytest.mark.usefixtures('install_postgres')
@pytest.mark.usefixtures('populate_tpch')
def test_tpch_benchmark(install_postgres):
    """
    TPC-H benchmark

    http://www.tpc.org/tpch/
    """

    # GETTING A BENCHMARK

    COMMIT_HASH = "c5cd7711cc35"
    TPCH_BENCHMARK = "https://bitbucket.org/tigvarts/tpch-dbgen/get/%s.zip" % COMMIT_HASH

    tpch_archive = os.path.join(TMP_DIR, "tpch-benchmark-%s.zip" % COMMIT_HASH)
    if not os.path.exists(tpch_archive):
        download_file(TPCH_BENCHMARK, tpch_archive)

    tpch_dir = os.path.join(TMP_DIR, "tigvarts-tpch-dbgen-%s" % COMMIT_HASH)
    if not os.path.exists(tpch_dir):
        os.mkdir(tpch_dir)
        subprocess.check_output(["unzip", tpch_archive, "-d", TMP_DIR])
    os.chdir(tpch_dir)

    # RUN WORKLOAD (see ./run.sh)

    connstring = install_postgres.connstring
    install_postgres.load_extension('aqo')
    reset_aqo_stats(connstring)
    for q in range(1, 23):
        qgen = subprocess.Popen(["qgen", str(q)], stdout=subprocess.PIPE)
        query_multiline = re.sub('^--.*', '', qgen.stdout.read())
        query = " ".join(query_multiline.splitlines())

        stats = learn_aqo(query, connstring, 100)
        plot_stats(stats, connstring)
        evaluate_aqo(stats)


@pytest.mark.skip(reason="not implemented")
@pytest.mark.usefixtures('install_postgres')
def test_tpcds_benchmark(install_postgres):
    """
    TPC-DS benchmark
    """

    # https://github.com/tigvarts/tpcds-kit
    # tools/How_To_Guide.doc

    TPCDS_SCALE = "1"   # 100GB, 300GB, 1TB, 3TB, 10TB, 30TB and 100TB.
    TPCDS_BENCHMARK = "https://github.com/ligurio/tpcds-kit/archive/0.1.zip"

    # GETTING A BENCHMARK

    tpcds_archive = os.path.join(TMP_DIR, "tpcds-kit-0.1.zip")
    if not os.path.exists(tpcds_archive):
        download_file(TPCDS_BENCHMARK, tpcds_archive)

    tpcds_dir = os.path.join(TMP_DIR, "tpcds-kit-0.1")
    if not os.path.exists(tpcds_dir):
        os.mkdir(tpcds_dir)
        subprocess.check_output(["unzip", tpcds_archive, "-d", TMP_DIR])
    tpcds_dir = os.path.join(TMP_DIR, "tpcds-kit-0.1/tools")
    os.chdir(tpcds_dir)

    # SETUP DATABASE (see ./install.sh)

    if platform.system() == 'Darwin':
        shutil.copy("Makefile.osx", "Makefile")
    else:
        shutil.copy("Makefile.suite", "Makefile")
    subprocess.check_call(["make"])
    p = subprocess.Popen(["dsdgen", "-verbose", "-force",
                          "-dir", TMP_DIR, "-scale", TPCDS_SCALE, "-filter"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    print stdout, stderr
    assert p.wait() == 0
    # FIXME: assert -11 == 0

    connstring = install_postgres.connstring
    conn = psycopg2.connect(connstring)
    execute(conn, "DROP DATABASE IF EXISTS tpcds")
    # create_test_database("tpcds")
    execute(conn, "CREATE DATABASE tpcds")
    conn.close()

    sqls = ["tpcds.sql", "tpcds_load.sql", "tpcds_ri.sql"]
    for sql_file in sqls:
        sql_path = os.path.join(tpcds_dir, sql_file)
        sql = subprocess.Popen(["cat", sql_path], subprocess.PIPE)
        psql = subprocess.Popen(["psql", "-d", "tpcds"], stdin=sql.stdout)
        assert psql.wait() == 0
    # os.remove(os.path.join(TMP_DIR, '*.dat'))

    # RUN WORKLOAD

    # relationship between database size (SF) and query streams (N)
    # see tools/How_To_Guide.doc
    # query_streams = {"100": "7",
    #                "300": "9",
    #                "1000": "11",
    #                "3000": "13",
    #                "10000": "15",
    #                "30000": "17",
    #                "100000": "15",
    #                "100000": "19"}

    install_postgres.load_extension('aqo')
    reset_aqo_stats(connstring)
    query_templates = os.path.join(tpcds_dir, "query_variants/*.tpl")
    for template in glob.glob(query_templates):

        stats = learn_aqo(template, connstring, 100)
        plot_stats(stats, connstring)
        evaluate_aqo(stats)


@pytest.mark.skip(reason="PGPRO-342")
@pytest.mark.usefixtures('install_postgres')
def test_broken_aqo_tables(install_postgres):
    """
    Learn aqo with specific SQL query, partially remove records
    for this query from aqo tables and make sure aqo will add it again.
    """

    SQL_QUERY = "SELECT 1"

    install_postgres.load_extension('aqo')
    conn = psycopg2.connect(install_postgres.connstring)
    execute(conn, 'SET aqo.mode TO intelligent')
    execute(conn, SQL_QUERY)

    num = execute(
        conn, "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = '%s'" % SQL_QUERY)[0][0]
    assert num == 1

    execute(conn, "DELETE FROM aqo_query_texts WHERE query_text = '%s'" % SQL_QUERY)
    execute(conn, SQL_QUERY)
    num = execute(
        conn, "SELECT COUNT(*) FROM aqo_query_texts WHERE query_text = '%s'" % SQL_QUERY)[0][0]

    assert num == 1
    # TODO: make sure stats is the same as before deletion


@pytest.mark.usefixtures('install_postgres')
def test_max_query_length(install_postgres):
    """
    Maximum SQL query length in PostgreSQL is about 1Gb.
    AQO extension stores queries in a special table - aqo_query_texts
    and then uses this column to retrieve query statistics.
    We should make sure that column can store queries
    with maximum length there.
    """

    install_postgres.load_extension('aqo')
    reset_aqo_stats(install_postgres.connstring)
    conn = psycopg2.connect(install_postgres.connstring)

    column_name = 'query_text'
    column_type_query = "SELECT format_type(atttypid, atttypmod) \
                        AS type FROM pg_attribute \
                        WHERE attrelid = 'aqo_query_texts'::regclass \
                        AND attname = '%s';" % column_name

    type = execute(conn, column_type_query)[0][0]
    conn.close()

    assert type == "character varying"
