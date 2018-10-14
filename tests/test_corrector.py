# This test requires that you have
# - cloned hit_models (to the root directory)
# - installed hit_csys (pip install)

from unittest import mock
import os
import time

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


@pytest.yield_fixture
def session(app):
    config = load_config(isolated=True)
    with Session(config) as session:
        session.control._settings.update({
            'jitter_interval': 0.001,
            'jitter': True,
            'auto_params': True,
            'auto_sd': True,
        })
        yield session


def test_simple_procedure(session):
    session.load_model(
        session.find_model('hit_models/hht3'))
    session.control.set_backend('hit_csys.plugin:TestBackend')
    session.control.connect()

    corrector = Corrector(session)
    assert corrector.fit_results is None


def test_procbot(session):
    session.load_model(
        session.find_model('hit_models/hht3'))
    session.control.set_backend('hit_csys.plugin:TestBackend')
    session.control.connect()

    corrector = Corrector(session)
    corrector.setup({
        'monitors': [
            't3dg2g',
            't3dg1g',
            't3df1',
        ],
        'optics':   [
            'ax_g3mw2',
            'ax_g3ms2',
            'ay_g3mw1',
            'ay_g3ms1',
        ],
    })
    num_mons = 3
    num_optics = 5          # 4+1 for base_optics
    num_shots = 2

    corrector.set_optics_delta({}, 1e-4)
    corrector.open_export('timeseries.yml')
    assert os.path.exists('timeseries.yml')

    try:
        widget = mock.Mock()
        procbot = ProcBot(widget, corrector)
        procbot.start(1, num_shots, gui=False)

        assert widget.update_ui.call_count == 1

        i = 0
        while procbot.running and i < 100:
            procbot.poll()
            time.sleep(0.010)
            i += 1

        assert not procbot.running
        assert len(corrector.records) == num_mons * num_optics * num_shots

    finally:
        os.remove('timeseries.yml')
