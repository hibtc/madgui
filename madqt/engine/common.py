# encoding: utf-8
"""
Shared base classes for different backends.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import os

from collections import namedtuple

from six import string_types as basestring

from madqt.core.base import Object, Signal
from madqt.core.unit import UnitConverter
from madqt.resource.file import FileResource
from madqt.resource.package import PackageResource


__all__ = [
    'ElementInfo',
    'FloorCoords',
    'minrpc_flags',
]


ElementInfo = namedtuple('ElementInfo', ['name', 'index', 'at'])
FloorCoords = namedtuple('FloorCoords', ['x', 'y', 'z', 'theta', 'phi', 'psi'])


class EngineBase(Object):

    """

    Abstract properties:

        backend             backend object
        backend_libname     name of the binding.
        backend_title       ui title of the backend accelerator code.
        segment
    """

    destroyed = Signal()

    def __init__(self, filename):
        super(EngineBase, self).__init__()
        module = self.__class__.__module__.rsplit('.', 1)[-1]
        self.config = PackageResource('madqt.engine').yaml(module + '.yml')
        self.utool = UnitConverter.from_config_dict(self.config['units'])
        self.load(filename)

    def load(self, filename):
        """Load model or plain MAD-X file."""
        path, name = os.path.split(filename)
        self.repo = FileResource(path)
        ext = os.path.splitext(name)[1].lower()
        self.load_dispatch(name, ext)

    def load_dispatch(self, filename, ext):
        raise NotImplementedError

    def minrpc_flags(self):
        """Flags for launching the backend library in a remote process."""
        import subprocess
        return dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # stdin=None leads to an error on windows when STDIN is broken.
            # Therefore, we need set stdin=os.devnull by passing stdin=False:
            stdin=False,
            bufsize=0)

    def destroy(self):
        """Annihilate current universe. Stop interpreter."""
        if self.rpc_client:
            self.rpc_client.close()
        self.backend = None
        if self.segment is not None:
            self.segment.destroy()
        self.destroyed.emit()

    @property
    def rpc_client(self):
        """Low level RPC client."""
        return self.backend and self.backend._service

    @property
    def remote_process(self):
        """Backend process."""
        return self.backend and self.backend._process

    def _load_params(self, data, name):
        """Load parameter dict from file if necessary."""
        vals = data.get(name, {})
        if isinstance(vals, basestring):
            data[name] = self.repo.yaml(vals, encoding='utf-8')


class SegmentBase(Object):

    """
    Models a continuous section of the machine. This is represented in MAD-X
    as a `range` and in Bmad as a `branch`.
    """

    updated = Signal()
    destroyed = Signal()

    def destroy(self):
        self.universe.segment = None
        self.destroyed.emit()

    def elements(self):
        raise NotImplementedError

    def survey(self):
        raise NotImplementedError

    def survey_elements(self):
        raise NotImplementedError

    def get_twiss_args_raw(self, elem):
        raise NotImplementedError

    def get_element_data_raw(self, elem):
        raise NotImplementedError

    def get_element_index(self, elem):
        raise NotImplementedError

    @property
    def data(self):
        return {
            'sequence': self.sequence,
            'range': self.range,
            'beam': self.beam,
            'twiss': self.twiss_args,
        }

    @property
    def utool(self):
        return self.universe.utool

    def get_element_info(self, element):
        """Get :class:`ElementInfo` from element name or index."""
        if isinstance(element, ElementInfo):
            return element
        if isinstance(element, basestring):
            element = self.get_element_index(element)
        if element < 0:
            element += len(self.elements)
        element_data = self.get_element_data(element)
        return ElementInfo(element_data['name'], element, element_data['at'])

    def get_beam(self):
        return self.utool.dict_add_unit(self.get_beam_raw())

    def set_beam(self, beam):
        self.set_beam_raw(self.utool.dict_strip_unit(beam))

    def get_twiss_args(self):
        return self.utool.dict_add_unit(self.get_twiss_args_raw())

    def set_twiss_args(self, twiss):
        self.set_twiss_args_raw(self.utool.dict_strip_unit(twiss))

    beam = property(get_beam, set_beam)
    twiss_args = property(get_twiss_args, set_twiss_args)

    def get_element_data(self, index):
        return self.utool.dict_add_unit(self.get_element_data_raw(index))

    def get_element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        if pos is None:
            return None
        for elem in self.elements:
            at, L = elem['at'], elem['l']
            if pos >= at and pos <= at+L:
                return elem
        return None

    def get_element_by_name(self, name):
        return self.elements[self.get_element_index(name)]

    # curves

    def get_graph_data(self, name):
        """Get the data for a particular graph as dict of numpy arrays."""
        if name == 'envelope':
            beta = self.get_graph_data('beta')
            return {
                's': beta['s'],
                'x': (beta['x'] * self.ex())**0.5,
                'y': (beta['y'] * self.ey())**0.5,
            }

        columns = dict(zip(
            ['s', 'x', 'y'],
            self.universe.config['graphs'].get(name, [])))

        return {k: self.utool.add_unit(columns.get(k), v)
                for k, v in self.get_graph_data_raw(name).items()}

    def get_graph_data_raw(self, name):
        """Get the data for a particular graph as dict of numpy arrays."""
        raise NotImplementedError

    def get_graph_names(self):
        """Get a list of graph names."""
        raise NotImplementedError

    def retrack(self):
        raise NotImplementedError
