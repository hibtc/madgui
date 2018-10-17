from madgui.qt import QtCore
from madgui.core.app import init_app
from madgui.core.session import Session
from madgui.core.config import load as load_config
from madgui.model.orm import (
    analyze, load_yaml, load_record_file, join_record_files)


def main(model_file, twiss_file, spec_file, *record_files):
    """
    Usage:
        analysis MODEL TWISS PARAMS RECORDS...

    MODEL must be the path of the model/sequence file to initialize MAD-X.

    TWISS is a YAML file that contains the initial twiss parameters.

    PARAMS is a YAML file describing the machine errors to be considered.

    RECORDS is a list of record YAML files that were dumped by madgui's ORM
    dialog.
    """
    app = QtCore.QCoreApplication([])
    init_app(app)

    config = load_config(isolated=True)
    with Session(config) as session:
        session.load_model(
            session.find_model(model_file),
            stdout=False,
            command_log=lambda text: print("X:>", text))
        madx = session.model().madx
        return analyze(madx, load_yaml(twiss_file), join_record_files([
            load_record_file(filename)
            for filename in record_files
        ]), load_yaml(spec_file)['analysis'])


if __name__ == '__main__':
    import sys
    sys.exit(main(*sys.argv[1:]))
