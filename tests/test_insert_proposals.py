from base64 import b64encode
from unittest import mock

import github
import pytest
import yaml

from komodo.insert_proposals import insert_proposals

VALID_REPOSITORY_CONTENT = {
    "addlib": {
        "1.1.3": {"source": "pypi", "make": "pip", "maintainer": "scout"},
        "1.1.2": {"source": "pypi", "make": "pip", "maintainer": "scout"},
        "1.1.1": {"source": "pypi", "make": "pip", "maintainer": "scout"},
    },
    "testlib2": {
        "3.7": {"source": "pypi", "make": "pip", "maintainer": "scout"},
        "1.1.2": {"source": "pypi", "make": "pip", "maintainer": "scout"},
        "1.1.1": {"source": "pypi", "make": "pip", "maintainer": "scout"},
    },
}


class MockContent(object):
    def __init__(self, dicty):
        self.sha = "testsha"
        self.content = b64encode(yaml.dump(dicty).encode())


class MockRepo(object):
    existing_branches = ["git_ref", "2222.22.rc1", "2222.22.rc2"]

    def __init__(self, files):
        self.files = files
        self.updated_files = {}
        self.created_pulls = {}

    def get_contents(self, filename, ref):
        if filename in self.files:
            return MockContent(self.files[filename])
        else:
            raise ValueError(f"unexpected call with file {filename}")

    def get_branch(self, ref):
        if ref in MockRepo.existing_branches:
            o = mock.Mock()
            o.commit.sha = "testsha1"
            return o
        else:
            raise github.GithubException(None, None, None)

    def create_git_ref(self, ref, sha):
        o = mock.Mock()
        return o

    def create_file(self, target_file, msg, content, branch):
        assert target_file not in self.updated_files
        self.updated_files[target_file] = {
            "content": yaml.load(content, Loader=yaml.CLoader),
            "branch": branch,
        }

    def update_file(self, target_file, msg, content, sha, branch):
        assert target_file not in self.updated_files
        self.updated_files[target_file] = {
            "content": yaml.load(content, Loader=yaml.CLoader),
            "branch": branch,
        }

    def create_pull(self, title, body, head, base):
        o = mock.Mock()
        self.created_pulls[title] = {"head": head}
        return o


