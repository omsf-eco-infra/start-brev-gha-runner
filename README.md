# start-brev-gha-runner

Create ephemeral, repository-scoped GitHub Actions runners on
[NVIDIA Brev](https://docs.nvidia.com/brev/llms.txt). The action uses Brev's
documented CLI and the [`gha-runner`](https://gha-runner.readthedocs.io/)
deployment lifecycle.

## Setup

1. In the Brev organization that owns the runners, create a
   [Brev API key](https://docs.nvidia.com/brev/guides/api-keys) with
   **Read & Write** access. Copy the full key when it is shown: Brev shows it
   only once, and it expires on the date you configure.
2. Add the key as the repository secret `BREV_API_KEY`.
3. Add a GitHub token able to manage repository self-hosted runners as
   `GH_PAT`.
4. Run `brev search` locally to choose an available instance type. A
   comma-separated list is accepted as a capacity fallback chain.

## Development

Install [Pixi](https://pixi.sh), then run:

```sh
pixi install --locked
pixi run test
pixi run lint
pixi run format-check
pixi run brev --version
```

`pyproject.toml` defines the Python, Brev, and development dependencies;
`pixi.lock` pins packages and hashes for Linux and macOS on x86-64 and ARM64.
The Docker image installs the `prod` environment, without development tools.

To update Brev from conda-forge, run `pixi update brev` and commit the updated
lockfile. Adjust the version constraint in `pyproject.toml` when moving beyond
Brev 0.6.x. Conda-forge releases may lag upstream GitHub releases.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `brev_instance_type` | yes | | Instance type or comma-separated fallback chain. |
| `brev_timeout` | no | `600` | Brev provisioning timeout in seconds. |
| `extra_gh_labels` | no | | Extra comma-separated runner labels. |
| `instance_count` | no | `1` | Number of runners. |
| `repo` | no | current repository | Repository to register with. |
| `gh_timeout` | no | `1200` | GitHub registration timeout in seconds. |

The action requires `BREV_API_KEY` and `GH_PAT` in its environment. The API key
selects its organization automatically.

## Outputs

| Output | Description |
| --- | --- |
| `mapping` | JSON object mapping Brev instance names to runner labels. |
| `instances` | JSON list of runner labels for `runs-on`. |

## Usage

```yaml
jobs:
  start-brev-runner:
    runs-on: ubuntu-latest
    outputs:
      mapping: ${{ steps.brev-start.outputs.mapping }}
      instances: ${{ steps.brev-start.outputs.instances }}
    steps:
      - name: Create Brev runner
        id: brev-start
        uses: omsf-eco-infra/start-brev-gha-runner@8caae6a56ffe6f455278dea33e20b9b8dc003d4e # v1
        with:
          brev_instance_type: g5.xlarge,g6.xlarge
        env:
          BREV_API_KEY: ${{ secrets.BREV_API_KEY }}
          GH_PAT: ${{ secrets.GH_PAT }}

  test:
    needs: start-brev-runner
    runs-on: ${{ fromJSON(needs.start-brev-runner.outputs.instances) }}
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
      - run: nvidia-smi
```

Pin the action to a commit SHA in production workflows.

Use the output `mapping` with the corresponding stop action so instances are
deleted even when downstream jobs fail.
