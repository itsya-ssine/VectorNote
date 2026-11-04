import type { AskResult, ChatTurn, DocumentInfo, Source } from "./types";

export const DEMO_DOCUMENTS: DocumentInfo[] = [
  { name: "operating-systems-lecture-05.pdf", size_bytes: 1_204_331 },
  { name: "networks-summary.md", size_bytes: 18_220 },
  { name: "databases-exam-notes.pdf", size_bytes: 482_907 },
];

const OS = "operating-systems-lecture-05.pdf";
const NET = "networks-summary.md";
const DB = "databases-exam-notes.pdf";

function src(number: number, source: string, page: number, snippet: string, score: number): Source {
  return { number, source, page, snippet, score };
}

interface Reply {
  answer: string;
  sources: Source[];
}

interface Topic {
  /** Questions that belong to this topic. */
  match: RegExp;
  /** What the follow-up "explain that more" is rewritten into, as the real backend would. */
  standalone: string;
  first: Reply;
  more: Reply;
}

// The passages are invented for the demo; the real app cites your own files and pages.
const TOPICS: Topic[] = [
  {
    match: /\b(mutex(es)?|locks?|deadlocks?|critical sections?)\b/i,
    standalone: "How are deadlocks prevented when using mutexes?",
    first: {
      answer:
        "A mutex lets only one thread enter a critical section at a time [1]. A deadlock appears when threads hold locks while waiting for each other, so none can continue [2].",
      sources: [
        src(1, OS, 12, "A mutex provides mutual exclusion: a thread must acquire it before entering the critical section and release it afterwards.", 0.82),
        src(2, OS, 17, "Deadlock requires four conditions: mutual exclusion, hold and wait, no preemption and circular wait.", 0.77),
      ],
    },
    more: {
      answer:
        "The usual fix is to break circular wait: number the locks and always take them in increasing order [1]. The alternative is a try-lock with a timeout, releasing everything held when it expires [1].",
      sources: [
        src(1, OS, 18, "Prevent circular wait by numbering the locks and always acquiring them in increasing order. A try-lock with a timeout is the alternative.", 0.79),
      ],
    },
  },
  {
    match: /\b(subnet\w*|netmask|mask|cidr|ip address(es)?)\b/i,
    standalone: "Can you give an example of a subnet calculation?",
    first: {
      answer:
        "A subnet mask separates the network part of an IP address from the host part [1]. A /24 mask leaves 8 bits for hosts, which gives 254 usable addresses [2].",
      sources: [
        src(1, NET, 3, "The subnet mask marks which bits belong to the network. With /24, the first three octets identify the network.", 0.8),
        src(2, NET, 4, "A /24 network has 2^8 = 256 addresses; the first is the network address and the last the broadcast address, leaving 254 for hosts.", 0.74),
      ],
    },
    more: {
      answer:
        "Take 192.168.1.0/24: the network address is 192.168.1.0, the broadcast address is 192.168.1.255, and hosts use 192.168.1.1 to 192.168.1.254 [1].",
      sources: [
        src(1, NET, 4, "Example: 192.168.1.0/24. Network 192.168.1.0, broadcast 192.168.1.255, usable hosts .1 to .254.", 0.81),
      ],
    },
  },
  {
    match: /\b(tcp|udp)\b/i,
    standalone: "How does the TCP three-way handshake work?",
    first: {
      answer:
        "TCP sets up a connection, numbers and acknowledges every segment and retransmits losses, so data arrives complete and in order [1]. UDP sends independent datagrams with no such guarantees, which makes it faster and a good fit for streaming or DNS queries [2].",
      sources: [
        src(1, NET, 8, "TCP is connection-oriented and reliable: segments are numbered, acknowledged and retransmitted when lost, and delivered in order.", 0.83),
        src(2, NET, 9, "UDP is connectionless: no handshake, no retransmission, no ordering. Used for DNS, streaming and games where speed matters more than completeness.", 0.78),
      ],
    },
    more: {
      answer:
        "TCP opens a connection with a three-way handshake: the client sends SYN, the server answers SYN-ACK, and the client confirms with ACK before any data is sent [1].",
      sources: [
        src(1, NET, 8, "Three-way handshake: SYN, SYN-ACK, ACK. Only after the ACK does application data flow.", 0.8),
      ],
    },
  },
  {
    match: /\b(paging|virtual memory|page faults?|page tables?)\b/i,
    standalone: "How does the operating system choose which page to evict?",
    first: {
      answer:
        "Virtual memory gives each process its own address space, split into fixed-size pages that the page table maps to physical frames [1]. A page fault happens when a page is not in memory: the OS loads it from disk and retries the instruction [2].",
      sources: [
        src(1, OS, 24, "Each process sees a private address space divided into pages. The page table maps virtual pages to physical frames.", 0.84),
        src(2, OS, 26, "On a page fault the OS finds the page on disk, loads it into a free frame, updates the page table and restarts the instruction.", 0.79),
      ],
    },
    more: {
      answer:
        "When memory is full the OS must evict a victim page. Exact LRU is too expensive, so systems use approximations such as the clock algorithm [1].",
      sources: [
        src(1, OS, 28, "Page replacement: FIFO, optimal, LRU. Real systems approximate LRU with the clock (second chance) algorithm using a reference bit.", 0.77),
      ],
    },
  },
  {
    match: /\b(schedul\w*|round[- ]robin|time slice|quantum)\b/i,
    standalone: "What is the trade-off when choosing the time slice in round robin?",
    first: {
      answer:
        "A scheduler decides which ready process runs next. Round robin gives each process a fixed time slice and moves it to the back of the queue when the slice ends, which is fair but adds context-switch overhead [1]. Shortest job first minimises the average waiting time but needs the run times in advance [2].",
      sources: [
        src(1, OS, 9, "Round robin: each process runs for at most one quantum, then goes to the end of the ready queue. Fair, but every switch costs time.", 0.81),
        src(2, OS, 10, "Shortest job first gives the lowest average waiting time, but the length of the next CPU burst must be known or predicted.", 0.75),
      ],
    },
    more: {
      answer:
        "A small time slice improves responsiveness but increases the number of context switches. A very large one makes round robin behave like first come, first served [1].",
      sources: [
        src(1, OS, 9, "Choosing the quantum: too small and the overhead dominates, too large and round robin degenerates into FCFS.", 0.8),
      ],
    },
  },
  {
    match: /\bjoins?\b/i,
    standalone: "How do I find rows that have no match in another table?",
    first: {
      answer:
        "An INNER JOIN keeps only the rows that have a match in both tables, while a LEFT JOIN keeps every row of the left table and fills the missing right-hand columns with NULL [1].",
      sources: [
        src(1, DB, 4, "INNER JOIN returns matching rows only. LEFT JOIN returns all rows of the left table, with NULL where the right table has no match.", 0.82),
      ],
    },
    more: {
      answer:
        "To find rows with no match, use a LEFT JOIN and keep only the rows where the key of the right table is NULL [1].",
      sources: [
        src(1, DB, 5, "Anti-join pattern: SELECT ... FROM a LEFT JOIN b ON a.id = b.a_id WHERE b.a_id IS NULL.", 0.8),
      ],
    },
  },
  {
    match: /\b(acid|transactions?)\b/i,
    standalone: "What do the SQL isolation levels mean?",
    first: {
      answer:
        "ACID stands for atomicity, consistency, isolation and durability [1]. Atomicity means a transaction is applied completely or not at all, and durability means committed changes survive a crash [2].",
      sources: [
        src(1, DB, 11, "A transaction must be Atomic, Consistent, Isolated and Durable (ACID).", 0.84),
        src(2, DB, 12, "Atomicity: all or nothing, undone with ROLLBACK. Durability: once COMMIT returns, the data survives a crash (write-ahead log).", 0.78),
      ],
    },
    more: {
      answer:
        "Isolation levels trade safety for speed: READ COMMITTED prevents dirty reads, while SERIALIZABLE makes concurrent transactions behave as if they ran one after another [1].",
      sources: [
        src(1, DB, 13, "Isolation levels: READ UNCOMMITTED, READ COMMITTED, REPEATABLE READ, SERIALIZABLE. Higher levels prevent more anomalies and allow less concurrency.", 0.79),
      ],
    },
  },
];

