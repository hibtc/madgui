"""
Models encapsulate metadata for accelerator machines.

For more information about models, see :class:`Model`.
"""

from __future__ import absolute_import

import logging
import os

from cpymad.madx import Madx
from cpymad.util import is_match_param
from cpymad.types import Range
from madgui.resource.file import FileResource


__all__ = [
    'Model',
    'Beam',
    'Sequence',
    'Range',
    'Locator',
]


class Model(object):

    """
    A model is a complete description of an accelerator machine.

    This class is used to bundle all metadata related to an accelerator and
    all its configurations. It takes care of loading the proper MAD-X files
    when needed. Models are conceptually derived from the JMad models, but
    have evolved to a more pythonic and simple API.

    To create a model instance from a model definition file, use the
    ``Model.load`` constructor.

    All instance variables are READ-ONLY at the moment.

    :ivar str Model.name: model name
    :ivar Beam beam:
    :ivar Sequence sequence:
    :ivar Madx madx: handle to the MAD-X library
    :ivar dict _data: model definition data
    :ivar ResourceProvider _repo: resource access

    The following example demonstrates the basic usage::

        model = Model.load('/path/to/model/definition.cpymad.yml')

        twiss = model.sequence.twiss()

        print("max/min beta x:", max(twiss['betx']), min(twiss['betx']))
        print("ex: {0}, ey: {1}", twiss.summary['ex'], twiss.summary['ey'])
    """

    # current version of model API
    API_VERSION = 1

    def __init__(self, data, repo, madx):
        """
        Initialize a Model object.

        :param dict data: model definition data
        :param ResourceProvider repo: resource repository
        :param Madx madx: MAD-X instance to use
        """
        self.check_compatibility(data)
        # init instance variables
        self._data = data
        self._repo = repo
        self.madx = madx
        self._loaded = False
        # create Beam/Optic/Sequence instances:
        self.beam = Beam(data['beam'], self)
        self.sequence = Sequence(data['sequence'], self)
        self.range = Range(*data['range'])
        self.initial_conditions = data['twiss']

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
    def load(cls,
             name,
             # *,
             # These should be passed as keyword-only parameters:
             locator=None,
             madx=None,
             command_log=None,
             error_log=None):
        """
        Create Model instance from a model definition file.

        :param str name: model definition file name
        :param Locator locator: model locator
        :param Madx madx: MAD-X instance to use
        :param str command_log: history file name; use only if madx is None!
        :param logging.Logger error_log:

        If the ``locator`` is not specified ``name`` is assumed to be an
        absolute path of a model definition file living in the ordinary file
        system.
        """
        if locator is None:
            path, name = os.path.split(name)
            locator = Locator(FileResource(path))
        data = locator.get_definition(name)
        repo = locator.get_repository(data)
        if madx is None:
            if error_log is None:
                error_log = logging.getLogger(__name__ + '.' + name)
            madx = Madx(command_log=command_log, error_log=error_log)
            madx.verbose(False)
        elif command_log is not None:
            raise ValueError("'command_log' cannot be used with 'madx'")
        elif error_log is not None:
            raise ValueError("'error_log' cannot be used with 'madx'")
        model = cls(data, repo=repo, madx=madx)
        model.init()
        return model

    def init(self):
        """Load model in MAD-X interpreter."""
        if self._loaded:
            return
        self._loaded = True
        self._load(*self._data['init-files'])
        self.madx.command.beam(**self.beam.data)

    def __repr__(self):
        return "{0}({1!r})".format(self.__class__.__name__, self.name)

    @property
    def name(self):
        """Model name."""
        return self._data['name']

    @property
    def data(self):
        """Get a serializable representation of this model."""
        data = self._data.copy()
        data['beam'] = self.beam.data
        data['sequence'] = self.sequence.data
        data['range'] = list(self.range)
        data['twiss'] = self.initial_conditions
        return data

    def _load(self, *files):
        """Load MAD-X files in interpreter."""
        for file in files:
            with self._repo.get(file).filename() as fpath:
                self.madx.call(fpath)


class Beam(object):

    """
    A beam defines the mass, charge, energy, etc. of the particles moved
    through the accelerator.

    :ivar dict Beam.data: beam parameters (keywords to BEAM command in MAD-X)
    :ivar Model _model: owning model
    :ivar bool _loaded: beam has been initialized in MAD-X
    """

    def __init__(self, data, model):
        """Initialize instance variables."""
        self.data = data


class Sequence(object):

    """
    A MAD-X beam line. It can be subdivided into arbitrary ranges.

    :ivar str Sequence.name: sequence name
    :ivar dict _data:
    :ivar Model _model:
    """

    def __init__(self, data, model):
        """Initialize instance variables."""
        self.name = data['name']
        self._data = data
        self._model = model

    @property
    def data(self):
        """Get a serializable representation of this sequence."""
        data = self._data.copy()
        data['name'] = self.name
        return data

    @property
    def beam(self):
        """Get :class:`Beam` instance for this sequence."""
        return self._model.beam

    @property
    def range(self):
        """Get default :class:`Range`."""
        return self._model.range

    @property
    def real_sequence(self):
        """Get the corresponding :class:`Sequence`."""
        return self._model.madx.sequences[self.name]

    @property
    def elements(self):
        """Get a proxy list for all the elements."""
        return self.real_sequence.elements


class Locator(object):

    """
    Model locator for yaml files that contain multiple model definitions.

    These are the model definition files that are currently used by default
    for filesystem resources.

    Serves the purpose of locating models and returning corresponding
    resource providers.
    """

    ext = '.cpymad.yml'

    def __init__(self, resource_provider):
        """
        Initialize a merged model locator instance.

        The resource_provider parameter must be a ResourceProvider instance
        that points to the filesystem location where the .cpymad.yml model
        files are stored.
        """
        self._repo = resource_provider

    def list_models(self, encoding='utf-8'):
        """
        Iterate all available models.

        Returns an iterable that may be a generator object.
        """
        for res_name in self._repo.listdir_filter(ext=self.ext):
            yield res_name[:-len(self.ext)]

    def get_definition(self, name, encoding='utf-8'):
        """
        Get the first found model with the specified name.

        :returns: the model definition
        :raises ValueError: if no model with the given name is found.
        """
        try:
            if not name.endswith(self.ext):
                name += self.ext
            return self._repo.yaml(name, encoding=encoding)
        except IOError:
            raise ValueError("The model {!r} does not exist in the database"
                             .format(name))

    def get_repository(self, data):
        """
        Get the resource loader for the given model.
        """
        # instantiate the resource providers for model resource data
        return self._repo.get(data.get('path-offset', '.'))
