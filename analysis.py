import numpy as np
import yaml

from cpymad.madx import Madx

from orm import NumericalORM
from errors import Param, Ealign, Efcomp


def load_yaml(filename):
    """Load yaml document from filename."""
    with open(filename) as f:
        return yaml.safe_load(f)


class ResponseMatrix:

    def __init__(self, sequence, strengths,
                 monitors, steerers, knobs,
                 responses):
        self.sequence = sequence
        self.strengths = strengths
        self.monitors = monitors
        self.steerers = steerers
        self.knobs = knobs
        self.responses = responses


class ParamSpec:

    def __init__(self, monitor_errors, steerer_errors, params, stddev):
        self.monitor_errors = monitor_errors
        self.steerer_errors = steerer_errors
        self.params = params
        self.stddev = stddev


def mean_var(x):
    """Return the mean and variance of ``x`` along its 0-axis."""
    return np.hstack((
        np.mean(x, axis=0),
        np.var(x, axis=0, ddof=1),
    ))


def diff_var(x1, x0):
    """Given two arrays ``[x, y, var(x), var(y)]``, return the difference
    ``[x1-x0, y1-y0, var(x1-x0), var(y1-y0)]``."""
    return np.hstack((
        x1[:2] - x0[:2],
        # FIXME…
        x1[2:] + x0[2:],
    ))


def load_record_file(filename):
    data = load_yaml(filename)
    sequence = data['sequence']
    strengths = data['model']
    monitors = data['monitors']
    steerers = data['steeerers']
    knobs = dict(zip(data['knobs'], steerers))
    records = {
        (monitor, knob): (s, mean_var([
            shot[monitor][:2]
            for shot in record['shots']
        ]))
        for record in data['records']
        for knob, s in (record['optics'] or {None: None}).items()
        for monitor in data['monitors']
    }
    return ResponseMatrix(sequence, strengths, monitors, steerers, knobs, {
        (monitor, knob): diff_var(orbit, base) / (strength - strengths[knob])
        for (monitor, knob), (strength, orbit) in records.items()
        if knob
        for _, base in [records[monitor, None]]
    })


def join_record_files(orbit_responses):
    mats = iter(orbit_responses)
    acc = next(mats)
    acc.monitors = set(acc.monitors)
    acc.steerers = set(acc.steerers)
    acc.knobs = acc.knobs.copy()
    for mat in mats:
        assert acc.sequence == mat.sequence
        assert acc.strengths == mat.strengths
        acc.responses.update(mat.responses)
        acc.monitors.update(mat.monitors)
        acc.steerers.update(mat.steerers)
        acc.knobs.update(mat.knobs)
    return acc


def load_param_spec(filename):
    # TODO: EALIGN, tilt, FINT, FINTX, L, AT, …
    spec = load_yaml(filename)
    return ParamSpec(
        spec['monitor_errors'],
        spec['steerer_errors'], [
            Param(knob)
            for knob in spec.get('knobs', ())
        ] + [
            Ealign(**s)
            for s in spec.get('ealign', ())
        ] + [
            Efcomp(**s)
            for s in spec.get('efcomp', ())
        ]
    )


def analyze(madx, twiss_args, measured, param_spec):
    madx.globals.update(measured.strengths)
    elems    = madx.sequences[measured.sequence].elements
    monitors = sorted(measured.steerers, key=elems.index)
    steerers = sorted(measured.monitors, key=elems.index)
    knobs    = [measured.knobs[elem] for elem in steerers]
    numerics = NumericalORM(
        madx, measured.sequence, twiss_args,
        monitors=monitors, steerers=steerers,
        knobs=knobs)
    numerics.set_operating_point()
    measured_orm = np.vstack([
        np.hstack([
            measured.responses.get((monitor, knob))[:2]
            for monitor in monitors
        ])
        for knob in knobs
    ])
    stddev = np.hstack([
        measured.responses.get((monitor, knob))[2:]
        for monitor in monitors
    ]).T if param_spec.stddev else 1
    results, chisq = numerics.fit_model(
        measured_orm, param_spec.params,
        monitor_errors=param_spec.monitor_errors,
        steerer_errors=param_spec.steerer_errors,
        stddev=stddev)
    print(results)
    print(chisq)


def main(model_file, twiss_file, spec_file, *record_files):
    """
    Usage:
        analysis MODEL TWISS PARAMS RECORDS...

    MODEL must be the path of the model/sequence file to initialize MAD-X.

    TWISS is a YAML file that contains the initial twiss parameters.

    PARAMS is a YAML file describing the machine errors to be considered.

    RECORDS is a list of record YAML files that were dumped by madgui's ORM
    dialog.
    """
    madx = Madx()
    madx.call(model_file)
    return analyze(madx, load_yaml(twiss_file), join_record_files([
        load_record_file(filename)
        for filename in record_files
    ], load_param_spec(spec_file)))


if __name__ == '__main__':
    import sys
    sys.exit(main(*sys.argv[1:]))
