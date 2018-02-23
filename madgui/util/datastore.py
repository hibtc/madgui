from abc import abstractmethod
from collections import OrderedDict

from madgui.resource import yaml


class DataStore:

    """
    Base class that defines the protocol between data source/sink and
    ParamTable.
    """

    # TODO: drop utool parameter - just save the units into the YAML file
    utool = None
    label = None
    data_key = None

    @abstractmethod
    def get(self):
        """Get a dictionary with all values."""

    @abstractmethod
    def update(self, values):
        """Update values from dictionary."""

    @abstractmethod
    def mutable(self, key):
        """Check whether the parameter belonging to a certain key is mutable."""

    @abstractmethod
    def default(self, key):
        """Get default value for the given key."""

    # data im-/export

    exportFilters = [
        ("YAML file", "*.yml", "*.yaml"),
        ("JSON file", "*.json"),
    ]

    importFilters = [
        ("YAML file", "*.yml", "*.yaml"),
    ]

    def importFrom(self, filename):
        """Import data from JSON/YAML file."""
        with open(filename, 'rt') as f:
            # Since JSON is a subset of YAML there is no need to invoke a
            # different parser (unless we want to validate the file):
            data = yaml.safe_load(f)
        if self.data_key:
            data = data[self.data_key]
        if self.utool:
            data = self.utool.dict_add_unit(data)
        self.set(data)

    def exportTo(self, filename):
        """Export parameters to YAML file."""
        data = self.get()
        if self.utool:
            data = self.utool.dict_strip_unit(data)
        if self.data_key:
            data = {self.data_key: data}
        with open(filename, 'wt') as f:
            yaml.safe_dump(data, f, default_flow_style=False)
