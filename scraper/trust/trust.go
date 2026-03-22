package trust

import "time"

// Trust represents a securitization trust entity found in EDGAR filings.
type Trust struct {
	Name         string    `json:"name"`
	CIK          string    `json:"cik"`
	FormTypes    []string  `json:"form_types"`
	FilingCount  int       `json:"filing_count"`
	LatestFiling time.Time `json:"latest_filing,omitempty"`
	LatestADSH   string    `json:"latest_adsh,omitempty"`
	Source       string    `json:"source"`
}
