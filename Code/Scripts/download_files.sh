#!/usr/bin/env zsh
# download_files.sh
#
# Purpose:
#   Fetch a remote CO5BOLD HDF5/OPeNDAP resource, bin in x/y, optionally
#   bin in z, and write a compact NetCDF output to a target directory.
#
# Usage:
#   ./download_files.sh <url_list.txt> <output_dir>
#
# Environment overrides:
#   REMOTE_TIMEOUT        (seconds) default 600
#   REMOTE_RETRIES        (count)   default 3
#   REMOTE_TIMEOUT_STEP   (seconds) default 300; added per retry attempt
#   SKIP_EXISTING         (0/1)     default 1; skip outputs already written
#   Z_BIN_ENABLED         (0/1)     default 1; apply vertical binning
#   Z_BIN                 (int)     default 11; z-bin factor
#   Z_SUBSET_START        (int)     default 54; first xc3 index before binning
#   Z_SUBSET_END          (int)     default 119; last xc3 index before binning
#
# Notes:
#   - Requires NCO tools: ncks, ncap2, ncwa, ncatted, ncrename
#   - Requires GNU timeout as `gtimeout` (macOS coreutils). If `timeout` exists,
#     the script will use it as a fallback.
#   - Failed URLs from the current run are written to <output_dir>/failed_urls.txt
#
set -euo pipefail

# ---------------------------
# Defaults (override via env)
# ---------------------------
: "${REMOTE_TIMEOUT:=600}"
: "${REMOTE_RETRIES:=3}"
: "${REMOTE_TIMEOUT_STEP:=300}"
: "${POST_FILE_SLEEP:=0}"
: "${MAX_JOBS:=1}"
: "${AUTO_MAX_JOBS_CAP:=4}"
: "${AUTO_MIN_IMPROVEMENT_PCT:=5}"
: "${SKIP_EXISTING:=1}"
: "${Z_BIN_ENABLED:=1}"
: "${Z_BIN:=11}"
: "${Z_SUBSET_START:=54}"
: "${Z_SUBSET_END:=119}"

# Use a fixed fast local scratch area for per-file intermediates.
WORK_TMP_ROOT="/tmp/morales_2025a_download_tmp"

# ---------------------------
# Helpers
# ---------------------------
log() { # log <step> <message>
  local step="$1"; shift
  echo "[$step] $*"
}

emit_log_block() {
  local log_file="$1"

  [[ -f "${log_file}" ]] || return 0

  printf '\n'
  cat "${log_file}"
  printf '\n'
  rm -f "${log_file}"
}

