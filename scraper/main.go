package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"text/tabwriter"

	"github.com/zacharydeaguuar/rialto-edgar-scraper/edgar"
	"github.com/zacharydeaguuar/rialto-edgar-scraper/filing"
	"github.com/zacharydeaguuar/rialto-edgar-scraper/trust"
)

func main() {
	cfg := ParseConfig()

	if !cfg.Verbose {
		log.SetOutput(os.Stderr)
	}

	ctx := context.Background()

	client := edgar.NewClient(cfg.Email, cfg.Verbose)
	defer client.Close()

	// Step 1: Confirm the entity exists via submissions API
	if cfg.Verbose {
		log.Printf("Fetching submissions for CIK %s...", cfg.CIK)
	}
	subs, err := client.GetSubmissions(ctx, cfg.CIK)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error fetching entity: %v\n", err)
		os.Exit(1)
	}
	fmt.Fprintf(os.Stderr, "Entity: %s (CIK %s)\n", subs.Name, subs.CIK)

	// Step 2: Search filings mentioning the query across all form types
	if cfg.Verbose {
		log.Printf("Searching for %q across forms: %s", cfg.Query, strings.Join(cfg.Forms, ", "))
	}
	hits, err := client.SearchFilings(ctx, cfg.Query, cfg.Forms, cfg.StartDt, cfg.EndDt)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error searching filings: %v\n", err)
		os.Exit(1)
	}
	fmt.Fprintf(os.Stderr, "Total filing hits: %d\n", len(hits))

	// Step 3: Extract and deduplicate trust entities
	trusts := trust.ExtractTrusts(hits)
	fmt.Fprintf(os.Stderr, "Unique trusts found: %d\n", len(trusts))

	// Step 4: Output results
	if cfg.JSON {
		outputJSON(trusts)
	} else {
		outputTable(trusts)
	}

	// Step 5: Download EX-99.1 exhibits if requested
	if cfg.DownloadEx {
		downloadExhibits(ctx, client, trusts, cfg)
	}
}

func downloadExhibits(ctx context.Context, client *edgar.Client, trusts []trust.Trust, cfg Config) {
	fmt.Fprintf(os.Stderr, "\nDownloading EX-99.1 exhibits to %s/\n", cfg.OutDir)

	downloaded := 0
	skipped := 0
	failed := 0

	for i, t := range trusts {
		if t.LatestADSH == "" {
			skipped++
			continue
		}

		// Strip leading zeros from CIK for the URL path
		cik := strings.TrimLeft(t.CIK, "0")
		if cik == "" {
			cik = "0"
		}

		fmt.Fprintf(os.Stderr, "[%d/%d] %s (ADSH %s)...", i+1, len(trusts), t.Name, t.LatestADSH)

		path, err := filing.DownloadExhibit99_1(ctx, client, cik, t.LatestADSH, t.Name, cfg.OutDir, cfg.Verbose)
		if err != nil {
			fmt.Fprintf(os.Stderr, " ERROR: %v\n", err)
			failed++
			continue
		}
		if path == "" {
			fmt.Fprintf(os.Stderr, " no EX-99.1 found\n")
			skipped++
			continue
		}

		fmt.Fprintf(os.Stderr, " saved\n")
		downloaded++
	}

	fmt.Fprintf(os.Stderr, "\nDone: %d downloaded, %d skipped, %d failed\n", downloaded, skipped, failed)
}

func outputJSON(trusts []trust.Trust) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(trusts); err != nil {
		fmt.Fprintf(os.Stderr, "Error encoding JSON: %v\n", err)
		os.Exit(1)
	}
}

func outputTable(trusts []trust.Trust) {
	w := tabwriter.NewWriter(os.Stdout, 0, 4, 2, ' ', 0)
	fmt.Fprintln(w, "NAME\tCIK\tFORM TYPES\tFILINGS\tLATEST FILING")
	fmt.Fprintln(w, "----\t---\t----------\t-------\t-------------")

	for _, t := range trusts {
		latest := ""
		if !t.LatestFiling.IsZero() {
			latest = t.LatestFiling.Format("2006-01-02")
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t%d\t%s\n",
			t.Name,
			t.CIK,
			strings.Join(t.FormTypes, ", "),
			t.FilingCount,
			latest,
		)
	}

	w.Flush()
}
