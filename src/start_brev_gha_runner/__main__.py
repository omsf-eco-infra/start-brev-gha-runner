import os
import subprocess

from gha_runner.clouddeployment import DeployInstance
from gha_runner.gh import GitHubInstance
from gha_runner.helper.input import EnvVarBuilder, check_required

from .start import StartBrev


def main():
    env = dict(os.environ)
    if "INPUT_BREV_ORG" in env:
        raise ValueError(
            "brev_org is no longer supported. Create a BREV_API_KEY in the "
            "organization that owns the runners and remove brev_org."
        )
    check_required(env, ["GH_PAT", "BREV_API_KEY"])

    subprocess.run(
        ["brev", "login", "--api-key", env["BREV_API_KEY"]], check=True
    )

    params = (
        EnvVarBuilder(env)
        .update_state("INPUT_BREV_INSTANCE_TYPE", "instance_type")
        .update_state("INPUT_BREV_TIMEOUT", "provision_timeout", type_hint=int)
        .update_state("INPUT_EXTRA_GH_LABELS", "labels")
        .update_state("INPUT_INSTANCE_COUNT", "instance_count", type_hint=int)
        .update_state("GITHUB_REPOSITORY", "repo")
        .update_state("INPUT_REPO", "repo")
        .params
    )
    try:
        count = params.pop("instance_count")
        repo = params["repo"]
    except KeyError as error:
        raise ValueError(f"Missing required action input: {error.args[0]}")

    deployment = DeployInstance(
        provider_type=StartBrev,
        cloud_params=params,
        gh=GitHubInstance(token=env["GH_PAT"], repo=repo),
        count=count,
        timeout=int(env["INPUT_GH_TIMEOUT"]),
    )
    deployment.start_runner_instances()


if __name__ == "__main__":
    main()
