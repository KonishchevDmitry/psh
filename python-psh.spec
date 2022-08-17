%if 0%{?fedora} > 12 || 0%{?epel} >= 6
%bcond_without python3
%else
%bcond_with python3
%endif

%if 0%{?epel} >= 7
%bcond_without python3_other
%endif

%if 0%{?rhel} <= 6
%{!?__python2: %global __python2 /usr/bin/python2}
%{!?python2_sitelib: %global python2_sitelib %(%{__python2} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}
%endif
%if 0%{with python3}
%{!?__python3: %global __python3 /usr/bin/python3}
%{!?python3_sitelib: %global python3_sitelib %(%{__python3} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}
%{!?python3_pkgversion: %global python3_pkgversion 3}
%endif  # with python3

# Enable building of doc package
%if 0%{?rhel} && 0%{?rhel} <= 6
%bcond_with docs
%else
%bcond_without docs
%endif

%bcond_without check

%global project_name psh
%global project_description %{expand:
psh allows you to spawn processes in Unix shell-style way.

Unix shell is very convenient for spawning processes, connecting them into
pipes, etc., but it has a very limited language which is often not suitable
for writing complex programs. Python is a very flexible and reach language
which is used in a wide variety of application domains, but its standard
subprocess module is very limited. psh combines the power of Python language
and an elegant shell-style way to execute processes.}

Name:    python-%project_name
Version: 0.2.12
Release: 1%{?dist}
Summary: Process management library

Group:   Development/Languages
License: MIT
URL:     https://konishchevdmitry.github.io/%project_name/
Source:  http://pypi.python.org/packages/source/p/%project_name/%project_name-%version.tar.gz

BuildArch:     noarch
BuildRequires: make
BuildRequires: python2-devel python-setuptools

%if 0%{with check}
BuildRequires: procps
BuildRequires: python-pcore
BuildRequires: python-psys >= 0.3
BuildRequires: pytest >= 2.2.4
%endif  # with check

%if 0%{with docs}
BuildRequires: python-pcore, python-psys >= 0.3, python-sphinx
%endif  # with docs

Requires: python-pcore, python-psys >= 0.3

%description %{project_description}


%if 0%{with python3}
%package -n python%{python3_pkgversion}-%project_name
Summary: %{summary}
Requires: python%{python3_pkgversion}-pcore
Requires: python%{python3_pkgversion}-psys >= 0.3
BuildRequires: python%{python3_pkgversion}-devel
BuildRequires: python%{python3_pkgversion}-setuptools
%if 0%{with check}
BuildRequires: python%{python3_pkgversion}-pcore
BuildRequires: python%{python3_pkgversion}-psys >= 0.3
BuildRequires: python%{python3_pkgversion}-pytest >= 2.2.4
%endif

%description -n python%{python3_pkgversion}-%project_name %{project_description}
%endif  # with python3


%if 0%{with python3_other}
%package -n python%{python3_other_pkgversion}-%project_name
Summary: %{summary}
Requires: python%{python3_other_pkgversion}-pcore
Requires: python%{python3_other_pkgversion}-psys >= 0.3
BuildRequires: python%{python3_other_pkgversion}-devel
BuildRequires: python%{python3_other_pkgversion}-setuptools
%if 0%{with check}
BuildRequires: python%{python3_other_pkgversion}-pcore
BuildRequires: python%{python3_other_pkgversion}-psys >= 0.3
BuildRequires: python%{python3_other_pkgversion}-pytest >= 2.2.4
%endif

%description -n python%{python3_other_pkgversion}-%project_name %{project_description}
%endif  # with python3_other


%if 0%{with docs}
%package doc
Summary: Documentation for psh
Group: Development/Languages
Requires: %name = %version-%release

%description doc
Documentation for psh
%endif  # with docs


%prep
%setup -n %project_name-%version -q


%build
make PYTHON=%{__python2}
%if %{with python3}
make PYTHON=%{__python3}
%endif  # with python3
%if 0%{with python3_other}
make PYTHON=%{__python3_other}
%endif  # with python3_other


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
%if 0%{with python3_other}
%{__python3_other} setup.py test
%endif  # with python3_other
%endif  # with check


%install
[ "%buildroot" = "/" ] || rm -rf "%buildroot"

make PYTHON=%{__python2} INSTALL_FLAGS="-O1 --root '%buildroot'" install
%if %{with python3}
make PYTHON=%{__python3} INSTALL_FLAGS="-O1 --root '%buildroot'" install
%endif  # with python3
%if 0%{with python3_other}
make PYTHON=%{__python3_other} INSTALL_FLAGS="-O1 --root '%buildroot'" install
%endif  # with python3_other


%files
%defattr(-,root,root,-)
%{python2_sitelib}/psh
%{python2_sitelib}/psh-*.egg-info
%doc ChangeLog INSTALL README.rst

%if 0%{with python3}
%files -n python%{python3_pkgversion}-%project_name
%defattr(-,root,root,-)
%{python3_sitelib}/psh
%{python3_sitelib}/psh-*.egg-info
%doc ChangeLog INSTALL README.rst
%endif  # with python3

%if 0%{with python3_other}
%files -n python%{python3_other_pkgversion}-%project_name
%defattr(-,root,root,-)
%{python3_other_sitelib}/psh
%{python3_other_sitelib}/psh-*.egg-info
%doc ChangeLog INSTALL README.rst
%endif  # with python3_other

%if 0%{with docs}
%files doc
%defattr(-,root,root,-)
%doc doc/_build/html
%endif  # with docs


%clean
[ "%buildroot" = "/" ] || rm -rf "%buildroot"


%changelog
* Wed Aug 17 2022 Dmitry Konishchev <konishchev@gmail.com> - 0.2.12-1
- New version

* Fri Apr 15 2022 Dmitry Konishchev <konishchev@gmail.com> - 0.2.11-1
- Add missing O_TRUNC to file creation mode

* Wed Jul 28 2021 Dmitry Konishchev <konishchev@gmail.com> - 0.2.10-1
- Change documentation URL

* Sun Feb 10 2019 Mikhail Ushanov <gm.mephisto@gmail.com> - 0.2.8-2
- Add python3 package build for EPEL

* Fri Sep 07 2018 Dmitry Konishchev <konishchev@gmail.com> - 0.2.8-1
- New version.

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
