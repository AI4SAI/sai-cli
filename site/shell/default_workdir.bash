# Sourced by the shared interactive login profile; native Slurm owns the default.
_sai_default_workdir() {
    local username config key equal value extra cluster='' rows
    local row_cluster account row_user lineage parent candidate selected='' home_root=/home
    local token='^[a-z][a-z0-9_-]{0,63}$'

    username=$(id -un) || return 1
    [[ $username =~ $token ]] || return 1
    config=$(timeout 2s scontrol show config 2>/dev/null) || return 1
    while read -r key equal value extra; do
        [[ $key == ClusterName && $equal == = ]] || continue
        [[ $value =~ $token && -z $extra && -z $cluster ]] || return 1
        cluster=$value
    done <<< "$config"
    [[ -n $cluster ]] || return 1

    rows=$(timeout 2s sacctmgr -nP show assoc OnlyDefaults \
        where "user=$username" "cluster=$cluster" \
        format=Cluster,Account,User,Lineage 2>/dev/null) || return 1
    [[ -n $rows && ${#rows} -le 32768 ]] || return 1
    while IFS='|' read -r row_cluster account row_user lineage extra; do
        [[ $row_cluster == "$cluster" && $row_user == "$username" \
            && $account =~ $token && -z $extra ]] || return 1
        [[ $lineage == */0-"$username"/ ]] || return 1
        lineage=${lineage%/0-"$username"/}
        case $account in
            private-"$username")
                [[ $lineage == /"$account" ]] || return 1
                candidate=$home_root/$username
                ;;
            private-*) return 1 ;;
            proj-*)
                parent=${lineage%/"$account"}
                parent=${parent#/}
                [[ $parent =~ $token && $lineage == /"$parent"/"$account" ]] || return 1
                candidate=/org/$parent/$account
                ;;
            *)
                [[ $lineage == /"$account" ]] || return 1
                candidate=/org/$account/$username
                ;;
        esac
        [[ -z $selected || $selected == "$candidate" ]] || return 1
        selected=$candidate
    done <<< "$rows"
    [[ -n $selected ]] || return 1
    printf '%s\n' "$selected"
}

# A nested shell, a job, or an explicit initial directory keeps its location.
if [[ $- == *i* && $UID != 0 && -z ${SLURM_JOB_ID:-} \
    && -z ${_SAI_LOGIN_DIRECTORY_ENTERED:-} && $PWD == "$HOME" ]] \
    && shopt -q login_shell; then
    _SAI_LOGIN_DIRECTORY_ENTERED=1
    if _sai_login_directory=$(_sai_default_workdir); then
        if ! builtin cd -- "$_sai_login_directory" 2>/dev/null; then
            printf '%s\n' 'SAI: the default identity directory is unavailable; current directory retained.' >&2
        fi
    else
        printf '%s\n' 'SAI: the default identity could not be resolved; current directory retained.' >&2
    fi
    unset _sai_login_directory
fi
