package model

// EvidencePlan holds the parsed parameters of an evidence(...) pipeline operator.
type EvidencePlan struct {
	Kind string     `json:"kind"`
	From *string    `json:"from,omitempty"`
	To   *string    `json:"to,omitempty"`
}

// EvidenceExplain holds the resolved execution chain produced by evidence(...).
type EvidenceExplain struct {
	EntityID         string            `json:"entity_id,omitempty"`
	EntityType       string            `json:"entity_type,omitempty"`
	EntityFieldValue string            `json:"entity_field_value,omitempty"`
	DataLinkName     string            `json:"data_link_name,omitempty"`
	DataSetKind      string            `json:"dataset_kind,omitempty"`
	DataSetName      string            `json:"dataset_name,omitempty"`
	StorageLinkName  string            `json:"storage_link_name,omitempty"`
	StorageName      string            `json:"storage_name,omitempty"`
	StorageType      string            `json:"storage_type,omitempty"`
	Provider         string            `json:"provider,omitempty"`
	FieldsMapping    map[string]string `json:"fields_mapping,omitempty"`
	TimeFrom         string            `json:"time_from,omitempty"`
	TimeTo           string            `json:"time_to,omitempty"`
	ScannedFiles     []string          `json:"scanned_files,omitempty"`
	ReturnedRows     int               `json:"returned_rows,omitempty"`
}
