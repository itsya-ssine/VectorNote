import type { AskResponse, DocumentInfo } from "./types";

export const DEMO_DOCUMENTS: DocumentInfo[] = [
  { name: "operating-systems-lecture-05.pdf", size_bytes: 1_204_331 },
  { name: "networks-summary.md", size_bytes: 18_220 },
  { name: "databases-exam-notes.pdf", size_bytes: 482_907 },
];

const CANNED: { match: RegExp; response: AskResponse }[] = [
  {
    match: /mutex|lock|deadlock/i,
    response: {
      answer:
        "A mutex lets only one thread enter a critical section at a time. A deadlock appears when threads hold locks while waiting for each other, so none can continue.",
      sources: [
        {
          source: "operating-systems-lecture-05.pdf",
          page: 12,
          snippet:
            "A mutex provides mutual exclusion: a thread must acquire it before entering the critical section and release it afterwards.",
          score: 0.82,
        },
        {
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
        "A subnet mask separates the network part of an IP address from the host part. A /24 mask leaves 8 bits for hosts, which gives 254 usable addresses.",
      sources: [
        {
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

const FALLBACK: AskResponse = {
  answer:
    "This is a canned demo answer. In the full local version, VectorNote retrieves the most relevant passages from your own documents and answers with citations.",
  sources: [
    {
      source: "databases-exam-notes.pdf",
      page: 1,
      snippet: "Demo passage: real answers cite the exact file and page they came from.",
      score: 0.5,
    },
  ],
};

export async function demoAnswer(question: string): Promise<AskResponse> {
  await new Promise((resolve) => setTimeout(resolve, 700));
  return CANNED.find((c) => c.match.test(question))?.response ?? FALLBACK;
}
