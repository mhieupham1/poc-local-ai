#!/usr/bin/env bash
set -euo pipefail

while IFS= read -r line || [[ -n "${line}" ]]; do
  case "${line}" in
    "* Your web credentials are:"*|\
    "* Open button token is also valid:"*|\
    "* To make API requests,"*)
      printf '%s\n' '[redacted]'
      ;;
    *)
      printf '%s\n' "${line}"
      ;;
  esac
done
