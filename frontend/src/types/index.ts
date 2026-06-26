export type Evidence = {
  id: string;
  title: string;
  authors?: string;
  source_type: "paper_en" | "paper_cn" | "meeting" | "guide" | "trial" | "package_insert" | "unknown";
  pmid?: string;
  doi?: string;
  nct_id?: string;
  abstract?: string;
  publish_date?: string;
  journal?: string;
  evidence_level?: "high" | "moderate" | "low" | "very_low";
  url?: string;
};

export type SearchResponse = {
  query: string;
  intent?: string;
  risk_level: "low" | "medium" | "high" | "prohibited";
  evidences: Evidence[];
  total: number;
};

export type ExplainResponse = {
  layer1_conclusion: { text: string; citations: string[] };
  layer2_evidence_cards: Array<{
    study_type: string;
    sample_size?: string;
    intervention?: string;
    comparator?: string;
    outcome?: string;
    limitations?: string;
    evidence_level: string;
    source_id: string;
    source_url?: string;
  }>;
  layer3_patient_explanation: {
    what_is_it: string;
    what_evidence_says: string;
    what_it_means_for_you: string;
    when_to_see_doctor: string;
    disclaimer: string;
  };
  risk_level: string;
  risk_message?: string;
};
