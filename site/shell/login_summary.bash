# Inline this fragment once after the existing default-directory selection.
if [[ $HOSTNAME =~ login && $- == *i* && $EUID != 0 && -z ${SLURM_JOB_ID:-} \
    && -z ${SLURM_JOBID:-} && -z ${_SAI_LOGIN_SUMMARY_SHOWN:-} ]] && shopt -q login_shell; then
    export _SAI_LOGIN_SUMMARY_SHOWN=1
    cat /opt/sai/shell/aliases.txt
    source /opt/sai/shell/rules.bash
    source /opt/sai/shell/status.bash --summary
    source /opt/sai/shell/notes.bash
    _sai_summary_args=(status --format tui --timeout 3)
    if [[ -n ${_SAI_LOGIN_ACCOUNT:-} ]]; then
        _sai_summary_args+=(--account "$_SAI_LOGIN_ACCOUNT")
    fi
    # Allow the bounded credential exchange to finish saving a rotated session.
    timeout -k 11s 5s /opt/sai/bin/sai "${_sai_summary_args[@]}" || {
        _sai_summary_rc=$?
        if [[ -n ${_SAI_LOGIN_ACCOUNT:-} ]]; then
            printf 'Slurm Account  %q\n' "$_SAI_LOGIN_ACCOUNT"
        fi
        printf '当前目录  %q\n' "$PWD"
        if [[ $_sai_summary_rc == 124 || $_sai_summary_rc == 137 ]]; then
            printf '%s\n' 'SAI：登录摘要读取超时，可用 sai status --format tui 重试。' >&2
        fi
    }
    unset _sai_summary_args _sai_summary_rc
fi
