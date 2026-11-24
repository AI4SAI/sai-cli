# Shared Tcl module preflight. File permissions remain the execution boundary.
namespace eval sai_software_access {
    variable binding_file [file join [file dirname [info script]] software-access.tsv]
}

proc sai_require_software_access {software install_root} {
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
            dict set bindings $key $label
        }
        set display_name [dict get $bindings $software]
        if {[file pathtype $install_root] ne "absolute" || [file normalize $install_root] ne $install_root} {
            error $unavailable
        }
        file lstat $install_root guard
        if {$guard(type) ne "directory" || ($guard(mode) & 0057) != 0050} {error $unavailable}
    }]} {
        error $unavailable
    }
    # Publication pairs each module with the installation guarded by its registered group.
    # The kernel can use supplementary groups even when their numbers are unmapped.
    if {![file readable $install_root] || ![file executable $install_root]} {
        error "$display_name 当前会话无权限：控制台开通；已开通请重新登录"
    }
}
