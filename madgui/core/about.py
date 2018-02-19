"""
About dialog that provides version and license information for the user.
"""

import docutils.core

from madgui.qt import QtGui
from madgui.widget.dialog import Dialog


__all__ = [
    'AboutDialog',
]


class VersionInfo:

    def __init__(self, module):
        """
        Get a :class:`VersionInfo` for a module/package or other object that
        has meta variables similar to :mod:`madgui`.
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


def AboutWidget(version_info, *args, **kwargs):
    """A panel showing information about one software component."""
    # QTextBrowser is good enough for our purposes. For a comparison of
    # QtGui.QTextBrowser and QWebKit.QWebView, see:
    # See http://www.mimec.org/node/383
    widget = QtGui.QTextBrowser(*args, **kwargs)
    widget.setOpenExternalLinks(True)
    widget.setHtml(version_info.to_html())
    widget.setMinimumSize(600, 400)
    return widget


def AboutDialog(version_info, *args, **kwargs):
    main = AboutWidget(version_info)
    line = HLine()
    button = QtGui.QPushButton("&OK")
    button.setDefault(True)
    dialog = Dialog(*args, **kwargs)
    dialog.setWidget([main, line, button])
    button.clicked.connect(dialog.accept)
    return dialog
