import type { AskResult, DocumentInfo } from "./types";

export const DEMO_DOCUMENTS: DocumentInfo[] = [
  { name: "operating-systems-lecture-05.pdf", size_bytes: 1_204_331 },
  { name: "networks-summary.md", size_bytes: 18_220 },
  { name: "databases-exam-notes.pdf", size_bytes: 482_907 },
];

const CANNED: { match: RegExp; response: AskResult }[] = [
  {
    match: /mutex|lock|deadlock/i,
    response: {
      answer:
        "A mutex lets only one thread enter a critical section at a time [1]. A deadlock appears when threads hold locks while waiting for each other, so none can continue [2].",
      answered: true,
      standalone_question: "",
      cited: true,
      sources: [
        {
          number: 1,
          source: "operating-systems-lecture-05.pdf",
          page: 12,
          snippet:
            "A mutex provides mutual exclusion: a thread must acquire it before entering the critical section and release it afterwards.",
          score: 0.82,
        },
        {
          number: 2,
          source: "operating-systems-lecture-05.pdf",
          page: 17,
          snippet:
            "Deadlock requires four conditions: mutual exclusion, hold and wait, no preemption and circular wait.",
          score: 0.77,
        },
      ],
    },
  },
  {
    match: /subnet|ip|mask/i,
    response: {
      answer:
        "A subnet mask separates the network part of an IP address from the host part [1]. A /24 mask leaves 8 bits for hosts, which gives 254 usable addresses.",
      answered: true,
      standalone_question: "",
      cited: true,
      sources: [
        {
          number: 1,
          source: "networks-summary.md",
          page: 3,
          snippet:
            "The subnet mask marks which bits belong to the network. With /24, the first three octets identify the network.",
          score: 0.8,
        },
      ],
    },
  },
];

const FALLBACK: AskResult = {
  answer:
    "This is a canned demo answer. In the full local version, VectorNote retrieves the most relevant passages from your own documents and answers with citations [1].",
  answered: true,
  standalone_question: "",
  cited: true,
  sources: [
    {
      number: 1,
      source: "databases-exam-notes.pdf",
      page: 1,
      snippet: "Demo passage: real answers cite the exact file and page they came from.",
      score: 0.5,
    },
  ],
};

export function demoResult(question: string): AskResult {
  return CANNED.find((c) => c.match.test(question))?.response ?? FALLBACK;
}

export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}
