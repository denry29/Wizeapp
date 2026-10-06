<#
.SYNOPSIS
    Turns an opaque logo on a plain light background into a transparent PNG.

.DESCRIPTION
    The master artwork has to be a PNG with a real alpha channel, because that
    is what every app icon is derived from (see scripts/make_icons.ps1). A
    freshly exported logo is usually a flat rectangle of opaque white instead,
    so this script carves the white away and writes a 32bpp ARGB master.

    Deleting *every* white pixel would be wrong: this mark has white gaps
    between its strokes that must survive, so the background is removed with a
    flood fill that starts at the image border and only reaches white pixels
    actually connected to it. White detail enclosed by the artwork is kept.

    Two details keep the result from looking ragged:

    * a tolerance (default 238) treats the near-white anti-aliased fringe as
      background, otherwise a one-pixel halo of white survives around every
      edge;
    * pixels immediately inside that fringe are un-multiplied - coverage is
      recovered from how far the colour sits from white and the colour is
      corrected to match - so soft edges keep their softness instead of turning
      into a hard staircase.

    The result is trimmed to the artwork plus a small transparent margin and
    saved as ``static/img/wize.png``.

    Uses the System.Drawing API that ships with Windows, so no extra Python
    package (Pillow / ImageMagick) has to be installed.

.PARAMETER Source
    The opaque logo to convert, e.g. the ``wize.png`` dropped in the project
    root.

.PARAMETER Destination
    Where to write the transparent master. A relative path is resolved against
    the project root.

.PARAMETER Tolerance
    Minimum value on *every* colour channel for a pixel to count as background.
    Lower it if the leftover fringe is too wide, raise it if real artwork that
    is nearly white starts disappearing.

