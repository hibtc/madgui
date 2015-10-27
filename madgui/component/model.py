"""
Models encapsulate metadata for accelerator machines.

For more information about models, see :class:`Model`.
"""


__all__ = [
    'Model',
]


class Model(object):

    """
    A model is a configuration of an accelerator machine. This class is only
    a static utility for model definitions and not meant to be instanciated.
    """

    # current version of model API
    API_VERSION = 1

    def __init__(self):
        raise NotImplementedError("Models are POD only!")

    @classmethod
    def check_compatibility(cls, data):
        """
        Check a model definition for compatibility.

        :param dict data: a model definition to be tested
        :raises ValueError: if the model definition is incompatible
        """
        model_api = data.get('api_version', 'undefined')
        if model_api != cls.API_VERSION:
            raise ValueError(("Incompatible model API version: {!r},\n"
                              "              Required version: {!r}")
                             .format(model_api, cls.API_VERSION))

    @classmethod
    def init(cls, madx, utool, repo, data):
        """Load model in MAD-X interpreter."""
        cls.check_compatibility(data)
        for file in data['init-files']:
            with repo.get(file).filename() as fpath:
                madx.call(fpath)

    @classmethod
    def load(cls, utool, repo, filename):
        """Load model data from file."""
        data = repo.yaml(filename, encoding='utf-8')
        cls.check_compatibility(data)
        cls._load_params(data, utool, repo, 'beam')
        cls._load_params(data, utool, repo, 'twiss')
        return data

    @classmethod
    def _load_params(cls, data, utool, repo, name):
        """Load parameter dict from file if necessary and add units."""
        vals = data.get(name, {})
        if isinstance(data[name], basestring):
            vals = repo.yaml(vals, encoding='utf-8')
        data[name] = utool.dict_add_unit(vals)

    @classmethod
    def get_seq_model(cls, madx, utool, sequence_name):
        """
        Return a model as good as possible from the last TWISS statement used
        for the given sequence, if available.

        Note that it seems currently not possible to reliably access prior
        TWISS statements and hence the information required to guess the
        model is extracted from the TWISS tables associated with the
        sequences. This means that

            - twiss tables may accidentally be associated with the wrong
              sequence
            - there is no reliable way to tell which parameters were set in
              the twiss command and hence deduce the correct (expected) model
            - you have to make sure the twiss range starts with a zero-width
              element (e.g. MARKER), otherwise TWISS parameters at the start
              of the range can not be reliably extrapolated

        The returned model should be seen as a first guess/approximation. Some
        fields may be empty if they cannot reliably be determined.

        :raises RuntimeError: if the sequence is undefined
        """
        try:
            sequence = madx.sequences[sequence_name]
        except KeyError:
            raise RuntimeError("The sequence is not defined.")
        try:
            beam = sequence.beam
        except RuntimeError:
            beam = {}
        try:
            range, twiss = cls._get_twiss(madx, utool, sequence)
        except RuntimeError:
            range = (sequence_name+'$start', sequence_name+'$end')
            twiss = {}
        return {
            'api_version': 1,
            'init-files': [],
            'sequence': sequence_name,
            'range': range,
            'beam': utool.dict_add_unit(beam),
            'twiss': utool.dict_add_unit(twiss),
        }

    @classmethod
    def _get_twiss(self, madx, utool, sequence):
        """
        Try to determine (range, twiss) from the MAD-X state.

        :raises RuntimeError: if unable to make a useful guess
        """
        table = sequence.twiss_table        # raises RuntimeError
        try:
            first, last = table.range
        except ValueError:
            raise RuntimeError("TWISS table inaccessible or nonsensical.")
        if first not in sequence.elements or last not in sequence.elements:
            raise RuntimeError("The TWISS table appears to belong to a different sequence.")
        # TODO: this inefficiently copies over the whole table over the pipe
        # rather than just the first row.
        mandatory_fields = {'betx', 'bety', 'alfx', 'alfy'}
        twiss = {
            key: data[0]
            for key, data in table.items()
            if data[0] != 0 or key in mandatory_fields
        }
        return (first, last), twiss
