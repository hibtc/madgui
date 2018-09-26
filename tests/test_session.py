# This test requires that you have cloned hit_models to the root directory!

import pytest

from madgui.qt import QtCore
from madgui.core.app import init_app
from madgui.core.session import Session


options = {
    '--config': None,
}


@pytest.fixture(scope="session")
def app():
    # NOTE: this fixture (in particular the sys.excepthook patch) is required
    # to not segfault the tests!
    app = QtCore.QCoreApplication([])
    init_app(app)
    return app


def test_empty_session(app):
    with Session(options):
        pass


def test_session_load_model(app):
    with Session(options) as session:
        path = session.find_model('hit_models/hht3')
        assert path.endswith('hht3.cpymad.yml')
        session.load_model(path)
        model = session.model()
        assert model.seq_name == 'hht3'


def test_session_destroyed(app):
    with Session(options) as session:
        session.load_model(session.find_model('hit_models/hht3'))
        model = session.model()
    assert session.model() is None
    assert model.madx is None
