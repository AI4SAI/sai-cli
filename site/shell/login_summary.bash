# Inline this fragment once after the existing default-directory selection.
if [[ $HOSTNAME =~ login && $- == *i* && $EUID != 0 && -z ${SLURM_JOB_ID:-} \
    && -z ${SLURM_JOBID:-} && -z ${_SAI_LOGIN_SUMMARY_SHOWN:-} ]] && shopt -q login_shell; then
    export _SAI_LOGIN_SUMMARY_SHOWN=1
    _sai_summary_args=(status --format tui)
    if [[ -n ${_SAI_LOGIN_ACCOUNT:-} ]]; then
        _sai_summary_args+=(--account "$_SAI_LOGIN_ACCOUNT")
    fi
    timeout -k 1s 2s /opt/sai/bin/sai "${_sai_summary_args[@]}" || {
        _sai_summary_rc=$?
        if [[ $_sai_summary_rc == 124 || $_sai_summary_rc == 137 ]]; then
            printf '%s\n' 'SAI：登录摘要读取超时，可用 sai status --format tui 重试。' >&2
        fi
    }
    unset _sai_summary_args _sai_summary_rc
fi
