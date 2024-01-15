#!/usr/bin/env python

import hashlib
import itertools as itr
import os
import pathlib
import stat
import sys
from pathlib import Path
from typing import Dict

import requests

from komodo.package_version import (
    LATEST_PACKAGE_ALIAS,
    latest_pypi_version,
    strip_version,
)
from komodo.shell import pushd, shell

flatten = itr.chain.from_iterable


def dfs(package_name: str, ver: str, pkgs: Dict[str, str], repo: Dict[str, Dict]):
    # package has no more dependencies - add the package itself
    if "depends" not in repo[package_name][ver]:
        return [package_name]

    if not all(map(pkgs.__contains__, repo[package_name][ver]["depends"])):
        print(
            "error: "
            + ",".join(repo[package_name][ver]["depends"])
            + " required as dependency, is not in distribution",
            file=sys.stderr,
        )
        sys.exit(1)

    # dependencies can change based on version (i.e. version 2 depends on
    # package X, but version 3 depends on X and Y)
    dependencies = [
        dfs(x, pkgs[x], pkgs, repo) for x in repo[package_name][ver]["depends"]
    ]
    dependencies.append([package_name])
    return flatten(dependencies)


def rpm(package_name, ver, pkgpath, prefix):
    # cpio always outputs to cwd, can't be overriden with switches
    with pushd(prefix):
        print(f"Installing {package_name} ({ver}) from rpm")
        shell(f"rpm2cpio {pkgpath}.rpm | cpio -imd --quiet")
        shell("rsync -a usr/* .")
        shell("rm -rf usr")


# When running cmake we pass the option -DDEST_PREFIX=fakeroot, this is an
# absolute hack to be able to build opm-common and sunbeam with the ~fakeroot
# implementation used by komodo.
#
# See sunbeam/CMakeLists.txt for a more detailed description of the issue.
# When/if the opm project updates the generated opm-common-config.cmake to work
# with "make DESTDIR=" the DEST_PREFIX cmake flag can be removed.


def cmake(
    package_name,
    ver,
    pkgpath,
    prefix,
    builddir,
    makeopts,
    jobs,
    fakeroot,
    ld_lib_path=None,
    bin_path=None,
    cmake="cmake",
):
    bdir = f"{package_name}-{ver}-build"
    if builddir is not None:
        bdir = os.path.join(builddir, bdir)

    fakeprefix = fakeroot + prefix

    flags = [
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DBOOST_ROOT={fakeprefix}",
        "-DBUILD_SHARED_LIBS=ON",
        f"-DCMAKE_PREFIX_PATH={fakeprefix}",
        f"-DCMAKE_MODULE_PATH={fakeprefix}/share/cmake/Modules",
        f"-DCMAKE_INSTALL_PREFIX={prefix}",
        f"-DDEST_PREFIX={fakeroot}",
    ]

    Path(bdir).mkdir(parents=True, exist_ok=True)
    with pushd(bdir):
        os.environ["LD_LIBRARY_PATH"] = ld_lib_path
        _pre_PATH = os.environ["PATH"]  # pylint: disable=invalid-name
        os.environ["PATH"] = bin_path

        print(f"Installing {package_name} ({ver}) from source with cmake")
        shell([cmake, pkgpath, *flags, makeopts])
        print(shell(f"make -j{jobs}"))
        print(shell(f"make DESTDIR={fakeroot} install"))

        del os.environ["LD_LIBRARY_PATH"]
        os.environ["PATH"] = _pre_PATH


