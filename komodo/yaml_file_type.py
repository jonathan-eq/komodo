import argparse
import os
from pathlib import Path
from typing import Dict

import yaml as yml


class YamlFile(argparse.FileType):
    def __init__(self, *args, **kwargs):
        super().__init__("r", *args, **kwargs)

    def __call__(self, value):
        file_handle = super().__call__(value)
        yaml = yml.safe_load(file_handle)
        file_handle.close()
        return yaml


class YamlString(dict):
    def __call__(self, value: bytes) -> dict:
        yaml = yml.safe_load(value)
        return yaml


class ReleaseFile(YamlFile):
    """
    Return the data from 'release' YAML, but validate it first.
    """

    def __call__(self, value: str) -> Dict[str, str]:
        yaml = super().__call__(value)
        message = (
            "The file you provided does not appear to be a release file "
            "produced by komodo. It may be a release file. Release files "
            "have a format like the following:\n\n"
            'python: 3.8.6-builtin\nsetuptools: 68.0.0\nwheel: 0.40.0\nzopfli: "0.3"'
        )
        for package_name, package_version in yaml.items():
            assert isinstance(package_name, str), (
                f"INVALID PACKAGE_NAME {package_name}\n" + message
            )
            assert isinstance(package_version, str), (
                f"INVALID PACKAGE_VERSION {package_version}\n" + message
            )
        return yaml


class ReleaseDir:
    def __call__(self, value: str) -> Dict[str, YamlFile]:
        if not os.path.isdir(value):
            raise NotADirectoryError(value)
        result = {}
        for yml_file in Path(value).glob("*.yml"):
            result.update(ReleaseFile()(yml_file))
        return result


class ManifestFile(YamlFile):
    """
    Return the data from 'manifest' YAML, but validate it first.
    """

    def __call__(self, value: str) -> Dict[str, Dict[str, str]]:
        yaml = super().__call__(value)
        message = (
            "The file you provided does not appear to be a manifest file "
            "produced by komodo. It may be a release file. Manifest files "
            "have a format like the following:\n\n"
            "python:\n  maintainer: foo@example.com\n  version: 3-builtin\n"
            "treelib:\n  maintainer: foo@example.com\n  version: 1.6.1\n"
        )
        for _, metadata in yaml.items():
            assert isinstance(metadata, dict), message
            assert isinstance(metadata["version"], str), message
        return yaml


class RepositoryFile(YamlFile):
    """
    Return the data from 'repository' YAML, but validate it first.
    """

    def __call__(self, value: str) -> Dict[str, Dict[str, str]]:
        yaml = super().__call__(value)
        message = (
            "The file you provided does not appear to be a repository file "
            "produced by komodo. It may be a release file. Repository files "
            "have a format like the following:\n\n"
            "pytest-runner:\n  6.0.0:\n    make: pip\n    "
            "maintainer: scout\n    depends:\n      - wheel\n      - "
            "setuptools\n      - python\n\npython:\n  3.8:\n    ..."
        )
        for package_name, versions in yaml.items():
            assert isinstance(package_name, str), message
            assert isinstance(versions, dict), message
            for version_id, version_metadata in versions.items():
                assert isinstance(version_id, str), f"bad version_id {version_id}"
                assert "make" in version_metadata.keys(), message
                assert "maintainer" in version_metadata.keys(), message
        return yaml


class UpgradeProposalsFile(YamlFile):
    """
    Return the data from 'upgrade_proposals' YAML, but validate it first.
    """

    def __call__(self, value: str) -> Dict[str, Dict[str, str]]:
        yaml = super().__call__(value)
        message = (
            "The file you provided does not appear to be a upgrade_proposals file "
            "produced by komodo. It may be a release file. Upgrade_proposals files "
            "have a format like the following:\n\n"
            "2022-08:\n  libecalc: 8.2.9\n2022-09  python: 3.9\n  zopfli: 0.3"
        )
        for release_version, packages_to_upgrade in yaml.items():
            assert isinstance(release_version, str), message
            assert isinstance(
                packages_to_upgrade, (Dict[str, str], type(None))
            ), message
        return yaml


class UpgradeProposalsYamlString:
    """
    Return the data from yaml string representation of 'upgrade_proposals', but validate it first.
    """

    @staticmethod
    def convert(value):
        yaml = yml.safe_load(value)
        message = (
            "The string you provided does not appear to be of upgrade_proposals format "
            "produced by komodo. It may be a release file. Upgrade_proposals files "
            "have a format like the following:\n\n"
            "2022-08:\n  libecalc: 8.2.9\n2022-09:\n  python: 3.9\n  zopfli: 0.3"
        )
        for release_version, packages_to_upgrade in yaml.items():
            assert isinstance(release_version, str), message
            if packages_to_upgrade is not None:
                for package_name, package_version in packages_to_upgrade.items():
                    assert isinstance(package_name, str), (
                        "Package name '{package_name}' has to be of type string\n"
                        + message
                    )
                    assert isinstance(package_version, str), (
                        f"Package version of '{package_name}' has to be of type string ({package_version})\n"
                        + message
                    )
        return yaml


class ReleaseFileYamlString:
    """
    Return the data from 'release' YAML, but validate it first.
    """

    @staticmethod
    def convert(value: bytes) -> Dict[str, str]:
        yaml = yml.safe_load(value)
        message = (
            "The file you provided does not appear to be a release file "
            "produced by komodo. It may be a release file. Release files "
            "have a format like the following:\n\n"
            """python: 3.8.6-builtin\nsetuptools: 68.0.0\nwheel: 0.40.0\nzopfli: "0.3" """
        )
        for package_name, package_version in yaml.items():
            assert isinstance(package_name, str), (
                f"INVALID PACKAGE_NAME {package_name}\n" + message
            )
            assert isinstance(package_version, str), (
                f"Package version of '{package_name}' has to be of type string ({package_version})\n"
                + message
            )
        return yaml


class RepositoryFileYamlString:
    """
    Return the data from 'repository' YAML, but validate it first.
    """

    @staticmethod
    def convert(value: bytes) -> Dict[str, Dict[str, str]]:
        yaml = yml.safe_load(value)
        message = (
            "The file you provided does not appear to be a repository file "
            "produced by komodo. It may be a release file. Repository files "
            "have a format like the following:\n\n"
            "pytest-runner:\n  6.0.0:\n    make: pip\n    "
            "maintainer: scout\n    depends:\n      - wheel\n      - "
            "setuptools\n      - python\n\npython:\n  3.8:\n    ..."
        )
        for package_name, versions in yaml.items():
            assert isinstance(package_name, str), (
                "Package name '{package_name}' has to be of type string" + message
            )
            assert isinstance(versions, dict), message
            for package_version in versions.keys():
                assert isinstance(package_version, str), (
                    f"Package version of '{package_name}' has to be of type string ({package_version}) \n"
                    + message
                )
        return yaml
