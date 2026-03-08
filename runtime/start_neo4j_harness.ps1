$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workDir = Join-Path $scriptRoot 'neo4j-harness'
$jarPath = Join-Path $workDir 'target\neo4j-harness-runner-0.1.0.jar'
$pidPath = Join-Path $workDir 'neo4j.pid'

if (-not (Test-Path $jarPath)) {
    throw "Neo4j harness jar not found: $jarPath"
}

if (Test-Path $pidPath) {
    $existingPid = (Get-Content $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($existingPid) {
        $running = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($running) {
            Write-Output "Neo4j harness is already running with PID $existingPid"
            exit 0
        }
    }
    Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
}

$javaCandidates = @()
if ($env:JAVA_HOME) {
    $javaCandidates += (Join-Path $env:JAVA_HOME 'bin\java.exe')
}
$javaCandidates += 'D:\get_jobs\JDK\bin\java.exe'
$javaCandidates += 'java'
$javaCommand = $javaCandidates | Where-Object { $_ -eq 'java' -or (Test-Path $_) } | Select-Object -First 1

if (-not $javaCommand) {
    throw 'No Java runtime found. Set JAVA_HOME or install Java 21.'
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $javaCommand
$psi.Arguments = "-jar `"$jarPath`""
$psi.WorkingDirectory = $workDir
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$process = [System.Diagnostics.Process]::Start($psi)
if (-not $process) {
    throw 'Failed to start Neo4j harness process.'
}

$process.Id | Set-Content -Encoding ascii $pidPath
Start-Sleep -Seconds 4
Write-Output "Neo4j harness started on bolt://localhost:7687 with PID $($process.Id)"