SHELL = /bin/sh
top_srcdir = ..
srcdir = ../docs
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

# all dirs
DIRS = $(DESTDIR)$(bindir) $(DESTDIR)/etc $(DESTDIR)$(pkgdatadir) $(DESTDIR)$(mandir)


# INSTALL scripts 
INSTALL         = install -p --verbose 
INSTALL_BIN     = $(INSTALL) -m 755 
INSTALL_DIR     = $(INSTALL) -m 755 -d 
INSTALL_DATA    = $(INSTALL) -m 644 
INSTALL_MODULES = $(INSTALL) -m 755 -D 
RM 		= rm -f


all: 
	echo "nothing to do"

install: all installdirs
	mkdir -p $(DESTDIR)$(mandir)/man8
	mkdir -p $(DESTDIR)$(mandir)/man1
	$(INSTALL_DATA) createrepo.8 $(DESTDIR)$(mandir)/man8/createrepo.8
	$(INSTALL_DATA) modifyrepo.1 $(DESTDIR)$(mandir)/man1/modifyrepo.1
	$(INSTALL_DATA) mergerepo.1 $(DESTDIR)$(mandir)/man1/mergerepo.1


uninstall:
	$(RM) $(bindir)/$(PKGNAME)



clean:


distclean:
	$(RM) -rf .libs
	$(RM) -f core
	$(RM) -f *~


mostlyclean:
	$(MAKE) clean


maintainer-clean:
	$(MAKE) distclean


distfiles:
	distdir=$(PKGNAME)-$(VERSION); \
	mkdir $(top_srcdir)/.disttmp/$$distdir/docs;\
	cp \
	$(srcdir)/createrepo.8 \
	$(srcdir)/modifyrepo.1 \
	$(srcdir)/mergerepo.1 \
	$(srcdir)/Makefile \
	$(top_srcdir)/.disttmp/$$distdir/docs

dailyfiles:
	distdir=$(PKGNAME); \
	mkdir $(top_srcdir)/.disttmp/$$distdir/docs;\
	cp \
	$(srcdir)/createrepo.8 \
	$(srcdir)/modifyrepo.1 \
	$(srcdir)/mergerepo.1 \
	$(srcdir)/Makefile \
	$(top_srcdir)/.disttmp/$$distdir/docs

installdirs:
	$(MAKE) -C $(top_srcdir) installdirs


.PHONY: all install install-strip uninstall clean distclean mostlyclean maintainer-clean info dvi dist distfiles check installcheck installdirs dailyfiles



