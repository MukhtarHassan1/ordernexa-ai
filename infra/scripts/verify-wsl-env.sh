#!/usr/bin/env bash
set -u

echo "========================================"
echo " OrderNexa AI - WSL Environment Check"
echo "========================================"
echo

echo "[OS]"
if [ -f /etc/os-release ]; then
  grep -E '^(NAME|VERSION|VERSION_ID)=' /etc/os-release
else
  uname -a
fi
echo

echo "[Kernel / WSL]"
uname -a
if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "WSL detected: YES"
else
  echo "WSL detected: NO/UNKNOWN"
fi
echo

for cmd in python3 node npm git docker; do
  echo "[$cmd]"
  if command -v "$cmd" >/dev/null 2>&1; then
    case "$cmd" in
      python3) python3 --version ;;
      node) node --version ;;
      npm) npm --version ;;
      git) git --version ;;
      docker) docker --version ;;
    esac
  else
    echo "NOT FOUND"
  fi
  echo
done

echo "[Docker Compose]"
if docker compose version >/dev/null 2>&1; then
  docker compose version
else
  echo "NOT FOUND"
fi
echo

echo "[Docker connectivity]"
if docker info >/dev/null 2>&1; then
  echo "Docker daemon reachable: YES"
else
  echo "Docker daemon reachable: NO"
fi
echo

echo "[Project location]"
pwd
case "$(pwd)" in
  /mnt/*)
    echo "WARNING: Project is on a Windows-mounted drive."
    echo "Recommended active development location: ~/projects/ordernexa-ai"
    ;;
  *)
    echo "Linux filesystem location: OK"
    ;;
esac
