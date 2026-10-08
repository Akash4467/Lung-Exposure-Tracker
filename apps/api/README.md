# lung (API + worker)

One Python package, two entry points from the same Docker image:

- API: `uvicorn lung.main:app`
- Worker: `python -m lung.worker`

Local dev: `uv sync`, then `uv run pytest`. See the root `Makefile`.
