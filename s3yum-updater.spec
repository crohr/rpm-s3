Name: s3yum-updater
Version: 1.0
Release: 1
Summary: Daemon script for updating an s3-hosted yum repository
Group: System Environment/Daemons
License: BSD
URL: https://github.com/rockpack/s3yum-updater
Source0: https://github.com/rockpack/s3yum-updater/archive/master.tar.gz

BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
BuildArch: noarch
Requires: createrepo python-daemon python-boto python-simplejson
Requires(post): chkconfig initscripts
Requires(pre): chkconfig initscripts

%description
A script that listens for SNS/SQS notifications of newly uploaded
packages on an s3-host yum repository.  On notification, the daemon
will update the repodata.

%prep
%setup -q -n s3yum-updater-master

%install
rm -rf %{buildroot}
%{__install} -D -m755 repoupdate-daemon.init \
	%{buildroot}%{_sysconfdir}/rc.d/init.d/repoupdate-daemon
%{__install} -D -m755 repoupdate-daemon.py \
	%{buildroot}%{_bindir}/repoupdate-daemon
%{__install} -D -m755 publish-packages.py \
	%{buildroot}%{_bindir}/publish-packages

%clean
rm -rf %{buildroot}

%post
/sbin/chkconfig --add repoupdate-daemon

%preun
if [ $1 -eq 0 ]; then
	/sbin/service repoupdate-daemon stop >/dev/null 2>&1
	/sbin/chkconfig --del repoupdate-daemon
fi

%files
%defattr(-,root,root,-)
%doc README.md LICENSE
%{_sysconfdir}/rc.d/init.d/*
%{_bindir}/*

%changelog
* Thu Jan 31 2013 Paul Egan <paulegan@rockpack.com> - 1.0-1
- Initial release

