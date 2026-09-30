param(
  [string]$WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python -and $python.Source -like '*WindowsApps*') { $python = $null }
$launcher = $null
if ($python) {
  $launcher = $python.Source
  $prefix = @()
} else {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if (-not $py) { throw '找不到 Python 3.11+；请先安装 Python。' }
  $launcher = $py.Source
  $prefix = @('-3')
}
$args = @((Join-Path $PSScriptRoot 'bootstrap.py'), '--workspace-root', $WorkspaceRoot)
if ($SkipTests) { $args += '--skip-tests' }
& $launcher @prefix @args
exit $LASTEXITCODE

