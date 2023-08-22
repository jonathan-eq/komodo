#!/usr/bin/env python

from typing import List

from komodo.yaml_file_type import ReleaseFileYamlString, RepositoryFileYamlString


def cleanup(repository_file: str, release_files: List[str]):
    with open(repository_file, "r", encoding="utf-8") as r:
        repository_file_yaml_string = r.read()
    repository = RepositoryFileYamlString.convert(repository_file_yaml_string)

    releases = []
    for file_name in release_files:
        with open(file_name, "r", encoding="utf-8") as f:
            release_file_yaml_string = f.read()
        release = ReleaseFileYamlString.convert(release_file_yaml_string)
        releases.append(release)

    registered_package_version_combinations = []
    for package in repository:
        for version in repository[package]:
            registered_package_version_combinations.append((package, version))

    seen_package_version_combinations = set()
    for release in releases:
        for package in release:
            seen_package_version_combinations.add((package, release[package]))

    seen_all = True
    for ver in registered_package_version_combinations:
        if ver not in seen_package_version_combinations:
            if seen_all:
                print("unused:")
                seen_all = False
            print(f"  - {ver[0]}: {ver[1]}")
    if seen_all:
        print("ok")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        exit("usage: komodo.cleanup repository.yml rel1.yml rel2.yml ... reln.yml")

    repository = sys.argv[1]
    releases = sys.argv[2:]
    cleanup(repository, releases)
