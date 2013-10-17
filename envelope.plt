#! /usr/local/bin/template -x tail -n +1 | tee o/$name.plt | gnuplot -

# Basic settings:
set encoding utf8
set terminal epslatex standalone color colortext header '\definecolor{t}{rgb}{0.5,0.5,0.5}'
set macros
set output 'o/$name.tex'

# tick format
set format '\color{t}\$%g\$'

# remove border on top and right and set color to gray
set style line 11 lc rgb '#808080' lt 1
set border 3 back ls 11
set tics nomirror
# define grid
set style line 12 lc rgb '#808080' lt 0 lw 1
set grid back ls 12

# color definitions
set style line 1 lc rgb '#8b1a0e' pt 1 ps 1 lt 1 lw 2   # red
set style line 2 lc rgb '#5e9c36' pt 6 ps 1 lt 1 lw 2   # green
set style line 3 lc rgb '#dd181f' pt 2 ps 1 lt 1 lw 2   # blue
set style line 4 lc rgb '#00d8df' pt 3 ps 1 lt 1 lw 2   # violett

set size ratio 0.5625
set ytics 0.01
set mytics 5
set mxtics 5


#
set key top left
set xlabel 'position \$s\$ [m]'
set ylabel 'beam envelope [m]'

# load epsx/epsy constants
load "i/madx.param"

set xrange [${x0:-0}:${x1:-85}]

ex(s) = epsx
ey(s) = epsy

# plot envelope: D = sqrt(beta * epsilon)
plot 'o/madx.twiss' using 2:(sqrt(\$3*ex(\$2))) title '\$\Delta x_{madX}\$'  with lp ls 1 pt 1, \
     'i/mirko.env'  using (\$1/1000):(\$2/1000) title '\$\Delta x_{mirko}\$' with lp ls 3 pt 2, \
     'o/madx.twiss' using 2:(sqrt(\$4*ey(\$2))) title '\$\Delta y_{madX}\$'  with lp ls 2 pt 1, \
     'i/mirko.env'  using (\$1/1000):(\$3/1000) title '\$\Delta y_{mirko}\$' with lp ls 4 pt 2

# vim: ft=gnuplot