.PARAMETER MarginPercent
    Transparent padding left around the trimmed artwork, as a percentage of its
    own size, so the mark never sits flush against the edge of the file.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\prepare_logo.ps1 -Source wize.png

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\prepare_logo.ps1 `
        -Source C:\pictures\logo.jpg -Destination static\img\wize.png
#>
[CmdletBinding()]
param(
    # Opaque logo that still has its background.
    [Parameter(Mandatory)][string]$Source,

    # Transparent master to write. Defaults to static/img/wize.png.
    [string]$Destination,

    [int]$Tolerance = 238,

    [double]$MarginPercent = 2.0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

# NOTE: resolved here rather than as a parameter default because Windows
# PowerShell binds param() defaults before $PSScriptRoot is populated.
$projectRoot = Split-Path $PSScriptRoot -Parent
if (-not $Destination) { $Destination = Join-Path $projectRoot 'static\img\wize.png' }
if (-not [System.IO.Path]::IsPathRooted($Destination)) {
    $Destination = Join-Path $projectRoot $Destination
}
function Get-ClearBackgroundMask {
    # Marks every pixel light enough to be background, regardless of whether it
    # is reachable from the border. The flood fill then decides which of those
    # actually get removed.
    param(
        [Parameter(Mandatory)][byte[]]$Buffer,
        [Parameter(Mandatory)][int]$Width,
        [Parameter(Mandatory)][int]$Height,
        [Parameter(Mandatory)][int]$Stride,
        [Parameter(Mandatory)][int]$Tolerance
    )

    # Format32bppArgb is little-endian BGRA in memory: B, G, R, then alpha.
    $mask = New-Object byte[] ($Stride * $Height)
    for ($y = 0; $y -lt $Height; $y++) {
        $row = $y * $Stride
        for ($x = 0; $x -lt $Width; $x++) {
            $offset = $row + ($x * 4)
            $b = [int]$Buffer[$offset]
            $g = [int]$Buffer[$offset + 1]
            $r = [int]$Buffer[$offset + 2]
            if ($r -ge $Tolerance -and $g -ge $Tolerance -and $b -ge $Tolerance) {
                $mask[$offset] = 1
            }
        }
    }
    # The leading comma is essential: without it PowerShell unrolls the byte
    # array into the pipeline and the caller receives one number, not the mask.
    return ,$mask
}


function Remove-ConnectedBackground {
    # Scanline flood fill from the border, then punches the filled pixels out
    # and recovers the soft edge. Returns the artwork's bounding rectangle as
    # @(x, y, width, height), or $null if nothing but background was found.
    param(
        [Parameter(Mandatory)][byte[]]$Buffer,
        [Parameter(Mandatory)][int]$Width,
        [Parameter(Mandatory)][int]$Height,
        [Parameter(Mandatory)][int]$Stride,
        [Parameter(Mandatory)][int]$Tolerance
    )

    $mask  = Get-ClearBackgroundMask -Buffer $Buffer -Width $Width -Height $Height -Stride $Stride -Tolerance $Tolerance
    $stack = New-Object 'System.Collections.Generic.Stack[int]'

    # Seed from every border pixel: the background is whatever the edges see.
    for ($x = 0; $x -lt $Width; $x++) {
        foreach ($y in @(0, ($Height - 1))) {
            $offset = $y * $Stride + ($x * 4)
            if ($mask[$offset] -eq 1) { $mask[$offset] = 2; $stack.Push($offset) }
        }
    }
    for ($y = 0; $y -lt $Height; $y++) {
        foreach ($x in @(0, ($Width - 1))) {
            $offset = $y * $Stride + ($x * 4)
            if ($mask[$offset] -eq 1) { $mask[$offset] = 2; $stack.Push($offset) }
        }
    }

    # A run is walked end to end, then the rows directly above and below it are
    # queued. Queueing one pixel per contiguous span (instead of every pixel)
    # keeps the stack tiny even on a large canvas.
    while ($stack.Count -gt 0) {
        $offset = $stack.Pop()
        $y = [int][Math]::Floor($offset / $Stride)
        $x = [int](($offset - ($y * $Stride)) / 4)

        while ($x -gt 0 -and $mask[$offset - 4] -eq 1) { $offset -= 4; $x-- }

        $runStart = $x
        while ($true) {
            $mask[$offset] = 2
            if ($x -ge ($Width - 1) -or $mask[$offset + 4] -ne 1) { break }
            $offset += 4; $x++
        }

        foreach ($neighbour in @(($y - 1), ($y + 1))) {
            if ($neighbour -lt 0 -or $neighbour -ge $Height) { continue }
            $base = $neighbour * $Stride
            $queued = $false
            for ($nx = $runStart; $nx -le $x; $nx++) {
                $nOffset = $base + ($nx * 4)
                if ($mask[$nOffset] -eq 1) {
                    if (-not $queued) { $stack.Push($nOffset); $queued = $true }
                } else {
                    $queued = $false
                }
            }
        }
    }
# Remove the background, recover the anti-aliased fringe and measure the
    # artwork in a single pass.
    $minX = $Width; $minY = $Height; $maxX = -1; $maxY = -1
    for ($y = 0; $y -lt $Height; $y++) {
        $row = $y * $Stride
        for ($x = 0; $x -lt $Width; $x++) {
            $offset = $row + ($x * 4)
            if ($mask[$offset] -eq 2) { $Buffer[$offset + 3] = 0; continue }

            $b = [int]$Buffer[$offset]
            $g = [int]$Buffer[$offset + 1]
            $r = [int]$Buffer[$offset + 2]

            # An opaque, near-white pixel touching the new transparency is an
            # anti-aliased edge pixel: the artwork was composited over white, so
            # both the coverage and the original colour can be recovered from
            #     observed = alpha*colour + (1 - alpha)*white,  white = 255
            # because the weakest channel m reports alpha = 255 - m.
            if ($r -ge 190 -and $g -ge 190 -and $b -ge 190 -and
                ($mask[$offset - 4] -eq 2 -or $mask[$offset + 4] -eq 2 -or
                 $mask[$offset - $Stride] -eq 2 -or $mask[$offset + $Stride] -eq 2)) {
                $m = [Math]::Min($r, [Math]::Min($g, $b))
                $span = 255 - $m
                if ($span -le 0) { $Buffer[$offset + 3] = 0; continue }
                $scale = 255.0 / $span
                $Buffer[$offset]     = [byte][Math]::Min(255, [Math]::Max(0, [Math]::Round(($b - $m) * $scale)))
                $Buffer[$offset + 1] = [byte][Math]::Min(255, [Math]::Max(0, [Math]::Round(($g - $m) * $scale)))
                $Buffer[$offset + 2] = [byte][Math]::Min(255, [Math]::Max(0, [Math]::Round(($r - $m) * $scale)))
                $Buffer[$offset + 3] = [byte](255 - $m)
            }

            if ($x -lt $minX) { $minX = $x }
            if ($x -gt $maxX) { $maxX = $x }
            if ($y -lt $minY) { $minY = $y }
            if ($y -gt $maxY) { $maxY = $y }
        }
    }

    if ($maxX -lt 0) { return $null }        # the whole file was background
    # Comma-prefixed so the four numbers arrive as one array, not four
    # separate pipeline values.
    return ,@($minX, $minY, ($maxX - $minX + 1), ($maxY - $minY + 1))
}


function Write-TrimmedPng {
    # Crops the canvas to the artwork and saves it, keeping a transparent margin
    # so the mark never touches the edge of the file.
    param(
        [Parameter(Mandatory)][System.Drawing.Bitmap]$Canvas,
        [Parameter(Mandatory)][int[]]$Bounds,
        [Parameter(Mandatory)][string]$Path,
        [double]$MarginPercent = 2.0
    )

    $margin = [int][Math]::Round([Math]::Max($Bounds[2], $Bounds[3]) * $MarginPercent / 100.0)
    $left   = [Math]::Max(0, $Bounds[0] - $margin)
    $top    = [Math]::Max(0, $Bounds[1] - $margin)
    $right  = [Math]::Min($Canvas.Width,  $Bounds[0] + $Bounds[2] + $margin)
    $bottom = [Math]::Min($Canvas.Height, $Bounds[1] + $Bounds[3] + $margin)
    $w = $right - $left
    $h = $bottom - $top
    if ($w -le 0 -or $h -le 0) { throw 'Nothing left to save after trimming.' }

    $cropped = New-Object System.Drawing.Bitmap($w, $h,
        [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($cropped)
        try {
            $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
            $graphics.DrawImage($Canvas,
                (New-Object System.Drawing.Rectangle 0, 0, $w, $h),
                $left, $top, $w, $h, [System.Drawing.GraphicsUnit]::Pixel)
        } finally { $graphics.Dispose() }

        $folder = Split-Path $Path -Parent
        if (-not (Test-Path $folder)) { New-Item -ItemType Directory -Path $folder -Force | Out-Null }
        $cropped.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally { $cropped.Dispose() }

    return ,@($w, $h)
}
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if (-not (Test-Path $Source)) { throw "Source logo not found: $Source" }

$sourcePath = (Resolve-Path $Source).Path
$original = [System.Drawing.Image]::FromFile($sourcePath)
try {
    # Draw onto an explicit 32bpp ARGB canvas: a 24bpp JPEG has no alpha channel
    # to write the transparency into.
    $canvas = New-Object System.Drawing.Bitmap($original.Width, $original.Height,
        [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($canvas)
        try {
            $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
            $graphics.InterpolationMode  = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode    = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $graphics.DrawImage($original, 0, 0, $original.Width, $original.Height)
        } finally { $graphics.Dispose() }

        $width  = $canvas.Width
        $height = $canvas.Height
        $rect   = New-Object System.Drawing.Rectangle 0, 0, $width, $height

        # Pixel access goes through LockBits/Marshal rather than GetPixel: this
        # loop touches every pixel of a ~1500x1000 image, and a per-pixel
        # GetPixel call is orders of magnitude slower.
        $locked = $canvas.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadWrite,
                                   [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        try {
            $stride = $locked.Stride
            $buffer = New-Object byte[] ($stride * $height)
            [System.Runtime.InteropServices.Marshal]::Copy($locked.Scan0, $buffer, 0, $buffer.Length)

            $bounds = Remove-ConnectedBackground -Buffer $buffer -Width $width -Height $height -Stride $stride -Tolerance $Tolerance

            [System.Runtime.InteropServices.Marshal]::Copy($buffer, 0, $locked.Scan0, $buffer.Length)
        } finally { $canvas.UnlockBits($locked) }

        Write-Host 'Wize logo preparation'
        Write-Host "  source:      $Source ($($original.Width)x$($original.Height))"
        Write-Host "  background:  tolerance $Tolerance / 255"

        if ($null -eq $bounds) {
            throw ('No artwork found - every pixel reads as background. ' +
                   "Lower -Tolerance (currently $Tolerance) and try again.")
        }

        Write-Host ('  artwork:     {0}x{1} at ({2},{3})' -f $bounds[2], $bounds[3], $bounds[0], $bounds[1])

        $size = Write-TrimmedPng -Canvas $canvas -Bounds $bounds -Path $Destination -MarginPercent $MarginPercent

        Write-Host ''
        Write-Host ('  wrote:       {0} ({1}x{2}, 32bpp ARGB, transparent background)' -f (Split-Path $Destination -Leaf), $size[0], $size[1])
    } finally { $canvas.Dispose() }
} finally { $original.Dispose() }

Write-Host ''
Write-Host 'Done. Now rebuild every icon from it:'
Write-Host '    powershell -ExecutionPolicy Bypass -File scripts\make_icons.ps1'
