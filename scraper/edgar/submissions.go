package edgar

import (
	"context"
	"fmt"
)

const submissionsBaseURL = "https://data.sec.gov/submissions"

// GetSubmissions fetches entity metadata and recent filings for the given CIK.
func (c *Client) GetSubmissions(ctx context.Context, cik string) (*SubmissionsResponse, error) {
	// CIK must be zero-padded to 10 digits
	paddedCIK := fmt.Sprintf("%010s", cik)
	url := fmt.Sprintf("%s/CIK%s.json", submissionsBaseURL, paddedCIK)

	var resp SubmissionsResponse
	if err := c.doRequest(ctx, url, &resp); err != nil {
		return nil, fmt.Errorf("fetching submissions for CIK %s: %w", cik, err)
	}
	return &resp, nil
}
