# Demo Alpine (Raspberry Pi)

Packaging and install helpers for the self-contained **Demo** deployment. This tree lives in **`adaan-pradaan-core`** (the GitHub repo that publishes Releases).

- Core API tarball (venv + uvicorn) on Alpine `aarch64` musl  
- Next.js standalone behind nginx (`NEXT_PUBLIC_API_URL=/api`) — UI checked out from `adan-pradan-ui`  
- Postgres on the Pi; Keycloak via `TENANT_KEYCLOAK_MODE=fake`  

See [INSTALL.md](./INSTALL.md) for Pi install steps.

## Publish a release (triggers CI)

From **`adaan-pradaan-core`** (not the parent `adaan-pradaan` folder):

```sh
git add deploy .github/workflows/demo-release.yml
git commit -m "Add Alpine demo packaging and release workflow"
git push origin main

git tag demo-0.1.0
git push origin demo-0.1.0
```

Or run **Actions → Demo Alpine Release → Run workflow** and enter a tag like `demo-0.1.0`.

If `adan-pradan-ui` is private, add a repo secret `DEMO_UI_CHECKOUT_TOKEN` (PAT with read access to that repo).

## Build artifacts locally

```sh
# Ops bundle only
./deploy/demo-alpine/scripts/package-ops.sh

# Full set for Pi (Docker linux/arm64 musl); UI must be at ../adan-pradan-ui or ./adan-pradan-ui
./deploy/demo-alpine/scripts/package-all.sh --docker
```

Outputs land in `dist/`.
