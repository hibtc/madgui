# This test requires that you have
# - cloned hit_models (to the root directory)
# - installed hit_acs (pip install)

from unittest import mock
import os

import pytest

from madgui.core.app import init_app
from madgui.core.session import Session
from madgui.core.config import load as load_config
from madgui.online.procedure import Corrector, ProcBot


@pytest.fixture(scope="session")
def app():
    # NOTE: this fixture (in particular the sys.excepthook patch) is required
    # to not segfault the tests!
    return init_app([], gui=False)


@pytest.yield_fixture
def session(app):
    config = load_config(isolated=True)
    with Session(config) as session:
        session.control._settings.update({
            'shot_interval': 0.001,
            'jitter': True,
            'auto_params': True,
            'auto_sd': True,
        })
        yield session


def test_simple_procedure(session):
    session.load_model('hit_models/hht3')
    session.control.set_backend('hit_acs.plugin:TestACS')
    session.control.connect()

    corrector = Corrector(session)
    assert corrector is not None        # for lack of a better test;) for now


@pytest.fixture
def corrector(session):
    session.load_model('hit_models/hht3')
    session.control.set_backend('hit_acs.plugin:TestACS')
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
    return corrector


@pytest.yield_fixture
def procbot(corrector):
    corrector.set_optics_delta({}, 1e-4)
    corrector.open_export('timeseries.yml')
    assert os.path.exists('timeseries.yml')
    try:
        widget = mock.Mock()
        procbot = ProcBot(widget, corrector)
        procbot.start(1, 2, gui=False)
        assert widget.update_ui.call_count == 1
        yield procbot
    finally:
        os.remove('timeseries.yml')
