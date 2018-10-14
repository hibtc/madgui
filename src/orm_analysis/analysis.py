import itertools

import numpy as np
import yaml

from cpymad.madx import Madx

from orm import NumericalORM
from errors import Param, Ealign, Efcomp


class PooledVariance:

    """Data for combining variances."""

    def __init__(self, nvar, size, ddof):
        self.nvar = nvar        # size * var, easier for processing
        self.size = size
        self.ddof = ddof

    @property
    def var(self):
        return self.nvar / self.size


def load_yaml(filename):
    """Load yaml document from filename."""
    with open(filename) as f:
        return yaml.safe_load(f)


class ResponseMatrix:

    def __init__(self, sequence, strengths,
                 monitors, steerers, knobs,
                 responses, variances):
        self.sequence = sequence
        self.strengths = strengths
        self.monitors = monitors
        self.steerers = steerers
        self.knobs = knobs
        self.responses = responses
        self.variances = variances


class ParamSpec:

    def __init__(self, monitor_errors, steerer_errors, params, stddev):
        self.monitor_errors = monitor_errors
        self.steerer_errors = steerer_errors
        self.params = params
        self.stddev = stddev


def load_record_file(filename):
    data = load_yaml(filename)
    sequence = data['sequence']
    strengths = data['model']
    monitors = data['monitors']
    steerers = data['steeerers']
    knobs = dict(zip(data['knobs'], steerers))
    records = {
        (monitor, knob): (s, np.mean([
            shot[monitor][:2]
            for shot in record['shots']
        ], axis=0))
        for record in data['records']
        for knob, s in (record['optics'] or {None: None}).items()
        for monitor in data['monitors']
    }
    varpool = combine_varpools([
        [(monitor, PooledVariance(
            nvar=np.var([
                shot[monitor][:2]
                for shot in record['shots']
            ], axis=0) * len(record['shots']),
            size=len(record['shots']),
            ddof=1))
         for monitor in monitors]
        for record in records
    ])
    return ResponseMatrix(sequence, strengths, monitors, steerers, knobs, {
        (monitor, knob): (orbit - base) / (strength - strengths[knob])
        for (monitor, knob), (strength, orbit) in records.items()
        if knob
        for _, base in [records[monitor, None]]
    }, varpool)


def combine_varpools(varpools):
    return [
        (monitor, PooledVariance(
            nvar=sum([v.nvar for v in variances]),
            size=sum([v.size for v in variances]),
            ddof=sum([v.ddof for v in variances])))
        for monitor, variances in groupby(
                itertools.chain.from_iterable(varpools),
                key=lambda x: x[0])
    ]


def groupby(data, key=None):
    return itertools.groupby(sorted(data, key=key), key=key)


def join_record_files(orbit_responses):
    mats = iter(orbit_responses)
    acc = next(mats)
    acc.monitors = set(acc.monitors)
    acc.steerers = set(acc.steerers)
    acc.knobs = acc.knobs.copy()
    acc.variances = combine_varpools([mat.variances for mat in mats])
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
    elems = madx.sequences[measured.sequence].elements
    monitors = sorted(measured.steerers, key=elems.index)
    steerers = sorted(measured.monitors, key=elems.index)
    knobs = [measured.knobs[elem] for elem in steerers]
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
    varpool = dict(measured.variances)
    stddev = np.hstack([
        varpool.get(monitor)
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
