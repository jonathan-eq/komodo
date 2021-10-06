import github
from datetime import datetime

from base64 import b64decode

import os
import argparse
import collections
from github import Github, UnknownObjectException
from komodo.prettier import load_yaml, write_to_string, write_to_file
import difflib
from ruamel.yaml.compat import StringIO, ordereddict
import ruamel.yaml


def recursive_update(left, right):
    for k, v in right.items():
        if isinstance(v, collections.abc.Mapping):
            d_val = left.get(k)
            if not d_val:
                left[k] = v
            else:
                recursive_update(d_val, v)
        else:
            left[k] = v
    return left


def _get_repo(token, fork, repo):
    client = Github(token)
    try:
        return client.get_repo("{}/{}".format(fork, repo))
    except UnknownObjectException:
        org = client.get_organization(fork)
        return org.get_repo(repo)


def diff_file_and_string(file_contents, string, leftname, rightname):
    return "".join(
        difflib.unified_diff(
            file_contents.splitlines(True),
            string.splitlines(True),
            leftname,
            rightname,
            n=0,
        )
    )


def load_yaml_from_repo(filename, repo, ref):
    ruamel_instance = ruamel.yaml.YAML()
    ruamel_instance.indent(  # Komodo prefers two space indendation
        mapping=2, sequence=4, offset=2
    )
    ruamel_instance.width = 1000  # Avoid ruamel wrapping long

    try:
        sym_conf_content = repo.get_contents(filename, ref=ref)

        input_dict = ruamel_instance.load(b64decode(sym_conf_content.content))
        return input_dict

    except (
        ruamel.yaml.scanner.ScannerError,
        ruamel.yaml.constructor.DuplicateKeyError,
    ) as e:
        raise SystemExit(
            "The file: <{}> contains invalid YAML syntax:\n {}".format(filename, str(e))
        )


def main():
    args = parse_args()
    repo = _get_repo(os.getenv("GITHUB_TOKEN"), args.git_fork, args.git_repo)
    status = insert_proposals(repo, args.base, args.target, args.git_ref, args.jobname, args.joburl)
    if status is not None:
        raise status


def insert_proposals(repo, base, target, git_ref, jobname, joburl):
    year = target.split(".")[0]
    month = target.split(".")[1]
    tmp_target = target+".tmp"

    # check that the branches do not already exist
    try:
        repo.get_branch(target)
    except github.GithubException:
        pass
    else:
        return ValueError(f"Branch {target} exists already")

    try:
        repo.get_branch(tmp_target)
    except github.GithubException:
        pass
    else:
        return ValueError(f"Branch {tmp_target} exists already")

    # create contents of new release
    proposal_yaml = load_yaml_from_repo("upgrade_proposals.yml", repo, git_ref)
    upgrade_key = f"{year}-{month}"
    upgrade = proposal_yaml.get(upgrade_key)
    if upgrade_key not in proposal_yaml:
        return ValueError(
            f"No section for this release ({upgrade_key}) in upgrade_proposals.yml"
        )
    base_file = f"releases/matrices/{base}.yml"
    target_file = f"releases/matrices/{target}.yml"
    base_dict = load_yaml_from_repo(base_file, repo, git_ref)
    if upgrade:
        recursive_update(base_dict, upgrade)
    result = write_to_string(base_dict)

    # create new release file
    from_sha = repo.get_branch(git_ref).commit.sha
    tmp_ref = repo.create_git_ref(ref="refs/heads/" + tmp_target, sha=from_sha)
    repo.create_file(
        target_file,
        f"Add release {target}",
        result,
        branch=tmp_target,
    )

    # clean the proposal file
    proposal_yaml[upgrade_key] = None
    cleaned_upgrade = write_to_string(proposal_yaml, False)
    upgrade_contents = repo.get_contents("upgrade_proposals.yml", ref=git_ref)
    repo.update_file(
        "upgrade_proposals.yml",
        "Clean proposals",
        cleaned_upgrade,
        sha=upgrade_contents.sha,
        branch=tmp_target,
    )

    # making PR
    base_content = repo.get_contents(base_file, ref=git_ref)
    diff = diff_file_and_string(
        b64decode(base_content.content).decode(), result, base, target
    )

    pr_msg = f""":robot: Release {target}
---
### Description
- New Release: `{target}`
- Based on: `{base}`
- When: `{datetime.now()}`

### Diff
```diff
diff {base_file} {target_file}:
{diff}
```

### Details
_This pull request was generated by [{jobname}]({joburl})_.

Source code for this script can be found [here](https://github.com/equinor/komodo).
"""

    repo.create_git_ref(ref="refs/heads/" + target, sha=from_sha)
    # making a temporary PR in order to squash the commits into one
    tmp_pr = repo.create_pull(
        title=f"Temporary PR {target}",
        body="should not be seen",
        head=tmp_target,
        base=target,
    )
    tmp_pr.merge(
        commit_message=pr_msg,
        commit_title=f"Add release {target}",
        merge_method="squash",
    )
    try:
        tmp_ref.delete()
    except github.GithubException:
        pass  # automatically deleted on PR merge
    # done with temporary PR

    # making the real PR
    repo.create_pull(
        title=f"Add release {target}", body=pr_msg, head=target, base=git_ref
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Copy proposals into release and create PR."
    )
    parser.add_argument(
        "base",
        type=str,
        help="The name of the release to base on. (E.g. 2021.06.b0). "
        "A corresponding file must exist in releases/matrices",
    )
    parser.add_argument(
        "target",
        type=str,
        help="The name of the new release file to create. (E.g. 2021.06.b0).",
    )
    parser.add_argument("joburl", help="link to the job that triggered this")
    parser.add_argument("jobname", help="name of the job")
    parser.add_argument("--git-fork", help="git fork", default="equinor")
    parser.add_argument("--git-repo", help="git repo", default="komodo-releases")
    parser.add_argument("--git-ref", help="git ref", default="master")
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    main()