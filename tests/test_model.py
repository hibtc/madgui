# This test requires that you have cloned hit_models to the root directory!

from unittest import mock

from madgui.model.madx import Model


def test_load_model():
    model = Model.load_file(
        'hit_models/hht3.cpymad.yml',
        undo_stack=mock.Mock())
    assert model.seq_name == 'hht3'


def test_load_model_without_def():
    model = Model.load_file(
        'hit_models/hht3/run.madx',
        undo_stack=mock.Mock())
    assert model.seq_name == 'hht3'
