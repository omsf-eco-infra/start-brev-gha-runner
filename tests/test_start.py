import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
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
        self.assertIn("set -euo pipefail", script)
        self.assertIn('runner_dir="${HOME}/gha-runner"', script)
        self.assertIn("curl --fail --location --retry 5", script)
        self.assertIn("--retry-all-errors", script)
        self.assertIn("--ephemeral --unattended", script)
        self.assertIn("https://github.com/owner/repo", script)
        self.assertNotIn("/home/ubuntu/workspace", script)
        self.assertNotIn("pre-runner-script", script)
        subprocess.run(["bash", "-n"], input=script, text=True, check=True)

    def test_startup_script_runs_in_home_and_quotes_values(self):
        self.brev.repo = "owner/repo with space"
        self.brev.runner_release = "https://example.test/runner?a=1&b=2"
        self.brev.labels = "gpu special"
        token = "token with 'quotes' and $dollars"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home with space"
            home.mkdir()
            bin_dir = root / "bin"
            bin_dir.mkdir()
            curl = bin_dir / "curl"
            curl.write_text(
                textwrap.dedent("""\
                #!/usr/bin/env python3
                import json
                import os
                from pathlib import Path
                import sys
                Path(os.environ["TEST_CURL_ARGS"]).write_text(json.dumps(sys.argv[1:]))
                Path("runner.tar.gz").touch()
                """)
            )
            curl.chmod(0o755)
            tar = bin_dir / "tar"
            tar.write_text(
                textwrap.dedent("""\
                #!/usr/bin/env python3
                from pathlib import Path
                Path("config.sh").write_text(
                    '#!/usr/bin/env bash\\nprintf "%s\\n" "$@" > "$TEST_CONFIG_ARGS"\\n'
                )
                Path("run.sh").write_text(
                    '#!/usr/bin/env bash\\npwd > "$TEST_RUN_DIR"\\n'
                )
                Path("config.sh").chmod(0o755)
                Path("run.sh").chmod(0o755)
                """)
            )
            tar.chmod(0o755)
            env = {
                **os.environ,
                "HOME": str(home),
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "TEST_CURL_ARGS": str(root / "curl-args.json"),
                "TEST_CONFIG_ARGS": str(root / "config-args.txt"),
                "TEST_RUN_DIR": str(root / "run-dir.txt"),
            }
            subprocess.run(
                ["bash"],
                input=self.brev._build_startup_script(token, "runner-test1234"),
                text=True,
                env=env,
                cwd=root,
                check=True,
            )
            curl_args = json.loads((root / "curl-args.json").read_text())
            self.assertEqual(
                curl_args,
                [
                    "--fail",
                    "--location",
                    "--retry",
                    "5",
                    "--retry-all-errors",
                    "--retry-delay",
                    "2",
                    "--output",
                    "runner.tar.gz",
                    "--",
                    self.brev.runner_release,
                ],
            )
            self.assertEqual(
                (root / "config-args.txt").read_text().splitlines(),
                [
                    "--url",
                    "https://github.com/owner/repo with space",
                    "--token",
                    token,
                    "--labels",
                    "gpu special,runner-test1234",
                    "--ephemeral",
                    "--unattended",
                ],
            )
            self.assertEqual(
                (root / "run-dir.txt").read_text().strip(),
                str(home / "gha-runner"),
            )

    def test_startup_script_stops_when_download_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            curl = bin_dir / "curl"
            curl.write_text("#!/usr/bin/env bash\nexit 22\n")
            curl.chmod(0o755)
            env = {
                **os.environ,
                "HOME": str(root),
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
            }
            result = subprocess.run(
                ["bash"],
                input=self.brev._build_startup_script("token", "label"),
                text=True,
                env=env,
                cwd=root,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 22)
            self.assertFalse((root / "gha-runner" / "config.sh").exists())

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
            "BREV_API_KEY": "brev-api-key",
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
            ["brev", "login", "--api-key", "brev-api-key"], check=True
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

    @patch("start_brev_gha_runner.__main__.subprocess.run")
    def test_rejects_old_organization_input(self, run):
        with patch.dict(
            "os.environ",
            {
                "GH_PAT": "gh-token",
                "BREV_API_KEY": "brev-api-key",
                "INPUT_BREV_ORG": "old-org",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError, "brev_org is no longer supported"
            ):
                main()
        run.assert_not_called()

    @patch("start_brev_gha_runner.__main__.subprocess.run")
    def test_requires_api_key(self, run):
        with patch.dict(
            "os.environ",
            {
                "GH_PAT": "gh-token",
                "BREV_TOKEN": "old-token",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(Exception, "BREV_API_KEY"):
                main()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
