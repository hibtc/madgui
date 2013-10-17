#! /bin/zsh

make o/madx.twiss

M()
{
    export name="comparison-$x0"
    name=$name x0=$x0 x1=$x1 ./envelope.plt
    epstopdf o/${name}-inc.eps --outfile=o/${name}-inc.pdf
    pdflatex -output-directory=o o/${name}.tex
}

for x0 in $(seq 0 10 70); do
   (( x1 = x0 + 11.5 ))
   x0=$x0 x1=$x1 M
done

make clean
