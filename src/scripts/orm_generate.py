from unittest import mock
from contextlib import ExitStack
import time

from madgui.qt import QtCore
from madgui.core.app import init_app
from madgui.core.session import Session
from madgui.core.config import load as load_config
from madgui.online.procedure import Corrector, ProcBot

from madgui.model.orm import load_yaml, load_param_spec


def main(model_file, twiss_file, spec_file, record_file):
    """
    Usage:
        analysis MODEL TWISS PARAMS RECORDS

    MODEL must be the path of the model/sequence file to initialize MAD-X.

    TWISS is a YAML file that contains the initial twiss parameters.

    PARAMS is a YAML file with arguments for the "measurement" procedure, it
        must contain at least a list of `monitors` and `optics` and should
        contain keys for errors to be inserted: `knobs`, `ealign`, `efcomp`

    RECORDS is the name of the YAML output file where
    """
    app = QtCore.QCoreApplication([])
    init_app(app)

    config = load_config(isolated=True)
    with ExitStack() as stack:
        twiss_args = load_yaml(twiss_file) if twiss_file else {}
        setup_args = load_yaml(spec_file)
        session = stack.enter_context(Session(config))
        session.control._settings.update({
            'shot_interval': 0.001,
            'jitter': setup_args.get('jitter', True),
            'auto_params': False,
            'auto_sd': True,
        })
        session.load_model(
            session.find_model(model_file),
            stdout=False,
            command_log=lambda text: print("X:>", text))
        session.model().update_twiss_args(twiss_args)
        session.control.set_backend('hit_csys.plugin:TestBackend')
        session.control.connect()
        session.control.write_all()
        corrector = Corrector(session)
        corrector.setup({
            'monitors': setup_args['monitors'],
            'optics': setup_args['optics'],
        })

        # FIXME: this is not yet compatible with general parameter errors. In
        # order to fix this, the hit_csys test backend will have to use an
        # independent model!
        model = session.model()
        errors = load_param_spec(spec_file)
        for error in errors.params:
            stack.enter_context(error.vary(model))
        model.twiss.invalidate()

        corrector.set_optics_delta(
            setup_args.get('optics_deltas', {}),
            setup_args.get('default_delta', 1e-4))
        corrector.open_export(record_file)

        widget = mock.Mock()
        procbot = ProcBot(widget, corrector)

        num_mons = len(setup_args['monitors'])
        num_optics = len(setup_args['optics'])+1
        num_ignore = setup_args.get('num_ignore', 1)
        num_shots = setup_args.get('num_shots', 5)

        procbot.start(num_ignore, num_shots, gui=False)

        total_steps = num_mons * (num_optics+1) * (num_ignore + num_shots)

        i = 0
        while procbot.running and i < 2 * total_steps:
            procbot.poll()
            time.sleep(0.010)
            i += 1

        assert not procbot.running


if __name__ == '__main__':
    import sys
    sys.exit(main(*sys.argv[1:]))