cleanup_run_tmpdirs() {
  local run_id="$1"
  local tmp_matches=( "${OUT_DIR}"/.tmp_*_run${run_id}(N) )

  if [[ -n "${WORK_TMP_ROOT:-}" ]]; then
    tmp_matches+=( "${WORK_TMP_ROOT}"/download_files_tmp_run${run_id}_*(N) )
  fi

  (( ${#tmp_matches[@]} > 0 )) || return 0
  rm -rf -- "${tmp_matches[@]}"
}

record_failed_url() {
  local url="$1"
  print -r -- "${url}" >> "${FAILED_URLS_FILE}"
}

print_progress_estimate() {
  local completed="$1"
  local total="$2"
  local run_start_seconds="$3"
  local elapsed_seconds remaining_files raw_eta_seconds eta_minutes

  elapsed_seconds=$(( SECONDS - run_start_seconds ))
  (( elapsed_seconds < 1 )) && elapsed_seconds=1
  remaining_files=$(( total - completed ))

  if (( completed <= 0 || remaining_files <= 0 )); then
    raw_eta_seconds="0"
  else
    raw_eta_seconds="$(awk -v elapsed="${elapsed_seconds}" -v completed="${completed}" -v remaining="${remaining_files}" 'BEGIN { printf "%.6f", (elapsed/completed)*remaining }')"
  fi

  if [[ -z "${SMOOTHED_ETA_SECONDS:-}" ]]; then
    SMOOTHED_ETA_SECONDS="${raw_eta_seconds}"
  else
    SMOOTHED_ETA_SECONDS="$(awk -v previous="${SMOOTHED_ETA_SECONDS}" -v current="${raw_eta_seconds}" 'BEGIN { printf "%.6f", 0.7*previous + 0.3*current }')"
  fi

  eta_minutes="$(awk -v seconds="${SMOOTHED_ETA_SECONDS}" 'BEGIN { printf "%.1f", seconds/60.0 }')"
  echo "[progress] ${completed}/${total} files complete - estimated time remaining: ${eta_minutes} minutes"
}

die() {
  echo "[ERROR] $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

# Choose a timeout command
TIMEOUT_CMD=""
if command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_CMD="gtimeout"
elif command -v timeout >/dev/null 2>&1; then
  TIMEOUT_CMD="timeout"
else
  die "Missing timeout utility: install coreutils (gtimeout) or provide timeout"
fi

# Remote-run wrapper: hard timeout + retries + quadratic backoff.
remote_run() {
  # Usage: remote_run <command...>
  local attempt=1
  local rc=0
  local attempt_timeout
  local scratch_dir
  REMOTE_RUN_LAST_ATTEMPTS=0
  REMOTE_RUN_LAST_RC=0

  # Reuse one scratch directory per remote command invocation.
  scratch_dir="$(mktemp -d "${TMPDIR:-/tmp}/download_files_remote.XXXXXX")" || die "Unable to create remote scratch dir"

  while (( attempt <= REMOTE_RETRIES )); do
    attempt_timeout=$(( REMOTE_TIMEOUT + (attempt - 1) * REMOTE_TIMEOUT_STEP ))
    set +e
    (
      cd "${scratch_dir}" || exit 1
      "${TIMEOUT_CMD}" "${attempt_timeout}" "$@"
    )
    rc=$?
    set -e

    if (( rc == 0 )); then
      rm -rf -- "${scratch_dir}"
      REMOTE_RUN_LAST_ATTEMPTS="${attempt}"
      REMOTE_RUN_LAST_RC=0
      return 0
    fi

    echo "[WARN] Remote command failed/timeout (attempt ${attempt}/${REMOTE_RETRIES}, timeout=${attempt_timeout}s, rc=${rc}): $@" >&2
    if (( attempt < REMOTE_RETRIES )); then
      local sleep_s=$(( 3 * attempt * attempt ))
      sleep "${sleep_s}"
    fi
    (( attempt += 1 ))
  done

  rm -rf -- "${scratch_dir}"
  REMOTE_RUN_LAST_ATTEMPTS=$(( attempt - 1 ))
  REMOTE_RUN_LAST_RC="${rc}"
  return "${rc}"
}

# Create a stable output stem from a URL/path.
stem_from_url() {
  local url="$1"
  # Replace non-filename chars with underscores
  print -r -- "${url}" | sed -E 's@^[a-zA-Z]+://@@; s@[^A-Za-z0-9._-]+@_@g'
}

# Read first dimension size reported by: ncks --trd -m -v VAR FILE
dim0_size_from_ncks_meta() {
  awk -F'[,= ]+' '/dimension 0:/{for(i=1;i<=NF;i++) if($i=="size"){print $(i+1); exit}}'
}

# Read a named dimension size from `ncks -M` metadata output.
dim_size_from_ncks_header() {
  local metadata="$1"
  local dim_name="$2"

  awk -v dim="${dim_name}" '
    $1 == dim && $2 == "=" {
      gsub(/[^0-9]/, "", $3)
      print $3
      exit
    }
  ' <<< "${metadata}"
}

# Check whether a variable exists in `ncks -M` metadata output.
var_exists_in_ncks_header() {
  local metadata="$1"
  local var_name="$2"

  awk -v var="${var_name}" '
    $0 ~ "^[[:space:]]*[A-Za-z_][A-Za-z0-9_[:space:]]+[[:space:]]" var "[[:space:]]*\\(" {
      found = 1
      exit
    }
    END {
      exit(found ? 0 : 1)
    }
  ' <<< "${metadata}"
}

# ---------------------------
# Validate inputs
# ---------------------------
(( $# == 2 )) || die "Usage: $0 <url_list.txt> <output_dir>"

URL_LIST="$1"
OUT_DIR="$2"

[[ -f "${URL_LIST}" ]] || die "URL list not found: ${URL_LIST}"
mkdir -p "${OUT_DIR}" || die "Unable to create output dir: ${OUT_DIR}"
URL_LIST="${URL_LIST:A}"
OUT_DIR="${OUT_DIR:A}"

if [[ -n "${WORK_TMP_ROOT}" ]]; then
  mkdir -p "${WORK_TMP_ROOT}" || die "Unable to create WORK_TMP_ROOT: ${WORK_TMP_ROOT}"
  WORK_TMP_ROOT="${WORK_TMP_ROOT:A}"
fi

FAILED_URLS_FILE="${OUT_DIR}/failed_urls.txt"
rm -f "${FAILED_URLS_FILE}"

need_cmd ncks
need_cmd ncap2
need_cmd ncwa
need_cmd ncatted
need_cmd ncrename
need_cmd sed
need_cmd awk
need_cmd date
need_cmd mktemp

# ---------------------------
# Read URLs
# ---------------------------
typeset -a URLS
URLS=()
while IFS=$'\n' read -r line || [[ -n "${line}" ]]; do
  # Strip whitespace
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "${line}" ]] && continue
  [[ "${line}" == \#* ]] && continue
  URLS+=("${line}")
done < "${URL_LIST}"

[[ "${AUTO_MAX_JOBS_CAP}" == <-> ]] || die "AUTO_MAX_JOBS_CAP must be an integer >= 1"
[[ "${AUTO_MIN_IMPROVEMENT_PCT}" == <-> ]] || die "AUTO_MIN_IMPROVEMENT_PCT must be an integer >= 0"
[[ "${REMOTE_TIMEOUT_STEP}" == <-> ]] || die "REMOTE_TIMEOUT_STEP must be an integer >= 0"
[[ "${SKIP_EXISTING}" == <-> ]] || die "SKIP_EXISTING must be 0 or 1"
[[ "${Z_BIN_ENABLED}" == <-> ]] || die "Z_BIN_ENABLED must be 0 or 1"
(( AUTO_MAX_JOBS_CAP >= 1 )) || die "AUTO_MAX_JOBS_CAP must be >= 1"
(( REMOTE_TIMEOUT_STEP >= 0 )) || die "REMOTE_TIMEOUT_STEP must be >= 0"
(( SKIP_EXISTING == 0 || SKIP_EXISTING == 1 )) || die "SKIP_EXISTING must be 0 or 1"
(( Z_BIN_ENABLED == 0 || Z_BIN_ENABLED == 1 )) || die "Z_BIN_ENABLED must be 0 or 1"

if (( Z_BIN_ENABLED )); then
  [[ "${Z_BIN}" == <-> ]] || die "Z_BIN must be an integer >= 1"
  [[ "${Z_SUBSET_START}" == <-> ]] || die "Z_SUBSET_START must be an integer"
  [[ "${Z_SUBSET_END}" == <-> ]] || die "Z_SUBSET_END must be an integer"
  (( Z_BIN >= 1 )) || die "Z_BIN must be >= 1"
  (( Z_SUBSET_END >= Z_SUBSET_START )) || die "Z_SUBSET_END must be >= Z_SUBSET_START"
fi

typeset -A seen_stems
for u in "${URLS[@]}"; do
  seen_stem="$(stem_from_url "${u}")"
  [[ -z "${seen_stems[$seen_stem]-}" ]] || die "Duplicate output stem detected in URL list: ${seen_stem}"
  seen_stems[$seen_stem]=1
done

original_count=${#URLS}
skipped_existing=0
if (( SKIP_EXISTING )); then
  typeset -a remaining_urls
  remaining_urls=()
  for u in "${URLS[@]}"; do
    stem="$(stem_from_url "${u}")"
    final_out="${OUT_DIR}/${stem}_subset.nc"
    if [[ -s "${final_out}" ]]; then
      (( skipped_existing += 1 ))
    else
      remaining_urls+=("${u}")
    fi
  done
  URLS=("${remaining_urls[@]}")
fi

local_count=${#URLS}
if (( local_count == 0 )); then
  echo "[INFO] All ${original_count} outputs already exist in ${OUT_DIR}. Nothing to do."
  exit 0
fi

auto_mode=0
effective_max_jobs=1
if [[ "${MAX_JOBS}" == "auto" ]]; then
  auto_mode=1
  effective_max_jobs=2
  (( effective_max_jobs > AUTO_MAX_JOBS_CAP )) && effective_max_jobs="${AUTO_MAX_JOBS_CAP}"
else
  [[ "${MAX_JOBS}" == <-> ]] || die "MAX_JOBS must be an integer >= 1 or 'auto'"
  (( MAX_JOBS >= 1 )) || die "MAX_JOBS must be >= 1"
  effective_max_jobs="${MAX_JOBS}"
fi

if (( skipped_existing > 0 )); then
  echo "[INFO] Skipping ${skipped_existing} existing output(s); ${local_count} file(s) remain."
fi
echo "[INFO] Will process ${local_count} file(s) with MAX_JOBS=${MAX_JOBS}"
if [[ -n "${WORK_TMP_ROOT}" ]]; then
  echo "[INFO] Using WORK_TMP_ROOT=${WORK_TMP_ROOT} for per-file intermediates"
fi

# ---------------------------
# Main per-URL processing
# ---------------------------
process_one() {
  local url="$1"
  local idx="$2"
  local total="$3"
  local run_id="$4"
  local start_seconds="${SECONDS}"
  local job_log_file="${OUT_DIR}/.joblog_${run_id}.txt"

  {
    echo "[INFO] (${idx}/${total}) ${url}"

    local stem
    stem="$(stem_from_url "${url}")"

    local ts pid tmpdir
    ts="$(date +%Y%m%d_%H%M%S)"
    pid="$$"
    if [[ -n "${WORK_TMP_ROOT}" ]]; then
      tmpdir="$(mktemp -d "${WORK_TMP_ROOT}/download_files_tmp_run${run_id}_XXXXXX")" || {
        echo "[ERROR] [${stem}] Unable to create temp directory under WORK_TMP_ROOT=${WORK_TMP_ROOT}" >&2
        return 1
      }
    else
      tmpdir="${OUT_DIR}/.tmp_${ts}_run${run_id}"
      mkdir -p "${tmpdir}"
    fi

    local tmp_subset_depth="${tmpdir}/.subset_depth.${stem}.tmp.nc"
    local tmp_binned="${tmpdir}/.binned_xyz.${stem}.tmp.nc"
    local tmp_rho_mean="${tmpdir}/.rho_xy_mean.${stem}.tmp.nc"
    local tmp_final_canonical="${tmpdir}/.final_canonical.${stem}.tmp.nc"
    local tmp_rho_canonical="${tmpdir}/.rho_canonical.${stem}.tmp.nc"
    local job_stats_file="${OUT_DIR}/.jobstats_${run_id}.txt"
    local final_out="${OUT_DIR}/${stem}_subset.nc"

    # ---------------------------
    # Step 1: initialize optional-variable flags
    # ---------------------------
    log "1/8" "[${stem}] Initializing optional-variable flags (bb1 bb2 bb3)"
    local has_bb1=0 has_bb2=0 has_bb3=0

    # ---------------------------
    # Step 2: define binning factors
    # ---------------------------
    log "2/8" "[${stem}] Setting binning factors (2/8)"
    local xy_bin=2
    local z_bin=1
    local z_subset_start="${Z_SUBSET_START}"
    local z_subset_end="${Z_SUBSET_END}"
    if (( Z_BIN_ENABLED )); then
      z_bin="${Z_BIN}"
      log "2/8" "[${stem}] z-binning enabled: bin=${z_bin}, xc3[${z_subset_start}:${z_subset_end}]"
    else
      log "2/8" "[${stem}] z-binning disabled"
    fi

    # ---------------------------
    # Step 3: download source data without z-axis subsetting
    # ---------------------------
    log "3/8" "[${stem}] Downloading source data (3/8)"

    if (( Z_BIN_ENABLED )); then
      local z_subset_end_bounds=$(( z_subset_end + 1 ))
      if ! remote_run ncks -O \
        -d xc3,"${z_subset_start}","${z_subset_end}" \
        -d xb3,"${z_subset_start}","${z_subset_end_bounds}" \
        "${url}" \
        "${tmp_subset_depth}"; then
        local download_attempts_failed="${REMOTE_RUN_LAST_ATTEMPTS:-0}"
        local download_rc="${REMOTE_RUN_LAST_RC:-1}"
        echo "[ERROR] [${stem}] Remote download failed after ${download_attempts_failed} attempt(s) (last rc=${download_rc}): ${url}" >&2
        return "${download_rc}"
      fi
    else
      if ! remote_run ncks -O \
        "${url}" \
        "${tmp_subset_depth}"; then
      local download_attempts_failed="${REMOTE_RUN_LAST_ATTEMPTS:-0}"
      local download_rc="${REMOTE_RUN_LAST_RC:-1}"
      echo "[ERROR] [${stem}] Remote download failed after ${download_attempts_failed} attempt(s) (last rc=${download_rc}): ${url}" >&2
      return "${download_rc}"
    fi
    fi
    local download_attempts="${REMOTE_RUN_LAST_ATTEMPTS:-1}"
    [[ -s "${tmp_subset_depth}" ]] || {
      echo "[ERROR] [${stem}] Remote download did not create expected output: ${tmp_subset_depth}" >&2
      return 1
    }

    # ---------------------------
    # Step 4: detect optional vars locally, then read coordinate sizes
    # ---------------------------
    log "4/8" "[${stem}] Detecting optional vars locally + deriving output dimensions (4/8)"
    local xc1_len xc2_len xb1_len xb2_len xc3_len xb3_len ncks_header

    # Read local metadata once to avoid repeated subprocess startup overhead.
    ncks_header="$(ncks -M "${tmp_subset_depth}")" || {
      echo "[ERROR] [${stem}] Failed to inspect metadata for ${tmp_subset_depth}" >&2
      return 1
    }

    var_exists_in_ncks_header "${ncks_header}" bb1 && has_bb1=1
    var_exists_in_ncks_header "${ncks_header}" bb2 && has_bb2=1
    var_exists_in_ncks_header "${ncks_header}" bb3 && has_bb3=1

    (( has_bb1 )) && log "4/8" "[${stem}] Found bb1"
    (( has_bb2 )) && log "4/8" "[${stem}] Found bb2"
    (( has_bb3 )) && log "4/8" "[${stem}] Found bb3"

    xc1_len="$(dim_size_from_ncks_header "${ncks_header}" xc1)"
    xc2_len="$(dim_size_from_ncks_header "${ncks_header}" xc2)"
    xb1_len="$(dim_size_from_ncks_header "${ncks_header}" xb1)"
    xb2_len="$(dim_size_from_ncks_header "${ncks_header}" xb2)"
    xc3_len="$(dim_size_from_ncks_header "${ncks_header}" xc3)"
    xb3_len="$(dim_size_from_ncks_header "${ncks_header}" xb3)"

    # Fallback for edge-case metadata formats from older NCO builds.
    if [[ -z "${xc1_len}" || -z "${xc2_len}" || -z "${xb1_len}" || -z "${xb2_len}" || -z "${xc3_len}" || -z "${xb3_len}" ]]; then
      xc1_len="$(ncks --trd -m -v xc1 "${tmp_subset_depth}" | dim0_size_from_ncks_meta)"
      xc2_len="$(ncks --trd -m -v xc2 "${tmp_subset_depth}" | dim0_size_from_ncks_meta)"
      xb1_len="$(ncks --trd -m -v xb1 "${tmp_subset_depth}" | dim0_size_from_ncks_meta)"
      xb2_len="$(ncks --trd -m -v xb2 "${tmp_subset_depth}" | dim0_size_from_ncks_meta)"
      xc3_len="$(ncks --trd -m -v xc3 "${tmp_subset_depth}" | dim0_size_from_ncks_meta)"
      xb3_len="$(ncks --trd -m -v xb3 "${tmp_subset_depth}" | dim0_size_from_ncks_meta)"
    fi

    [[ -n "${xc1_len}" && -n "${xc2_len}" && -n "${xb1_len}" && -n "${xb2_len}" && -n "${xc3_len}" && -n "${xb3_len}" ]] || {
      echo "[ERROR] [${stem}] Failed to derive coordinate lengths from ${tmp_subset_depth}" >&2
      return 1
    }

    (( xc1_len % xy_bin == 0 )) || die "xc1 length ${xc1_len} is not divisible by ${xy_bin}"
    (( xc2_len % xy_bin == 0 )) || die "xc2 length ${xc2_len} is not divisible by ${xy_bin}"
    (( xb1_len == xc1_len + 1 )) || die "xb1 length ${xb1_len} is inconsistent with xc1 length ${xc1_len}"
    (( xb2_len == xc2_len + 1 )) || die "xb2 length ${xb2_len} is inconsistent with xc2 length ${xc2_len}"
    (( xb3_len == xc3_len + 1 )) || die "xb3 length ${xb3_len} is inconsistent with xc3 length ${xc3_len}"
    (( xc3_len % z_bin == 0 )) || die "xc3 length ${xc3_len} is not divisible by z_bin=${z_bin}"

    local xc1_last=$(( xc1_len - 1 ))
    local xc2_last=$(( xc2_len - 1 ))
    local xb1_last=$(( xb1_len - 1 ))
    local xb2_last=$(( xb2_len - 1 ))
    local xc3_last=$(( xc3_len - 1 ))
    local xb3_last=$(( xb3_len - 1 ))

    local xc1b_len=$(( xc1_len / xy_bin ))
    local xc2b_len=$(( xc2_len / xy_bin ))
    local xb1b_len=$(( (xb1_len + 1) / xy_bin ))
    local xb2b_len=$(( (xb2_len + 1) / xy_bin ))
    local xc3b_len=$(( xc3_len / z_bin ))
    local xb3b_len=$(( xc3b_len + 1 ))

    # ---------------------------
    # Step 5: strip _FillValue (avoid NaNs breaking NCO arithmetic)
    # ---------------------------
    log "5/8" "[${stem}] Stripping _FillValue for coords + physical vars (NaN fill breaks NCO arithmetic) (5/8)"

    local coords=( xc1 xc2 xc3 xb1 xb2 xb3 )
    local phys=( rho v1 v2 v3 ei )
    (( has_bb1 )) && phys+=( bb1 )
    (( has_bb2 )) && phys+=( bb2 )
    (( has_bb3 )) && phys+=( bb3 )

    local v
    local ncatted_args=()
    for v in "${coords[@]}" "${phys[@]}"; do
      ncatted_args+=( -a _FillValue,"${v}",d,, )
    done
    ncatted -O "${ncatted_args[@]}" "${tmp_subset_depth}" >/dev/null || {
      echo "[ERROR] [${stem}] Failed to strip _FillValue attributes from ${tmp_subset_depth}" >&2
      return 1
    }

    # ---------------------------
    # Step 6: binning (x/y by 2; z unchanged)
    # ---------------------------
    log "6/8" "[${stem}] Binning: x/y by 2; z by ${z_bin} (6/8)"

    local expr=""
    expr+='defdim("xc1b",'${xc1b_len}');'
    expr+='defdim("xc2b",'${xc2b_len}');'
    expr+='defdim("xb1b",'${xb1b_len}');'
    expr+='defdim("xb2b",'${xb2b_len}');'
    expr+='defdim("xc3b",'${xc3b_len}');'
    expr+='defdim("xb3b",'${xb3b_len}');'

    # x/y centers averaged in pairs; x/y bounds take every other
    expr+='xc1b[$xc1b]=0.5*(xc1(0:'${xc1_last}':'${xy_bin}')+xc1(1:'${xc1_last}':'${xy_bin}'));'
    expr+='xc2b[$xc2b]=0.5*(xc2(0:'${xc2_last}':'${xy_bin}')+xc2(1:'${xc2_last}':'${xy_bin}'));'
    expr+='xb1b[$xb1b]=xb1(0:'${xb1_last}':'${xy_bin}');'
    expr+='xb2b[$xb2b]=xb2(0:'${xb2_last}':'${xy_bin}');'

    # Vertical coordinates averaged in bins; bounds take every z_bin-th entry
    local z_terms=""
    local k
    for (( k=0; k<z_bin; k++ )); do
      local term="xc3(${k}:${xc3_last}:${z_bin})"
      if [[ -z "${z_terms}" ]]; then
        z_terms="${term}"
      else
        z_terms+="+${term}"
      fi
    done
    expr+='xc3b[$xc3b]=(1.0/'${z_bin}')*('${z_terms}');'
    expr+='xb3b[$xb3b]=xb3(0:'${xb3_last}':'${z_bin}');'

    # Variables to bin
    local bin_vars=( rho v1 v2 v3 ei )
    (( has_bb1 )) && bin_vars+=( bb1 )
    (( has_bb2 )) && bin_vars+=( bb2 )
    (( has_bb3 )) && bin_vars+=( bb3 )

    # Build binned expressions for each variable
    for v in "${bin_vars[@]}"; do
      expr+="${v}_binned[\$xc3b,\$xc2b,\$xc1b]=(1.0/${z_bin})*0.25*("
      local z_sum=""
      for (( k=0; k<z_bin; k++ )); do
        local z_slice="${k}:${xc3_last}:${z_bin}"
        local xy_sum="(${v}(${z_slice},0:${xc2_last}:${xy_bin},0:${xc1_last}:${xy_bin})+"
        xy_sum+="${v}(${z_slice},1:${xc2_last}:${xy_bin},0:${xc1_last}:${xy_bin})+"
        xy_sum+="${v}(${z_slice},0:${xc2_last}:${xy_bin},1:${xc1_last}:${xy_bin})+"
        xy_sum+="${v}(${z_slice},1:${xc2_last}:${xy_bin},1:${xc1_last}:${xy_bin}))"
        if [[ -z "${z_sum}" ]]; then
          z_sum="${xy_sum}"
        else
          z_sum+="+${xy_sum}"
        fi
      done
      expr+="${z_sum});"
    done

    ncap2 -O -s "${expr}" "${tmp_subset_depth}" "${tmp_binned}" || {
      echo "[ERROR] [${stem}] Failed to compute binned output from ${tmp_subset_depth}" >&2
      return 1
    }

    # ---------------------------
    # Step 7: compute rho_xy_mean AFTER all binning
    # ---------------------------
    log "7/8" "[${stem}] Computing rho_xy_mean AFTER all binning (7/8)"
    ncwa -O -a xc1b,xc2b -v rho_binned "${tmp_binned}" "${tmp_rho_mean}" || {
      echo "[ERROR] [${stem}] Failed to compute rho_xy_mean from ${tmp_binned}" >&2
      return 1
    }
    ncrename -O -v rho_binned,rho "${tmp_rho_mean}" || {
      echo "[ERROR] [${stem}] Failed to rename rho_binned in ${tmp_rho_mean}" >&2
      return 1
    }

    # ---------------------------
    # Step 8: write final output
    # ---------------------------
    log "8/8" "[${stem}] Writing final output to ${final_out} (8/8)"

    # Collect output variables
    local out_vars=( xc1b xc2b xc3b xb1b xb2b xb3b )
    local keep_phys=( v1 v2 v3 ei )
    (( has_bb1 )) && keep_phys+=( bb1 )
    (( has_bb2 )) && keep_phys+=( bb2 )
    (( has_bb3 )) && keep_phys+=( bb3 )

    for v in "${keep_phys[@]}"; do
      out_vars+=( "${v}_binned" )
    done

    local out_vars_csv
    out_vars_csv="$(IFS=,; echo "${out_vars[*]}")"

    # Write a classic-NetCDF staging file first.
    #
    # Renaming binned coordinate dimensions/variables directly in the compressed
    # NetCDF4 output causes the coordinate payload to be replaced by the default
    # fill value (9.969e36). Staging through a classic file avoids that NCO path,
    # preserves the coordinate arrays, and still lets us compress the final output.
    ncks -O -3 -v "${out_vars_csv}" "${tmp_binned}" "${tmp_final_canonical}" || {
      echo "[ERROR] [${stem}] Failed to stage canonical output from ${tmp_binned}" >&2
      return 1
    }

    # Rename dims/vars back to canonical names (xc1b->xc1, v1_binned->v1, etc.)
    local rename_args=(
      -d xc1b,xc1 -d xc2b,xc2 -d xc3b,xc3 -d xb1b,xb1 -d xb2b,xb2 -d xb3b,xb3
      -v xc1b,xc1 -v xc2b,xc2 -v xc3b,xc3 -v xb1b,xb1 -v xb2b,xb2 -v xb3b,xb3
    )
    for v in "${keep_phys[@]}"; do
      rename_args+=( -v "${v}_binned,${v}" )
    done
    ncrename -O "${rename_args[@]}" "${tmp_final_canonical}" || {
      echo "[ERROR] [${stem}] Failed to rename canonical variables in ${tmp_final_canonical}" >&2
      return 1
    }

    # Prepare rho on the canonical vertical dimension before appending it.
    # This avoids reintroducing xc3b into the final file.
    ncks -O -3 -v xc3b,rho "${tmp_rho_mean}" "${tmp_rho_canonical}" || {
      echo "[ERROR] [${stem}] Failed to stage rho output from ${tmp_rho_mean}" >&2
      return 1
    }
    ncrename -O -d xc3b,xc3 -v xc3b,xc3 "${tmp_rho_canonical}" || {
      echo "[ERROR] [${stem}] Failed to canonicalize rho dimensions in ${tmp_rho_canonical}" >&2
      return 1
    }
    ncks -A -v rho "${tmp_rho_canonical}" "${tmp_final_canonical}" || {
      echo "[ERROR] [${stem}] Failed to append rho into ${tmp_final_canonical}" >&2
      return 1
    }

    # Compress only after the canonical-coordinate file is complete.
    ncks -O -4 -L 4 "${tmp_final_canonical}" "${final_out}" || {
      echo "[ERROR] [${stem}] Failed to compress final output to ${final_out}" >&2
      return 1
    }

    # Optional pacing knob for debugging or server-throttling experiments.
    (( POST_FILE_SLEEP > 0 )) && sleep "${POST_FILE_SLEEP}"

    local duration_sec=$(( SECONDS - start_seconds ))
    printf '%s %s\n' "${download_attempts}" "${duration_sec}" > "${job_stats_file}"
    echo "[DONE] [${stem}] Wrote: ${final_out}"

    # Clean up temp dir (comment out if you want to inspect intermediates)
    rm -rf "${tmpdir}"
  } > "${job_log_file}" 2>&1
}

# ---------------------------
# Run
# ---------------------------
typeset -a batch_pids
typeset -A pid_to_label
typeset -A pid_to_stats
typeset -A pid_to_log

current_jobs="${effective_max_jobs}"
best_jobs=1
best_throughput_milli=0
auto_locked=0
run_start_seconds="${SECONDS}"
completed_total=0
successful_total=0
failed_total=0
SMOOTHED_ETA_SECONDS=""

i=1
while (( i <= local_count )); do
  batch_pids=()
  pid_to_label=()
  pid_to_stats=()
  pid_to_log=()
  typeset -A pid_to_run_id
  pid_to_run_id=()

  batch_slots="${current_jobs}"
  (( batch_slots > local_count - i + 1 )) && batch_slots=$(( local_count - i + 1 ))
  batch_start="${SECONDS}"
  batch_completed=0
  batch_retry_count=0
  batch_failure_count=0

  if (( batch_slots == 1 )); then
    u="${URLS[$i]}"
    run_id="$$_${RANDOM}_${i}"
    stats_file="${OUT_DIR}/.jobstats_${run_id}.txt"
    log_file="${OUT_DIR}/.joblog_${run_id}.txt"
    if ! process_one "${u}" "${i}" "${local_count}" "${run_id}"; then
      emit_log_block "${log_file}"
      cleanup_run_tmpdirs "${run_id}"
      record_failed_url "${u}"
      (( failed_total += 1 ))
      batch_failure_count=1
      batch_completed=1
      (( completed_total += 1 ))
      print_progress_estimate "${completed_total}" "${local_count}" "${run_start_seconds}"
      echo "[WARN] Continuing after failed URL. Saved to ${FAILED_URLS_FILE}: ${u}"
      (( i += 1 ))
      continue
    fi
    emit_log_block "${log_file}"

    attempts=1
    duration=0
    if [[ -f "${stats_file}" ]]; then
      read -r attempts duration < "${stats_file}"
      rm -f "${stats_file}"
    fi

    if (( attempts > 1 )); then
      (( batch_retry_count += 1 ))
    fi
    batch_completed=1
    (( successful_total += 1 ))
    (( completed_total += 1 ))
    print_progress_estimate "${completed_total}" "${local_count}" "${run_start_seconds}"
    (( i += 1 ))
  else
    launched=0
    while (( launched < batch_slots )); do
      u="${URLS[$i]}"
      run_id="$$_${RANDOM}_${i}"
      process_one "${u}" "${i}" "${local_count}" "${run_id}" &
      batch_pids+=( "$!" )
      pid_to_label[$!]="${u}"
      pid_to_stats[$!]="${OUT_DIR}/.jobstats_${run_id}.txt"
      pid_to_log[$!]="${OUT_DIR}/.joblog_${run_id}.txt"
      pid_to_run_id[$!]="${run_id}"
      (( i += 1 ))
      (( launched += 1 ))
    done

    for pid in "${batch_pids[@]}"; do
      if ! wait "${pid}"; then
        emit_log_block "${pid_to_log[$pid]-}"
        cleanup_run_tmpdirs "${pid_to_run_id[$pid]-}"
        record_failed_url "${pid_to_label[$pid]}"
        (( failed_total += 1 ))
        (( batch_failure_count += 1 ))
        (( batch_completed += 1 ))
        (( completed_total += 1 ))
        print_progress_estimate "${completed_total}" "${local_count}" "${run_start_seconds}"
        echo "[WARN] Continuing after failed URL. Saved to ${FAILED_URLS_FILE}: ${pid_to_label[$pid]}"
        continue
      fi
      emit_log_block "${pid_to_log[$pid]-}"

      stats_file="${pid_to_stats[$pid]}"
      attempts=1
      duration=0
      if [[ -f "${stats_file}" ]]; then
        read -r attempts duration < "${stats_file}"
        rm -f "${stats_file}"
      fi

      if (( attempts > 1 )); then
        (( batch_retry_count += 1 ))
      fi
      (( batch_completed += 1 ))
      (( successful_total += 1 ))
      (( completed_total += 1 ))
      print_progress_estimate "${completed_total}" "${local_count}" "${run_start_seconds}"
    done
  fi

  if (( auto_mode )); then
    batch_wall=$(( SECONDS - batch_start ))
    (( batch_wall < 1 )) && batch_wall=1
    throughput_milli=$(( (1000 * batch_completed) / batch_wall ))

    echo "[AUTO] batch_jobs=${current_jobs} completed=${batch_completed} wall=${batch_wall}s retries=${batch_retry_count} failures=${batch_failure_count} throughput=${throughput_milli} mpf"

    if (( auto_locked == 0 )); then
      if (( batch_retry_count > 0 || batch_failure_count > 0 )); then
        (( current_jobs > 1 )) && current_jobs=$(( current_jobs - 1 ))
        best_jobs="${current_jobs}"
        auto_locked=1
        echo "[AUTO] Retries or failures detected. Holding remaining jobs at ${current_jobs}."
      elif (( best_throughput_milli == 0 )); then
        best_throughput_milli="${throughput_milli}"
        best_jobs="${current_jobs}"
        if (( current_jobs < AUTO_MAX_JOBS_CAP && i <= local_count )); then
          current_jobs=$(( current_jobs + 1 ))
          echo "[AUTO] Baseline established. Increasing jobs to ${current_jobs}."
        else
          auto_locked=1
        fi
      else
        required_throughput=$(( best_throughput_milli + (best_throughput_milli * AUTO_MIN_IMPROVEMENT_PCT) / 100 ))
        if (( throughput_milli >= required_throughput )); then
          best_throughput_milli="${throughput_milli}"
          best_jobs="${current_jobs}"
          if (( current_jobs < AUTO_MAX_JOBS_CAP && i <= local_count )); then
            current_jobs=$(( current_jobs + 1 ))
            echo "[AUTO] Throughput improved. Increasing jobs to ${current_jobs}."
          else
            auto_locked=1
          fi
        else
          current_jobs="${best_jobs}"
          auto_locked=1
          echo "[AUTO] Throughput gain was insufficient. Holding remaining jobs at ${current_jobs}."
        fi
      fi
    fi
  fi
done

if (( failed_total > 0 )); then
  echo "[WARN] Completed ${completed_total}/${local_count} files with ${successful_total} success(es) and ${failed_total} failure(s)."
  echo "[WARN] Failed URLs saved to ${FAILED_URLS_FILE}"
else
  rm -f "${FAILED_URLS_FILE}"
  echo "[INFO] Completed ${local_count}/${local_count}"
fi
