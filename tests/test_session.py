# This test requires that you have cloned hit_models to the root directory!

import pytest

from madgui.core.app import init_app
from madgui.core.session import Session


@pytest.fixture(scope="session")
def app():
    # NOTE: this fixture (in particular the sys.excepthook patch) is required
    # to not segfault the tests!
    return init_app([], gui=False)


def test_empty_session(app):
    session = Session()
    session.terminate()


def test_session_load_model(app):
    session = Session()
    path = session.find_model('hit_models/hht3')
    assert path.endswith('hht3.cpymad.yml')
    session.load_model(path)
    model = session.model()
    assert model.seq_name == 'hht3'


def test_session_destroyed(app):
    session = Session()
    session.load_model('hit_models/hht3')
    model = session.model()
    session.terminate()
    assert session.model() is None
    assert model.madx is None
