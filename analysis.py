import numpy as np
import yaml


class ResponseMatrix:

    def __init__(self, sequence, strengths, responses):
        self.sequence = sequence
        self.strengths = strengths
        self.responses = responses


def mean_var(x):
    return np.hstack((
        np.mean(x, axis=0),
        np.var(x, axis=0),
    ))


def diff_var(x1, x0):
    return np.hstack((
        x1[:2] - x0[:2],
        x1[2:]**2 + x0[2:]**2,
    ))


def read_orbit_responses(filename):
    with open(filename) as f:
        data = yaml.safe_load(f.read())
    sequence = data['sequence']
    strengths = data['model']
    records = {
        (monitor, knob): (s, mean_var([
            shot[monitor][:2]
            for shot in record['shots']
        ]))
        for record in data['records']
        for knob, s in (record['optics'] or {None: None}).items()
        for monitor in data['monitors']
    }
    return ResponseMatrix(sequence, strengths, {
        (monitor, knob): diff_var(orbit, base) / (strength - strengths[knob])
        for (monitor, knob), (strength, orbit) in records.items()
        if knob
        for _, base in [records[monitor, None]]
    })


def join_response_matrix(orbit_responses):
    mats = iter(orbit_responses)
    acc = next(mats)
    for mat in mats:
        assert acc.sequence == mat.sequence
        assert acc.strengths == mat.strengths
        acc.responses.update(mat.responses)
    return acc


def analyze(measured, modelled, params):
    pass
