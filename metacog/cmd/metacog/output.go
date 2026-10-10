package main

import (
	"encoding/json"
)

type OutputError struct {
	Message    string `json:"error"`
	Code       int    `json:"code"`
	Suggestion string `json:"suggestion"`
}

func FormatOutput(asJSON bool, output string, err *OutputError) string {
	if !asJSON {
		if err != nil {
			return err.Message
		}
		return output
	}

	if err != nil {
		data, _ := json.Marshal(err)
		return string(data)
	}

	data, _ := json.Marshal(map[string]string{"output": output})
	return string(data)
}

// FormatStructured renders text normally, or marshals v when --json is set.
// Use it for commands whose result is data (status, history, inspire, version,
// stratagem status/list). Primitive output stays FormatOutput's
// {"output": ...} because the text itself is the artifact.
func FormatStructured(asJSON bool, text string, v any) string {
	if !asJSON {
		return text
	}
	data, err := json.Marshal(v)
	if err != nil {
		return FormatOutput(true, "", &OutputError{Message: err.Error(), Code: 1})
	}
	return string(data)
}
