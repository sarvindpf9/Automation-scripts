#!/usr/bin/env bash
set -euo pipefail

# Override via env: JENKINS_JAVA_VERSION=17 ./install-jenkins.sh
REQUIRED_JAVA_MAJOR=${JENKINS_JAVA_VERSION:-21}

# ── 0. Root guard ────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || { echo "ERROR: run as root (sudo $0)"; exit 1; }

# ── 1. Jenkins repo + key ────────────────────────────────────────────────────
curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key \
  | tee /usr/share/keyrings/jenkins-keyring.asc > /dev/null

echo "deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] \
  https://pkg.jenkins.io/debian-stable binary/" \
  | tee /etc/apt/sources.list.d/jenkins.list > /dev/null

apt-get update -y

# ── 2. Install Java first ────────────────────────────────────────────────────
INSTALLED_MAJOR=""
if command -v java &>/dev/null; then
  INSTALLED_MAJOR=$(java -version 2>&1 | grep -oP '(?<=version ")[0-9]+' | head -1)
fi

if [[ "$INSTALLED_MAJOR" == "$REQUIRED_JAVA_MAJOR" ]]; then
  echo "Java ${INSTALLED_MAJOR} already installed — skipping"
else
  echo "Installing openjdk-${REQUIRED_JAVA_MAJOR}-jre (found: ${INSTALLED_MAJOR:-none})"
  apt-get install -y "openjdk-${REQUIRED_JAVA_MAJOR}-jre"
fi

# Resolve actual JVM path from alternatives — works on amd64 and arm64
JAVA_BIN=$(update-alternatives --list java | grep "java-${REQUIRED_JAVA_MAJOR}" | head -1)
if [[ -z "$JAVA_BIN" ]]; then
  echo "ERROR: could not locate java-${REQUIRED_JAVA_MAJOR} in update-alternatives"
  exit 1
fi
update-alternatives --set java "$JAVA_BIN"
# JAVA_HOME is two levels up from the java binary (.../bin/java → .../jre or .../jdk)
JAVA_HOME_DIR=$(dirname "$(dirname "$JAVA_BIN")")

# ── 3. Install Jenkins ───────────────────────────────────────────────────────
apt-get install -y jenkins

# ── 4. Pin JAVA_HOME for Jenkins service ─────────────────────────────────────
mkdir -p /etc/systemd/system/jenkins.service.d
cat > /etc/systemd/system/jenkins.service.d/override.conf <<EOF
[Service]
Environment="JAVA_HOME=${JAVA_HOME_DIR}"
EOF

# ── 5. Enable + start ────────────────────────────────────────────────────────
systemctl daemon-reload
systemctl enable --now jenkins
systemctl status jenkins --no-pager

# ── 6. Wait for first-run init and print admin password ──────────────────────
echo ""
echo "Waiting for Jenkins first-run initialisation..."
WAIT=0
until [[ -f /var/lib/jenkins/secrets/initialAdminPassword ]]; do
  sleep 2
  WAIT=$((WAIT + 2))
  if [[ $WAIT -ge 120 ]]; then
    echo "ERROR: timed out waiting for initialAdminPassword after 120s"
    exit 1
  fi
done

echo "Initial admin password:"
cat /var/lib/jenkins/secrets/initialAdminPassword
