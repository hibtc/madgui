"""
Models encapsulate metadata for accelerator machines.

For more information about models, see :class:`Model`.
"""

from __future__ import absolute_import

import logging
import os

from cpymad.madx import Madx
from madgui.resource.file import FileResource


__all__ = [
    'Model',
    'Locator',
]


def _load(madx, repo, *files):
    """Load MAD-X files in interpreter."""
    for file in files:
        with repo.get(file).filename() as fpath:
            madx.call(fpath)


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
    def init(cls, madx, repo, data):
        """Load model in MAD-X interpreter."""
        cls.check_compatibility(data)
        _load(madx, repo, *data['init-files'])
        beam = dict(data['beam'], sequence=data['sequence'])
        madx.command.beam(**beam)


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
