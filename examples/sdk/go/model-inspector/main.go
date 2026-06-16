package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	mmodel "mmodel_go_cli/mmodel"

	"gopkg.in/yaml.v3"
)

type fileSummary struct {
	Path   string
	Kind   string
	Domain string
	Name   string
	Schema string
	Link   string
}

func main() {
	modelPath := flag.String("path", "../../quickstart-multidomain", "model file or directory to inspect")
	limit := flag.Int("limit", 20, "maximum rows to print; use 0 for all rows")
	flag.Parse()

	summaries, skipped, err := inspectPath(*modelPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "inspect model pack: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("MModel Go SDK %s\n", mmodel.Version)
	fmt.Printf("Parsed %d MModel files", len(summaries))
	if skipped > 0 {
		fmt.Printf(" (%d non-model files skipped)", skipped)
	}
	fmt.Println()

	counts := map[string]int{}
	for _, summary := range summaries {
		counts[summary.Kind]++
	}
	kinds := make([]string, 0, len(counts))
	for kind := range counts {
		kinds = append(kinds, kind)
	}
	sort.Strings(kinds)
	for _, kind := range kinds {
		fmt.Printf("- %s: %d\n", kind, counts[kind])
	}

	fmt.Println()
	maxRows := len(summaries)
	if *limit > 0 && *limit < maxRows {
		maxRows = *limit
	}
	for _, summary := range summaries[:maxRows] {
		if summary.Link != "" {
			fmt.Printf("%s %s/%s -> %s (%s)\n", summary.Kind, summary.Domain, summary.Name, summary.Link, summary.Path)
			continue
		}
		fmt.Printf("%s %s/%s schema=%s (%s)\n", summary.Kind, summary.Domain, summary.Name, summary.Schema, summary.Path)
	}
	if maxRows < len(summaries) {
		fmt.Printf("... %d more files\n", len(summaries)-maxRows)
	}
}

func inspectPath(root string) ([]fileSummary, int, error) {
	info, err := os.Stat(root)
	if err != nil {
		return nil, 0, err
	}

	var files []string
	if !info.IsDir() {
		files = []string{root}
	} else {
		if err := filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.IsDir() {
				return nil
			}
			if isModelCandidate(path) {
				files = append(files, path)
			}
			return nil
		}); err != nil {
			return nil, 0, err
		}
	}
	sort.Strings(files)

	var summaries []fileSummary
	skipped := 0
	for _, file := range files {
		data, err := os.ReadFile(file)
		if err != nil {
			return nil, skipped, err
		}
		if !looksLikeMModel(data) {
			skipped++
			continue
		}

		obj, err := parseMModel(file, data)
		if err != nil {
			return nil, skipped, fmt.Errorf("%s: %w", file, err)
		}
		if err := obj.Validate(); err != nil {
			return nil, skipped, fmt.Errorf("%s: %w", file, err)
		}

		metadata := obj.GetMetadata()
		schema := obj.GetSchema()
		summary := fileSummary{
			Path:   filepath.ToSlash(file),
			Kind:   obj.GetKind(),
			Domain: metadata.Domain,
			Name:   metadata.Name,
			Schema: schema.Version,
		}
		if src, dest := mmodel.GetLinkEndpoints(obj); src != nil && dest != nil {
			summary.Link = fmt.Sprintf("%s/%s -> %s/%s", src.Kind, src.Name, dest.Kind, dest.Name)
		}
		summaries = append(summaries, summary)
	}
	return summaries, skipped, nil
}

func isModelCandidate(path string) bool {
	switch strings.ToLower(filepath.Ext(path)) {
	case ".json", ".yaml", ".yml":
		return true
	default:
		return false
	}
}

func parseMModel(path string, data []byte) (mmodel.MModelCoreObject, error) {
	if strings.EqualFold(filepath.Ext(path), ".json") {
		return mmodel.ParseJsonMModel(data)
	}
	return mmodel.ParseYamlMModel(data)
}

func looksLikeMModel(data []byte) bool {
	var header struct {
		Kind     string `json:"kind" yaml:"kind"`
		Metadata struct {
			Domain string `json:"domain" yaml:"domain"`
			Name   string `json:"name" yaml:"name"`
		} `json:"metadata" yaml:"metadata"`
		Schema struct {
			Version string `json:"version" yaml:"version"`
		} `json:"schema" yaml:"schema"`
	}
	if json.Unmarshal(data, &header) != nil {
		if yaml.Unmarshal(data, &header) != nil {
			return false
		}
	}
	return header.Kind != "" && header.Metadata.Domain != "" && header.Metadata.Name != "" && header.Schema.Version != ""
}
