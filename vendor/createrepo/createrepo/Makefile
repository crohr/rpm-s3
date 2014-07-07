PYTHON=python
PACKAGE = $(shell basename `pwd`)
PYFILES = $(wildcard *.py)
PYVER := $(shell $(PYTHON) -c 'import sys; print "%.3s" %(sys.version)')
PYSYSDIR := $(shell $(PYTHON) -c 'import sys; print sys.prefix')
PYLIBDIR = $(PYSYSDIR)/lib/python$(PYVER)
PKGDIR = $(PYLIBDIR)/site-packages/$(PKGNAME)

SHELL = /bin/sh
top_srcdir = ..
srcdir = ../$(PKGNAME)
prefix = /usr
exec_prefix = ${prefix}

bindir = ${exec_prefix}/bin
sbindir = ${exec_prefix}/sbin
libexecdir = ${exec_prefix}/libexec
datadir = ${prefix}/share
sysconfdir = ${prefix}/etc
sharedstatedir = ${prefix}/com
localstatedir = ${prefix}/var
libdir = ${exec_prefix}/lib
infodir = ${prefix}/info
docdir = 
includedir = ${prefix}/include
oldincludedir = /usr/include
mandir = ${datadir}/man

pkgdatadir = $(datadir)/$(PKGNAME)
pkglibdir = $(libdir)/$(PKGNAME)
pkgincludedir = $(includedir)/$(PKGNAME)
top_builddir = ../


all: 
	echo "Nothing to do"

clean:
	rm -f *.pyc *.pyo *~

install:
	mkdir -p $(DESTDIR)/$(PKGDIR)
	for p in $(PYFILES) ; do \
		install -m 644 $$p $(DESTDIR)/$(PKGDIR)/$$p; \
	done
	$(PYTHON) -c "import compileall; compileall.compile_dir('$(DESTDIR)/$(PKGDIR)', 1, '$(PKGDIR)', 1)"

distfiles:
	distdir=$(PKGNAME)-$(VERSION); \
	mkdir $(top_srcdir)/.disttmp/$$distdir/$(PKGNAME);\
	cp \
	$(srcdir)/$(PYFILES) \
	$(srcdir)/Makefile \
	$(top_srcdir)/.disttmp/$$distdir/$(PKGNAME)

dailyfiles:
	distdir=$(PKGNAME); \
	mkdir $(top_srcdir)/.disttmp/$$distdir/$(PKGNAME);\
	cp \
	$(srcdir)/$(PYFILES) \	
	$(srcdir)/__init__.py \
	$(srcdir)/Makefile \
	$(top_srcdir)/.disttmp/$$distdir/$(PKGNAME)

