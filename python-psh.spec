%if 0%{?fedora} > 12 || 0%{?rhel} > 7
%bcond_without python3
%else
%bcond_with python3
%endif

%if 0%{?rhel} && 0%{?rhel} <= 6
%{!?__python2: %global __python2 /usr/bin/python2}
%{!?python2_sitelib: %global python2_sitelib %(%{__python2} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}
%endif
%if %{with python3}
%{!?__python3: %global __python3 /usr/bin/python3}
%{!?python3_sitelib: %global python3_sitelib %(%{__python3} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}
%endif  # with python3

# Enable building of doc package
%if 0%{?rhel} && 0%{?rhel} <= 6
%bcond_with docs
%else
%bcond_without docs
%endif

# Run tests
%bcond_without check

Name:    python-psh
Version: 0.2.5
Release: 1%{?dist}
Summary: Process management library

Group:   Development/Languages
License: GPLv3
URL:     http://konishchevdmitry.github.com/psh/
Source:  http://pypi.python.org/packages/source/p/psh/psh-%version.tar.gz

BuildArch:     noarch
BuildRequires: make
BuildRequires: python2-devel python-setuptools
%if 0%{with python3}
BuildRequires: python3-devel python3-setuptools
%endif  # with python3

%if 0%{with check}
BuildRequires: procps
BuildRequires: python-pcore, python-psys >= 0.3, pytest >= 2.2.4
%if 0%{with python3}
BuildRequires: python3-pcore, python3-psys >= 0.3, python3-pytest >= 2.2.4
%endif  # with python3
%endif  # with check

%if 0%{with docs}
BuildRequires: python-pcore, python-psys >= 0.3, python-sphinx
%endif  # with docs

Requires: python-pcore, python-psys >= 0.3

%description
psh allows you to spawn processes in Unix shell-style way.

Unix shell is very convenient for spawning processes, connecting them into
pipes, etc., but it has a very limited language which is often not suitable
for writing complex programs. Python is a very flexible and reach language
which is used in a wide variety of application domains, but its standard
subprocess module is very limited. psh combines the power of Python language
and an elegant shell-style way to execute processes.


%if 0%{with python3}
%package -n python3-psh
Summary: Process management library

Requires: python3-pcore, python3-psys >= 0.3

%description -n python3-psh
psh allows you to spawn processes in Unix shell-style way.

Unix shell is very convenient for spawning processes, connecting them into
pipes, etc., but it has a very limited language which is often not suitable
for writing complex programs. Python is a very flexible and reach language
which is used in a wide variety of application domains, but its standard
subprocess module is very limited. psh combines the power of Python language
and an elegant shell-style way to execute processes.
%endif  # with python3


%if 0%{with docs}
%package doc
Summary: Documentation for psh
Group: Development/Languages
Requires: %name = %version-%release

%description doc
Documentation for psh
%endif  # with docs


%prep
%setup -n psh-%version -q


%build
make PYTHON=%{__python2}
%if %{with python3}
make PYTHON=%{__python3}
%endif  # with python3


%if 0%{with docs}
make doc
rm doc/_build/html/.buildinfo
%endif  # with docs


%check
%if 0%{with check}
%{__python2} setup.py test
%if 0%{with python3}
%{__python3} setup.py test
%endif  # with python3
%endif  # with check


%install
[ "%buildroot" = "/" ] || rm -rf "%buildroot"

make PYTHON=%{__python2} INSTALL_FLAGS="-O1 --root '%buildroot'" install
%if %{with python3}
make PYTHON=%{__python3} INSTALL_FLAGS="-O1 --root '%buildroot'" install
%endif  # with python3


%files
%defattr(-,root,root,-)
%{python2_sitelib}/psh
%{python2_sitelib}/psh-*.egg-info
%doc ChangeLog INSTALL README.rst

%if 0%{with python3}
%files -n python3-psh
%defattr(-,root,root,-)
%{python3_sitelib}/psh
%{python3_sitelib}/psh-*.egg-info
%doc ChangeLog INSTALL README.rst
%endif  # with python3

%if 0%{with docs}
%files doc
%defattr(-,root,root,-)
%doc doc/_build/html
%endif  # with docs


%clean
[ "%buildroot" = "/" ] || rm -rf "%buildroot"


%changelog
* Thu Sep 24 2015 Dmitry Konishchev <konishchev@gmail.com> - 0.2.5-1
- New version.

* Mon Nov 18 2013 Dmitry Konishchev <konishchev@gmail.com> - 0.2.4-1
- New version.

* Fri Jun 28 2013 Dmitry Konishchev <konishchev@gmail.com> - 0.2.3-2
- Don't remove *.egg-info to make setup.py with entry_points work

* Fri Dec 21 2012 Dmitry Konishchev <konishchev@gmail.com> - 0.2.3-1
- New version.

* Thu Oct 25 2012 Dmitry Konishchev <konishchev@gmail.com> - 0.2.2-1
- New version.

* Tue Oct 23 2012 Dmitry Konishchev <konishchev@gmail.com> - 0.2.1-1
- New version.

* Mon Oct 22 2012 Dmitry Konishchev <konishchev@gmail.com> - 0.2-1
- New version.

* Fri Oct 12 2012 Dmitry Konishchev <konishchev@gmail.com> - 0.1-1
- New package.
