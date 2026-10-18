# Demo deploy (Raspberry Pi)

Primary target: **Raspberry Pi OS (Debian, aarch64, glibc)** with `apt` + systemd.

Alpine (`apk` + OpenRC + musl) remains supported by the same install script when detected.

## Publish a release

From **`adaan-pradaan-core`**:

```sh
git add deploy .github/workflows/demo-release.yml
git commit -m "Demo Pi: Debian/glibc artifacts + systemd install"
git push origin main

git tag demo-0.1.2
git push origin demo-0.1.2
```

## Install on Raspberry Pi OS

```sh
sudo apt-get update && sudo apt-get install -y curl
curl -fsSL "https://github.com/codeninepoint/adaan-pradaan-core/releases/download/demo-0.1.2/install-demo.sh" -o install-demo.sh
chmod +x install-demo.sh
sudo ./install-demo.sh --repo codeninepoint/adaan-pradaan-core --version demo-0.1.2
```

## Build locally

```sh
# Raspberry Pi OS (gnu)
./deploy/demo-alpine/scripts/package-all.sh --docker --libc gnu

# Alpine (musl)
./deploy/demo-alpine/scripts/package-all.sh --docker --libc musl
```

See [INSTALL.md](./INSTALL.md).
