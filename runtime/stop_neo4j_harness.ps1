$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workDir = Join-Path $scriptRoot 'neo4j-harness'
$pidPath = Join-Path $workDir 'neo4j.pid'

$stopped = $false
if (Test-Path $pidPath) {
    $pidValue = (Get-Content $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($pidValue) {
        $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $pidValue -Force
            Write-Output "Stopped Neo4j harness PID $pidValue"
            $stopped = $true
        }
    }
    Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
}

if (-not $stopped) {
    $connection = Get-NetTCPConnection -LocalPort 7687 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($connection) {
        Stop-Process -Id $connection.OwningProcess -Force
        Write-Output "Stopped process bound to port 7687 (PID $($connection.OwningProcess))"
        $stopped = $true
    }
}

if (-not $stopped) {
    Write-Output 'Neo4j harness is not running.'
}