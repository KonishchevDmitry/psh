%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}

# Enable building of doc package
%global with_docs 1

# Run tests
%global with_check 1

Name:    python-psh
Version: 0.2.1
Release: 1%{?dist}
Summary: Process management library

Group:   Development/Languages
License: GPLv3
URL:     http://konishchevdmitry.github.com/psh/
Source:  http://pypi.python.org/packages/source/p/psh/psh-%{version}.tar.gz

BuildArch:     noarch
BuildRequires: python-setuptools
%if 0%{?with_check}
BuildRequires: pytest >= 2.2.4
%endif
%if 0%{?with_docs}
BuildRequires: make, python-sphinx
%endif

%description
psh allows you to spawn processes in Unix shell-style way.

Unix shell is very convenient for spawning processes, connecting them into
pipes, etc., but it has a very limited language which is often not suitable
for writing complex programs. Python is a very flexible and reach language
which is used in a wide variety of application domains, but its standard
subprocess module is very limited. psh combines the power of Python language
and an elegant shell-style way to execute processes.


%if 0%{?with_docs}
%package doc
Summary: Documentation for psh
Group: Development/Languages
Requires: %name = %version-%release

%description doc
Documentation for psh
%endif


%prep
%setup -n psh-%{version} -q


%build
%{__python} setup.py build

%if 0%{?with_docs}
make doc
rm doc/_build/html/.buildinfo
%endif


%if 0%{?with_check}
%check
%{__python} setup.py test
%endif


%install
[ %buildroot = "/" ] || rm -rf %buildroot

%{__python} setup.py install -O1 --skip-build --root %{buildroot}
find %buildroot/ -name '*.egg-info' -exec rm -rf -- '{}' '+'


%files
%defattr(-,root,root,-)
%{python_sitelib}/pcore
%{python_sitelib}/psh
%{python_sitelib}/psys

%if 0%{?with_docs}
%files doc
%defattr(-,root,root,-)
%doc doc/_build/html
%endif


%clean
[ %buildroot = "/" ] || rm -rf %buildroot


%changelog
* Tue Oct 23 2012 Dmitry Konishchev <konishchev@gmail.com> - 0.2.1-1
- New version.

* Mon Oct 22 2012 Dmitry Konishchev <konishchev@gmail.com> - 0.2-1
- New version.

* Fri Oct 12 2012 Dmitry Konishchev <konishchev@gmail.com> - 0.1-1
- New package.
