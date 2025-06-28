# open-codespeak

By submitting to this repo, you agree to the terms in [CLA.md](./CLA.md)

## Dev environment

Install `uv`, then

```
uv python install 3.11
uv sync
```

### Activate venv

Option 1. `source .venv/bin/activate`

Option 2. Install `direnv` to automatically load environments when you change dirs

Follow https://direnv.net/docs/installation.html

## Provide .env with API keys

1. Copy `env.template` to `.env`:

```
cp env.template .env
```

2. Provide actual values for API keys in `.env`

3. Run the setup script to install git hooks:

```bash
./setup-hooks.sh
```

## Use `./dev` for testing and debugging

```
Usage: ./dev {new|current|retry|clear|rmcur}

Commands:
  new <specfile>     Create new project from spec file
  current            Show current project directory
  retry [--project_dir path] [TransitionName]  Retry from specific transition
  clear              Clear all test outputs
  rmcur              Remove current project

Examples:
  ./dev new spec_examples/lumama.spec.md
  ./dev retry ExtractEntities
  ./dev retry --project_dir test_outputs/02_lumama GenerateDjangoProject
```