def sh(
    package_name,
    ver,
    pkgpath,
    data,
    prefix,
    makefile,
    fakeroot,
    pythonpath,
    bin_path,
    pip,
    virtualenv,
    ld_lib_path,
    jobs=None,
    cmake=None,
    makeopts=None,
):  # pylint: disable=invalid-name
    makefile = data.get(makefile)

    with pushd(pkgpath):
        cmd = [
            f"bash {makefile} --prefix {prefix}",
            f"--fakeroot {fakeroot}",
            f"--python {prefix}/bin/python",
        ]
        if jobs:
            cmd.append(f"--jobs {jobs}")
        if cmake:
            cmd.append(f"--cmake {cmake}")
        cmd.append(f"--pythonpath {pythonpath}")
        cmd.append(f"--path {bin_path}")
        cmd.append(f"--pip {pip}")
        cmd.append(f"--virtualenv {virtualenv}")
        cmd.append(f"--ld-library-path {ld_lib_path}")
        cmd.append(makeopts)

        print(f"Installing {package_name} ({ver}) from sh")
        shell(cmd)


def rsync(package_name, ver, pkgpath, prefix, fakeroot, makeopts=None):
    print(f"Installing {package_name} ({ver}) with rsync")
    # assume a root-like layout in the pkgpath dir, and just copy it
    shell(
        [
            "rsync -am",
            makeopts,
            f"{pkgpath}/",
            fakeroot + prefix,
        ],
    )


def download(package_name, ver, prefix, url, hash_str, fakeroot, destination):
    print(f"Installing {package_name} ({ver}) with download")

    if not url.startswith("https"):
        msg = f"{url} does not use https:// protocol"
        raise ValueError(msg)

    hash_type, hash_value = hash_str.split(":")
    if hash_type != "sha256":
        msg = f"Hash type {hash_type} given - only sha256 implemented"
        raise NotImplementedError(
            msg,
        )

    fakeprefix = pathlib.Path(fakeroot + prefix)
    dest_path = fakeprefix / destination

    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=20))
    response = session.get(url, stream=True)

    if response.status_code != 200:
        msg = f"GET request to {url} returned status code {response.status_code}"
        raise RuntimeError(
            msg,
        )

    sha256 = hashlib.sha256()

    with open(dest_path, "wb") as file_handle:
        for chunk in response.iter_content(chunk_size=1024):
            file_handle.write(chunk)
            sha256.update(chunk)

    if sha256.hexdigest() != hash_value:
        msg = f"Hash of downloaded file ({sha256.hexdigest()}) not equal to expected hash."
        raise ValueError(
            msg,
        )

    # Add executable permission if in bin folder:
    if "bin" in dest_path.parts:
        dest_path.chmod(
            dest_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
        )


def pip_install(package_name, ver, prefix, dlprefix, fakeroot, pip="pip", makeopts=""):
    ver = strip_version(ver)
    if ver == LATEST_PACKAGE_ALIAS:
        ver = latest_pypi_version(package_name)
    cmd = [
        pip,
        f"install {package_name}=={strip_version(ver)}",
        f"--root {fakeroot}",
        f"--prefix {prefix}",
        "--no-index",
        "--no-deps",
        "--ignore-installed",
        f"--cache-dir {dlprefix}",
        f"--find-links {dlprefix}",
        makeopts,
    ]

    print(f"Installing {package_name} ({ver}) from pip")
    shell(cmd)


def noop(package_name, ver):
    print(f"Doing nothing for noop package {package_name} ({ver})")


def pypaths(prefix, version):
    if version is None:
        return ""
    pyver = "python" + ".".join(version.split(".")[:-1])
    return ":".join(
        [
            f"{prefix}/lib/{pyver}",
            f"{prefix}/lib/{pyver}/site-packages",
            f"{prefix}/lib64/{pyver}/site-packages",
        ],
    )


