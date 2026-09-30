param(
  [Parameter(Mandatory=$true)][string]$WorkspaceRoot,
  [switch]$WithVideo,
  [switch]$WithOptional,
  [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
  $launcher = $py.Source
  $prefix = @('-3')
} else {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if (-not $python) { throw '找不到 Python 3.11+；请先安装 Python。' }
  $launcher = $python.Source
  $prefix = @()
}
$args = @((Join-Path $PSScriptRoot 'restore_from_remote.py'), '--workspace-root', $WorkspaceRoot)
if ($WithVideo) { $args += '--with-video' }
if ($WithOptional) { $args += '--with-optional' }
if ($SkipTests) { $args += '--skip-tests' }
& $launcher @prefix @args
exit $LASTEXITCODE
