# This test requires that you have
# - cloned hit_models (to the root directory)
# - installed hit_csys (pip install)

import pytest

from madgui.qt import QtCore
from madgui.core.app import init_app
from madgui.core.session import Session
from madgui.core.config import load as load_config
from madgui.online.procedure import Corrector


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
