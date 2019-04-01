"""
Utility functions to load numpy tables from files.
"""

__all__ = [
    'read_tfsfile',
    'read_table',
]

from os.path import abspath

import numpy as np

from madgui.util.unit import from_config, from_ui


TFS_READER = None


def read_tfsfile(filename):
    """
    Read TFS table.
    """
    from cpymad.madx import Madx
    global TFS_READER
    if not TFS_READER:
        TFS_READER = Madx()
    TFS_READER.command.readmytable(file=abspath(filename), table='user')
    return TFS_READER.get_table('user')


def read_table(filename):
    """
    Read a data file that defines the column names and units in a comment.

    Simple example file:

        # s[mm] env[mm] envy[mm]
        0       1       1
        1       2       1
        2       1       2

    For which this function returns a dictionary:

        's'     -> np.array([0, 1000, 2000])
        'envx'  -> np.array([1000, 2000, 1000])
        'envy'  -> np.array([1000, 1000, 2000])
    """
    with open(filename) as f:
        titles = _parse_header(f)
    columns = map(_parse_column_title, titles)
    data = np.genfromtxt(filename, dtype=None, encoding='utf-8')
    return {
        name: from_ui(name, _add_unit(data[col], unit))
        for col, (name, unit) in zip(data.dtype.names, columns)
    }


def _parse_header(lines, comment='#'):
    # TODO: make safe against different formatting
    header = None
    for line in lines:
        if line and line[0] in comment:
            if line[1:].strip():
                header = line[1:]
        elif line.strip():
            n_cols = len(line.split())
            titles = header.strip().split()
            if header and n_cols == len(titles):
                return titles
            return None


def _parse_column_title(title):
    parts = title.strip().split('[', 1)
    if len(parts) == 2 and parts[1][-1] == ']':
        name, unit = parts
        unit = unit[:-1].strip()
    else:
        parts = title.split('/', 1)
        if len(parts) == 1:
            return title, None
        name, unit = parts
    return name.strip(), unit.strip()


def _add_unit(data, unit):
    # TODO: does not use `name` so far:
    if not unit:
        return data
    parsed_unit = from_config(unit)
    return parsed_unit * data
