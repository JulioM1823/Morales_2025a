#!/usr/bin/env zsh
# run_download_batches.sh
#
# Purpose
#   Run the CO5BOLD download + binning pipeline over multiple URL lists while
#   keeping dataset groups sequential and letting download_files.sh parallelize
#   within each individual URL list.
#
# Usage
#   ./run_download_batches.sh
#
# Environment overrides
#   MAX_JOBS                 Passed through to download_files.sh
#   AUTO_MAX_JOBS_CAP        Passed through to download_files.sh
#   AUTO_MIN_IMPROVEMENT_PCT Passed through to download_files.sh
#   REMOTE_TIMEOUT           Passed through to download_files.sh
#   REMOTE_RETRIES           Passed through to download_files.sh
#   REMOTE_TIMEOUT_STEP      Passed through to download_files.sh
#   POST_FILE_SLEEP          Passed through to download_files.sh
#   SKIP_EXISTING            Passed through to download_files.sh
#   SKIP_OUTPUT_DIRS         Comma-separated output dirs or suffixes to skip
#
set -euo pipefail

script_dir="${0:A:h}"
project_root="${script_dir:h:h}"
downloader="${script_dir}/download_files.sh"

[[ -x "${downloader}" ]] || [[ -f "${downloader}" ]] || {
  echo "[ERROR] Missing downloader script: ${downloader}" >&2
  exit 1
}

data_root="/Users/juliomorales/Research/Projects/Morales_2025a/Data/co5bold"
: "${SKIP_OUTPUT_DIRS:=}"

typeset -a mappings
mappings=(
  "${data_root}/hx/file_names_hx_0.txt|${data_root}/hx/10G"
  "${data_root}/hx/file_names_hx_1.txt|${data_root}/hx/50G"
  "${data_root}/hx/file_names_hx_2.txt|${data_root}/hx/100G"
  "${data_root}/vx/file_names_vx_0.txt|${data_root}/vx/10G"
  "${data_root}/vx/file_names_vx_1.txt|${data_root}/vx/50G"
  "${data_root}/vx/file_names_vx_2.txt|${data_root}/vx/100G"
  "${data_root}/z0/file_names_z0_0.txt|${data_root}/z0/0G"
)

echo "[INFO] Project root: ${project_root}"
echo "[INFO] Downloader: ${downloader}"
echo "[INFO] MAX_JOBS=${MAX_JOBS:-1}"
if [[ -n "${SKIP_OUTPUT_DIRS}" ]]; then
  echo "[INFO] SKIP_OUTPUT_DIRS=${SKIP_OUTPUT_DIRS}"
fi
echo "[INFO] Starting sequential dataset processing across ${#mappings[@]} URL lists"

should_skip_output_dir() {
  local out_dir="$1"
  local relative_out_dir="${out_dir#${data_root}/}"
  local skip_entry

  [[ -n "${SKIP_OUTPUT_DIRS}" ]] || return 1

  for skip_entry in ${(s:,:)SKIP_OUTPUT_DIRS}; do
    skip_entry="${skip_entry#"${skip_entry%%[![:space:]]*}"}"
    skip_entry="${skip_entry%"${skip_entry##*[![:space:]]}"}"
    [[ -n "${skip_entry}" ]] || continue

    if [[ "${out_dir}" == "${skip_entry}" || "${relative_out_dir}" == "${skip_entry}" ]]; then
      return 0
    fi

    if [[ "${out_dir}" == *"/${skip_entry}" || "${relative_out_dir}" == *"/${skip_entry}" ]]; then
      return 0
    fi
  done

  return 1
}

for mapping in "${mappings[@]}"; do
  url_list="${mapping%%|*}"
  out_dir="${mapping#*|}"

  if should_skip_output_dir "${out_dir}"; then
    echo
    echo "[INFO] Skipping list: ${url_list}"
    echo "[INFO] Skipping dir:  ${out_dir}"
    continue
  fi

  echo
  echo "[INFO] Processing list: ${url_list}"
  echo "[INFO] Output dir:      ${out_dir}"

  [[ -f "${url_list}" ]] || {
    echo "[ERROR] URL list not found: ${url_list}" >&2
    exit 1
  }

  mkdir -p "${out_dir}"

  env \
    MAX_JOBS="${MAX_JOBS:-1}" \
    AUTO_MAX_JOBS_CAP="${AUTO_MAX_JOBS_CAP:-4}" \
    AUTO_MIN_IMPROVEMENT_PCT="${AUTO_MIN_IMPROVEMENT_PCT:-5}" \
    REMOTE_TIMEOUT="${REMOTE_TIMEOUT:-600}" \
    REMOTE_RETRIES="${REMOTE_RETRIES:-3}" \
    REMOTE_TIMEOUT_STEP="${REMOTE_TIMEOUT_STEP:-300}" \
    POST_FILE_SLEEP="${POST_FILE_SLEEP:-0}" \
    SKIP_EXISTING="${SKIP_EXISTING:-1}" \
    zsh "${downloader}" "${url_list}" "${out_dir}"
done

echo
echo "[INFO] All dataset groups completed successfully."
