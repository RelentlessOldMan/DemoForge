# Cut a GitHub Release carrying the rendered presentation video.
# A split presentation (split = true in the set's demoforge.toml) ships as one zip
# of numbered MP4s; otherwise the single presentation.mp4 ships.
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
    [string]$AssetName = ""
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
$manifestPath = Join-Path $videoDir "manifest.json"
if (-not (Test-Path $manifestPath)) { throw "No $manifestPath - run: python -m demoforge --set $Set build --video" }

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
# The manifest names what the build made: presentation.mp4, or the split zip.
$video = Join-Path $videoDir $manifest.video
if (-not (Test-Path $video)) { throw "No $video - rebuild the video." }
if (-not $AssetName) {
    $AssetName = if ($manifest.video -like "*.zip") { $manifest.video } else { "ClaudeDemoKit.mp4" }
}
$head = git rev-parse HEAD
if ($manifest.git_commit -ne $head) {
    throw "The video was built from $($manifest.git_commit), not HEAD ($head). Rebuild it."
}
if ($manifest.git_dirty) { throw "The video was built from a dirty tree. Commit, then rebuild it." }
$sha = (Get-FileHash $video -Algorithm SHA256).Hash.ToLower()
if ($manifest.video_sha256 -ne $sha) { throw "$($manifest.video) does not match its manifest. Rebuild it." }
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
