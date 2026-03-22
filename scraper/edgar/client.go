package edgar

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"
)

const (
	rateInterval = 110 * time.Millisecond // ~9 req/sec (SEC limit is 10/sec)
	maxRetries   = 3
)

// Client is an HTTP client for the SEC EDGAR APIs with rate limiting and retries.
type Client struct {
	http      *http.Client
	userAgent string
	ticker    *time.Ticker
	verbose   bool
}

// NewClient creates a new EDGAR API client.
// The email is required by the SEC for the User-Agent header.
func NewClient(email string, verbose bool) *Client {
	return &Client{
		http:      &http.Client{Timeout: 30 * time.Second},
		userAgent: fmt.Sprintf("RialtoTrustScraper/1.0 (%s)", email),
		ticker:    time.NewTicker(rateInterval),
		verbose:   verbose,
	}
}

// Close releases resources held by the client.
func (c *Client) Close() {
	c.ticker.Stop()
}

// doRequest performs an HTTP GET with rate limiting and retries.
func (c *Client) doRequest(ctx context.Context, url string, result interface{}) error {
	var lastErr error

	for attempt := 0; attempt <= maxRetries; attempt++ {
		if attempt > 0 {
			backoff := time.Duration(1<<uint(attempt-1)) * time.Second
			if c.verbose {
				log.Printf("Retry %d/%d after %v for %s", attempt, maxRetries, backoff, url)
			}
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(backoff):
			}
		}

		// Rate limit
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-c.ticker.C:
		}

		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			return fmt.Errorf("creating request: %w", err)
		}
		req.Header.Set("User-Agent", c.userAgent)
		req.Header.Set("Accept", "application/json")

		if c.verbose {
			log.Printf("GET %s", url)
		}

		resp, err := c.http.Do(req)
		if err != nil {
			lastErr = fmt.Errorf("HTTP request failed: %w", err)
			continue
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			lastErr = fmt.Errorf("reading response body: %w", err)
			continue
		}

		switch resp.StatusCode {
		case http.StatusOK:
			if err := json.Unmarshal(body, result); err != nil {
				return fmt.Errorf("decoding JSON from %s: %w", url, err)
			}
			return nil
		case http.StatusForbidden:
			return fmt.Errorf("403 Forbidden from %s — the SEC requires a valid User-Agent header with contact email. Provided: %q", url, c.userAgent)
		case http.StatusTooManyRequests, http.StatusServiceUnavailable, http.StatusInternalServerError:
			lastErr = fmt.Errorf("HTTP %d from %s", resp.StatusCode, url)
			continue
		default:
			return fmt.Errorf("unexpected HTTP %d from %s: %s", resp.StatusCode, url, string(body[:min(len(body), 200)]))
		}
	}

	return fmt.Errorf("max retries exceeded: %w", lastErr)
}

// DoRequestRaw performs an HTTP GET and returns the response body as a string.
// Uses the same rate limiting and retry logic as doRequest.
func (c *Client) DoRequestRaw(ctx context.Context, url string, result *string) error {
	var lastErr error

	for attempt := 0; attempt <= maxRetries; attempt++ {
		if attempt > 0 {
			backoff := time.Duration(1<<uint(attempt-1)) * time.Second
			if c.verbose {
				log.Printf("Retry %d/%d after %v for %s", attempt, maxRetries, backoff, url)
			}
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(backoff):
			}
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-c.ticker.C:
		}

		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			return fmt.Errorf("creating request: %w", err)
		}
		req.Header.Set("User-Agent", c.userAgent)

		if c.verbose {
			log.Printf("GET %s", url)
		}

		resp, err := c.http.Do(req)
		if err != nil {
			lastErr = fmt.Errorf("HTTP request failed: %w", err)
			continue
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			lastErr = fmt.Errorf("reading response body: %w", err)
			continue
		}

		switch resp.StatusCode {
		case http.StatusOK:
			*result = string(body)
			return nil
		case http.StatusForbidden:
			return fmt.Errorf("403 Forbidden from %s", url)
		case http.StatusTooManyRequests, http.StatusServiceUnavailable, http.StatusInternalServerError:
			lastErr = fmt.Errorf("HTTP %d from %s", resp.StatusCode, url)
			continue
		default:
			return fmt.Errorf("unexpected HTTP %d from %s: %s", resp.StatusCode, url, string(body[:min(len(body), 200)]))
		}
	}

	return fmt.Errorf("max retries exceeded: %w", lastErr)
}
