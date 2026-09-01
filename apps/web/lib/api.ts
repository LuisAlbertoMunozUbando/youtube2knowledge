export const QUESTION_TYPES = [
  "What",
  "Which",
  "Where",
  "When",
  "How",
  "Why",
  "Who",
  "Whose",
] as const;

export type QuestionType = (typeof QUESTION_TYPES)[number];
export type JobStage =
  | "queued"
  | "downloading"
  | "transcribing"
  | "generating"
  | "completed"
  | "failed";

export type GeneratedQuestion = {
  type: string;
  question: string;
  answer: string;
  evidence: string;
};

export type Job = {
  id: string;
  stage: JobStage;
  progress: number;
  message: string;
  video: null | {
    video_id: string;
    title: string;
    channel: string | null;
    duration_seconds: number | null;
    thumbnail_url: string | null;
  };
  transcript: string | null;
  questions: GeneratedQuestion[];
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type CreateJob = {
  youtube_url: string;
  question_types: QuestionType[];
  custom_questions: string[];
  keywords: string[];
  questions_per_type: number;
  output_language: "auto" | "en" | "es";
};

const API_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

async function parseResponse(response: Response): Promise<Job> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<Job>;
}

export async function createJob(payload: CreateJob): Promise<Job> {
  const response = await fetch(`${API_URL}/api/v1/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function getJob(jobId: string): Promise<Job> {
  const response = await fetch(`${API_URL}/api/v1/jobs/${jobId}`, { cache: "no-store" });
  return parseResponse(response);
}
