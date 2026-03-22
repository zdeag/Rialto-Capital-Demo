package edgar

// SubmissionsResponse represents the response from data.sec.gov/submissions/CIK{cik}.json.
type SubmissionsResponse struct {
	CIK        string   `json:"cik"`
	EntityType string   `json:"entityType"`
	SIC        string   `json:"sic"`
	Name       string   `json:"name"`
	Tickers    []string `json:"tickers"`
	Exchanges  []string `json:"exchanges"`
	EIN        string   `json:"ein"`
	Category   string   `json:"category"`
	Filings    struct {
		Recent struct {
			AccessionNumber []string `json:"accessionNumber"`
			Form            []string `json:"form"`
			FilingDate      []string `json:"filingDate"`
			PrimaryDocument []string `json:"primaryDocument"`
		} `json:"recent"`
	} `json:"filings"`
}

// SearchResponse represents the Elasticsearch-shaped response from efts.sec.gov/LATEST/search-index.
type SearchResponse struct {
	Hits SearchHitsWrapper `json:"hits"`
}

// SearchHitsWrapper is the outer "hits" object containing total and the hit array.
type SearchHitsWrapper struct {
	Total struct {
		Value    int    `json:"value"`
		Relation string `json:"relation"` // "eq" or "gte"
	} `json:"total"`
	Hits []SearchHit `json:"hits"`
}

// SearchHit represents a single filing result from the search API.
type SearchHit struct {
	ID     string    `json:"_id"`
	Source HitSource `json:"_source"`
}

// HitSource contains the filing metadata within a search hit.
type HitSource struct {
	DisplayNames   []string `json:"display_names"`
	CIKs           []string `json:"ciks"`
	ADSH           string   `json:"adsh"`
	Form           string   `json:"form"`
	FileDate       string   `json:"file_date"`
	FileNum        []string `json:"file_num"`
	BizLocations   []string `json:"biz_locations"`
	PeriodEnding   string   `json:"period_ending"`
}
