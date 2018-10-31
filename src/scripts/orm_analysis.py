#! /usr/bin/env python3
"""
Utility for analyzing on ORM measurements.

Usage:
    ./orm_analysis.py MODEL PARAMS RECORDS...

Arguments:

    MODEL must be the path of the model/sequence file to initialize MAD-X.

    PARAMS is a YAML file describing the machine errors to be considered.

    RECORDS is a list of record YAML files that were dumped by madgui's ORM
    dialog.
"""

from docopt import docopt

from madgui.qt import QtGui
from madgui.core.app import init_app
from madgui.core.session import Session
from madgui.core.config import load as load_config
from madgui.model.orm import analyze, load_yaml, OrbitResponse


def main(args=None):
    opts = docopt(__doc__, args)
    app = QtGui.QApplication([])
    init_app(app)

    model_file = opts['MODEL']
    spec_file = opts['PARAMS']
    record_files = opts['RECORDS']

    config = load_config(isolated=True)
    with Session(config) as session:
        session.load_model(
            model_file,
            stdout=False)
        model = session.model()
        return analyze(
            model, OrbitResponse.load(model, record_files),
            load_yaml(spec_file)['analysis'])


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
