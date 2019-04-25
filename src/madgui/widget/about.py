"""
About dialog that provides version and license information for the user.
"""

__all__ = [
    'VersionInfo',
    'AboutWidget',
]

import docutils.core
from PyQt5.QtCore import pyqtSlot as slot
from PyQt5.QtWidgets import QWidget

from madgui.util.qt import load_ui


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


class AboutWidget(QWidget):
    """A panel showing information about one software component."""

    # QTextBrowser is good enough for our purposes. For a comparison of
    # QTextBrowser and QWebKit.QWebView, see:
    # See http://www.mimec.org/node/383

    def __init__(self, version_info, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_ui(self, __package__, 'about.ui')
        self.textBrowser.setHtml(version_info.to_html())
        self.setWindowTitle("About {}".format(version_info.name))

    @slot()
    def on_okButton_clicked(self):
        self.window().close()
