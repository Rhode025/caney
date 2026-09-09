/**
 * The v3 wire contract, as TypeScript. §7, §75, §79.
 *
 * Mirrors caney/domain/planning.py and caney/api/contract.py. Python is the source of
 * truth; this file exists so the UI cannot quietly assume a field that is not sent, and
 * so a schema change is a compile error rather than an undefined at 5 a.m.
 *
 * DataState is the type that matters most here. `unknown` is not `null` and is not zero —
 * the whole point of the Observation model is that "we do not know the release forecast"
 * and "the release forecast is zero" are different facts, and a UI that renders both as
 * a dash has thrown away the distinction the backend spent an architecture preserving.
 */

export type DataState = "known" | "stale" | "unknown" | "error";

export interface Observation<T = number> {
  value: T | null;
  unit: string;
  state: DataState;
  observed_at: number | null;
  fetched_at: number | null;
  source: string;
  source_url: string;
  confidence: number;
  note: string;
  age_label: string;
}

export type Species = "striped_bass" | "smallmouth" | "largemouth" | "trout";
export type Craft = "any" | "wade" | "kayak" | "drift" | "power";
export type Method = "fly" | "conventional" | "either";
export type ConfidenceLabel = "HIGH" | "MEDIUM" | "LOW";
export type ResearchStatus = "fresh" | "cached" | "stale" | "degraded" | "disabled";

export interface PlanRequest {
  species: Species;
  craft: Craft;
  method: Method;
  availability: {
    depart_after?: string | number | null;
    return_by?: string | number | null;
    fish_after?: string | number | null;
    fish_before?: string | number | null;
  };
  origin?: { lat: number; lon: number } | null;
  max_drive_minutes?: number | null;
  preferences?: Record<string, unknown>;
}

export interface Leg {
  kind:
    | "depart" | "drive_out" | "prep" | "run_out" | "fish" | "move"
    | "run_back" | "takeout" | "drive_home" | "home";
  label: string;
  start: number;
  end: number;
  minutes: number;
  detail: string;
  zone_id: string;
  provenance: "routed" | "known" | "estimated" | "unknown";
}

export interface LogisticsSummary {
  leave: number | null;
  launch: number | null;
  fish_start: number;
  fish_end: number;
  off_water: number | null;
  home: number | null;
  fishing_minutes: number;
  travel_minutes: number;
  overhead_minutes: number;
}

export interface Logistics {
  legs: Leg[];
  summary: LogisticsSummary;
  envelope: Record<string, unknown>;
  origin: [number, number] | null;
  door_to_door: boolean;
  constants: Record<string, unknown>;
  routing: Record<string, unknown>;
}

export interface Technique {
  primary: string;
  primary_fly: string;
  primary_lure: string;
  primary_size: string;
  primary_color: string;
  line: string;
  leader: string;
  presentation: string;
  depth: string;
  retrieve: string;
  target_structure: string;
  why: string;
  method: Method;
  method_label: string;
  condition_key: string;
  alternate: Record<string, string> | null;
}

export interface Segment {
  type:
    | "launch" | "fish" | "move" | "move_feature" | "wait"
    | "change_technique" | "safety_exit" | "optional_backup" | "end";
  start: number;
  end: number;
  duration_minutes: number;
  zone_id: string;
  zone_name: string;
  instructions: string;
  reason: string;
  confidence: number | null;
  location_confidence: number | null;
  technique: Record<string, unknown> | null;
  triggers: Array<Record<string, unknown>>;
  feature_id: string;
  feature_name: string;
  feature_type: string;
  feature_confidence: string;
  feature_fit: number | null;
  feature_holding: string;
}

export interface Itinerary {
  id: string;
  segments: Segment[];
  windows: Array<{ zone_id: string; start: number; end: number; utility: number }>;
  zone_sequence: string[];
  total_fishing_minutes: number;
  total_transition_minutes: number;
  why: string[];
}

export interface SafetyClaim {
  id: string;
  kind: string;
  zone_id: string;
  text: string;
  at: number | null;
  bound: "earliest" | "typical" | "latest";
  source: string;
  source_url: string;
  state: DataState;
}

export interface FreshnessRow {
  label: string;
  state: DataState;
  age: string | null;
  source: string;
  source_url: string;
}

export interface Recommendation {
  id: string;
  species: Species;
  craft: Craft;
  method: Method;
  verdict: "GO" | "CONDITIONAL" | "SKIP";
  verdict_why: string;
  opportunity: number;
  confidence: number;
  location_confidence: number;
  research_confidence: number;
  primary_candidate: string;
  location: {
    zone_id: string; name: string; waterbody: string; drive: string;
    detail_page: string; kind: string; holds: string;
    geometry: Record<string, unknown> | null;
    hazards: string[]; regs: string;
    location_confidence: Record<string, unknown>;
  };
  access: Record<string, unknown>;
  itinerary: Itinerary | null;
  technique: Technique | null;
  why_this_won: string[];
  backup_plan: { branches: Array<{ if: string; then: string }> } | null;
  alternatives: Array<Record<string, unknown>>;
  water: Record<string, Observation>;
  weather: Record<string, Observation>;
  lunar: Record<string, unknown>;
  biological_context: Record<string, unknown>;
  evidence: Array<Record<string, unknown>>;
  score_breakdown: Array<{ key: string; label: string; earned: number; possible: number; why: string }>;
  safety: SafetyClaim[];
  data_freshness: FreshnessRow[];
  limitations: string[];
  logistics: Logistics | null;
  versions: Record<string, string>;
}

export interface PlanEnvelope {
  plan_id: string;
  created_at: number;
  expires_at: number;
  schema_version: string;
  request: Record<string, unknown>;
  recommendation: Recommendation;
  itinerary: Itinerary | null;
  alternatives: Array<Record<string, unknown>>;
  snapshot_id: string;
  opportunity: number;
  forecast_confidence: number;
  location_confidence: number;
  research_confidence: number;
  confidence_label: ConfidenceLabel;
  confidence_explain: string;
  freshness: FreshnessRow[];
  safety: SafetyClaim[];
  research_status: ResearchStatus;
  research_status_label: string;
  model_versions: Record<string, string>;
  logistics: Logistics | null;
  timings: Record<string, unknown>;
  limitations: string[];
}

export type PlanState =
  | "DRAFT" | "READY" | "EN_ROUTE" | "AT_LAUNCH" | "ON_WATER" | "COMPLETED" | "ABORTED";

export interface Session {
  id: string;
  plan_id: string;
  snapshot_id: string;
  state: PlanState;
  state_label: string;
  active: boolean;
  terminal: boolean;
  refresh_seconds: number | null;
  started_at: number | null;
  ended_at: number | null;
  outcome: Record<string, unknown> | null;
}

export interface DeltaChange {
  field: string;
  label: string;
  was_label: string;
  now_label: string;
  materiality: "informational" | "notable" | "material";
  why: string;
  zone_id: string;
}

export interface PlanDelta {
  verdict: "UNCHANGED" | "MATERIAL_CHANGE";
  checked_at: number;
  changes: DeltaChange[];
  headline: string;
  new_plan_id: string;
  thresholds: Record<string, number>;
}

export interface RefreshResponse {
  plan_id: string;
  checked_at: number;
  delta: PlanDelta;
  plan: PlanEnvelope | null;
}

export interface ApiError {
  error: { message: string; field: string; code: string; status: number };
}
