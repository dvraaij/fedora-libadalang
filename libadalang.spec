# The test suite is normally run. It can be disabled with "--without=check".
%bcond_without check

# Upstream source information.
%global upstream_owner    AdaCore
%global upstream_name     libadalang
%global upstream_version  22.0.0
%global upstream_gittag   v%{upstream_version}

Name:           libadalang
Version:        %{upstream_version}
Release:        1%{?dist}
Summary:        The Ada semantic analysis library

License:        GPL-3.0-only WITH GCC-exception-3.1

URL:            https://github.com/%{upstream_owner}/%{upstream_name}
Source:         %{url}/archive/%{upstream_gittag}/%{upstream_name}-%{upstream_version}.tar.gz

BuildRequires:  gcc-gnat gprbuild make sed
# A fedora-gnat-project-common that contains GPRbuild_flags is needed.
BuildRequires:  fedora-gnat-project-common >= 3.17
BuildRequires:  python3-devel
BuildRequires:  python3-e3-core
%if %{with check}
BuildRequires:  python3-e3-testsuite
%endif
BuildRequires:  python3-setuptools
BuildRequires:  python3-funcy
BuildRequires:  python3-mako
BuildRequires:  python3-jsonschema
BuildRequires:  python3-langkit

# Build only on architectures where GPRbuild is available.
ExclusiveArch:  %{GPRbuild_arches}

%global common_description_en \
Libadalang is a library for parsing and semantic analysis of Ada code. It is \
meant as a building block for integration into other tools. (IDE, static \
analyzers, etc.)

%description %{common_description_en}


#################
## Subpackages ##
#################

%package devel
Summary:    Development files for the Ada semantic analysis library
Requires:   %{name}%{?_isa} = %{version}-%{release}
Requires:   fedora-gnat-project-common
Requires:   gnatcoll-core-devel
Requires:   gnatcoll-gmp-devel
Requires:   gnatcoll-iconv-devel
Requires:   libgnatprj-devel
Requires:   xmlada-devel
Requires:   langkit-devel

# An additional provides to help users find the package.
Provides:   python3-%{name}

%description devel %{common_description_en}

This package contains source code and linking information for developing
applications that use the Ada semantic analysis library. It also contains
the C and Python API.


#############
## Prepare ##
#############

%prep
%autosetup -p1

# Generate the libadalang source code.
%python3 manage.py generate --library-types=relocatable --version='%{version}'

# ??? Version does not propagate into `setup.py`.
sed --in-place \
    --expression 's/version='\''0.1'\''/version='\''%{version}'\''/'\
    ./build/python/setup.py


###########
## Build ##
###########

%build

# As libadalang.gpr is generated and does not contain a Library_Version
# attribute, we set the soname manually, and create a proper symbolic
# link later, after running GPRinstall.
%global GPRbuild_flags_soname -largs -Wl,-soname=%{name}.so.%{version} -gargs

# Build the library.
gprbuild %{GPRbuild_flags} %{GPRbuild_flags_soname} \
         -XBUILD_MODE=prod -XLIBRARY_TYPE=relocatable \
         -P build/libadalang.gpr

# Additional flags to link the executables dynamically with the GNAT runtime
# and make the executables (tools) position independent.
%global GPRbuild_flags_pie -cargs -fPIC -largs -pie -bargs -shared -gargs

# Build the tools.
gprbuild %{GPRbuild_flags} %{GPRbuild_flags_pie} \
         -XBUILD_MODE=prod -XLIBRARY_TYPE=relocatable \
         -P build/mains.gpr

# Build the Python API.
pushd . && cd ./build/python
%py3_build
popd


#############
## Install ##
#############

%install

# Install the library.
gprinstall %{GPRinstall_flags} --no-build-var \
           -XBUILD_MODE=prod -XLIBRARY_TYPE=relocatable \
           -P build/libadalang.gpr

# Install the tools.
gprinstall --create-missing-dirs --no-build-var --no-manifest \
           --prefix=%{buildroot}%{_prefix} --mode=usage \
           -XBUILD_MODE=prod -XLIBRARY_TYPE=relocatable \
           -P build/mains.gpr

