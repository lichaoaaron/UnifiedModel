package main

import (
	"encoding/json"
	"fmt"
	"reflect"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

var toonNumberLike = regexp.MustCompile(`^[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$`)

func encodeTOON(value any) string {
	normalized := normalizeTOONValue(value)
	var b strings.Builder
	writeTOONValue(&b, "", normalized, 0)
	return strings.TrimRight(b.String(), "\n")
}

func normalizeTOONValue(value any) any {
	switch typed := value.(type) {
	case nil, string, bool, float64, float32, int, int64, int32, uint, uint64, uint32, json.Number:
		return typed
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, item := range typed {
			out[key] = normalizeTOONValue(item)
		}
		return out
	case []any:
		out := make([]any, 0, len(typed))
		for _, item := range typed {
			out = append(out, normalizeTOONValue(item))
		}
		return out
	default:
		if reflect.ValueOf(value).Kind() == reflect.Slice {
			body, _ := json.Marshal(value)
			var out []any
			if err := json.Unmarshal(body, &out); err == nil {
				return normalizeTOONValue(out)
			}
		}
		body, err := json.Marshal(value)
		if err != nil {
			return fmt.Sprint(value)
		}
		var out any
		if err := json.Unmarshal(body, &out); err != nil {
			return fmt.Sprint(value)
		}
		return normalizeTOONValue(out)
	}
}

func writeTOONValue(b *strings.Builder, key string, value any, level int) {
	switch typed := value.(type) {
	case map[string]any:
		if key != "" {
			writeIndent(b, level)
			b.WriteString(key)
			b.WriteString(":\n")
			level++
		}
		keys := make([]string, 0, len(typed))
		for itemKey := range typed {
			keys = append(keys, itemKey)
		}
		sort.Strings(keys)
		for _, itemKey := range keys {
			writeTOONValue(b, itemKey, typed[itemKey], level)
		}
	case []any:
		writeTOONArray(b, key, typed, level)
	default:
		writeIndent(b, level)
		if key != "" {
			b.WriteString(key)
			b.WriteString(": ")
		}
		b.WriteString(toonScalar(typed))
		b.WriteString("\n")
	}
}

func writeTOONArray(b *strings.Builder, key string, values []any, level int) {
	writeIndent(b, level)
	if key != "" {
		b.WriteString(key)
	}
	if fields, ok := uniformScalarObjectFields(values); ok {
		b.WriteString(fmt.Sprintf("[%d]{%s}:\n", len(values), strings.Join(fields, ",")))
		for _, row := range values {
			rowMap := row.(map[string]any)
			writeIndent(b, level+1)
			for index, field := range fields {
				if index > 0 {
					b.WriteString(",")
				}
				b.WriteString(toonScalar(rowMap[field]))
			}
			b.WriteString("\n")
		}
		return
	}
	if allScalars(values) {
		b.WriteString(fmt.Sprintf("[%d]: ", len(values)))
		for index, item := range values {
			if index > 0 {
				b.WriteString(",")
			}
			b.WriteString(toonScalar(item))
		}
		b.WriteString("\n")
		return
	}
	b.WriteString(fmt.Sprintf("[%d]:\n", len(values)))
	for _, item := range values {
		writeIndent(b, level+1)
		b.WriteString("-")
		if isScalar(item) {
			b.WriteString(" ")
			b.WriteString(toonScalar(item))
			b.WriteString("\n")
			continue
		}
		if itemMap, ok := item.(map[string]any); ok && len(itemMap) == 1 {
			wroteInline := false
			for onlyKey, onlyValue := range itemMap {
				if isScalar(onlyValue) {
					b.WriteString(" ")
					b.WriteString(onlyKey)
					b.WriteString(": ")
					b.WriteString(toonScalar(onlyValue))
					b.WriteString("\n")
					wroteInline = true
				}
			}
			if wroteInline {
				continue
			}
		}
		b.WriteString("\n")
		writeTOONValue(b, "", item, level+2)
	}
}

func uniformScalarObjectFields(values []any) ([]string, bool) {
	if len(values) == 0 {
		return nil, false
	}
	first, ok := values[0].(map[string]any)
	if !ok || len(first) == 0 {
		return nil, false
	}
	fields := make([]string, 0, len(first))
	for key, value := range first {
		if !isScalar(value) {
			return nil, false
		}
		fields = append(fields, key)
	}
	sort.Strings(fields)
	for _, item := range values[1:] {
		row, ok := item.(map[string]any)
		if !ok || len(row) != len(fields) {
			return nil, false
		}
		for _, field := range fields {
			value, ok := row[field]
			if !ok || !isScalar(value) {
				return nil, false
			}
		}
	}
	return fields, true
}

func allScalars(values []any) bool {
	for _, value := range values {
		if !isScalar(value) {
			return false
		}
	}
	return true
}

func isScalar(value any) bool {
	switch value.(type) {
	case nil, string, bool, float64, float32, int, int64, int32, uint, uint64, uint32, json.Number:
		return true
	default:
		return false
	}
}

func toonScalar(value any) string {
	switch typed := value.(type) {
	case nil:
		return "null"
	case bool:
		if typed {
			return "true"
		}
		return "false"
	case string:
		return toonString(typed)
	case float64:
		return strconv.FormatFloat(typed, 'f', -1, 64)
	case float32:
		return strconv.FormatFloat(float64(typed), 'f', -1, 32)
	case int:
		return strconv.Itoa(typed)
	case int64:
		return strconv.FormatInt(typed, 10)
	case int32:
		return strconv.FormatInt(int64(typed), 10)
	case uint:
		return strconv.FormatUint(uint64(typed), 10)
	case uint64:
		return strconv.FormatUint(typed, 10)
	case uint32:
		return strconv.FormatUint(uint64(typed), 10)
	case json.Number:
		return typed.String()
	default:
		return toonString(fmt.Sprint(typed))
	}
}

func toonString(value string) string {
	if needsTOONQuote(value) {
		return strconv.Quote(value)
	}
	return value
}

func needsTOONQuote(value string) bool {
	if value == "" || strings.TrimSpace(value) != value {
		return true
	}
	if value == "true" || value == "false" || value == "null" || value == "-" || toonNumberLike.MatchString(value) {
		return true
	}
	if strings.HasPrefix(value, "-") {
		return true
	}
	return strings.ContainsAny(value, ":\"\\[]{},\n\t\r")
}

func writeIndent(b *strings.Builder, level int) {
	for i := 0; i < level; i++ {
		b.WriteString("  ")
	}
}
