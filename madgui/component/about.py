# encoding: utf-8
"""
About dialog that provides version and license information for the user.
"""

# force new style imports
from __future__ import absolute_import

from collections import namedtuple

# internal
import madgui
import cpymad
from cpymad.madx import metadata as madx

from madgui.core import wx

# 3rdparty
import docutils.core
import wx.html


# exported symbols
__all__ = [
    'show_about_dialog',
]


VersionInfo = namedtuple('VersionInfo', [
    'name',
    'version',
    'description',
    'website',
    'license',
    'credits',
])


class StaticHtmlWindow(wx.html.HtmlWindow):

    def OnLinkClicked(self, link):
        wx.LaunchDefaultBrowser(link.GetHref())


def _section(level, title, content, level_chr='=~'):
    """Output a ReST formatted heading followed by the content."""
    return title + '\n' + level_chr[level] * len(title) + '\n\n' + content


class AboutPanel(wx.Panel):

    """A panel showing information about one software component."""

    def __init__(self, parent, version_info):
        super(AboutPanel, self).__init__(parent)
        # compose ReStructuredText document
        title = version_info.name + ' ' + version_info.version
        summary = version_info.description + '\n\n' + version_info.website
        text = "\n\n".join([
            _section(0, title, summary),
            _section(1, 'Copyright', version_info.license),
            _section(1, 'Credits', version_info.credits),
        ])
        # convert to HTML and display
        html = docutils.core.publish_string(text, writer_name='html4css1')
        html = html.decode('utf-8')
        textctrl = StaticHtmlWindow(self, size=(600, 400))
        textctrl.SetPage(html)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(textctrl, 1, flag=wx.ALL|wx.EXPAND, border=5)
        self.SetSizer(sizer)


class AboutDialog(wx.Dialog):

    """Tabbed AboutDialog for multiple software components."""

    def __init__(self, parent, all_version_info=()):
        super(AboutDialog, self).__init__(parent)
        self.CreateControls()
        for version_info in all_version_info:
            self.AddVersionInfo(version_info)
        self.Layout()
        self.Fit()
        self.Centre()

    def CreateControls(self):
        """Create the empty controls."""
        book = self.book = wx.Notebook(self)
        line = wx.StaticLine(self, style=wx.LI_HORIZONTAL)
        button = wx.Button(self, wx.ID_OK)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(book, 1, flag=wx.ALL|wx.EXPAND, border=5)
        sizer.Add(line, flag=wx.ALL|wx.EXPAND, border=5)
        sizer.Add(button, flag=wx.ALL|wx.ALIGN_CENTER, border=5)
        self.SetSizer(sizer)

    def AddVersionInfo(self, info):
        """Show a :class:`VersionInfo` in a new tab."""
        self.book.AddPage(AboutPanel(self.book, info), info.name)


def _get_version_info(module):
    """
    Get a :class:`VersionInfo` for a module/package or other object that has
    meta variables similar to :mod:`madgui`.
    """
    return VersionInfo(
        name=module.__title__,
        version=module.__version__,
        description=module.__summary__,
        website=module.__uri__,
        license=module.get_copyright_notice(),
        credits=module.__credits__,
    )


def show_about_dialog(parent):
    """Show the about dialog."""
    AboutDialog(parent, [
        _get_version_info(madgui),
        _get_version_info(cpymad),
        _get_version_info(madx),
    ]).Show(True)
