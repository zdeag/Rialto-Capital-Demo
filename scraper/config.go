package main

import (
	"flag"
	"fmt"
	"os"
	"strings"
)

// Config holds CLI configuration parsed from flags.
type Config struct {
	Email      string
	CIK        string
	Query      string
	StartDt    string
	EndDt      string
	JSON       bool
	Verbose    bool
	Forms      []string
	DownloadEx bool
	OutDir     string
}

// ParseConfig reads CLI flags and validates required fields.
func ParseConfig() Config {
	var cfg Config

	flag.StringVar(&cfg.Email, "email", "", "Contact email for SEC User-Agent header (required)")
	flag.StringVar(&cfg.CIK, "cik", "0001563982", "CIK of the entity to look up")
	flag.StringVar(&cfg.Query, "query", "Rialto Capital Advisors", "Full-text search query")
	flag.BoolVar(&cfg.JSON, "json", false, "Output results as JSON")
	flag.BoolVar(&cfg.Verbose, "verbose", false, "Enable verbose/debug logging")
	flag.StringVar(&cfg.StartDt, "startdt", "2024-01-01", "Start date for filing search (YYYY-MM-DD)")
	flag.StringVar(&cfg.EndDt, "enddt", "2026-03-20", "End date for filing search (YYYY-MM-DD)")
	flag.BoolVar(&cfg.DownloadEx, "download", false, "Download EX-99.1 exhibits from most recent filing per trust")
	flag.StringVar(&cfg.OutDir, "outdir", "exhibits", "Output directory for downloaded exhibits")

	var forms string
	flag.StringVar(&forms, "forms", "10-D", "Comma-separated form types to search")

	flag.Parse()

	if cfg.Email == "" {
		fmt.Fprintln(os.Stderr, "Error: --email is required (SEC requires a contact email in the User-Agent header)")
		flag.Usage()
		os.Exit(1)
	}

	cfg.Forms = strings.Split(forms, ",")
	for i := range cfg.Forms {
		cfg.Forms[i] = strings.TrimSpace(cfg.Forms[i])
	}

	return cfg
}