# Install the C API.
mkdir --parents %{buildroot}%{_includedir}
install --mode=u=rw,go=r --preserve-timestamps \
        --target-directory=%{buildroot}%{_includedir} \
        %{_builddir}/%{name}-%{version}/build/libadalang.h

# Install the Python API.
pushd . && cd ./build/python
%py3_install
popd

# Now we rename the library...
mv %{buildroot}%{_libdir}/%{name}.so \
   %{buildroot}%{_libdir}/%{name}.so.%{version}

# ...and create the symbolic link manually.
ln --symbolic --no-target-directory %{name}.so.%{version} %{buildroot}%{_libdir}/%{name}.so

# Make the generated usage project file architecture-independent.
sed --regexp-extended --in-place \
    '--expression=1i with "directories";' \
    '--expression=/^--  This project has been generated/d' \
    '--expression=s|^( *for +Source_Dirs +use +).*;$|\1(Directories.Includedir \& "/%{name}");|i' \
    '--expression=s|^( *for +Library_Dir +use +).*;$|\1Directories.Libdir;|i' \
    '--expression=s|^( *for +Library_ALI_Dir +use +).*;$|\1Directories.Libdir \& "/%{name}";|i' \
    %{buildroot}%{_GNAT_project_dir}/%{name}.gpr
# The Sed commands are:
# 1: Insert a with clause before the first line to import the directories
#    project.
# 2: Delete a comment that mentions the architecture.
# 3: Replace the value of Source_Dirs with a pathname based on
#    Directories.Includedir.
# 4: Replace the value of Library_Dir with Directories.Libdir.
# 5: Replace the value of Library_ALI_Dir with a pathname based on
#    Directories.Libdir.


###########
## Check ##
###########

%if %{with check}
%check

# Create an override for directories.gpr.
mkdir testsuite/multilib
cat << EOF > ./testsuite/multilib/directories.gpr
abstract project Directories is
   Libdir     := "%{buildroot}%{_libdir}";
   Includedir := "%{buildroot}%{_includedir}";
end Directories;
EOF

# Disable test that cannot be run on Fedora.
cat << EOF > testsuite/tests/dsl_unparse/test.yaml
control:
- [XFAIL, "True", "Assumes \"langkit\" checked out and built in the Libadalang repository"]
EOF

# Make the files installed in the buildroot and the override for directories.gpr
# visible to the test runner.
export PATH=%{buildroot}%{_bindir}:$PATH
export LIBRARY_PATH=%{buildroot}%{_libdir}:$LIBRARY_PATH
export LD_LIBRARY_PATH=%{buildroot}%{_libdir}:$LD_LIBRARY_PATH
export C_INCLUDE_PATH=%{buildroot}%{_includedir}:$C_INCLUDE_PATH
export GPR_PROJECT_PATH=${PWD}/testsuite/multilib:%{buildroot}%{_GNAT_project_dir}:$GPR_PROJECT_PATH
export PYTHONPATH=%{buildroot}%{python3_sitearch}:%{buildroot}%{python3_sitelib}:$PYTHONPATH

# Run the tests, but skip those for the OCaml API as we don't include it fow now.
%python3 ./manage.py test \
         --with-python=%python3 \
         --show-error-output \
         --max-consecutive-failures=4 \
         --disable-ocaml

%endif


###########
## Files ##
###########

%files
%license COPYING3 COPYING.RUNTIME
%doc README*
%{_libdir}/%{name}.so.%{version}
%{_bindir}/lal_parse
%{_bindir}/navigate
%{_bindir}/nameres
%{_bindir}/gnat_compare

%files devel
%{_GNAT_project_dir}/%{name}.gpr
%{_includedir}/%{name}
%dir %{_libdir}/%{name}
%attr(444,-,-) %{_libdir}/%{name}/*.ali
%{_libdir}/%{name}.so
# C API.
%{_includedir}/%{name}.h
# Python API.
%{python3_sitelib}/*.egg-info/
%{python3_sitelib}/%{name}/


###############
## Changelog ##
###############

%changelog
* Sun Sep 04 2022 Dennis van Raaij <dvraaij@fedoraproject.org> - 22.0.0-1
- New package.
