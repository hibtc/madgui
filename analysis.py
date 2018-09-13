import numpy as np
import yaml

from cpymad.madx import Madx

from orm import NumericalORM


def load_yaml(filename):
    """Load yaml document from filename."""
    with open(filename) as f:
        return yaml.safe_load(f)


class ResponseMatrix:

    def __init__(self, sequence, strengths, monitors, steerers, responses):
        self.sequence = sequence
        self.strengths = strengths
        self.monitors = monitors
        self.steerers = steerers
        self.responses = responses


def mean_var(x):
    """Return the mean and variance of ``x`` along its 0-axis."""
    return np.hstack((
        np.mean(x, axis=0),
        np.var(x, axis=0),
    ))


def diff_var(x1, x0):
    """Given two arrays ``[x, y, var(x), var(y)]``, return the difference
    ``[x1-x0, y1-y0, var(x1-x0), var(y1-y0)]``."""
    return np.hstack((
        x1[:2] - x0[:2],
        x1[2:]**2 + x0[2:]**2,
    ))


def load_record_file(filename):
    data = load_yaml(filename)
    sequence = data['sequence']
    strengths = data['model']
    monitors = data['monitors']
    steerers = data['steeerers']
    records = {
        (monitor, knob): (s, mean_var([
            shot[monitor][:2]
            for shot in record['shots']
        ]))
        for record in data['records']
        for knob, s in (record['optics'] or {None: None}).items()
        for monitor in data['monitors']
    }
    return ResponseMatrix(sequence, strengths, monitors, steerers, {
        (monitor, knob): diff_var(orbit, base) / (strength - strengths[knob])
        for (monitor, knob), (strength, orbit) in records.items()
        if knob
        for _, base in [records[monitor, None]]
    })


def join_record_files(orbit_responses):
    mats = iter(orbit_responses)
    acc = next(mats)
    # FIXME: data['steerers'] currently has the wrong format…
    acc.monitors = set(acc.monitors)
    acc.steerers = set(acc.steerers)
    for mat in mats:
        assert acc.sequence == mat.sequence
        assert acc.strengths == mat.strengths
        acc.responses.update(mat.responses)
        acc.monitors.update(acc.monitors)
        acc.steerers.update(acc.steerers)
    return acc


def load_param_defs(filename):
    pass


def analyze(madx, twiss_args, measured, params):
    madx.globals.update(measured.strengths)
    elems = madx.sequences[measured.sequence].elements
    monitors = sorted(measured.steerers, key=elems.index)
    steerers = sorted(measured.monitors, key=elems.index)
    numerics = NumericalORM(
        madx, measured.sequence, twiss_args,
        monitors=monitors, steerers=steerers,
        knobs=[measured.knobs[elem] for elem in steerers])
    # FIXME: steerer should be the knob
    # FIXME: array layout?
    measured_orm = np.array([
        [measured.responses.get((monitor, steerer))
         for monitor in monitors]
        for steerer in steerers
    ])
    results, chisq = numerics.fit_model(measured_orm, params)
    print(results)
    print(chisq)


def main(model_file, twiss_file, param_defs, *record_files):
    """
    Usage:
        analysis MODEL TWISS RECORDS...

    MODEL must be the path of the model/sequence file to initialize MAD-X.

    TWISS is a YAML file that contains the initial twiss parameters.

    RECORDS is a list of record YAML files that were dumped by madgui's ORM
    dialog.
    """
    madx = Madx()
    madx.call(model_file)
    return analyze(madx, load_yaml(twiss_file), join_record_files([
        load_record_file(filename)
        for filename in record_files
    ], load_param_defs(param_defs)))


if __name__ == '__main__':
    import sys
    sys.exit(main(*sys.argv[1:]))
