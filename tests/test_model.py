# This test requires that you have cloned hit_models to the root directory!

from unittest import mock

from madgui.model.madx import Model


def test_load_model():
    model = Model(
        'hit_models/hht3/hht3.cpymad.yml',
        undo_stack=mock.Mock())
    assert model.seq_name == 'hht3'
