import json
import matplotlib.pyplot as plot
import numpy
import psycopg2
import pytest
import re
from helpers.sql_helpers import execute
from helpers.sql_helpers import pg_set_option

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

    plot.axvline(AQO_AUTO_TUNING_MAX_ITERATIONS, label='auto_tuning_max_iterations', color='k')
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

    plot.axvline(AQO_AUTO_TUNING_MAX_ITERATIONS, label='auto_tuning_max_iterations', color='k')
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
