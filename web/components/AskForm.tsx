"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import styles from "../app/ask/page.module.css";

export interface AskFormCompanyOption {
  ticker: string;
  name: string;
}

export interface AskFormProps {
  initialQuestion: string;
  initialCompany: string;
  initialReportYear: string;
  companies: readonly AskFormCompanyOption[];
  reportYears: readonly string[];
}

/**
 * Client component so the "Ask" button can show a real loading state
 * (brief: "loading state") while Next.js navigates to the new `/ask?q=...`
 * URL -- `useTransition` reflects actual navigation pendency, not a fake
 * timer. The underlying navigation is still a plain URL with query
 * parameters (no client-side fetch of report data), matching every other
 * page's server-component-first, bookmarkable-URL discipline.
 */
export function AskForm({ initialQuestion, initialCompany, initialReportYear, companies, reportYears }: AskFormProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [question, setQuestion] = useState(initialQuestion);
  const [company, setCompany] = useState(initialCompany);
  const [reportYear, setReportYear] = useState(initialReportYear);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams();
    if (question.trim()) params.set("q", question.trim());
    if (company) params.set("company", company);
    if (reportYear) params.set("year", reportYear);
    startTransition(() => {
      router.push(`/ask?${params.toString()}`);
    });
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} aria-label="Ask a question about the report corpus">
      <div className={styles.formField}>
        <label htmlFor="ask-question" className={styles.label}>
          Question
        </label>
        <input
          id="ask-question"
          name="q"
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          className={styles.input}
          placeholder="e.g. What did the company disclose about liquidity risk?"
        />
      </div>
      <div className={styles.formField}>
        <label htmlFor="ask-company" className={styles.label}>
          Company (optional)
        </label>
        <select
          id="ask-company"
          name="company"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          className={styles.select}
        >
          <option value="">All companies</option>
          {companies.map((c) => (
            <option key={c.ticker} value={c.ticker}>
              {c.ticker} -- {c.name}
            </option>
          ))}
        </select>
      </div>
      <div className={styles.formField}>
        <label htmlFor="ask-year" className={styles.label}>
          Report year (optional)
        </label>
        <select
          id="ask-year"
          name="year"
          value={reportYear}
          onChange={(e) => setReportYear(e.target.value)}
          className={styles.select}
        >
          <option value="">All years</option>
          {reportYears.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </div>
      <button type="submit" className={styles.submit} disabled={isPending} aria-busy={isPending}>
        {isPending ? "Asking..." : "Ask"}
      </button>
    </form>
  );
}
