package trust

import (
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/zacharydeaguuar/rialto-edgar-scraper/edgar"
)

var displayNameRe = regexp.MustCompile(`^(.+?)\s{2,}\(CIK\s+(\d+)\)$`)

// trustKeywords are substrings that indicate a trust-related entity.
var trustKeywords = []string{
	"trust",
	"mortgage",
	"securit",
	"cmbs",
	"rmbs",
	"abs",
	"pass-through",
	"pass through",
	"certificate",
	"loan",
	"asset-backed",
	"asset backed",
	"funding",
	"issuance",
}

// nameVariant tracks how often each name appears for a CIK, so we can pick the most common.
type nameVariant struct {
	name  string
	count int
}

// ExtractTrusts parses search hits and returns deduplicated trust entities.
func ExtractTrusts(hits []edgar.SearchHit) []Trust {
	type trustAccum struct {
		names       map[string]int
		formTypes   map[string]bool
		filingCount int
		latest      time.Time
		latestADSH  string
	}

	accum := make(map[string]*trustAccum) // keyed by CIK

	for _, hit := range hits {
		fileDate, _ := time.Parse("2006-01-02", hit.Source.FileDate)

		for _, dn := range hit.Source.DisplayNames {
			name, cik := parseDisplayName(dn)
			if name == "" || cik == "" {
				continue
			}

			if !isTrustRelated(name) {
				continue
			}

			ta, ok := accum[cik]
			if !ok {
				ta = &trustAccum{
					names:     make(map[string]int),
					formTypes: make(map[string]bool),
				}
				accum[cik] = ta
			}

			ta.names[name]++
			ta.filingCount++
			if hit.Source.Form != "" {
				ta.formTypes[hit.Source.Form] = true
			}
			if !fileDate.IsZero() && fileDate.After(ta.latest) {
				ta.latest = fileDate
				ta.latestADSH = hit.Source.ADSH
			}
		}
	}

	trusts := make([]Trust, 0, len(accum))
	for cik, ta := range accum {
		trusts = append(trusts, Trust{
			Name:         bestName(ta.names),
			CIK:          cik,
			FormTypes:    sortedKeys(ta.formTypes),
			FilingCount:  ta.filingCount,
			LatestFiling: ta.latest,
			LatestADSH:   ta.latestADSH,
			Source:       "efts-search",
		})
	}

	sort.Slice(trusts, func(i, j int) bool {
		return trusts[i].Name < trusts[j].Name
	})

	return trusts
}

// MergeTrusts combines two trust slices, deduplicating by CIK and merging form types.
func MergeTrusts(a, b []Trust) []Trust {
	index := make(map[string]*Trust, len(a))
	for i := range a {
		index[a[i].CIK] = &a[i]
	}

	for _, t := range b {
		if existing, ok := index[t.CIK]; ok {
			// Merge form types
			seen := make(map[string]bool)
			for _, f := range existing.FormTypes {
				seen[f] = true
			}
			for _, f := range t.FormTypes {
				if !seen[f] {
					existing.FormTypes = append(existing.FormTypes, f)
				}
			}
			sort.Strings(existing.FormTypes)
			existing.FilingCount += t.FilingCount
			if t.LatestFiling.After(existing.LatestFiling) {
				existing.LatestFiling = t.LatestFiling
			}
		} else {
			clone := t
			index[t.CIK] = &clone
		}
	}

	result := make([]Trust, 0, len(index))
	for _, t := range index {
		result = append(result, *t)
	}
	sort.Slice(result, func(i, j int) bool {
		return result[i].Name < result[j].Name
	})
	return result
}

// parseDisplayName extracts entity name and CIK from a display_names entry.
// Format: "Entity Name  (CIK 0001234567)"
func parseDisplayName(dn string) (name, cik string) {
	matches := displayNameRe.FindStringSubmatch(dn)
	if len(matches) != 3 {
		return "", ""
	}
	return strings.TrimSpace(matches[1]), matches[2]
}

// isTrustRelated checks if an entity name suggests a securitization trust.
func isTrustRelated(name string) bool {
	lower := strings.ToLower(name)
	for _, kw := range trustKeywords {
		if strings.Contains(lower, kw) {
			return true
		}
	}
	return false
}

// bestName returns the most frequently occurring name variant.
func bestName(names map[string]int) string {
	var best string
	var bestCount int
	for name, count := range names {
		if count > bestCount || (count == bestCount && name < best) {
			best = name
			bestCount = count
		}
	}
	return best
}

// sortedKeys returns the keys of a map in sorted order.
func sortedKeys(m map[string]bool) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}
