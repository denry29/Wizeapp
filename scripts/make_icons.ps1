<#
.SYNOPSIS
    Derives every Wize app icon from the master logo (static/img/wize.png).

.DESCRIPTION
    Phones do not read the master PNG directly, they need
    purpose-built sizes:

        favicon.ico            16 / 32 / 48   browser tab, rounded corners
        favicon-32.png         32             browser tab, rounded corners
        apple-touch-icon.png   180            iOS home screen (must be opaque)
        icon-192.png           192            PWA + Android launcher
        icon-512.png           512            PWA splash / store listing
        icon-maskable-512.png  512            Android adaptive icon safe zone
        logo-160.png           160            logo shown in the in-app header

    Run this whenever the logo changes and every size stays in sync.

    The master carries a real alpha channel, so its background is transparency
    rather than white. Get-ContentBounds skips transparent pixels when it finds
    the artwork box, and the maskable icon falls back to a white padding colour
    because a transparent corner has no colour to sample.

    Resizing uses the System.Drawing API bundled with Windows, so no extra
    Python package (Pillow / ImageMagick) has to be installed.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\make_icons.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\make_icons.ps1 -Source C:\pics\logo.png
#>
[CmdletBinding()]
param(
    # Master artwork. Defaults to the copy stored inside the project.
    [string]$Source
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

# NOTE: resolved here rather than as a $Source default because Windows
# PowerShell binds param() defaults before $PSScriptRoot is populated.
$projectRoot = Split-Path $PSScriptRoot -Parent
if (-not $Source) { $Source = Join-Path $projectRoot 'static\img\wize.png' }


function Get-ContentBounds {
    # Finds the artwork inside the master file by ignoring everything that is
    # (near) white. A freshly exported logo carries a wide white margin - the
    # artwork only fills part of it - so every icon is built from this box
    # instead of the whole file, otherwise each icon ends up mostly empty.
    #
    # Returns a Rectangle in the ORIGINAL image's coordinates, or $null if the
    # artwork is blank.
    param(
        [Parameter(Mandatory)][System.Drawing.Image]$Image,
        [int]$Threshold = 12,
        [int]$AlphaThreshold = 24
    )

    # Scan a downsampled copy: 400x400 is plenty to locate the bounds and keeps
    # the per-pixel GetPixel loop fast.
    $scan = 400
    $probe = New-Object System.Drawing.Bitmap($Image, $scan, $scan)
    try {
        $minX = $scan; $minY = $scan; $maxX = -1; $maxY = -1
        for ($y = 0; $y -lt $scan; $y++) {
            for ($x = 0; $x -lt $scan; $x++) {
                $c = $probe.GetPixel($x, $y)
                # Alpha MUST be checked before the colour test. An alpha master
                # (wize.png) stores its background as transparency, and a
                # transparent pixel carries R=G=B=0 - which the colour test
                # below reads as "far from white", so without this guard the
                # whole canvas is mistaken for artwork and every icon comes out
                # nearly empty. Soft anti-aliased edges are excluded too.
                if ($c.A -lt $AlphaThreshold) { continue }
                # Distance from white, measured on the weakest channel so a
                # faint tint still counts as artwork.
                if ((255 - [Math]::Min($c.R, [Math]::Min($c.G, $c.B))) -gt $Threshold) {
                    if ($x -lt $minX) { $minX = $x }
                    if ($x -gt $maxX) { $maxX = $x }
                    if ($y -lt $minY) { $minY = $y }
                    if ($y -gt $maxY) { $maxY = $y }
                }
            }
        }
    } finally { $probe.Dispose() }

    if ($maxX -lt 0) { return $null }        # blank artwork, nothing to trim to

    # Project the scan box back onto the full-resolution image.
    $sx = $Image.Width  / $scan
    $sy = $Image.Height / $scan
    $x = [int][Math]::Floor($minX * $sx)
    $y = [int][Math]::Floor($minY * $sy)
    $w = [int][Math]::Ceiling(($maxX - $minX + 1) * $sx)
    $h = [int][Math]::Ceiling(($maxY - $minY + 1) * $sy)

    # Clamp: rounding can push the box one pixel past the edge.
    $x = [Math]::Max(0, [Math]::Min($x, $Image.Width  - 1))
    $y = [Math]::Max(0, [Math]::Min($y, $Image.Height - 1))
    $w = [Math]::Min($w, $Image.Width  - $x)
    $h = [Math]::Min($h, $Image.Height - $y)

    return New-Object System.Drawing.Rectangle $x, $y, $w, $h
}


function New-IconBitmap {
    # Renders the trimmed artwork onto a canvas.
    #   $Size     square edge length, or the canvas width when -Natural is used
    #   $Scale    fraction of the canvas the artwork occupies (1.0 = fill it)
    #   -Natural  canvas keeps the artwork's own aspect ratio instead of being
    #             square, so the header logo has no empty bands above/below it
    #   -Opaque   writes 24bpp with no alpha at all, because iOS renders any
    #             transparency in apple-touch-icon.png as solid black
    #   -Rounded  clips the canvas to a rounded square, so the browser tab shows
    #             a curved-corner icon instead of a hard-edged square
    param(
        [Parameter(Mandatory)][System.Drawing.Image]$Image,
        [Parameter(Mandatory)][int]$Size,
        [double]$Scale = 1.0,
        [System.Drawing.Color]$Background,
        [switch]$Opaque,
        [switch]$Natural,
        [int]$Threshold = 12,
        [switch]$Rounded
    )

    $bounds = Get-ContentBounds -Image $Image -Threshold $Threshold
    if ($null -eq $bounds) {
        $bounds = New-Object System.Drawing.Rectangle 0, 0, $Image.Width, $Image.Height
    }

    $format = if ($Opaque) { [System.Drawing.Imaging.PixelFormat]::Format24bppRgb }
              else          { [System.Drawing.Imaging.PixelFormat]::Format32bppArgb }

    # "Contain" fit: the artwork is never cropped, it is centred and made as
    # large as the box allows. This logo is wider than it is tall, so it spans
    # the full width of a square icon and leaves slim bands top and bottom.
    if ($Natural) {
        $canvasW = [int][Math]::Round($Size * $Scale)
        $canvasH = [int][Math]::Round($canvasW * $bounds.Height / $bounds.Width)
    } else {
        $canvasW = $Size
        $canvasH = $Size
    }

    $bitmap   = New-Object System.Drawing.Bitmap($canvasW, $canvasH, $format)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)

    try {
        $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
        $graphics.InterpolationMode  = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.PixelOffsetMode    = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $graphics.SmoothingMode      = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality

        if ($PSBoundParameters.ContainsKey('Background')) { $graphics.Clear($Background) }
        elseif ($Opaque) { $graphics.Clear([System.Drawing.Color]::White) }
        else { $graphics.Clear([System.Drawing.Color]::Transparent) }

        # Clip to a rounded square BEFORE the artwork is drawn, so the corners
        # stay empty. Those corners must remain transparent rather than white:
        # a browser tab draws the icon on its own chrome, and a white corner
        # would read as a hard square again. Not used with -Opaque, because an
        # opaque icon has no alpha for the curve to show through.
        if ($Rounded -and -not $Opaque) {
            $radius   = [int][Math]::Round([Math]::Min($canvasW, $canvasH) * 0.22)
            $diameter = $radius * 2
            $path = New-Object System.Drawing.Drawing2D.GraphicsPath
            try {
                $path.AddArc(0, 0, $diameter, $diameter, 180, 90)
                $path.AddArc($canvasW - $diameter, 0, $diameter, $diameter, 270, 90)
                $path.AddArc($canvasW - $diameter, $canvasH - $diameter, $diameter, $diameter, 0, 90)
                $path.AddArc(0, $canvasH - $diameter, $diameter, $diameter, 90, 90)
                $path.CloseFigure()
                $graphics.SetClip($path)
            } finally { $path.Dispose() }
        }

        $boxW = $canvasW * $Scale
        $boxH = $canvasH * $Scale
        $ratio = [Math]::Min($boxW / $bounds.Width, $boxH / $bounds.Height)
        $w = [int][Math]::Round($bounds.Width  * $ratio)
        $h = [int][Math]::Round($bounds.Height * $ratio)
        $x = [int][Math]::Round(($canvasW - $w) / 2)
        $y = [int][Math]::Round(($canvasH - $h) / 2)

        # Source rectangle = the trimmed artwork only, so the white margin in
        # the master file is scaled away instead of being baked into the icon.
        $graphics.DrawImage($Image,
                            (New-Object System.Drawing.Rectangle $x, $y, $w, $h),
                            $bounds.X, $bounds.Y, $bounds.Width, $bounds.Height,
                            [System.Drawing.GraphicsUnit]::Pixel)
    } finally { $graphics.Dispose() }

    return $bitmap
}


