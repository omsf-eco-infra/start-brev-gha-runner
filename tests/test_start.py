import json
import unittest
from unittest.mock import call, mock_open, patch

from start_brev_gha_runner.__main__ import main
from start_brev_gha_runner.start import StartBrev


class StartBrevTests(unittest.TestCase):
    def setUp(self):
        self.brev = StartBrev(
            instance_type="g5.xlarge,g6.xlarge",
            repo="owner/repo",
            runner_release="https://example.test/runner.tar.gz",
            gh_runner_tokens=["secret-token"],
        )

    @patch("start_brev_gha_runner.start.subprocess.run")
    @patch(
        "start_brev_gha_runner.start.gh.GitHubInstance.generate_random_label",
        return_value="runner-test1234",
    )
    def test_create_instance(self, _label, run):
        self.assertEqual(
            self.brev.create_instances(),
            {"runner-test1234": "runner-test1234"},
        )
        command = run.call_args.args[0]
        self.assertEqual(
            command[:5],
            [
                "brev",
                "create",
                "runner-test1234",
                "--type",
                "g5.xlarge,g6.xlarge",
            ],
        )
        self.assertNotIn("secret-token", command)
        run.assert_called_once_with(command, check=True)

    def test_startup_script_registers_ephemeral_runner(self):
        script = self.brev._build_startup_script(
            "secret-token", "runner-test1234"
        )
        self.assertIn("--token secret-token", script)
        self.assertIn("--labels runner-test1234 --ephemeral", script)
        self.assertIn("https://github.com/owner/repo", script)

    def test_requires_runner_tokens(self):
        self.brev.gh_runner_tokens = []
        with self.assertRaisesRegex(ValueError, "No GitHub runner tokens"):
            self.brev.create_instances()

    @patch("builtins.open", new_callable=mock_open)
    def test_sets_outputs(self, opened):
        with patch.dict("os.environ", {"GITHUB_OUTPUT": "outputs"}):
            self.brev.set_instance_mapping({"brev-name": "runner-label"})
        self.assertEqual(opened.call_args_list, [call("outputs", "a")] * 2)
        writes = [args.args[0] for args in opened().write.call_args_list]
        self.assertIn(json.dumps({"brev-name": "runner-label"}), writes[0])


class MainTests(unittest.TestCase):
    @patch("start_brev_gha_runner.__main__.DeployInstance")
    @patch("start_brev_gha_runner.__main__.GitHubInstance")
    @patch("start_brev_gha_runner.__main__.subprocess.run")
    def test_main(self, run, github, deploy):
        env = {
            "BREV_TOKEN": "brev-token",
            "GH_PAT": "gh-token",
            "GITHUB_REPOSITORY": "owner/repo",
            "INPUT_BREV_INSTANCE_TYPE": "g5.xlarge",
            "INPUT_BREV_TIMEOUT": "600",
            "INPUT_GH_TIMEOUT": "1200",
            "INPUT_INSTANCE_COUNT": "1",
        }
        with patch.dict("os.environ", env, clear=True):
            main()

        run.assert_called_once_with(
            ["brev", "login", "--token", "brev-token"], check=True
        )
        github.assert_called_once_with(token="gh-token", repo="owner/repo")
        self.assertEqual(
            deploy.call_args.kwargs["cloud_params"],
            {
                "instance_type": "g5.xlarge",
                "provision_timeout": 600,
                "repo": "owner/repo",
            },
        )
        deploy.return_value.start_runner_instances.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
