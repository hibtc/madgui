from madgui.qt import QtGui
from madgui.core.app import init_app
from madgui.core.session import Session
from madgui.core.config import load as load_config
from madgui.model.orm import analyze, load_yaml, OrbitResponse


def main(model_file, spec_file, *record_files):
    """
    Usage:
        analysis MODEL PARAMS RECORDS...

    MODEL must be the path of the model/sequence file to initialize MAD-X.

    PARAMS is a YAML file describing the machine errors to be considered.

    RECORDS is a list of record YAML files that were dumped by madgui's ORM
    dialog.
    """
    app = QtGui.QApplication([])
    init_app(app)

    config = load_config(isolated=True)
    with Session(config) as session:
        session.load_model(
            model_file,
            stdout=False,
            command_log=lambda text: print("X:>", text))
        model = session.model()
        return analyze(
            model, OrbitResponse.load(model, record_files),
            load_yaml(spec_file)['analysis'])


if __name__ == '__main__':
    import sys
    sys.exit(main(*sys.argv[1:]))
