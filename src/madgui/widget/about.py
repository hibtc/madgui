"""
A dialog that displays version and license information about given software
components.
"""

__all__ = [
    'VersionInfo',
    'AboutDialog',
    'AboutWidget',
]

from dataclasses import dataclass, field

import docutils.core
from PyQt5.QtWidgets import QFrame, QPushButton, QTextBrowser

from madgui.widget.dialog import Dialog


@dataclass
class VersionInfo:

    name: str
    version: str
    description: str = field(repr=False)
    website: str = field(repr=False)
    license: str = field(repr=False)
    credits: str = field(repr=False)

    @classmethod
    def from_module(cls, module):
        """
        Get a :class:`VersionInfo` for a module/package or other object that
        has meta variables similar to :mod:`madgui`.
        """
        return cls(
            name=module.__title__,
            version=module.__version__,
            description=module.__summary__,
            website=module.__uri__,
            license=module.get_copyright_notice(),
            credits=module.__credits__)

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
        text = self.to_restructuredtext()
        html = docutils.core.publish_string(text, writer_name='html4css1')
        return html.decode('utf-8')


def _section(level, title, content, level_chr='=~'):
    """Output a ReST formatted heading followed by the content."""
    return title + '\n' + level_chr[level] * len(title) + '\n\n' + content


def HLine():
    """Create horizontal line widget (as divider between stacked widgets)."""
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


def AboutWidget(version_info, *args, **kwargs):
    """Create a widget showing information about one software component."""
    # QTextBrowser is good enough, no need for the heavier QWebKit.QWebView.
    widget = QTextBrowser(*args, **kwargs)
    widget.setOpenExternalLinks(True)
    widget.setHtml(version_info.to_html())
    widget.setMinimumSize(600, 400)
    return widget


def AboutDialog(version_info: VersionInfo, *args, **kwargs):
    """Create a dialog showing information about one software component."""
    main = AboutWidget(version_info)
    line = HLine()
    button = QPushButton("&OK")
    button.setDefault(True)
    dialog = Dialog(*args, **kwargs)
    dialog.setWidget([main, line, button])
    button.clicked.connect(dialog.accept)
    return dialog