/** Topics the demo can answer, shown when a question is outside them. */
const TOPIC_HINT = "locks and deadlocks, subnets, TCP and UDP, paging, scheduling, SQL joins and transactions";

const NOT_FOUND = "I couldn't find the answer to that in your documents.";

// "explain that more", "why?", "can you give an example": short and without a topic of its own.
const FOLLOW_UP = /\b(more|explain|elaborate|example|detail|why|how so|that|this|it)\b/i;

function topicOf(text: string): Topic | undefined {
  return TOPICS.find((t) => t.match.test(text));
}

function previousTopic(history: ChatTurn[]): Topic | undefined {
  for (let i = history.length - 1; i >= 0; i--) {
    if (history[i].role !== "user") continue;
    const topic = topicOf(history[i].content);
    if (topic) return topic;
  }
  return undefined;
}

function refusal(): AskResult {
  return {
    answer: `${NOT_FOUND} (This demo only has answers for a few topics: ${TOPIC_HINT}. Run VectorNote locally to ask about your own documents.)`,
    answered: false,
    standalone_question: "",
    cited: false,
    sources: [],
  };
}

/**
 * The canned answer for a question. Follow-ups are understood from the history, and a
 * question about documents that were unticked is refused, like the real search filter does.
 */
export function demoResult(
  question: string,
  history: ChatTurn[] = [],
  selected?: string[],
): AskResult {
  let topic = topicOf(question);
  let reply = topic?.first;
  let standalone = "";

  if (!topic && question.trim().split(/\s+/).length <= 8 && FOLLOW_UP.test(question)) {
    topic = previousTopic(history);
    if (topic) {
      reply = topic.more;
      standalone = topic.standalone;
    }
  }
  if (!topic || !reply) return refusal();

  const allowed = selected && new Set(selected);
  if (allowed && !reply.sources.every((s) => allowed.has(s.source))) return refusal();

  return {
    answer: reply.answer,
    answered: true,
    standalone_question: standalone,
    cited: true,
    sources: reply.sources,
  };
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
