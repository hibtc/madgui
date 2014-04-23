# encoding: utf-8
"""
Locator for LHC models.

Should be moved to cpymad.
"""

# force new style imports
from __future__ import absolute_import

# 3rdparty
from cern.cpymad.model_locator import ModelData, MergedModelLocator
from cern.resource.package import PackageResource

# exported symbols
__all__ = ['locator']


locator = MergedModelLocator(PackageResource('cern.cpymad', '_models'))
