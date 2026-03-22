package edgar

import (
	"context"
	"fmt"
	"log"
	"net/url"
)

const (
	searchBaseURL = "https://efts.sec.gov/LATEST/search-index"
	pageSize      = 100
	maxResults    = 10000

	// Stop paginating if a full page yields zero new CIKs we haven't seen.
	stalePagesBeforeStop = 2
)

// SearchFilings performs a paginated full-text search across SEC filings.
// It stops early per form type once new pages stop yielding new trusts.
func (c *Client) SearchFilings(ctx context.Context, query string, forms []string, startDt, endDt string) ([]SearchHit, error) {
	var allHits []SearchHit

	for _, form := range forms {
		hits, err := c.searchByForm(ctx, query, form, startDt, endDt)
		if err != nil {
			return nil, err
		}
		allHits = append(allHits, hits...)
	}

	return allHits, nil
}

// searchByForm searches for a single form type, handling pagination.
// It stops early when consecutive pages yield no new CIKs (trusts).
func (c *Client) searchByForm(ctx context.Context, query, form, startDt, endDt string) ([]SearchHit, error) {
	var allHits []SearchHit
	seenCIKs := make(map[string]bool)
	from := 0
	stalePages := 0

	for {
		resp, err := c.searchPage(ctx, query, form, from, startDt, endDt)
		if err != nil {
			return nil, err
		}

		// Count how many new CIKs this page introduces
		newCIKs := 0
		for _, hit := range resp.Hits.Hits {
			for _, cik := range hit.Source.CIKs {
				if !seenCIKs[cik] {
					seenCIKs[cik] = true
					newCIKs++
				}
			}
		}

		allHits = append(allHits, resp.Hits.Hits...)

		total := resp.Hits.Total.Value
		if c.verbose {
			log.Printf("Form %s: page from=%d — %d hits, %d new CIKs (%d unique total)", form, from, len(resp.Hits.Hits), newCIKs, len(seenCIKs))
		}

		// Track consecutive pages with no new CIKs
		if newCIKs == 0 {
			stalePages++
		} else {
			stalePages = 0
		}

		if stalePages >= stalePagesBeforeStop {
			if c.verbose {
				log.Printf("Form %s: stopping early — %d consecutive pages with no new trusts", form, stalePagesBeforeStop)
			}
			break
		}

		from += pageSize

		// ES hard limit: from+size cannot exceed 10,000
		if from+pageSize > maxResults || from >= total {
			break
		}
	}

	if c.verbose {
		log.Printf("Form %s: done — %d hits fetched, %d unique CIKs", form, len(allHits), len(seenCIKs))
	}

	return allHits, nil
}

// searchPage fetches a single page of search results.
func (c *Client) searchPage(ctx context.Context, query, form string, from int, startDt, endDt string) (*SearchResponse, error) {
	params := url.Values{
		"q":         {`"` + query + `"`},
		"forms":     {form},
		"from":      {fmt.Sprintf("%d", from)},
		"size":      {fmt.Sprintf("%d", pageSize)},
		"dateRange": {"custom"},
		"startdt":   {startDt},
		"enddt":     {endDt},
	}

	reqURL := searchBaseURL + "?" + params.Encode()

	var resp SearchResponse
	if err := c.doRequest(ctx, reqURL, &resp); err != nil {
		return nil, fmt.Errorf("searching form %s (from=%d): %w", form, from, err)
	}
	return &resp, nil
}
