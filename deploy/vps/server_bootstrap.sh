# One-time server bootstrap for callagent (run ON the VPS as root).
#
# Completes playbook section 11 items that cannot be automated from the
# developer machine: the clone, the deploy key, the .env scaffold, the
# watcher site-list line, and (optionally) the first deploy.
#
# Usage:
#   bash deploy/vps/server_bootstrap.sh              # idempotent setup
#   FIRST_DEPLOY=1 bash deploy/vps/server_bootstrap.sh   # + first watcher deploy
#
# What you must do by hand (once): register the generated deploy key's
# public half as a deploy key (read) on forexgrasp-cyber/callagent, and fill
# the real secrets into /opt/sites/callagent/.env.

set -euo pipefail

SITE_DIR="/opt/sites/callagent"
SHARED_DIR="/opt/sites/shared-canonical-services"
REPO="git@github.com:forexgrasp-cyber/callagent.git"
KEY_NAME="callagent_deploy"
CONF="/opt/sites/scripts/deploy_sites.conf"
CONF_LINE="callagent|${SITE_DIR}|main|deploy/vps/deploy.sh|yes|callagent.snapford.com"

echo "==> 1/5 deploy key (${KEY_NAME})"
if [ ! -f "/root/.ssh/${KEY_NAME}" ]; then
  ssh-keygen -t ed25519 -N "" -C "${KEY_NAME}" -f "/root/.ssh/${KEY_NAME}" -q
  echo "    generated. PUBLIC HALF (register as a read deploy key on the repo):"
  cat "/root/.ssh/${KEY_NAME}.pub"
else
  echo "    exists (keeping)"
fi
grep -q "IdentityFile /root/.ssh/${KEY_NAME}" /root/.ssh/config 2>/dev/null || cat >> /root/.ssh/config <<EOF

Host github-callagent
  HostName github.com
  User git
  IdentityFile /root/.ssh/${KEY_NAME}
  IdentitiesOnly yes
EOF

echo "==> 2/5 clone (${SITE_DIR})"
if [ ! -d "${SITE_DIR}/.git" ]; then
  git clone --branch main "${REPO/git@github.com:/git@github-callagent:}" "${SITE_DIR}"
else
  echo "    exists (watcher owns it from here)"
fi

echo "==> 3/5 .env scaffold"
if [ ! -f "${SITE_DIR}/.env" ]; then
  cp "${SITE_DIR}/.env.example" "${SITE_DIR}/.env"
  chmod 600 "${SITE_DIR}/.env"
  echo "    scaffolded from .env.example - FILL IN REAL SECRETS before first deploy:"
  echo "      TRAEFIK_HOST, JWT_SECRET_KEY (match hub), TWILIO_*, STRIPE_*, OPENAI_API_KEY"
else
  echo "    exists (never overwrite)"
fi

echo "==> 4/5 watcher site list"
touch "${CONF}"
grep -q "^callagent|" "${CONF}" || echo "${CONF_LINE}" >> "${CONF}"
tail -1 "${CONF}"

echo "==> 5/5 shared checkout"
[ -d "${SHARED_DIR}/.git" ] && echo "    exists: ${SHARED_DIR}" || echo "    WARN: ${SHARED_DIR} missing - clone forexgrasp-cyber/shared-canonical-services there"

if [ "${FIRST_DEPLOY:-0}" = "1" ]; then
  echo "==> first deploy (watcher, single site)"
  bash /opt/sites/scripts/deploy_watcher.sh callagent
else
  echo "==> done. First deploy when ready:"
  echo "      ssh vps 'bash /opt/sites/scripts/deploy_watcher.sh callagent'"
fi
