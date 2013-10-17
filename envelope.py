#! /usr/bin/env python2

# standard modules:
import sys
import math
import cmath

# import pymad module:
from cern import madx

# import scipy:
# (fitting, plotting, efficient arrays, statistical functions, etc)
import numpy as np
import scipy as sp
from scipy import stats
import matplotlib as mp
import matplotlib.pyplot as plt     # plotting
from matplotlib.ticker import MultipleLocator

# NOTE:
from subprocess import call
call(["make", "o/madx.seq"])


# madx params
import param
twiss_init = {
    'betx':'init_betx', 'bety':'init_bety',
    'dx':'init_dx',     'dy':'init_dy',
    'x':'init_x',       'y':'init_y',
    'alfx':'init_alfx', 'alfy':'init_alfy',
    'mux':'init_mux',   'muy':'init_muy',
    'dpx':'init_dpx',   'dpy':'init_dpy',
    'px':'init_px',     'py':'init_py'
}
twiss_columns = ['name','s','betx','bety','x','dx','y','dy']

#
w,h = mp.figure.figaspect(9./16)
fig = plt.figure(figsize=(w,h))
ax = fig.add_subplot(111)
ax.set_xlim(0, 82)
ax.set_ylim(0, 50)

yunit = {'label': 'mm', 'scale': 1e-3}

# plot the madx results
m = madx.madx()
m.call("pymad.madx")
c = [('#8b1a0e','#5e9c36'), ('#ffa500', '#00d8df')]

tw, summary = m.twiss('hht3', columns=twiss_columns, twiss_init=twiss_init)

s = tw.s
dx = np.array([math.sqrt(betx*param.epsx) for betx in tw.betx])
dy = np.array([math.sqrt(bety*param.epsy) for bety in tw.bety])

if param.rot_angle > 0:
    for i in range(len(s)):
        if s[i] >= 5.44273196e+01:
            dx[i], dy[i] = dy[i], dx[i]

ax.plot(tw.s, dx/yunit['scale'], "o-", color=c[0][0], fillstyle='none', label="$\Delta x_\mathrm{MAD}$")
ax.plot(tw.s, dy/yunit['scale'], "o-", color=c[0][1], fillstyle='none', label="$\Delta y_\mathrm{MAD}$")

# plot the mirko results
mirko = np.loadtxt("i/mirko.env")
plt.plot(mirko[:,0]/1000, mirko[:,1]/1000/yunit['scale'], "x-", color=c[1][0], fillstyle='none', label="$\Delta x_\mathrm{mirko}$")
plt.plot(mirko[:,0]/1000, mirko[:,2]/1000/yunit['scale'], "x-", color=c[1][1], fillstyle='none', label="$\Delta y_\mathrm{mirko}$")

# create figure
ax.grid(True)
ax.set_xlabel("position $s$ [m]")
ax.set_ylabel("beam envelope [" + yunit['label'] + "]")
ax.get_xaxis().set_minor_locator(MultipleLocator(2))
ax.get_yaxis().set_minor_locator(MultipleLocator(0.002/yunit['scale']))
ax.legend(loc='upper left')
fig.savefig("o/envelope.pdf", bbox_inches='tight')
fig.savefig("o/envelope.png", bbox_inches='tight', dpi=256)
