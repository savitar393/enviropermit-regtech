$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$maven = Get-Command mvn -ErrorAction SilentlyContinue
if ($maven) { $mavenPath = $maven.Source }
else { $mavenPath = Join-Path $projectRoot '.tools/apache-maven-3.9.9/bin/mvn.cmd' }
if (-not (Test-Path -LiteralPath $mavenPath)) { throw 'Install Maven 3.9.9 or put it in .tools/apache-maven-3.9.9' }
if (-not $env:JAVA_HOME) {
    $javaPath = (Get-Command javac).Source
    $env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $javaPath)
}
& $mavenPath "-Dmaven.repo.local=$projectRoot/.tools/m2" -f "$projectRoot/services/reasoner/pom.xml" package -B -ntp
exit $LASTEXITCODE
