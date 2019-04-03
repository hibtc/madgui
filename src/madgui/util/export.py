"""
Functions for serializing parameter data to files.
"""

__all__ = [
    'import_params',
    'export_params',
    'read_str_file',
]

import os
import re

import madgui.util.yaml as yaml


def import_params(filename, data_key=None):
    _, ext = os.path.splitext(filename.lower())
    if ext in ('.yml', '.yaml'):
        data = yaml.load_file(filename)
        if data_key:
            data = data[data_key]
    elif ext == '.str':
        data = read_str_file(filename)
        if data is None:
            raise ValueError(
                "SyntaxError in {!r}. Not the simplest of .str files?"
                .format(filename))
    else:
        raise ValueError(
            "Unknown file format for import: {!r}".format(filename))
    return data


def export_params(filename, data, data_key=None):
    """Export parameters to .YAML/.STR file."""
    _, ext = os.path.splitext(filename.lower())
    if ext in ('.yml', '.yaml'):
        if data_key:
            data = {data_key: data}
        text = yaml.safe_dump(data, default_flow_style=False)
    elif ext == '.str':
        text = ''.join([
            '{} = {!r};\n'.format(k, v)
            for k, v in data.items()
        ])
    else:
        raise ValueError(
            "Unknown file format for export: {!r}".format(filename))
    with open(filename, 'wt') as f:
        f.write(text)


def read_str_file(filename):
    """Read .str file, return as dict."""
    with open(filename) as f:
        try:
            return _parse_str_lines(f)
        except (ValueError, AttributeError):
            return None


def _parse_str_lines(lines):
    return dict(
        _parse_str_line(line)
        for line in map(str.strip, lines)
        if line and not line.startswith(('#', '!')))


RE_ASSIGN = re.compile(r'^([a-z_][a-z0-9_]*)\s*:?=\s*(.*);$', re.IGNORECASE)


def _parse_str_line(line):
    m = RE_ASSIGN.match(line)
    if not m:
        raise ValueError("not an assignment: {!r}".format(line))
    k, v = m.groups()
    return k, float(v)