def make(
    pkgs: Dict[str, str],
    repo,
    data,
    prefix,
    dlprefix=None,
    builddir=None,
    jobs=1,
    cmk="cmake",
    pip="pip",
    virtualenv=None,
    fakeroot=".",
):
    packages_needed = flatten(dfs(pkg, ver, pkgs, repo) for pkg, ver in pkgs.items())

    seen_package = set()
    pkgorder = []
    for package_needed in packages_needed:
        if package_needed in seen_package:
            continue
        seen_package.add(package_needed)
        pkgorder.append(package_needed)

    fakeprefix = fakeroot + prefix
    shell(["mkdir -p", fakeprefix])
    prefix = os.path.abspath(prefix)

    # assuming there always is a python *and* that python will be installed
    # before pip is required. This dependency *must* be explicit in the
    # repository
    os.environ["DESTDIR"] = fakeroot
    os.environ["BOOST_ROOT"] = fakeprefix
    ld_lib_path = ":".join(
        filter(
            None,
            [
                os.path.join(fakeprefix, "lib"),
                os.path.join(fakeprefix, "lib64"),
                os.environ.get("LD_LIBRARY_PATH"),
            ],
        ),
    )
    extra_makeopts = os.environ.get("EXTRA_MAKEOPTS")
    build_pythonpath = pypaths(fakeprefix, pkgs.get("python"))
    bin_path = ":".join([os.path.join(fakeprefix, "bin"), os.environ["PATH"]])

    pkgpaths = [f"{package_name}-{pkgs[package_name]}" for package_name in pkgorder]
    if dlprefix:
        pkgpaths = [os.path.join(dlprefix, path) for path in pkgpaths]

    def resolve(input_str):
        return input_str.replace("$(prefix)", prefix)

    for package_name, path in zip(pkgorder, pkgpaths):
        ver = pkgs[package_name]
        current = repo[package_name][ver]
        make = current["make"]
        pkgpath = os.path.abspath(path)

        download_keys = ["url", "destination", "hash"]
        if any(key in current for key in download_keys) and make != "download":
            raise ValueError(
                ", ".join(download_keys) + " only valid with 'make: download'",
            )
        if not all(key in current for key in download_keys) and make == "download":
            raise ValueError(
                ", ".join(download_keys) + " all required with 'make: download'",
            )

        if "pypi_package_name" in current and make != "pip":
            msg = "pypi_package_name is only valid when building with pip"
            raise ValueError(msg)

        package_name = current.get("pypi_package_name", package_name)

        makeopts = current.get("makeopts", "")
        if extra_makeopts:
            makeopts = f"{makeopts} {extra_makeopts}"
        makeopts = resolve(makeopts)

        if make == "rpm":
            rpm(package_name=package_name, ver=ver, pkgpath=pkgpath, prefix=prefix)
        if make == "cmake":
            cmake(
                package_name=package_name,
                ver=ver,
                pkgpath=pkgpath,
                prefix=prefix,
                builddir=builddir,
                makeopts=makeopts,
                jobs=jobs,
                fakeroot=fakeroot,
                ld_lib_path=ld_lib_path,
                bin_path=bin_path,
                cmake=cmk,
            )
        elif make == "pip":
            pip_install(
                package_name=package_name,
                ver=ver,
                prefix=prefix,
                dlprefix=dlprefix,
                fakeroot=fakeroot,
                pip=pip,
                makeopts=makeopts,
            )
        elif make == "sh":
            sh(
                package_name=package_name,
                ver=ver,
                pkgpath=pkgpath,
                data=data,
                prefix=prefix,
                makefile=current.get("makefile"),
                fakeroot=fakeroot,
                pythonpath=build_pythonpath,
                bin_path=bin_path,
                pip=pip,
                virtualenv=virtualenv,
                ld_lib_path=ld_lib_path,
                jobs=jobs,
                cmake=cmk,
                makeopts=makeopts,
            )
        elif make == "rsync":
            rsync(
                package_name=package_name,
                ver=ver,
                pkgpath=pkgpath,
                prefix=prefix,
                fakeroot=fakeroot,
                makeopts=makeopts,
            )
        elif make == "noop":
            noop(package_name=package_name, ver=ver)
        elif make == "download":
            download(
                package_name=package_name,
                ver=ver,
                prefix=prefix,
                url=current.get("url"),
                hash_str=current.get("hash"),
                fakeroot=fakeroot,
                destination=current.get("destination"),
            )
        else:
            raise ValueError(f"Non-supported make: {make}")
