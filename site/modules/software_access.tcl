# Shared Tcl module preflight. File permissions remain the execution boundary.
namespace eval sai_software_access {
    variable binding_file [file join [file dirname [info script]] software-access.tsv]
}

proc sai_require_software_access {software} {
    if {![module-info mode load]} {
        return
    }
    set unavailable "软件访问配置不可用，请联系管理员"
    if {[catch {
        set channel [open $::sai_software_access::binding_file r]
        try {
            fconfigure $channel -encoding utf-8
            set contents [read $channel 65537]
        } finally {
            close $channel
        }
        if {[string length $contents] > 65536} {error $unavailable}
        set lines [split [string trimright $contents "\n"] "\n"]
        if {[lindex $lines 0] ne "# sai-software-access/v1"} {error $unavailable}
        set bindings [dict create]
        foreach line [lrange $lines 1 end] {
            set fields [split $line "\t"]
            if {[llength $fields] != 3} {error $unavailable}
            lassign $fields key gid label
            if {![regexp {^[a-z][a-z0-9_-]{1,63}$} $key]
                || ![regexp {^[1-9][0-9]{0,9}$} $gid]
                || $gid >= 4294967295
                || [string length $label] == 0 || [string length $label] > 128
                || [regexp {[\x00-\x1f\x7f-\x9f]} $label]
                || [dict exists $bindings $key]} {error $unavailable}
            dict set bindings $key [list $gid $label]
        }
        lassign [dict get $bindings $software] required_gid display_name
    }]} {
        error $unavailable
    }
    # No username: numeric credentials of this process, with no NSS name lookup.
    if {[catch {exec /usr/bin/id -G} groups]} {
        error "当前会话权限无法读取，请重新登录"
    }
    if {![regexp {^[0-9]+([ \t]+[0-9]+)*$} [string trim $groups]]} {
        error "当前会话权限无法读取，请重新登录"
    }
    set groups [regexp -all -inline {[0-9]+} $groups]
    if {[lsearch -exact $groups $required_gid] < 0} {
        error "$display_name 当前会话无权限：控制台开通；已开通请重新登录"
    }
}
