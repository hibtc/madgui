"""
Utilities to create a plot of some TWISS parameter along the accelerator
s-axis.
"""

__all__ = [
    'plot_curve',
    'plot_element_indicators',
    'plot_element_indicator',
    'plot_constraint',
    'plot_selection_marker',
    'plot_curves',
    'draw_patch',
    'ax_label',
    'indicator_params',
]

import math
import logging
from types import SimpleNamespace

from madgui.util.yaml import load_resource

from madgui.util.unit import to_ui, get_raw_label, ui_units
from madgui.plot.scene import LineBundle, plot_line

import matplotlib.patheffects as pe
import matplotlib.colors as mpl_colors

CONFIG = load_resource(__package__, 'twissfigure.yml')
ELEM_STYLES = CONFIG['element_style']


def plot_curve(axes, data, x_name, y_name, style, label=None):
    """Plot a TWISS parameter curve model into a 2D figure."""
    def get_xydata():
        table = data() if callable(data) else data
        xdata = _get_curve_data(table, x_name)
        ydata = _get_curve_data(table, y_name)
        if xdata is None or ydata is None:
            return (), ()
        return xdata, ydata
    return plot_line(axes, get_xydata, label=label, **style)


def plot_element_indicators(ax, elements, elem_styles=ELEM_STYLES,
                            default_style=None, effects=None):
    """Plot element indicators, i.e. create lattice layout plot."""
    return LineBundle([
        plot_element_indicator(ax, elem, elem_styles, default_style, effects)
        for elem in elements
    ])


def draw_patch(ax, position, length, style):
    at = to_ui('s', position)
    if length != 0:
        patch_w = to_ui('l', length)
        return ax.axvspan(at, at + patch_w, **style)
    else:
        return ax.axvline(at, **style)


def plot_element_indicator(ax, elem, elem_styles=ELEM_STYLES,
                           default_style=None, effects=None,
                           **defaults):
    """Return the element type name used for properties like coloring."""
    type_name = elem.base_name.lower()
    style = elem_styles.get(type_name, default_style)
    if style is None:
        return LineBundle()

    axes_dirs = {n[-1] for n in ax.y_name} & set("xy")
    # sigmoid flavor with convenient output domain [-1,+1]:
    sigmoid = math.tanh

    style = dict(defaults, zorder=0, **style)
    styles = [(style, elem.position, elem.length)]

    if type_name == 'quadrupole':
        invert = ax.y_name[0].endswith('y')
        k1 = float(elem.k1) * 100                   # scale = 0.1/m²
        scale = sigmoid(k1) * (1-2*invert)
        style['color'] = ((1+scale)/2, (1-abs(scale))/2, (1-scale)/2)
    elif type_name == 'sbend':
        angle = float(elem.angle) * 180/math.pi     # scale = 1 degree
        ydis = sigmoid(angle) * (-0.15)
        style['ymin'] += ydis
        style['ymax'] += ydis
        # MAD-X uses the condition k0=0 to check whether the attribute
        # should be used (against my recommendations, and even though that
        # means you can never have a kick that exactlycounteracts the
        # bending angle):
        if elem.k0 != 0:
            style = dict(elem_styles.get('hkicker'),
                         ymin=style['ymin'], ymax=style['ymax'])
            styles.append((style, elem.position+elem.length/2, 0))
            type_name = 'hkicker'

    if type_name in ('hkicker', 'vkicker'):
        axis = "xy"[type_name.startswith('v')]
        kick = float(elem.kick) * 10000         # scale = 0.1 mrad
        ydis = sigmoid(kick) * 0.1
        style['ymin'] += ydis
        style['ymax'] += ydis
        if axis not in axes_dirs:
            style['alpha'] = 0.2

    effects = effects or (lambda x: x)
    return LineBundle([
        draw_patch(ax, position, length, effects(style))
        for style, position, length in styles
    ])


def indicator_params(elem):
    """Return the parameters used by ``plot_element_indicator``. This is
    useful for caching a reduced set of parameters that is faster to compare
    for changes."""
    base_name = elem.base_name
    ns = SimpleNamespace(
        position=elem.position,
        length=elem.length,
        base_name=elem.base_name)
    if base_name == 'sbend':
        ns.angle = elem.angle
        ns.k0 = elem.k0
        ns.kick = elem.kick
    elif base_name == 'quadrupole':
        ns.k1 = elem.k1
    elif base_name.endswith('kicker'):
        ns.kick = elem.kick
    return ns


def plot_constraint(ax, scene, constraint):
    """Draw one constraint representation in the graph."""
    elem, pos, axis, val = constraint
    style = scene.config['constraint_style']
    return LineBundle(ax.plot(
        to_ui('s', pos),
        to_ui(axis, val),
        **style) if axis in ax.y_name else ())


def plot_selection_marker(ax, model, el_idx, elem_styles=ELEM_STYLES,
                          highlight=True):
    """In-figure markers for active/selected elements."""
    elem = model.elements[el_idx]
    drift_color = '#ffffff' if highlight else '#eeeeee'
    default = dict(ymin=0, ymax=1, color=drift_color)
    effects = _hover_effects if highlight else _selection_effects
    return plot_element_indicator(ax, elem, elem_styles, default, effects)


def _selection_effects(style):
    r, g, b = mpl_colors.colorConverter.to_rgb(style['color'])
    h, s, v = mpl_colors.rgb_to_hsv((r, g, b))
    s = (s + 0) / 2
    v = (v + 1) / 2
    return dict(
        style,
        color=mpl_colors.hsv_to_rgb((h, s, v)),
        path_effects=[
            pe.withStroke(linewidth=2, foreground='#000000', alpha=1.0),
        ],
    )


def _hover_effects(style):
    r, g, b = mpl_colors.colorConverter.to_rgb(style['color'])
    h, s, v = mpl_colors.rgb_to_hsv((r, g, b))
    s = (s + 0) / 1.5
    v = (v + 0) / 1.025
    return dict(
        style,
        color=mpl_colors.hsv_to_rgb((h, s, v)),
        path_effects=[
            pe.withStroke(linewidth=1, foreground='#000000', alpha=1.0),
        ],
    )


def plot_twiss_curve(ax, table, x_name, y_name, label, style):
    style = with_outline(style)
    label = ax_label(label, ui_units.get(y_name))
    return plot_curves(ax, table, style, label, [(x_name, y_name)])


def plot_user_curve(ax, data, x_names, y_names, label, style):
    style = CONFIG[style] if isinstance(style, str) else style
    return plot_curves(ax, data, style, label, list(zip(x_names, y_names)))


def plot_curves(ax, data, style, label, names):
    return LineBundle([
        plot_curve(ax, data, x_name, y_name, style, label=label)
        for x_name, y_name in zip(ax.x_name, ax.y_name)
        if (x_name, y_name) in names
    ])


def _get_curve_data(data, name):
    try:
        return to_ui(name, data[name])
    except KeyError:
        logging.debug("Missing curve data {!r}, we only know: {}"
                      .format(name, ','.join(data)))


def ax_label(label, unit):
    if unit in (1, None):
        return label
    return "{} [{}]".format(label, get_raw_label(unit))


def with_outline(style, linewidth=6, foreground='w', alpha=0.7):
    return dict(style, path_effects=[
        pe.withStroke(linewidth=linewidth, foreground=foreground, alpha=alpha),
    ])
