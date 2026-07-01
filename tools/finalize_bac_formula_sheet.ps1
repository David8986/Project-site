param(
    [string]$DocxPath = "C:\Users\david\OneDrive\Desktop\Archive\Projects\CodeX\fisa_formule_curent_continuu_BAC_RO.docx",
    [string]$PdfPath = "C:\Users\david\OneDrive\Desktop\Archive\Projects\CodeX\fisa_formule_curent_continuu_BAC_RO.pdf"
)

$ErrorActionPreference = "Stop"

$docxResolved = (Resolve-Path $DocxPath).Path
$pdfResolved = [System.IO.Path]::GetFullPath($PdfPath)

$word = $null
$document = $null

try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.ScreenUpdating = $false

    $document = $word.Documents.Open($docxResolved, $false, $false)

    foreach ($mathObject in $document.OMaths) {
        $mathObject.Range.Font.Size = 9
        $mathObject.BuildUp()
    }

    $document.Repaginate()
    $pageCount = $document.ComputeStatistics(2)
    $document.Save()

    $document.ExportAsFixedFormat(
        $pdfResolved,
        17,
        $false,
        0,
        0,
        1,
        1,
        0,
        $true,
        $true,
        0,
        $true,
        $false,
        $false
    )

    Write-Output "DOCX_PAGES=$pageCount"
    Write-Output "DOCX_PATH=$docxResolved"
    Write-Output "PDF_PATH=$pdfResolved"
}
finally {
    if ($document -ne $null) {
        $document.Close([ref]0)
    }
    if ($word -ne $null) {
        $word.Quit()
    }
}
