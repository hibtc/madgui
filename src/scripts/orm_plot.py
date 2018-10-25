import numpy as np
import matplotlib.pyplot as plt

from madgui.qt import QtGui
from madgui.core.app import init_app
from madgui.core.session import Session
from madgui.core.config import load as load_config
from madgui.model.orm import (
    load_yaml, load_record_file, join_record_files, NumericalORM)


def get_orms(madx, twiss_args, measured, fit_args):
    madx.globals.update(measured.strengths)
    elems = madx.sequence[measured.sequence].expanded_elements
    monitors = sorted(measured.monitors, key=elems.index)
    steerers = sorted(measured.steerers, key=elems.index)
    knobs = [measured.knobs[elem] for elem in steerers]
    numerics = NumericalORM(
        madx, measured.sequence, twiss_args,
        monitors=monitors, steerers=steerers,
        knobs=knobs)
    numerics.set_operating_point()
    print("\n".join("{}: {}".format(m, k) for m, k in sorted([
        (monitor, knob)
        for knob in knobs
        for monitor in monitors
        if (monitor.lower(), knob.lower()) not in measured.responses
    ])))

    no_response = (np.array([0.0, 0.0]),    # delta_orbit
                   1e5,                     # delta_param
                   np.array([1.0, 1.0]))    # mean_error    TODO use base error
    measured_orm = np.vstack([
        np.hstack([
            delta_orbit / delta_param
            for monitor in monitors
            for delta_orbit, delta_param, _ in [
                    measured.responses.get(
                        (monitor.lower(), knob.lower()), no_response)]
        ])
        for knob in knobs
    ]).T

    stddev = np.vstack([
        np.hstack([
            np.sqrt(mean_error) / delta_param
            for monitor in monitors
            for _, delta_param, mean_error in [
                    measured.responses.get(
                        (monitor.lower(), knob.lower()), no_response)]
        ])
        for knob in knobs
    ]).T if fit_args.get('stddev', False) else 1

    return monitors, steerers, measured_orm, numerics.base_orm, stddev


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
            session.find_model(model_file),
            stdout=False,
            command_log=lambda text: print("X:>", text))
        model = session.model()

        monitors, steerers, measured_orm, model_orm, stddev = get_orms(
            model.madx, model.twiss_args, join_record_files([
                load_record_file(filename, model)
                for filename in record_files
            ]), load_yaml(spec_file)['analysis'])

        setup_args = load_yaml(spec_file)['analysis']
        monitor_subset = setup_args.get('plot_monitors', monitors)
        steerer_subset = setup_args.get('plot_steerers', steerers)
        xpos = [model.elements[elem].position for elem in steerers]

        shape = (len(monitors), 2, len(steerers))
        measured_orm = measured_orm.reshape(shape)
        model_orm = model_orm.reshape(shape)
        stddev = stddev.reshape(shape)

        for i, monitor in enumerate(monitors):
            if monitor not in monitor_subset:
                continue

            for j, ax in enumerate("xy"):
                axes = plt.subplot(1, 2, 1+j)
                plt.title(ax)
                plt.xlabel(r"steerer position [m]")
                if ax == 'x':
                    plt.ylabel(r"orbit response $\Delta x/\Delta \phi$ [mm/mrad]")
                else:
                    axes.yaxis.tick_right()

                plt.errorbar(
                    xpos,
                    measured_orm[i, j, :].flatten(),
                    stddev[i, j, :].flatten(),
                    label=ax + " measured")

                plt.plot(
                    xpos,
                    model_orm[i, j, :].flatten(),
                    label=ax + " model")

                plt.legend()

            plt.suptitle(monitor)

            plt.show()
            plt.cla()

        xpos = [model.elements[elem].position for elem in monitors]
        for i, steerer in enumerate(steerers):
            if steerer not in steerer_subset:
                continue

            for j, ax in enumerate("xy"):
                axes = plt.subplot(1, 2, 1+j)
                plt.title(ax)
                plt.xlabel(r"monitor position [m]")
                if ax == 'x':
                    plt.ylabel(r"orbit response $\Delta x/\Delta \phi$ [mm/mrad]")
                else:
                    axes.yaxis.tick_right()

                plt.errorbar(
                    xpos,
                    measured_orm[:, j, i].flatten(),
                    stddev[:, j, i].flatten(),
                    label=ax + " measured")

                plt.plot(
                    xpos,
                    model_orm[:, j, i].flatten(),
                    label=ax + " model")

                plt.legend()

            plt.suptitle(steerer)

            plt.show()
            plt.cla()


if __name__ == '__main__':
    import sys
    sys.exit(main(*sys.argv[1:]))
