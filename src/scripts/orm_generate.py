#! /usr/bin/env python3
from unittest import mock
from contextlib import ExitStack
import time

from madgui.core.app import init_app
from madgui.core.session import Session
from madgui.core.config import load as load_config
from madgui.online.procedure import Corrector, ProcBot

import madgui.util.yaml as yaml
from madgui.model.orm import create_errors_from_spec


def main(model_file, spec_file, record_file):
    """
    Usage:
        analysis MODEL PARAMS RECORDS

    MODEL must be the path of the model/sequence file to initialize MAD-X.

    PARAMS is a YAML file with arguments for the "measurement" procedure, it
        must contain at least a list of `monitors` and `optics` and should
        contain keys for errors to be inserted: `knobs`, `ealign`, `efcomp`

    RECORDS is the name of the YAML output file where
    """
    init_app([], gui=False)

    config = load_config(isolated=True)
    with ExitStack() as stack:
        setup_args = yaml.load_file(spec_file)['procedure']
        session = stack.enter_context(Session(config))
        session.control._settings.update({
            'shot_interval': 0.001,
            'jitter': setup_args.get('jitter', True),
            'auto_params': False,
            'auto_sd': True,
        })
        session.load_model(
            model_file,
            stdout=False,
            command_log=lambda text: print("X:>", text))
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
        errors = create_errors_from_spec(setup_args['errors'])
        for error in errors:
            stack.enter_context(error.vary(model))
        model.twiss.invalidate()

        corrector.set_optics_delta(
            setup_args.get('optics_deltas', {}),
            setup_args.get('default_delta', 1e-4))
        corrector.open_export(record_file)

        widget = mock.Mock()
        procbot = ProcBot(widget, corrector)

        num_mons = len(setup_args['monitors'])
        num_optics = len(setup_args['optics']) + 1
        if setup_args.get('jitter', True):
            num_ignore = setup_args.get('num_ignore', 1)
            num_shots = setup_args.get('num_shots', 5)
        else:
            num_ignore = 0
            num_shots = 1

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
