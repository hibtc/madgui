all: o/envelope.pdf

compare: compare.sh
	./compare.sh

# post processing: create neat plots
o/%.pdf: o/%.tex
	epstopdf o/$*-inc.eps --outfile=o/$*-inc.pdf
	pdflatex -output-directory=o $<

o/%.png: o/%.dvi
	dvipng -bg "rgb 1.0 1.0 1.0" -T -Q 10 --follow --png -o $@ $<

o/%.dvi: o/%.tex
	latex -output-directory=o $<

o/%.tex: o/madx.twiss i/mirko.env envelope.plt
	name=$* ./envelope.plt

# perform the calculation
o/madx.twiss: main.madx *.madx i/madx.def i/madx.param  o/madx.seq
	madx_dev <$<

# pre-processing: prepare the madx sequence file
o/madx.seq: i/madx.proseq toseq.pl
	./toseq.pl centre <$< >$@

# cleanup
clean:
	rm -rf o/*.log o/*.aux o/*.eps o/*.plt o/*-inc.pdf o/*.tex
