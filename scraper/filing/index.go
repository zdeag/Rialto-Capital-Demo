package filing

import (
	"context"
	"fmt"
	"regexp"
	"strings"

	"github.com/zacharydeaguuar/rialto-edgar-scraper/edgar"
)

const archivesBaseURL = "https://www.sec.gov/Archives/edgar/data"

// FilingDoc represents a document within an SEC filing.
type FilingDoc struct {
	Sequence    string
	Filename    string
	Type        string
	Size        string
	Description string
	URL         string
}

// FilingIndex holds the parsed list of documents in a filing.
type FilingIndex struct {
	CIK  string
	ADSH string
	Docs []FilingDoc
}

var docRowRe = regexp.MustCompile(`(?s)<tr[^>]*>(.*?)</tr>`)
var cellRe = regexp.MustCompile(`(?s)<td[^>]*>(.*?)</td>`)
var tagRe = regexp.MustCompile(`<[^>]+>`)
var hrefRe = regexp.MustCompile(`href="([^"]+)"`)

// GetFilingIndex fetches and parses the filing index page to list all documents.
func GetFilingIndex(ctx context.Context, client *edgar.Client, cik, adsh string) (*FilingIndex, error) {
	// Convert ADSH "0001888524-24-002033" to path "000188852424002033"
	adshPath := strings.ReplaceAll(adsh, "-", "")
	indexURL := fmt.Sprintf("%s/%s/%s/%s-index.html", archivesBaseURL, cik, adshPath, adsh)

	var htmlBody string
	if err := client.DoRequestRaw(ctx, indexURL, &htmlBody); err != nil {
		return nil, fmt.Errorf("fetching filing index for %s: %w", adsh, err)
	}

	idx := &FilingIndex{
		CIK:  cik,
		ADSH: adsh,
	}

	baseURL := fmt.Sprintf("%s/%s/%s", archivesBaseURL, cik, adshPath)

	rows := docRowRe.FindAllStringSubmatch(htmlBody, -1)
	for _, row := range rows {
		cells := cellRe.FindAllStringSubmatch(row[1], -1)
		if len(cells) < 4 {
			continue
		}

		seq := cleanHTML(cells[0][1])
		// Skip header rows and non-document rows
		if seq == "" || seq == "Seq" {
			continue
		}

		// Extract href from filename cell
		filename := ""
		if m := hrefRe.FindStringSubmatch(cells[2][1]); len(m) > 1 {
			// href might be a full path or just filename
			parts := strings.Split(m[1], "/")
			filename = parts[len(parts)-1]
		}
		if filename == "" {
			filename = cleanHTML(cells[2][1])
		}

		docType := cleanHTML(cells[3][1])
		size := ""
		if len(cells) > 4 {
			size = cleanHTML(cells[4][1])
		}

		doc := FilingDoc{
			Sequence: seq,
			Filename: filename,
			Type:     docType,
			Size:     size,
			URL:      baseURL + "/" + filename,
		}
		idx.Docs = append(idx.Docs, doc)
	}

	return idx, nil
}

// FindExhibit99_1 returns the URL of the EX-99.1 document in the filing, if present.
func (idx *FilingIndex) FindExhibit99_1() (string, bool) {
	for _, doc := range idx.Docs {
		if strings.EqualFold(doc.Type, "EX-99.1") {
			return doc.URL, true
		}
	}
	return "", false
}

func cleanHTML(s string) string {
	s = tagRe.ReplaceAllString(s, "")
	s = strings.ReplaceAll(s, "&nbsp;", "")
	return strings.TrimSpace(s)
}
