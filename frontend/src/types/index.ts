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

export type EmotionState = "panic" | "anxiety" | "despair" | "urgent" | "calm";

export type TrialCard = {
  nct_id: string;
  recruitment_status: string;
  phase: string;
  eligibility: string;
  location: string;
  note: string;
};

export type ResearchProgress = {
  summary: string;
  research_stage: "breakthrough_rct" | "early_trial" | "preclinical";
  evidence_level: string;
  uncertainty_note?: string;
  source_id?: string;
};

export type VisitPrepPack = {
  questions_for_doctor: string[];
  info_to_tell_doctor: string[];
  tests_to_request: string[];
  treatment_options_to_confirm: string[];
  positioning_note: string;
};

export type VisitPrepResponse = {
  visit_prep_pack: VisitPrepPack;
  evidence_based: boolean;
  note?: string;
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
  companion_message?: string;
  emotion_state: EmotionState | string;
  trial_cards: TrialCard[];
  research_progress: ResearchProgress[];
  subscription_offer?: { disease_keyword: string; prompt_text: string };
  clarification_questions?: string[];
};

// Research Radar Subscription types

export type Subscription = {
  id: string;
  disease_keyword: string;
  status: string;
  created_at: string;
};

export type PushDigestItem = {
  summary: string;
  research_stage: "breakthrough_rct" | "early_trial" | "preclinical";
  evidence_level: string;
  uncertainty_note?: string;
  source_id?: string;
};

export type PushDigest = {
  disease_keyword: string;
  items: PushDigestItem[];
  generated_at: string;
  is_demo: boolean;
};

export type InAppMessage = {
  id: string;
  digest: PushDigest;
  created_at: string;
  read: boolean;
};
