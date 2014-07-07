%{!?python_sitelib: %define python_sitelib %(python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

%if ! 0%{?rhel}
# we don't have this in rhel yet...
BuildRequires: bash-completion
%endif

# disable broken /usr/lib/rpm/brp-python-bytecompile
%define __os_install_post %{nil}
%define compdir %(pkg-config --variable=completionsdir bash-completion)
%if "%{compdir}" == ""
%define compdir "/etc/bash_completion.d"
%endif

Summary: Creates a common metadata repository
Name: createrepo
Version: 0.10
Release: 1
License: GPL
Group: System Environment/Base
Source: %{name}-%{version}.tar.gz
URL: http://createrepo.baseurl.org/
BuildRoot: %{_tmppath}/%{name}-%{version}root
BuildArchitectures: noarch
Requires: python >= 2.1, rpm-python, rpm >= 0:4.1.1, libxml2-python
Requires: yum-metadata-parser, yum >= 3.2.29, python-deltarpm, pyliblzma

%description
This utility will generate a common metadata repository from a directory of
rpm packages

%prep
%setup -q

%install
[ "$RPM_BUILD_ROOT" != "/" ] && rm -rf $RPM_BUILD_ROOT
make DESTDIR=$RPM_BUILD_ROOT sysconfdir=%{_sysconfdir} install

%clean
[ "$RPM_BUILD_ROOT" != "/" ] && rm -rf $RPM_BUILD_ROOT


%files
%defattr(-, root, root)
%dir %{_datadir}/%{name}
%doc ChangeLog README COPYING COPYING.lib
%(dirname %{compdir})
%{_datadir}/%{name}/*
%{_bindir}/%{name}
%{_bindir}/modifyrepo
%{_bindir}/mergerepo
%{_mandir}/man8/createrepo.8*
%{_mandir}/man1/modifyrepo.1*
%{_mandir}/man1/mergerepo.1*
%{python_sitelib}/createrepo

%changelog
* Fri Sep  9 2011 Seth Vidal <skvidal at fedoraproject.org>
- add lzma dep

* Wed Jan 26 2011 Seth Vidal <skvidal at fedoraproject.org>
- bump to 0.9.9
- add worker.py

* Thu Aug 19 2010 Seth Vidal <skvidal at fedoraproject.org>
- increase yum requirement for the modifyrepo use of RepoMD, RepoData and RepoMDError

* Fri Aug 28 2009 Seth Vidal <skvidal at fedoraproject.org>
- 0.9.8

* Tue Mar 24 2009 Seth Vidal <skvidal at fedoraproject.org>
- 0.9.7

* Fri Oct 17 2008 Seth Vidal <skvidal at fedoraproject.org>
- add mergerepo -  0.9.6

* Mon Feb 18 2008 Seth Vidal <skvidal at fedoraproject.org>
- 0.9.5

* Mon Jan 28 2008 Seth Vidal <skvidal at fedoraproject.org>
- 0.9.4

* Tue Jan 22 2008 Seth Vidal <skvidal at fedoraproject.org>
- 0.9.3

* Thu Jan 17 2008 Seth Vidal <skvidal at fedoraproject.org>
- significant api changes

* Tue Jan  8 2008 Seth Vidal <skvidal at fedoraproject.org>
- 0.9.1 - lots of fixes
- cleanup changelog, too

* Thu Dec 20 2007 Seth Vidal <skvidal at fedoraproject.org>
- beginning of the new version

