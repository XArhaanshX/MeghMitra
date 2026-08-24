# Windows stand-in for Makefile targets. GNU make is not required.
# From the repo root:
#   .\scripts\dev.ps1 docker-up
#   .\scripts\dev.ps1 migrate
#   .\scripts\dev.ps1 seed
#   .\scripts\dev.ps1 dev

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "help", "docker-up", "docker-down", "docker-reset", "migrate",
        "seed", "dev", "test", "lint", "format", "ps", "web"
    )]
    [string]$Target = "help"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Initialize-EnvFile {
    $envFile = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $envFile)) {
        Copy-Item (Join-Path $RepoRoot ".env.example") $envFile
        Write-Host "created .env from .env.example"
    }
}

function Invoke-DockerUp {
    Initialize-EnvFile
    docker compose up -d --wait
}

function Invoke-Migrate {
    uv run python scripts/migrate.py
}

switch ($Target) {
    "help" {
        @"
Ankur (Windows) — same jobs as the Makefile:

  .\scripts\dev.ps1 docker-up      Start Postgres/PostGIS and wait until healthy
  .\scripts\dev.ps1 migrate        Apply db/migrations/*.sql (idempotent)
  .\scripts\dev.ps1 seed           3 cited Sirsa demo rules via ReviewService.approve
  .\scripts\dev.ps1 dev            Postgres + migrate + FastAPI on :8000
  .\scripts\dev.ps1 test           pytest (no live Postgres required)
  .\scripts\dev.ps1 lint           ruff check
  .\scripts\dev.ps1 format         ruff format
  .\scripts\dev.ps1 web            Next.js dashboard on :3000
  .\scripts\dev.ps1 docker-down    Stop containers
  .\scripts\dev.ps1 docker-reset   Drop the volume and start fresh
  .\scripts\dev.ps1 ps             docker compose ps
"@
    }
    "docker-up" { Invoke-DockerUp }
    "docker-down" { docker compose down }
    "docker-reset" {
        docker compose down -v
        Invoke-DockerUp
    }
    "migrate" {
        Invoke-DockerUp
        Invoke-Migrate
    }
    "seed" {
        Invoke-DockerUp
        Invoke-Migrate
        uv run python -m app.seed
    }
    "dev" {
        Invoke-DockerUp
        Invoke-Migrate
        uv run uvicorn app.main:app --reload --app-dir apps/api --host 0.0.0.0 --port 8000
    }
    "test" { uv run pytest }
    "lint" { uv run ruff check . }
    "format" { uv run ruff format . }
    "ps" { docker compose ps }
    "web" {
        Set-Location (Join-Path $RepoRoot "apps\app")
        pnpm dev
    }
}
