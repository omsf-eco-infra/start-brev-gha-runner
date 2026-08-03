import importlib.resources
import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from string import Template

from gha_runner import gh
from gha_runner.clouddeployment import CreateCloudInstance
from gha_runner.helper.workflow_cmds import output


@dataclass
class StartBrev(CreateCloudInstance):
    """Create ephemeral GitHub Actions runners on NVIDIA Brev."""

    instance_type: str
    repo: str
    provision_timeout: int = 600
    labels: str = ""
    runner_release: str = ""
    gh_runner_tokens: list[str] = field(default_factory=list)

    def _build_startup_script(self, token: str, label: str) -> str:
        template = importlib.resources.files("gha_runner").joinpath(
            "templates/user-script.sh.templ"
        )
        labels = ",".join(filter(None, (self.labels, label)))
        return Template(template.read_text()).substitute(
            homedir="/home/ubuntu/workspace",
            script="",
            repo=self.repo,
            token=token,
            runner_release=self.runner_release,
            labels=labels,
        )

    def create_instances(self) -> dict[str, str]:
        if not self.gh_runner_tokens:
            raise ValueError(
                "No GitHub runner tokens provided, cannot create instances."
            )
        if not self.runner_release:
            raise ValueError(
                "No runner release provided, cannot create instances."
            )

        mapping = {}
        for token in self.gh_runner_tokens:
            label = gh.GitHubInstance.generate_random_label()
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh") as script:
                script.write(self._build_startup_script(token, label))
                script.flush()
                subprocess.run(
                    [
                        "brev",
                        "create",
                        label,
                        "--type",
                        self.instance_type,
                        "--startup-script",
                        f"@{script.name}",
                        "--timeout",
                        str(self.provision_timeout),
                        "--jupyter=false",
                    ],
                    check=True,
                )
            mapping[label] = label
        return mapping

    def wait_until_ready(self, ids: list[str], **kwargs):
        # `brev create` blocks until every created instance is ready.
        return None

    def set_instance_mapping(self, mapping: dict[str, str]):
        output("mapping", json.dumps(mapping))
        output("instances", json.dumps(list(mapping.values())))
