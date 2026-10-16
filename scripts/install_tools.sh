#!/usr/bin/env bash
# Installs pinned CLI tools into the gitignored .tools/bin (macOS and Linux).
# Versions come from tools/versions.env, copied to .tools/versions.env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$ROOT/.tools"
BIN="$TOOLS/bin"
mkdir -p "$BIN"
cp "$ROOT/tools/versions.env" "$TOOLS/versions.env"
# shellcheck source=/dev/null
source "$TOOLS/versions.env"

os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"
case "$arch" in
  x86_64 | amd64) arch_go=amd64; arch_hl=x86_64; arch_sc=x86_64; arch_tv=64bit ;;
  arm64 | aarch64) arch_go=arm64; arch_hl=arm64; arch_sc=aarch64; arch_tv=ARM64 ;;
  *) echo "unsupported architecture: $arch" >&2; exit 1 ;;
esac

fetch() { curl -fsSL --retry 4 --retry-delay 2 -o "$2" "$1"; }

have() { [[ -x "$BIN/$1" ]] && "$BIN/$1" "${@:2}" 2>&1 | grep -q "$3"; }

# Hadolint
if ! have hadolint --version "$HADOLINT_VERSION"; then
  hl_os="$os"; [[ "$os" == darwin ]] && hl_os=macos
  fetch "https://github.com/hadolint/hadolint/releases/download/v${HADOLINT_VERSION}/hadolint-${hl_os}-${arch_hl}" "$BIN/hadolint"
  chmod +x "$BIN/hadolint"
fi

# ShellCheck
if ! have shellcheck --version "$SHELLCHECK_VERSION"; then
  tmp="$(mktemp -d)"
  fetch "https://github.com/koalaman/shellcheck/releases/download/v${SHELLCHECK_VERSION}/shellcheck-v${SHELLCHECK_VERSION}.${os}.${arch_sc}.tar.xz" "$tmp/sc.tar.xz"
  tar -xJf "$tmp/sc.tar.xz" -C "$tmp"
  mv "$tmp/shellcheck-v${SHELLCHECK_VERSION}/shellcheck" "$BIN/shellcheck"
  rm -rf "$tmp"
fi

# Trivy
if ! have trivy --version "$TRIVY_VERSION"; then
  tmp="$(mktemp -d)"
  tv_os=Linux; [[ "$os" == darwin ]] && tv_os=macOS
  fetch "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_${tv_os}-${arch_tv}.tar.gz" "$tmp/trivy.tgz"
  tar -xzf "$tmp/trivy.tgz" -C "$tmp" trivy
  mv "$tmp/trivy" "$BIN/trivy"
  rm -rf "$tmp"
fi

# actionlint and gitleaks through the Go module proxy
if command -v go >/dev/null 2>&1; then
  if ! have actionlint --version "$ACTIONLINT_VERSION"; then
    GOBIN="$BIN" GOARCH="$arch_go" go install "github.com/rhysd/actionlint/cmd/actionlint@v${ACTIONLINT_VERSION}"
  fi
  if ! have gitleaks version "$GITLEAKS_VERSION"; then
    GOBIN="$BIN" GOARCH="$arch_go" go install -ldflags "-X github.com/zricethezav/gitleaks/v8/version.Version=${GITLEAKS_VERSION}" \
      "github.com/zricethezav/gitleaks/v8@v${GITLEAKS_VERSION}"
  fi
else
  echo "warning: go not found; actionlint and gitleaks not installed" >&2
fi

# markdownlint-cli2 and @playwright/mcp through pnpm
if command -v pnpm >/dev/null 2>&1; then
  (cd "$ROOT/tools/node" && pnpm install --frozen-lockfile --silent)
  printf '#!/usr/bin/env bash\nexec "%s/tools/node/node_modules/.bin/markdownlint-cli2" "$@"\n' "$ROOT" > "$BIN/markdownlint-cli2"
  chmod +x "$BIN/markdownlint-cli2"
else
  echo "warning: pnpm not found; markdownlint-cli2 not installed" >&2
fi

echo "tools installed in $BIN:"
ls "$BIN"
