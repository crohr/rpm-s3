PKGNAME = createrepo
ALIASES = mergerepo modifyrepo genpkgmetadata.py mergerepo.py modifyrepo.py
VERSION=$(shell awk '/Version:/ { print $$2 }' ${PKGNAME}.spec)
RELEASE=$(shell awk '/Release:/ { print $$2 }' ${PKGNAME}.spec)
CVSTAG=createrepo-$(subst .,_,$(VERSION)-$(RELEASE))
PYTHON=python
SUBDIRS = $(PKGNAME) bin docs
PYFILES = $(wildcard *.py)


SHELL = /bin/sh
top_srcdir = .
srcdir = .
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
mandir = ${prefix}/share/man
compdir = $(shell pkg-config --variable=completionsdir bash-completion)
compdir := $(or $(compdir), "/etc/bash_completion.d")

pkgdatadir = $(datadir)/$(PKGNAME)
pkglibdir = $(libdir)/$(PKGNAME)
pkgincludedir = $(includedir)/$(PKGNAME)
top_builddir = 

# all dirs
DIRS = $(DESTDIR)$(bindir) $(DESTDIR)$(compdir) \
	$(DESTDIR)$(pkgdatadir) $(DESTDIR)$(mandir)


# INSTALL scripts 
INSTALL         = install -p --verbose 
INSTALL_BIN     = $(INSTALL) -m 755 
INSTALL_DIR     = $(INSTALL) -m 755 -d 
INSTALL_DATA    = $(INSTALL) -m 644 
INSTALL_MODULES = $(INSTALL) -m 755 -D 
RM              = rm -f

MODULES = $(srcdir)/genpkgmetadata.py \
	$(srcdir)/modifyrepo.py \
	$(srcdir)/mergerepo.py	\
	$(srcdir)/worker.py

.SUFFIXES: .py .pyc
.py.pyc: 
	python -c "import py_compile; py_compile.compile($*.py)"


all: $(MODULES)
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir VERSION=$(VERSION) PKGNAME=$(PKGNAME) DESTDIR=$(DESTDIR); \
	done

check: 
	pychecker $(MODULES) || exit 0 

install: all installdirs
	$(INSTALL_MODULES) $(srcdir)/$(MODULES) $(DESTDIR)$(pkgdatadir)
	$(INSTALL_DATA) $(PKGNAME).bash $(DESTDIR)$(compdir)/$(PKGNAME)
	(cd $(DESTDIR)$(compdir); for n in $(ALIASES); do ln -s $(PKGNAME) $$n; done)
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir install VERSION=$(VERSION) PKGNAME=$(PKGNAME); \
	done

installdirs:
	for dir in $(DIRS) ; do \
      $(INSTALL_DIR) $$dir ; \
	done


uninstall:
	for module in $(MODULES) ; do \
	  $(RM) $(pkgdatadir)/$$module ; \
	done
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir uninstall VERSION=$(VERSION) PKGNAME=$(PKGNAME); \
	done

clean:
	$(RM)  *.pyc *.pyo
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir clean VERSION=$(VERSION) PKGNAME=$(PKGNAME); \
	done

distclean: clean
	$(RM) -r .libs
	$(RM) core
	$(RM) *~
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir distclean VERSION=$(VERSION) PKGNAME=$(PKGNAME); \
	done

pylint:
	@pylint --rcfile=test/createrepo-pylintrc *.py createrepo

pylint-short:
	@pylint -r n --rcfile=test/createrepo-pylintrc *.py createrepo

mostlyclean:
	$(MAKE) clean


maintainer-clean:
	$(MAKE) distclean
	$(RM) $(srcdir)/configure

changelog:
	git log --pretty --numstat --summary | git2cl  > ChangeLog

dist:
	olddir=`pwd`; \
	distdir=$(PKGNAME)-$(VERSION); \
	$(RM) -r .disttmp; \
	$(INSTALL_DIR) .disttmp; \
	$(INSTALL_DIR) .disttmp/$$distdir; \
	$(MAKE) distfiles
	distdir=$(PKGNAME)-$(VERSION); \
	cd .disttmp; \
	tar -cvz > ../$$distdir.tar.gz $$distdir; \
	cd $$olddir
	$(RM) -r .disttmp

daily:
	olddir=`pwd`; \
	distdir=$(PKGNAME); \
	$(RM) -r .disttmp; \
	$(INSTALL_DIR) .disttmp; \
	$(INSTALL_DIR) .disttmp/$$distdir; \
	$(MAKE) dailyfiles
	day=`/bin/date +%Y%m%d`; \
	distdir=$(PKGNAME); \
	tarname=$$distdir-$$day ;\
	cd .disttmp; \
	perl -pi -e "s/\#DATE\#/$$day/g" $$distdir/$(PKGNAME)-daily.spec; \
	echo $$day; \
	tar -cvz > ../$$tarname.tar.gz $$distdir; \
	cd $$olddir
	$(RM) -rf .disttmp

dailyfiles:
	distdir=$(PKGNAME); \
	cp \
	$(srcdir)/*.py \
	$(srcdir)/Makefile \
	$(srcdir)/ChangeLog \
	$(srcdir)/COPYING \
	$(srcdir)/COPYING.lib \
	$(srcdir)/README \
	$(srcdir)/$(PKGNAME).spec \
	$(srcdir)/$(PKGNAME).bash \
	$(top_srcdir)/.disttmp/$$distdir
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir dailyfiles VERSION=$(VERSION) PKGNAME=$(PKGNAME); \
	done

distfiles:
	distdir=$(PKGNAME)-$(VERSION); \
	cp \
	$(srcdir)/*.py \
	$(srcdir)/Makefile \
	$(srcdir)/ChangeLog \
	$(srcdir)/COPYING \
	$(srcdir)/COPYING.lib \
	$(srcdir)/README \
	$(srcdir)/$(PKGNAME).spec \
	$(srcdir)/$(PKGNAME).bash \
	$(top_srcdir)/.disttmp/$$distdir
	for subdir in $(SUBDIRS) ; do \
	  $(MAKE) -C $$subdir distfiles VERSION=$(VERSION) PKGNAME=$(PKGNAME); \
	done

archive: dist

.PHONY: todo
todo:
	@echo ---------------===========================================
	@grep -n TODO\\\|FIXME `find . -type f` | grep -v grep
	@echo ---------------===========================================
.PHONY: all install install-strip uninstall clean distclean mostlyclean maintainer-clean info dvi dist distfiles check installcheck installdirs daily dailyfiles
