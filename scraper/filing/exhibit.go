package filing

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	"github.com/zacharydeaguuar/rialto-edgar-scraper/edgar"
)

// DownloadExhibit99_1 fetches the EX-99.1 HTML for a given filing and saves it to outDir.
// Returns the local file path, or empty string if no EX-99.1 was found.
func DownloadExhibit99_1(ctx context.Context, client *edgar.Client, cik, adsh, trustName, outDir string, verbose bool) (string, error) {
	idx, err := GetFilingIndex(ctx, client, cik, adsh)
	if err != nil {
		return "", err
	}

	exURL, found := idx.FindExhibit99_1()
	if !found {
		if verbose {
			log.Printf("No EX-99.1 found in filing %s for CIK %s", adsh, cik)
		}
		return "", nil
	}

	var html string
	if err := client.DoRequestRaw(ctx, exURL, &html); err != nil {
		return "", fmt.Errorf("downloading EX-99.1 from %s: %w", exURL, err)
	}

	// Build a clean filename: TrustName_ADSH_ex991.htm
	safeName := sanitizeFilename(trustName)
	filename := fmt.Sprintf("%s_%s_ex991.htm", safeName, adsh)
	outPath := filepath.Join(outDir, filename)

	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return "", fmt.Errorf("creating output directory: %w", err)
	}

	if err := os.WriteFile(outPath, []byte(html), 0o644); err != nil {
		return "", fmt.Errorf("writing %s: %w", outPath, err)
	}

	if verbose {
		log.Printf("Saved EX-99.1 for %s → %s (%d bytes)", trustName, outPath, len(html))
	}

	return outPath, nil
}

func sanitizeFilename(name string) string {
	name = strings.ReplaceAll(name, "/", "_")
	name = strings.ReplaceAll(name, "\\", "_")
	name = strings.ReplaceAll(name, " ", "_")
	name = strings.ReplaceAll(name, ",", "")
	name = strings.ReplaceAll(name, ".", "")
	return name
}
