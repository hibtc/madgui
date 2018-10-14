from cpymad.madx import Madx

from madgui.model.orm import (
    analyze, load_yaml, load_record_file, join_record_files, load_param_spec)


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
    madx.call(model_file, True)
    return analyze(madx, load_yaml(twiss_file), join_record_files([
        load_record_file(filename)
        for filename in record_files
    ]), load_param_spec(spec_file))


if __name__ == '__main__':
    import sys
    sys.exit(main(*sys.argv[1:]))
