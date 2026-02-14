import mysql.connector
from os_check import *


DBS = {
    "CBB": mysql.connector.connect(user=USER, password=PASSWORD,
                                host=HOST,
                                database='cbb'),
    "NFL": mysql.connector.connect(user=USER, password=PASSWORD,
                                host=HOST,
                                database='nfl'),
    "news_sources": mysql.connector.connect(user=USER, password=PASSWORD,
                                host=HOST,
                                database='news_sources'),
}


def execute_any_query(database, query, return_rows=True):
    """Executes any query and returns rows for a select, if desired"""
    cursor = database.cursor(buffered=True)
    cursor.execute(query)
    if return_rows:
        rows = fetchall_named(cursor)
        return rows


def insert_replace_data(database, table, values, insert=True, columns=None):
    """Builds and executes an insert or replace query where data contains all
    fields to enter
    Args:
        table (str): the name of the table
        values (list): list of data in the correct column order
        insert (bool): set to False to use REPLACE instead of INSERT
        columns (list): list of all column names to insert
    """
    if columns is not None and len(values) != len(columns):
        raise Exception("Data Length != Specified Columnn Length")
    # need to use single quotes becuase of player name apostrophes
    kword = 'INSERT' if insert else 'REPLACE'
    query = list()
    query.append(kword + ' INTO ' + table)
    if columns is not None:
        query.append('(')
        counter = 0
        for col in columns:
            query.append(col)
            if counter < len(values) - 1:
                query.append(',')
            else:
                query.append(')')
            counter += 1
    query.append(' VALUES(')

    for i in range(len(values)):
        if type(values[i]) == str:
            query.append('"' + values[i] + '"')
        else:
            query.append(str(values[i]))
        if i < len(values) - 1:
            query.append(',')
        else:
            query.append(')')

    # print("".join(query))
    cursor = database.cursor(buffered=True)
    cursor.execute("".join(query))
    database.commit()


def insert_mlb_tweet(database, tweet_id, author_handle, text, url=None, posted_at=None):
    """Insert a tweet into news_sources.mlb_tweets. Uses parameterized query.
    Ignores duplicate tweet_id (INSERT IGNORE).
    """
    cursor = database.cursor(buffered=True)
    cursor.execute(
        "INSERT IGNORE INTO mlb_tweets (tweet_id, author_handle, text, url, posted_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (tweet_id, author_handle, text, url, posted_at),
    )
    database.commit()
    cursor.close()


# TODO test
def update_data(database, table, values, columns, where=None):
    """Builds and executes an update query where values contains all
    fields to enter

    Args:
        table (str): the name of the table
        values (list): list of data in the correct column order
        columns (list): list of all column names to insert
        where (Optional[dict]): dict of where clauses
    """
    if columns is not None and len(values) != len(columns):
        raise Exception("Data Length != Specified Columnn Length")
    # need to use single quotes becuase of player name apostrophes
    col_val_dict = {}
    for i in range(len(values)):
        col_val_dict[columns[i]] = values[i]

    kword = 'UPDATE '
    query = list()
    query.append(kword + table + " SET ")
    query.append(','.join(
        '%s = "%s"' % (k, v) for k, v in col_val_dict.items()))

    if where is not None:
        query.append(' WHERE ' + ' AND '.join(
            '%s = "%s"' % (k, v) for k, v in where.items()))

    cursor = database.cursor(buffered=True)
    cursor.execute("".join(query))
    database.commit()


def select_data(database, table, where=None, orderby=None):
    """Build and executes a SELECT statement. Returns a list of rows,
    where each row is a dictionary with data accessible by column name
    Args:
        table (str): the name of the table
        where (dict): dict of where clauses, in format {"x": y} would append
        "WHERE x = y" to the statement, could be None if the statement does
        not need a where clause
        orderby (str): adds one orderby clause to the statement
    """
    query = list()
    query.append('SELECT * FROM ' + table)

    if where is not None:
        query.append(' WHERE ' + ' AND '.join(
            '%s = "%s"' % (k, v) for k, v in where.items()))

    if orderby is not None:
        query.append('ORDER BY ' + orderby)

    cursor = database.cursor(buffered=True)
    cursor.execute(''.join(query))
    return fetchall_named(cursor)


def delete_row(database, table, where):
    """Delete a row from a database table

    Args:
        table (str): table name
        where (dict): dict of where clauses, in format {"x": y} would append
        "WHERE x = y" to the statement

    """
    query = list()
    query.append('DELETE FROM ' + table)
    query.append(' WHERE ' + ' AND '.join(
        '%s = "%s"' % (k, v) for k, v in where.items()))

    cursor = database.cursor(buffered=True)
    cursor.execute(''.join(query))
    database.commit()


def get_player_by_pos_name_year(database, pos, name, year):
    """Returns the row of a player in the roster_player table at this
    position with this name who played in the year

    Args:
        pos (str):
        name (str):
        year (int):

    """
    query = ('SELECT * FROM roster_player WHERE name = "' + name + '" AND '
                                                                   'position = "' + pos + '" AND years like "%' + str(
        year) + '%"')
    cursor = database.cursor(buffered=True)
    cursor.execute(query)
    return fetchall_named(cursor)


def fetchall_named(cursor):
    """Returns results as a dictionary so data can be accessed by name
    of column instead of by index."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]