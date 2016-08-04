# encoding: utf-8
"""
About dialog that provides version and license information for the user.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import namedtuple

from PyQt4 import QtCore, QtGui
import docutils.core

# We want to show metadata of these modules:
import madqt
import cpymad
from cpymad.madx import metadata as madx


__all__ = [
    'show_about_dialog',
]


def show_about_dialog(*args, **kwargs):
    """Show the about dialog."""
    dialog = AboutDialog([
        VersionInfo(madqt),
        VersionInfo(cpymad),
        VersionInfo(madx),
    ], *args, **kwargs)
    dialog.show()


class VersionInfo(object):

    def __init__(self, module):
        """
        Get a :class:`VersionInfo` for a module/package or other object that
        has meta variables similar to :mod:`madqt`.
        """
        self.name = module.__title__
        self.version = module.__version__
        self.description = module.__summary__
        self.website = module.__uri__
        self.license = module.get_copyright_notice()
        self.credits = module.__credits__

    def to_restructuredtext(self):
        """Compose ReStructuredText document."""
        title = self.name + ' ' + self.version
        summary = self.description + '\n\n' + self.website
        return "\n\n".join([
            _section(0, title, summary),
            _section(1, 'Copyright', self.license),
            _section(1, 'Credits', self.credits),
        ])

    def to_html(self):
        """Create the HTML for inside the About dialog."""
        # convert to HTML and display
        text = self.to_restructuredtext()
        html = docutils.core.publish_string(text, writer_name='html4css1')
        return html.decode('utf-8')


def _section(level, title, content, level_chr='=~'):
    """Output a ReST formatted heading followed by the content."""
    return title + '\n' + level_chr[level] * len(title) + '\n\n' + content


def HLine():
    """Create horizontal line widget (as divider between stacked widgets)."""
    line = QtGui.QFrame()
    line.setFrameShape(QtGui.QFrame.HLine)
    line.setFrameShadow(QtGui.QFrame.Sunken)
    return line


class AboutWidget(QtGui.QTextBrowser):

    # QTextBrowser is good enough for our purposes. For a comparison of
    # QtGui.QTextBrowser and QWebKit.QWebView, see:
    # See http://www.mimec.org/node/383

    """A panel showing information about one software component."""

    def __init__(self, version_info, *args, **kwargs):
        super(AboutWidget, self).__init__(*args, **kwargs)
        self.setOpenExternalLinks(True)
        self.setHtml(version_info.to_html())
        self.setMinimumSize(600, 400)


class AboutDialog(QtGui.QDialog):

    """Tabbed AboutDialog for multiple software components."""

    def __init__(self, all_version_info=(), *args, **kwargs):
        super(AboutDialog, self).__init__(*args, **kwargs)
        self.createControls()
        for version_info in all_version_info:
            self.addVersionInfo(version_info)

    def createControls(self):
        """Create the empty controls."""
        tabs = self.tabs = QtGui.QTabWidget(self)
        line = HLine()
        button = QtGui.QPushButton("&OK")
        button.clicked.connect(self.close)
        layout = QtGui.QVBoxLayout()
        layout.addWidget(tabs)
        layout.addWidget(line)
        layout.addWidget(button)
        self.setLayout(layout)

    def addVersionInfo(self, info):
        """Show a :class:`VersionInfo` in a new tab."""
        self.tabs.addTab(AboutWidget(info), info.name)
