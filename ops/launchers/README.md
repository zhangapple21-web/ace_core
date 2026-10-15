# launchers

Two hidden Windows Script Host launchers, plus the installer that reconstructs the
tinghe site's scheduled tasks. They were untracked files under `C:\tmp` until
2026-10-15; the repository is now the source of truth and the deployed copies are
written *from* here.

## run-hidden-wait.vbs

Launches hidden and waits for the child to exit, so a scheduled task stays
`Running` for the real lifetime of its job and `MultipleInstances=IgnoreNew`
actually works.

It routes `.cmd`/`.bat` targets through `cmd.exe /c` rather than handing them to
ShellExecute. That is not decoration. ShellExecute asks the Attachment Manager
about the file being executed; for an unsigned `.cmd` that raised "Open File -
Security Warning" and **blocked the job until somebody clicked it**. All eight
tinghe tasks went through this launcher, so every fire was waiting on a person.

The routing is conditional on the extension. A caller passing anything else keeps
the previous behaviour.

The `.cmd` routing is pinned by `ops/test_hidden_launcher.py`, including a
behavioural test that launches a real `.cmd` and asserts both that it ran and that
no dialog appeared. See that file before changing this one.

## run-hidden.vbs

The non-waiting sibling, used by four ACE tasks that pass `powershell.exe` with
its own arguments. **Do not add `cmd.exe` routing here.** Its first argument is a
signed, unzoned executable, so no dialog arises, and wrapping it would mis-handle
the arguments that follow it.

## install_tinghe_tasks.ps1

Reconstructs the eight tinghe scheduled tasks from the table inside it:

```powershell
ops\install_tinghe_tasks.ps1 -Check          # does the machine match the table?
ops\install_tinghe_tasks.ps1                 # deploy launcher, wrappers, tasks
ops\install_tinghe_tasks.ps1 -Force          # also replace existing wrappers
ops\install_tinghe_tasks.ps1 -Remove
```

`-Check` reports `[ok]`, `[drift]` or `[not installed]` per task and exits non-zero
on any of them. The install path re-reads every definition back after registering
and refuses to report success on drift.

The task table is **not uniform**, and the per-task rows are deliberate:
`tinghe-genre-check` alone runs elevated with a one-hour cap and no battery or wake
permission, and `tinghe-daily-origin` alone retries twice. Collapsing the rows into
one settings block would silently change both.

### Site path

The script contains no CJK literal. PowerShell 5.1 reads a `.ps1` without a BOM in
the ANSI codepage, so a Chinese path written here would be silently mangled. The
site root is recovered from the deployed wrappers - the machine's own record of
where its site lives - or supplied with `-Site` on a fresh host:

```powershell
ops\install_tinghe_tasks.ps1 -Site "D:\..." 
```

### Wrapper encoding

Wrappers are written as **GBK (codepage 936)** with CRLF and absolute log paths
under the site directory. cmd.exe reads a batch file in the OEM codepage, so a
UTF-8 wrapper would make its `cd` fail; a relative log path would write into the
wrappers directory instead of the site. `ops/test_tinghe_task_installer.py` pins
both of these, and pins `-Argument` being singular - `New-ScheduledTaskAction`'s
parameter is `-Argument` while the task object's property is `Arguments`, and
passing the plural form fails parameter binding so the installer registers nothing
at all.
