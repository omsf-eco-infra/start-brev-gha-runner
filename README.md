# start-brev-gha-runner

Create ephemeral, repository-scoped GitHub Actions runners on
[NVIDIA Brev](https://docs.nvidia.com/brev/llms.txt). The action uses Brev's
documented CLI and the [`gha-runner`](https://gha-runner.readthedocs.io/)
deployment lifecycle.

## Setup

1. Create a Brev CLI token from the
   [Brev CLI settings page](https://brev.nvidia.com/settings/cli).
2. Add it as the repository secret `BREV_TOKEN`.
3. Add a GitHub token able to manage repository self-hosted runners as
   `GH_PAT`.
4. Run `brev search` locally to choose an available instance type. A
   comma-separated list is accepted as a capacity fallback chain.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `brev_instance_type` | yes | | Instance type or comma-separated fallback chain. |
| `brev_org` | no | token's active org | Brev organization name. |
| `brev_timeout` | no | `600` | Brev provisioning timeout in seconds. |
| `extra_gh_labels` | no | | Extra comma-separated runner labels. |
| `instance_count` | no | `1` | Number of runners. |
| `repo` | no | current repository | Repository to register with. |
| `gh_timeout` | no | `1200` | GitHub registration timeout in seconds. |

The action requires `BREV_TOKEN` and `GH_PAT` in its environment.

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
        uses: omsf/start-brev-gha-runner@v1
        with:
          brev_instance_type: g5.xlarge,g6.xlarge
        env:
          BREV_TOKEN: ${{ secrets.BREV_TOKEN }}
          GH_PAT: ${{ secrets.GH_PAT }}

  test:
    needs: start-brev-runner
    runs-on: ${{ fromJSON(needs.start-brev-runner.outputs.instances) }}
    steps:
      - uses: actions/checkout@v4
      - run: nvidia-smi
```

Use the output `mapping` with the corresponding stop action so instances are
deleted even when downstream jobs fail.