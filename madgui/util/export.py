import os
import re

import madgui.util.yaml as yaml


def import_params(filename, data_key=None):
    with open(filename, 'rt') as f:
        # Since JSON is a subset of YAML there is no need to invoke a
        # different parser (unless we want to validate the file):
        data = yaml.safe_load(f)
    if data_key:
        data = data[data_key]
    return data


def export_params(filename, data, data_key=None):
    """Export parameters to .YAML/.STR file."""
    if data_key:
        data = {data_key: data}
    _, ext = os.path.splitext(filename.lower())
    if ext in ('.yml', '.yaml'):
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
    return dict(_parse_str_line(line)
                for line in map(str.strip, lines)
                if line and not line.startswith('#'))

RE_ASSIGN = re.compile(r'^([a-z_][a-z0-9_]*)\s*:?=\s*(.*);$', re.IGNORECASE)


def _parse_str_line(line):
    m = RE_ASSIGN.match(line)
    if not m:
        raise ValueError("not an assignment: {!r}".format(line))
    k, v = m.groups()
    try:
        return k, float(v)
    except ValueError:
        return k, v
