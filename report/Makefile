MAIN = main
LATEX = pdflatex
BIBTEX = bibtex

.PHONY: all clean

all:
	$(LATEX) $(MAIN)
	$(BIBTEX) $(MAIN)
	$(LATEX) $(MAIN)
	$(LATEX) $(MAIN)

clean:
	rm -f *.aux *.log *.bbl *.blg *.toc *.out *.fls *.fdb_latexmk