function Write-Png {
    param([System.Drawing.Bitmap]$Bitmap, [string]$Path)
    try { $Bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png) } finally { $Bitmap.Dispose() }
    Write-Host ('  {0,-24} {1,7:N0} bytes' -f (Split-Path $Path -Leaf), (Get-Item $Path).Length)
}


function Write-Ico {
    # Multi-resolution .ico, one PNG-compressed frame per size. PNG-compressed
    # icon entries are understood by every browser from IE11 / Windows Vista on.
    param([System.Drawing.Image]$Image, [int[]]$Sizes, [string]$Path, [switch]$Rounded)

    $frames = @{}
    foreach ($size in $Sizes) {
        $bitmap = New-IconBitmap -Image $Image -Size $size -Rounded:$Rounded
        $stream = New-Object System.IO.MemoryStream
        try {
            $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
            $frames[$size] = $stream.ToArray()
        } finally { $stream.Dispose(); $bitmap.Dispose() }
    }

    $output = New-Object System.IO.MemoryStream
    $writer = New-Object System.IO.BinaryWriter($output)
    try {
        $writer.Write([UInt16]0)                 # ICONDIR reserved
        $writer.Write([UInt16]1)                 # type 1 = icon
        $writer.Write([UInt16]$Sizes.Count)

        $offset = 6 + (16 * $Sizes.Count)        # ICONDIRENTRY, 16 bytes each
        foreach ($size in $Sizes) {
            $payload = $frames[$size]
            $edge = if ($size -ge 256) { 0 } else { $size }   # 0 encodes 256
            $writer.Write([byte]$edge)            # width
            $writer.Write([byte]$edge)            # height
            $writer.Write([byte]0)                # palette size (0 = truecolour)
            $writer.Write([byte]0)                # reserved
            $writer.Write([UInt16]1)              # colour planes
            $writer.Write([UInt16]32)             # bits per pixel
            $writer.Write([UInt32]$payload.Length)
            $writer.Write([UInt32]$offset)
            $offset += $payload.Length
        }
        foreach ($size in $Sizes) { $writer.Write($frames[$size]) }
        $writer.Flush()
        [System.IO.File]::WriteAllBytes($Path, $output.ToArray())
    } finally { $writer.Dispose(); $output.Dispose() }

    Write-Host ('  {0,-24} {1,7:N0} bytes' -f (Split-Path $Path -Leaf), (Get-Item $Path).Length)
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if (-not (Test-Path $Source)) { throw "Logo not found: $Source" }

$staticFolder = Join-Path $projectRoot 'static'
if (-not (Test-Path $staticFolder)) { throw "Static folder not found: $staticFolder" }

$logo = [System.Drawing.Image]::FromFile((Resolve-Path $Source).Path)
try {
    # Report how much of the master file is actual artwork.
    $bounds = Get-ContentBounds -Image $logo
    Write-Host "Wize icon generator"
    Write-Host "  source: $Source ($($logo.Width)x$($logo.Height))"
    Write-Host ("  artwork: {0}x{1} = {2:P0} of the file (the rest is white margin)" -f `
        $bounds.Width, $bounds.Height, ($bounds.Width * $bounds.Height / ($logo.Width * $logo.Height)))
    Write-Host ''

    # Background sampled from the master file, so the maskable icon's padding
    # blends into the artwork instead of showing a mismatched colour. An alpha
    # master has no background colour to sample - its corner is transparent
    # black, which would paint the whole adaptive icon black - so fall back to
    # white, matching apple-touch-icon and a light browser tab.
    $probe = New-Object System.Drawing.Bitmap($logo)
    try {
        $padding = $probe.GetPixel(0, 0)
        if ($padding.A -lt 16) { $padding = [System.Drawing.Color]::White }
    } finally { $probe.Dispose() }

    # Browser tab (desktop + Android shortcut). -Rounded gives the tab a
    # curved-corner icon; the corners are transparent so the tab chrome shows
    # through instead of a white square.
    Write-Ico $logo @(16, 32, 48) (Join-Path $staticFolder 'favicon.ico') -Rounded
    Write-Png (New-IconBitmap $logo 32 -Rounded) (Join-Path $staticFolder 'favicon-32.png')

    # Progressive Web App icons. Left square: the launcher applies its own mask,
    # so a curve baked in here would be doubled up or clipped away.
    Write-Png (New-IconBitmap $logo 192) (Join-Path $staticFolder 'icon-192.png')
    Write-Png (New-IconBitmap $logo 512) (Join-Path $staticFolder 'icon-512.png')

    # Android adaptive icon: the artwork stays inside the 80% safe zone so any
    # launcher mask (circle, squircle, teardrop) still shows the whole logo.
    Write-Png (New-IconBitmap $logo 512 -Scale 0.8 -Background $padding) `
             (Join-Path $staticFolder 'icon-maskable-512.png')

    # iOS "Add to Home Screen" - opaque PNG, iOS draws transparency black.
    Write-Png (New-IconBitmap $logo 180 -Opaque) `
             (Join-Path $staticFolder 'apple-touch-icon.png')

    # Header logo: rendered at 32 CSS pixels, so 160px wide is a crisp 5x on a
    # retina phone. -Natural keeps the artwork's aspect ratio, which means no
    # empty white bands above and below it in the header bar.
    Write-Png (New-IconBitmap $logo 160 -Natural) (Join-Path $staticFolder 'logo-160.png')

    Write-Host ''
    Write-Host 'Done.'
} finally { $logo.Dispose() }

