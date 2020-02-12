# This test requires that you have cloned hit_models to the root directory!

from unittest import mock

from madgui.model.madx import Model


def test_load_model():
    model = Model.load_file(
        'sample_model/sample.cpymad.yml',
        undo_stack=mock.Mock())
    assert model.seq_name == 'beamline1'


def test_load_model_without_def():
    model = Model.load_file(
        'sample_model/sample.cpymad.yml',
        undo_stack=mock.Mock())
    assert model.seq_name == 'beamline1'
