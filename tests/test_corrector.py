# This test requires that you have
# - cloned hit_models (to the root directory)
# - installed hit_csys (pip install)

from unittest import mock

import pytest

from madgui.qt import QtCore
from madgui.core.app import init_app
from madgui.core.session import Session
from madgui.core.config import load as load_config
from madgui.online.procedure import Corrector, ProcBot


@pytest.fixture(scope="session")
def app():
    # NOTE: this fixture (in particular the sys.excepthook patch) is required
    # to not segfault the tests!
    app = QtCore.QCoreApplication([])
    init_app(app)
    return app


def test_simple_procedure(app):
    config = load_config(isolated=True)
    with Session(config) as session:
        session.load_model(
            session.find_model('hit_models/hht3'))
        session.control.set_backend('hit_csys.plugin:TestBackend')
        session.control.connect()

        corrector = Corrector(session, {'default': {
            'monitors': [],
            'steerers': {'x': [], 'y': []},
            'targets':  {},
            'optics':   [],
        }})
        assert corrector.fit_results is None


def test_procbot(app):
    config = load_config(isolated=True)
    with Session(config) as session:
        session.config.online_control.jitter_interval = 0.010
        session.load_model(
            session.find_model('hit_models/hht3'))
        session.control.set_backend('hit_csys.plugin:TestBackend')
        session.control.connect()

        corrector = Corrector(session, {'default': {
            'monitors': [
                't3dg2g',
                't3dg1g',
                't3df1',
            ],
            'steerers': {
                'x': ['ax_g3mw2', 'ax_g3ms2'],
                'y': ['ay_g3mw1', 'ay_g3ms1'],
            },
            'targets':  {},
            'optics':   ['ax_g3mw2', 'ax_g3ms2', 'ay_g3mw1', 'ay_g3ms1'],
        }})

        widget = mock.Mock()
        procbot = ProcBot(widget, corrector)
        procbot.start(0, 1)

        assert widget.update_ui.call_count == 1
