import os
from pathlib import Path
import subprocess


def test_quota_function_delegates_once_and_keeps_filenames_as_data(tmp_path):
    root=Path(__file__).parents[1]
    before=tmp_path/'profile.before';after=tmp_path/'profile.after'
    before.write_text('''quota() {
    local path="${1:-.}" project_id
    read -r project_id _ < <(lfs project -d -- "$path") || return
    [[ $project_id =~ ^[1-9][0-9]*$ ]] || {
        printf 'No project quota for %s\\n' "$path" >&2
        return 1
    }
    lfs quota -ph "$project_id" "$path"
}
''')
    subprocess.run(['patch','--batch','--forward','-o',str(after),str(before),
                    str(root/'site/shell/local_quota.patch')],check=True,capture_output=True)
    subprocess.run(['bash','-n',str(after)],check=True)
    command=tmp_path/'sai'
    command.write_text('#!/bin/bash\nprintf "argument=%s\\n" "$@"\n')
    command.chmod(0o755)
    after.write_text(after.read_text().replace('/opt/sai/bin/sai',str(command)))
    for path in (None,'space name','-leading','semi;$(command)'):
        args=[] if path is None else [path]
        done=subprocess.run(['bash','--noprofile','--norc','-c','source "$1"; shift; quota "$@"',
                             'bash',str(after),*args],env=os.environ,text=True,capture_output=True)
        assert done.returncode==0 and not done.stderr
        assert done.stdout.splitlines()==['argument=storage','argument=local-quota','argument=--format',
                                           'argument=table','argument=--','argument='+('.' if path is None else path)]