@pytest.mark.parametrize(
    "base, target, repo_files, changed_files, prs, return_type, error_message",
    [
        pytest.param(
            "1111.11.rc1",
            "1111.11.rc2",
            {
                "releases/matrices/1111.11.rc1.yml": {
                    "testlib1": "1.1.1",
                    "testlib2": "1.1.1",
                },
                "upgrade_proposals.yml": {
                    "1111-11": None,
                    "1111-12": {"testlib2": "ignore"},
                },
                "repository.yml": VALID_REPOSITORY_CONTENT,
            },
            {
                "releases/matrices/1111.11.rc2.yml": {
                    "testlib1": "1.1.1",
                    "testlib2": "1.1.1",
                },
                "upgrade_proposals.yml": {
                    "1111-11": None,
                    "1111-12": {"testlib2": "ignore"},
                },
            },
            ["Temporary PR 1111.11.rc2", "Add release 1111.11.rc2"],
            type(None),
            "",
            id="empty_upgrade_proposal",
        ),
        pytest.param(
            "1111.11.rc1",
            "1111.11.rc2",
            {
                "releases/matrices/1111.11.rc1.yml": {
                    "testlib1": "1.1.1",
                    "testlib2": "1.1.1",
                },
                "upgrade_proposals.yml": {
                    "1111-11": {"testlib2": "1.1.2", "addlib": "1.1.3"},
                    "1111-12": {"testlib2": "ignore"},
                },
                "repository.yml": VALID_REPOSITORY_CONTENT,
            },
            {
                "releases/matrices/1111.11.rc2.yml": {
                    "testlib1": "1.1.1",
                    "testlib2": "1.1.2",
                    "addlib": "1.1.3",
                },
                "upgrade_proposals.yml": {
                    "1111-11": None,
                    "1111-12": {"testlib2": "ignore"},
                },
            },
            ["Temporary PR 1111.11.rc2", "Add release 1111.11.rc2"],
            type(None),
            "",
            id="with_upgrade_proposal",
        ),
        pytest.param(
            "1111.11.rc1",
            "1111.12.rc2",
            {
                "releases/matrices/1111.11.rc1.yml": {
                    "testlib1": "1.1.1",
                    "testlib2": "1.1.1",
                },
                "upgrade_proposals.yml": {
                    "1111-11": {"testlib2": "1.1.2"},
                },
                "repository.yml": VALID_REPOSITORY_CONTENT,
            },
            {},
            [],
            AssertionError,
            r"No section for this release \(1111-12\) in upgrade_proposals\.yml",
            id="missing_proposal_heading",
        ),
        pytest.param(
            MockRepo.existing_branches[-2],
            MockRepo.existing_branches[-1],
            {},
            {},
            [],
            ValueError,
            "Branch 2222.22.rc2 exists already",
            id="branch_already_exists",
        ),
        pytest.param(
            "1111.11.rc1",
            "1111.12.rc1",
            {
                "releases/matrices/1111.11.rc1.yml": {
                    "testlib1": "1.1.1",
                    "testlib2": "1.1.1",
                },
                "upgrade_proposals.yml": {
                    "1111-11": None,
                    "1111-12": {"addlib": "1.1.4"},
                },
                "repository.yml": VALID_REPOSITORY_CONTENT,
            },
            {},
            [],
            AssertionError,
            "Version '1.1.4' for package 'addlib' was not found in repository file",
            id="upgrade_proposal_new_version_not_present_in_repository",
        ),
        pytest.param(
            "1111.11.rc1",
            "1111.12.rc1",
            {
                "releases/matrices/1111.11.rc1.yml": {
                    "testlib1": "1.1.1",
                    "testlib2": "1.1.1",
                },
                "upgrade_proposals.yml": {
                    "1111-11": None,
                    "1111-12": {"package_does_not_exist": "1.1.4"},
                },
                "repository.yml": VALID_REPOSITORY_CONTENT,
            },
            {},
            [],
            AssertionError,
            "Package 'package_does_not_exist' was not found in repository file",
            id="upgrade_proposal_new_package_not_present_in_repository",
        ),
        pytest.param(
            "1111.11.rc1",
            "1111.12.rc1",
            {
                "releases/matrices/1111.11.rc1.yml": {
                    "testlib1": "1.1.1",
                    "testlib2": "1.1.1",
                },
                "upgrade_proposals.yml": {
                    "1111-11": None,
                    "1111-12": {"testlib2": 3.7},
                },
                "repository.yml": VALID_REPOSITORY_CONTENT,
            },
            {},
            [],
            AssertionError,
            r"Package version of 'testlib2' has to be of type string",
            id="float_version_number_in_proposal",
        ),
        pytest.param(
            "1111.11.rc1",
            "1111.12.rc1",
            {
                "releases/matrices/1111.11.rc1.yml": {
                    "testlib1": "1.1.1",
                    "testlib2": "1.1.1",
                },
                "upgrade_proposals.yml": {
                    "1111-11": None,
                    "1111-12": {"addlib": "1.1.2"},
                },
                "repository.yml": {
                    "addlib": {
                        3.7: {"source": "pypi", "make": "pip", "maintainer": "scout"},
                        "1.1.2": {
                            "source": "pypi",
                            "make": "pip",
                            "maintainer": "scout",
                        },
                        "1.1.1": {
                            "source": "pypi",
                            "make": "pip",
                            "maintainer": "scout",
                        },
                    },
                },
            },
            {},
            [],
            AssertionError,
            r"Package version of 'addlib' has to be of type string",
            id="float_version_number_in_repository",
        ),
    ],
)
def test_insert_proposals(
    base, target, repo_files, changed_files, prs, return_type, error_message
):
    repo = MockRepo(files=repo_files)

    if isinstance(return_type(), Exception):
        with pytest.raises(return_type, match=error_message):
            insert_proposals(repo, base, target, "git_ref", "jobname", "joburl")
            # except Exception as e:
            #    assert str(e) == error_message
            #    raise e
    else:
        insert_proposals(repo, base, target, "git_ref", "jobname", "joburl")

    assert len(changed_files) == len(repo.updated_files)
    for file, content in changed_files.items():
        assert file in repo.updated_files
        assert repo.updated_files[file]["content"] == content

    assert len(prs) == len(repo.created_pulls)
    for pr in prs:
        assert pr in repo.created_pulls
