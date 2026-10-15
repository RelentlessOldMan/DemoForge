# Cut a GitHub Release carrying the rendered presentation video.
#
#   .\release.ps1 v1.1 "What changed in this video"
#
# The video is never committed (output/ is regenerable); it ships as a release
# asset under a fixed name, so the README's .../releases/latest/download/ link
# always points at the newest one. The build writes manifest.json beside the
# video; a release is refused unless that manifest says the video was built from
# exactly this commit, with a clean tree, and the file is the one it describes.
param(
    [Parameter(Mandatory)][string]$Version,
    [string]$Notes = "",
    [string]$Set = "examples/claude-demo-kit",
    [string]$AssetName = "ClaudeDemoKit.mp4"
)
$ErrorActionPreference = "Stop"

if ($Version -notmatch '^v\d+\.\d+(\.\d+)?$') { throw "Version must look like v1.2 or v1.2.3, not '$Version'." }
$branch = git rev-parse --abbrev-ref HEAD
if ($branch -ne "main") { throw "Releases are cut from main; you are on '$branch'." }
if (git status --porcelain) { throw "Working tree is not clean; commit first." }

git fetch --tags origin
if ($LASTEXITCODE) { throw "git fetch failed" }
if (git tag --list $Version) { throw "Tag $Version already exists." }
$behind = git rev-list --count "HEAD..origin/main"
if ([int]$behind -gt 0) { throw "main is $behind commit(s) behind origin/main; pull first." }

$videoDir = Join-Path $Set "output/video"
$video = Join-Path $videoDir "presentation.mp4"
$manifestPath = Join-Path $videoDir "manifest.json"
if (-not (Test-Path $video)) { throw "No $video - run: python -m demoforge --set $Set build --video" }
if (-not (Test-Path $manifestPath)) { throw "No $manifestPath - rebuild the video so it records what it was built from." }

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$head = git rev-parse HEAD
if ($manifest.git_commit -ne $head) {
    throw "The video was built from $($manifest.git_commit), not HEAD ($head). Rebuild it."
}
if ($manifest.git_dirty) { throw "The video was built from a dirty tree. Commit, then rebuild it." }
$sha = (Get-FileHash $video -Algorithm SHA256).Hash.ToLower()
if ($manifest.video_sha256 -ne $sha) { throw "presentation.mp4 does not match its manifest. Rebuild it." }
if ($manifest.narration_provider -like "silent*") { throw "The video's narration track is silence. Rebuild with a voice installed." }

$staged = Join-Path ([IO.Path]::GetTempPath()) $AssetName
Copy-Item $video $staged -Force
try {
    git push origin main
    if ($LASTEXITCODE) { throw "git push failed" }
    $short = git rev-parse --short HEAD
    $body = "Narrated, captioned walkthrough of every approved ClaudeDemoKit demo, rendered from commit $short.`n`n$Notes"
    gh release create $Version $staged $manifestPath --title "DemoForge $Version" --notes $body --target main
    if ($LASTEXITCODE) { throw "gh release create failed" }
} finally {
    Remove-Item $staged -ErrorAction SilentlyContinue
}
