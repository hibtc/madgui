from madgui.qt import QtGui
from madgui.core.app import init_app
from madgui.core.session import Session
from madgui.core.config import load as load_config
from madgui.model.orm import (
    load_yaml, load_record_files, get_orms,
    plot_monitor_response, plot_steerer_response)



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

        monitors, steerers, knobs, base_orbit, measured_orm, stddev = get_orms(
            model, load_record_files(record_files),
            load_yaml(spec_file)['analysis'])

        model_orm = model.get_orbit_response_matrix(monitors, knobs)

        setup_args = load_yaml(spec_file)['analysis']
        monitor_subset = setup_args.get('plot_monitors', monitors)
        steerer_subset = setup_args.get('plot_steerers', steerers)

        plot_monitor_response(
            model, monitors, steerers, monitor_subset,
            model_orm, measured_orm, stddev)

        plot_steerer_response(
            model, monitors, steerers, steerer_subset,
            model_orm, measured_orm, stddev)


if __name__ == '__main__':
    import sys
    sys.exit(main(*sys.argv[1:]))
