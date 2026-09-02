"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  createJob,
  getJob,
  Job,
  QUESTION_TYPES,
  QuestionType,
  retryGeneration,
} from "@/lib/api";

const INITIAL_TYPES: QuestionType[] = ["What", "How", "Why"];
const GITHUB_URL =
  process.env.NEXT_PUBLIC_GITHUB_URL ||
  "https://github.com/LuisAlbertoMunozUbando/youtube2knowledge";
const LAST_JOB_KEY = "youtube2knowledge:last-job-id";

function duration(seconds: number | null): string {
  if (!seconds) return "";
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${remainder.toString().padStart(2, "0")}`;
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [selectedTypes, setSelectedTypes] = useState<QuestionType[]>(INITIAL_TYPES);
  const [keywords, setKeywords] = useState("");
  const [customQuestions, setCustomQuestions] = useState("");
  const [questionsPerType, setQuestionsPerType] = useState(2);
  const [language, setLanguage] = useState<"auto" | "en" | "es">("auto");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const running = job && !["completed", "failed"].includes(job.stage);

  useEffect(() => {
    let cancelled = false;
    const savedJobId = window.localStorage.getItem(LAST_JOB_KEY);
    if (!savedJobId) return;

    void getJob(savedJobId)
      .then((savedJob) => {
        if (!cancelled) setJob(savedJob);
      })
      .catch((restoreError) => {
        if (restoreError instanceof ApiError && restoreError.status === 404) {
          window.localStorage.removeItem(LAST_JOB_KEY);
          return;
        }
        if (!cancelled) {
          setError("Unable to restore the last job yet. Reload to try again.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!job || !running) return;
    let cancelled = false;
    const jobId = job.id;

    async function poll() {
      try {
        const updated = await getJob(jobId);
        if (!cancelled) {
          setJob(updated);
          setError(null);
        }
      } catch (pollError) {
        if (!cancelled) {
          const message =
            pollError instanceof Error ? pollError.message : "Unable to check progress";
          setError(`${message}. Progress checks will continue automatically.`);
        }
      }
    }

    void poll();
    const timer = window.setInterval(poll, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.id, running]);

  const groupedQuestions = useMemo(() => {
    const groups = new Map<string, Job["questions"]>();
    for (const question of job?.questions || []) {
      groups.set(question.type, [...(groups.get(question.type) || []), question]);
    }
    return groups;
  }, [job?.questions]);

  function toggleType(type: QuestionType) {
    setSelectedTypes((current) =>
      current.includes(type) ? current.filter((item) => item !== type) : [...current, type],
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (selectedTypes.length === 0) {
      setError("Select at least one question type.");
      return;
    }
    setSubmitting(true);
    setJob(null);
    try {
      const created = await createJob({
        youtube_url: url,
        question_types: selectedTypes,
        keywords: keywords
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        custom_questions: customQuestions
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean),
        questions_per_type: questionsPerType,
        output_language: language,
      });
      setJob(created);
      window.localStorage.setItem(LAST_JOB_KEY, created.id);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to start processing");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRetryGeneration() {
    if (!job) return;
    setRetrying(true);
    setError(null);
    try {
      const retried = await retryGeneration(job.id);
      setJob(retried);
      window.localStorage.setItem(LAST_JOB_KEY, retried.id);
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "Unable to retry generation");
    } finally {
      setRetrying(false);
    }
  }

  function downloadResults() {
    if (!job) return;
    const blob = new Blob([JSON.stringify(job, null, 2)], { type: "application/json" });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `youtube2knowledge-${job.video?.video_id || job.id}.json`;
    anchor.click();
    URL.revokeObjectURL(href);
  }

  return (
    <main>
      <nav className="nav shell">
        <a className="brand" href="#top" aria-label="Youtube2knowledge home">
          <span className="brandMark">Y2K</span>
          <span>Youtube2knowledge</span>
        </a>
        <a className="githubLink" href={GITHUB_URL} target="_blank" rel="noreferrer">
          Open source <span aria-hidden="true">↗</span>
        </a>
      </nav>

      <section className="hero shell" id="top">
        <div className="eyebrow"><span /> Video in. Understanding out.</div>
        <h1>Turn any video into<br /><em>questions worth asking.</em></h1>
        <p className="heroCopy">
          Transcribe a YouTube video and build a grounded knowledge set using the question
          words that shape understanding.
        </p>
      </section>

      <section className="workspace shell">
        <form className="composer" onSubmit={handleSubmit}>
          <div className="fieldGroup primaryField">
            <label htmlFor="youtube-url">YouTube URL</label>
            <div className="urlRow">
              <span className="playIcon" aria-hidden="true">▶</span>
              <input
                id="youtube-url"
                type="url"
                required
                placeholder="https://youtube.com/watch?v=..."
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                disabled={Boolean(running)}
              />
            </div>
          </div>

          <div className="divider" />

          <fieldset className="fieldGroup">
            <legend>What do you want to understand?</legend>
            <p className="fieldHint">Select one or more question lenses.</p>
            <div className="questionGrid">
              {QUESTION_TYPES.map((type) => (
                <button
                  className={selectedTypes.includes(type) ? "questionChip selected" : "questionChip"}
                  type="button"
                  key={type}
                  aria-pressed={selectedTypes.includes(type)}
                  onClick={() => toggleType(type)}
                  disabled={Boolean(running)}
                >
                  <span className="check">{selectedTypes.includes(type) ? "✓" : "+"}</span>
                  {type}
                </button>
              ))}
            </div>
          </fieldset>

          <div className="formColumns">
            <div className="fieldGroup">
              <label htmlFor="keywords">Focus keywords <span>Optional</span></label>
              <input
                id="keywords"
                type="text"
                placeholder="robotics, policy, investment"
                value={keywords}
                onChange={(event) => setKeywords(event.target.value)}
                disabled={Boolean(running)}
              />
              <p className="fieldHint">Separate terms with commas.</p>
            </div>

            <div className="fieldGroup">
              <label htmlFor="language">Output language</label>
              <select
                id="language"
                value={language}
                onChange={(event) => setLanguage(event.target.value as typeof language)}
                disabled={Boolean(running)}
              >
                <option value="auto">Same as video</option>
                <option value="en">English</option>
                <option value="es">Spanish</option>
              </select>
            </div>
          </div>

          <div className="fieldGroup">
            <label htmlFor="custom-questions">Your own questions <span>Optional · one per line</span></label>
            <textarea
              id="custom-questions"
              rows={3}
              placeholder={"What is the central claim?\nHow could I apply this idea?"}
              value={customQuestions}
              onChange={(event) => setCustomQuestions(event.target.value)}
              disabled={Boolean(running)}
            />
          </div>

          <div className="actionRow">
            <label className="countControl">
              <span>Questions per type</span>
              <select
                value={questionsPerType}
                onChange={(event) => setQuestionsPerType(Number(event.target.value))}
                disabled={Boolean(running)}
              >
                {[1, 2, 3, 4, 5].map((count) => <option key={count}>{count}</option>)}
              </select>
            </label>
            <button className="submitButton" type="submit" disabled={submitting || Boolean(running)}>
              {running ? "Building knowledge…" : submitting ? "Starting…" : "Generate knowledge"}
              <span aria-hidden="true">→</span>
            </button>
          </div>
          {error && <p className="errorMessage" role="alert">{error}</p>}
        </form>

        {job && (
          <section className="results" aria-live="polite">
            <div className="statusCard">
              <div className="statusTop">
                <div>
                  <p className="statusLabel">{job.stage}</p>
                  <h2>{job.video?.title || job.message}</h2>
                  {job.video && (
                    <p>
                      {[job.video.channel, duration(job.video.duration_seconds)]
                        .filter(Boolean)
                        .join(" · ")}
                      {" · "}
                      <a
                        className="sourceLink"
                        href={url || `https://youtu.be/${job.video.video_id}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Source ↗
                      </a>
                    </p>
                  )}
                </div>
                <strong>{job.progress}%</strong>
              </div>
              <div className="progressTrack"><span style={{ width: `${job.progress}%` }} /></div>
              <p className="statusMessage">{job.error || job.message}</p>
              {job.stage === "failed" && job.transcript && (
                <button
                  className="retryButton"
                  type="button"
                  onClick={handleRetryGeneration}
                  disabled={retrying}
                >
                  {retrying ? "Retrying…" : "Retry question generation"}
                  <span aria-hidden="true">↻</span>
                </button>
              )}
            </div>

            {job.stage === "completed" && (
              <>
                <div className="resultsHeader">
                  <div>
                    <p className="eyebrow"><span /> Knowledge set</p>
                    <h2>{job.questions.length} grounded answers</h2>
                  </div>
                  <button className="downloadButton" type="button" onClick={downloadResults}>
                    Download JSON ↓
                  </button>
                </div>

                {job.archive_files.length > 0 && (
                  <div className="archiveNotice">
                    <span aria-hidden="true">✓</span>
                    <p>
                      Evidence package archived
                      <small>JSON and Markdown are queued for Google Drive.</small>
                    </p>
                  </div>
                )}

                {[...groupedQuestions.entries()].map(([type, questions]) => (
                  <section className="questionSection" key={type}>
                    <div className="typeHeading"><span>{type}</span><i /></div>
                    <div className="answerGrid">
                      {questions.map((item, index) => (
                        <article className="answerCard" key={`${type}-${index}`}>
                          <p className="questionNumber">{String(index + 1).padStart(2, "0")}</p>
                          <h3>{item.question}</h3>
                          <p className="answer">{item.answer}</p>
                          {item.evidence && <blockquote>“{item.evidence}”</blockquote>}
                        </article>
                      ))}
                    </div>
                  </section>
                ))}

                {job.transcript && (
                  <details className="transcript">
                    <summary>View full transcript <span>+</span></summary>
                    <p>{job.transcript}</p>
                  </details>
                )}
              </>
            )}
          </section>
        )}
      </section>

      <footer className="shell">
        <span>Youtube2knowledge</span>
        <p>Open knowledge, grounded in the source.</p>
      </footer>
    </main>
  );
}
