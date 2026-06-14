// PaperFeed — client-side React app

const { useState, useEffect, useCallback } = React;

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatDate(isoStr, locale = "en-US") {
  if (!isoStr) return "No date";
  try {
    return new Date(isoStr).toLocaleDateString(locale, {
      year: "numeric", month: "long", day: "numeric",
    });
  } catch {
    return isoStr;
  }
}

function groupByMonth(papers) {
  const groups = {};
  for (const p of papers) {
    const dateStr = p.publication_date || (p.year ? `${p.year}-01-01` : null);
    let key = "Unknown date";
    if (dateStr) {
      try {
        const d = new Date(dateStr);
        key = d.toLocaleDateString("en-US", { year: "numeric", month: "long" });
      } catch {}
    } else if (p.year) {
      key = `${p.year}`;
    }
    if (!groups[key]) groups[key] = [];
    groups[key].push(p);
  }
  return groups;
}

function sourceBadge(src) {
  const labels = { arxiv: "arXiv", semantic_scholar: "Semantic Scholar", openalex: "OpenAlex" };
  return (
    <span key={src} className={`badge-${src} mr-1`}>
      {labels[src] || src}
    </span>
  );
}

// ─── localStorage helpers ────────────────────────────────────────────────────

function loadStarred() {
  try { return new Set(JSON.parse(localStorage.getItem("paperfeed_starred") || "[]")); }
  catch { return new Set(); }
}

function saveStarred(s) {
  localStorage.setItem("paperfeed_starred", JSON.stringify([...s]));
}

function loadDeleted() {
  try { return new Set(JSON.parse(localStorage.getItem("paperfeed_deleted") || "[]")); }
  catch { return new Set(); }
}

function saveDeleted(s) {
  localStorage.setItem("paperfeed_deleted", JSON.stringify([...s]));
}

// ─── SkeletonCard ────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 mb-3 space-y-3">
      <div className="skeleton h-5 w-3/4"></div>
      <div className="skeleton h-3 w-1/4"></div>
      <div className="skeleton h-3 w-full"></div>
      <div className="skeleton h-3 w-5/6"></div>
      <div className="skeleton h-2 w-full mt-2"></div>
    </div>
  );
}

// ─── PaperCard ───────────────────────────────────────────────────────────────

function PaperCard({ paper, isReject, starred, onStar }) {
  const [expanded, setExpanded] = useState(false);
  const abstract = paper.abstract || "";
  const shortAbstract = abstract.slice(0, 220);
  const showToggle = abstract.length > 220;
  const authors = paper.authors || [];
  const displayAuthors =
    authors.length > 3
      ? authors.slice(0, 3).join(", ") + ` +${authors.length - 3} more`
      : authors.join(", ");
  const sourceHits = paper.source_hits || [paper.source].filter(Boolean);
  const isMulti = sourceHits.length > 1;
  const score = paper.score || 0;
  const pid = paper.paper_id || paper.candidate_id;

  const borderCls = starred
    ? "border-yellow-400 dark:border-yellow-500"
    : "border-gray-200 dark:border-gray-700";

  return (
    <div className={`border ${borderCls} rounded-lg p-4 mb-3 bg-white dark:bg-gray-800 hover:shadow-md transition-shadow`}>
      {/* Title row + star button */}
      <div className="flex items-start gap-2 mb-1">
        <a
          href={paper.url || "#"}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 font-bold text-blue-700 dark:text-blue-400 hover:underline"
          style={{ fontSize: "17px", lineHeight: "1.4" }}
        >
          {paper.title || "(No title)"}
        </a>
        {!isReject && (
          <button
            onClick={() => onStar(pid)}
            title={starred ? "Unstar" : "Star this paper"}
            className={`flex-shrink-0 mt-0.5 text-lg transition-colors
              ${starred ? "text-yellow-400" : "text-gray-300 dark:text-gray-600 hover:text-yellow-400"}`}
          >★</button>
        )}
      </div>

      {/* Badges */}
      <div className="flex flex-wrap gap-1 items-center mb-2">
        {sourceHits.map(sourceBadge)}
        {isMulti && <span className="badge-multi">Multi-source ✓</span>}
        {isReject && paper.reject_reason && (
          <span className={`badge-${paper.reject_reason}`}>
            {paper.reject_reason === "below_threshold" ? "Below threshold"
              : paper.reject_reason === "outside_timeline" ? "Out of range"
              : "Missing metadata"}
          </span>
        )}
      </div>

      {/* Date + authors */}
      <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">
        {formatDate(paper.publication_date || (paper.year ? `${paper.year}-06-01` : null))}
        {displayAuthors && <span className="ml-2">{displayAuthors}</span>}
      </div>

      {/* Abstract */}
      {abstract && (
        <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
          {expanded ? abstract : shortAbstract}
          {showToggle && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="ml-1 text-blue-500 hover:underline text-xs"
            >
              {expanded ? "Show less" : "Show more"}
            </button>
          )}
        </p>
      )}

      {/* Similarity bar */}
      <div className="flex items-center gap-2 mt-2">
        <div className="flex-1 h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-1.5 bg-indigo-500 rounded-full similarity-bar"
            style={{ width: `${Math.min(score * 100, 100)}%` }}
          ></div>
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
          {(score * 100).toFixed(0)}% match
        </span>
      </div>

      {/* paper_id chip */}
      <div className="mt-2">
        <span className="text-xs bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 px-2 py-0.5 rounded-full font-mono">
          {pid || "no id"}
        </span>
      </div>
    </div>
  );
}

// ─── MonthGroup ──────────────────────────────────────────────────────────────

function MonthGroup({ month, papers, starred, onStar }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="mb-6">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-base font-semibold text-gray-700 dark:text-gray-300 mb-3 hover:text-indigo-600 dark:hover:text-indigo-400"
      >
        <span>{open ? "▼" : "▶"}</span>
        <span>{month} ({papers.length})</span>
      </button>
      {open && papers.map((p, i) => {
        const pid = p.paper_id || p.candidate_id;
        return (
          <PaperCard
            key={pid || i}
            paper={p}
            isReject={false}
            starred={starred.has(pid)}
            onStar={onStar}
          />
        );
      })}
    </div>
  );
}

// ─── StatusCard ──────────────────────────────────────────────────────────────

function StatusCard({ status, papersCount }) {
  const statusMap = {
    idle:          { label: "Idle",            cls: "text-green-600 dark:text-green-400" },
    crawling:      { label: "Fetching...",      cls: "text-blue-600 dark:text-blue-400 status-pulse" },
    deduplicating: { label: "Deduplicating...", cls: "text-blue-500 dark:text-blue-300 status-pulse" },
    scoring:       { label: "Scoring...",       cls: "text-yellow-600 dark:text-yellow-400 status-pulse" },
    filtering:     { label: "Filtering...",     cls: "text-yellow-500 dark:text-yellow-300 status-pulse" },
    publishing:    { label: "Publishing...",    cls: "text-orange-600 dark:text-orange-400 status-pulse" },
  };
  const { label, cls } = statusMap[status?.status] || { label: status?.status || "Unknown", cls: "text-gray-500" };

  return (
    <div className="mb-4 p-3 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800">
      <div className={`font-semibold text-sm ${cls}`}>{label}</div>
      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
        Last run: {status?.last_run ? formatDate(status.last_run) : "Never"}
      </div>
      <div className="text-xs text-gray-500 dark:text-gray-400">
        {papersCount} papers collected
      </div>
    </div>
  );
}

// ─── HistoryPage ─────────────────────────────────────────────────────────────

function HistoryPage({ history, papers, starred, onStar, deleted, onDelete }) {
  const paperById = {};
  for (const p of papers) {
    const pid = p.paper_id || p.candidate_id;
    if (pid) paperById[pid] = p;
  }

  const runs = [...history].reverse();

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">Run History</h1>

      {runs.length === 0 && (
        <p className="text-gray-400 dark:text-gray-600">No runs yet.</p>
      )}

      {runs.map((run, i) => {
        const paperIds = run.paper_ids || [];
        const runPapers = paperIds.map(id => paperById[id]).filter(Boolean);
        const src = run.source_counts || {};

        return (
          <div key={run.run_id || i} className="mb-8 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
            {/* Run header */}
            <div className="bg-gray-50 dark:bg-gray-800 px-5 py-4 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <span className="text-base font-bold text-gray-900 dark:text-white">
                    {formatDate(run.timestamp)}
                  </span>
                  <span className="ml-3 text-sm text-gray-500 dark:text-gray-400">
                    {run.topic}
                  </span>
                </div>
                <span className="text-sm font-semibold text-indigo-600 dark:text-indigo-400">
                  +{run.new_count ?? paperIds.length} new papers
                </span>
              </div>

              {/* Stats row */}
              <div className="flex flex-wrap gap-3 mt-3 text-xs text-gray-500 dark:text-gray-400">
                <span>Raw: {run.raw_count ?? "—"}</span>
                <span>After dedup: {run.dedup_count ?? "—"}</span>
                <span>Accepted: {run.accepted_count ?? "—"}</span>
                <span>Rejected: {run.rejected_count ?? "—"}</span>
              </div>

              {/* Source counts */}
              <div className="flex flex-wrap gap-2 mt-2">
                {src.arxiv != null && <span className="badge-arxiv">arXiv: {src.arxiv}</span>}
                {src.semantic_scholar != null && <span className="badge-semantic_scholar">S2: {src.semantic_scholar}</span>}
                {src.openalex != null && <span className="badge-openalex">OpenAlex: {src.openalex}</span>}
              </div>
            </div>

            {/* Paper list */}
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {runPapers.length === 0 && (
                <div className="px-5 py-3 text-sm text-gray-400 dark:text-gray-600 italic">
                  No paper details available for this run.
                </div>
              )}
              {runPapers.map((p, j) => {
                const pid = p.paper_id || p.candidate_id;
                const sourceHits = p.source_hits || [p.source].filter(Boolean);
                const isDeleted = deleted.has(pid);
                const isStarred = starred.has(pid);

                return (
                  <div
                    key={pid || j}
                    className={`px-5 py-3 flex items-start gap-3 transition-colors
                      ${isDeleted ? "opacity-40 bg-red-50 dark:bg-red-900/10" : "hover:bg-gray-50 dark:hover:bg-gray-800"}`}
                  >
                    <span className="text-gray-400 dark:text-gray-600 text-xs mt-1 w-5 flex-shrink-0 text-right">
                      {j + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <a
                        href={p.url || "#"}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`text-sm font-medium hover:underline block truncate
                          ${isDeleted ? "line-through text-gray-400 dark:text-gray-500" : "text-blue-700 dark:text-blue-400"}`}
                      >
                        {p.title || "(No title)"}
                      </a>
                      <div className="flex flex-wrap gap-1 mt-1 items-center">
                        {sourceHits.map(sourceBadge)}
                        <span className="text-xs text-gray-400 dark:text-gray-500">
                          {(p.score * 100).toFixed(0)}% match
                        </span>
                      </div>
                    </div>

                    {/* Star + Delete buttons */}
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <button
                        onClick={() => onStar(pid)}
                        title={isStarred ? "Unstar" : "Star"}
                        className={`text-lg transition-colors
                          ${isStarred ? "text-yellow-400" : "text-gray-300 dark:text-gray-600 hover:text-yellow-400"}`}
                      >★</button>
                      <button
                        onClick={() => onDelete(pid)}
                        title={isDeleted ? "Restore" : "Delete from list"}
                        className={`w-7 h-7 rounded-full flex items-center justify-center text-sm border transition-colors
                          ${isDeleted
                            ? "bg-red-500 border-red-500 text-white"
                            : "border-gray-300 dark:border-gray-600 text-gray-400 hover:border-red-400 hover:text-red-400"}`}
                      >✕</button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── PapersPage ──────────────────────────────────────────────────────────────

function PapersPage({ papers, rejects, surveyConfig, starred, onStar, deleted }) {
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("score");
  const [minScore, setMinScore] = useState(0.05);
  const [sources, setSources] = useState({ arxiv: true, semantic_scholar: true, openalex: true });
  const [yearFrom, setYearFrom] = useState(2023);
  const [yearTo, setYearTo] = useState(2026);
  const [showRejects, setShowRejects] = useState(false);
  const [starFilter, setStarFilter] = useState("all"); // all | starred | unread

  useEffect(() => {
    if (surveyConfig) {
      setYearFrom(surveyConfig.timeline_from_year ?? 2023);
      setYearTo(surveyConfig.timeline_to_year ?? 2026);
    }
  }, [surveyConfig]);

  const filtered = papers
    .filter(p => {
      const pid = p.paper_id || p.candidate_id;
      if (deleted.has(pid)) return false; // hide deleted papers
      if (starFilter === "starred" && !starred.has(pid)) return false;
      if (starFilter === "unread" && starred.has(pid)) return false;

      const src = p.source_hits || [p.source];
      const srcMatch = src.some(s => sources[s]);
      const scoreMatch = (p.score || 0) >= minScore;
      const yr = p.year || 0;
      const yearMatch = yr >= yearFrom && yr <= yearTo;
      const q = search.toLowerCase();
      const textMatch = !q || (p.title || "").toLowerCase().includes(q) || (p.abstract || "").toLowerCase().includes(q);
      return srcMatch && scoreMatch && yearMatch && textMatch;
    })
    .sort((a, b) => {
      if (sortBy === "score") return (b.score || 0) - (a.score || 0);
      if (sortBy === "date") {
        const da = new Date(a.publication_date || `${a.year}-01-01` || 0);
        const db = new Date(b.publication_date || `${b.year}-01-01` || 0);
        return db - da;
      }
      if (sortBy === "sources") return (b.source_hits?.length || 0) - (a.source_hits?.length || 0);
      return 0;
    });

  const grouped = groupByMonth(filtered);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 h-screen overflow-y-auto p-4">

        <div className="space-y-5">
          {/* Star filter */}
          <div>
            <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">Filter</p>
            {[["all","All"], ["starred","★ Starred"], ["unread","Unread"]].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setStarFilter(val)}
                className={`block w-full text-left text-sm px-2 py-1 rounded mb-0.5 transition-colors
                  ${starFilter === val
                    ? "bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300 font-semibold"
                    : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"}`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Score slider */}
          <div>
            <label className="text-xs font-semibold text-gray-700 dark:text-gray-300 block mb-1">
              Min similarity: {(minScore * 100).toFixed(0)}%
            </label>
            <input
              type="range" min="0.05" max="1.0" step="0.05"
              value={minScore}
              onChange={e => setMinScore(parseFloat(e.target.value))}
              className="w-full accent-indigo-600"
            />
          </div>

          {/* Sources */}
          <div>
            <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">Sources</p>
            {[["arxiv","arXiv"], ["semantic_scholar","Semantic Scholar"], ["openalex","OpenAlex"]].map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer mb-0.5">
                <input
                  type="checkbox"
                  checked={sources[k]}
                  onChange={e => setSources(prev => ({ ...prev, [k]: e.target.checked }))}
                  className="accent-indigo-600"
                />
                {label}
              </label>
            ))}
          </div>

          {/* Year range */}
          <div>
            <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">Year range</p>
            <div className="flex items-center gap-2">
              <input
                type="number" value={yearFrom} min="2000" max="2030"
                onChange={e => setYearFrom(parseInt(e.target.value))}
                className="w-20 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm dark:bg-gray-800 dark:text-white"
              />
              <span className="text-gray-500">~</span>
              <input
                type="number" value={yearTo} min="2000" max="2030"
                onChange={e => setYearTo(parseInt(e.target.value))}
                className="w-20 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-sm dark:bg-gray-800 dark:text-white"
              />
            </div>
          </div>

          {/* Rejects toggle */}
          <button
            onClick={() => setShowRejects(!showRejects)}
            className="w-full text-left text-sm text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            {showRejects ? "▼" : "▶"} Show rejected ({rejects.length})
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto p-6 bg-gray-50 dark:bg-gray-950">
        {/* Top bar */}
        <div className="flex items-center gap-3 mb-6 flex-wrap">
          <input
            type="text"
            placeholder="Search title or abstract..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="flex-1 min-w-48 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm dark:bg-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
            className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm dark:bg-gray-800 dark:text-white focus:outline-none"
          >
            <option value="score">By similarity</option>
            <option value="date">Latest first</option>
            <option value="sources">By sources</option>
          </select>
          <span className="text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">
            {filtered.length} papers shown
          </span>
        </div>

        {/* Empty state */}
        {papers.length === 0 && !showRejects && (
          <div className="text-center mt-24 text-gray-400 dark:text-gray-600">
            <p className="text-2xl mb-3">📭</p>
            <p className="text-lg">No papers yet.</p>
            <code className="text-sm bg-gray-100 dark:bg-gray-800 px-3 py-1 rounded mt-2 inline-block">
              Run python -m app.run to fetch papers
            </code>
          </div>
        )}

        {/* Papers grouped by month */}
        {!showRejects && Object.entries(grouped).map(([month, monthPapers]) => (
          <MonthGroup key={month} month={month} papers={monthPapers} starred={starred} onStar={onStar} />
        ))}

        {/* Reject panel */}
        {showRejects && (
          <div>
            <h2 className="text-lg font-bold text-gray-700 dark:text-gray-300 mb-4">
              Rejected papers ({rejects.length})
            </h2>
            {rejects.length === 0 && (
              <p className="text-gray-400 dark:text-gray-600 text-sm">No rejected papers</p>
            )}
            {rejects.map((p, i) => (
              <PaperCard key={p.paper_id || p.candidate_id || i} paper={p} isReject={true} status={null} onStatus={() => {}} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

// ─── App ─────────────────────────────────────────────────────────────────────

function App() {
  const [papers, setPapers] = useState([]);
  const [rejects, setRejects] = useState([]);
  const [history, setHistory] = useState([]);
  const [status, setStatus] = useState(null);
  const [surveyConfig, setSurveyConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem("darkMode") === "true");
  const [tab, setTab] = useState("papers");
  const [starred, setStarred] = useState(() => loadStarred());
  const [deleted, setDeleted] = useState(() => loadDeleted());

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
    localStorage.setItem("darkMode", darkMode);
  }, [darkMode]);

  useEffect(() => {
    async function loadAll() {
      const [p, h, s, cfg, rj] = await Promise.all([
        fetch("./data/papers.json").then(r => r.ok ? r.json() : []).catch(() => []),
        fetch("./data/run_history.json").then(r => r.ok ? r.json() : []).catch(() => []),
        fetch("./data/system_status.json").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("./data/survey_config.json").then(r => r.ok ? r.json() : null).catch(() => null),
        fetch("./data/rejects.json").then(r => r.ok ? r.json() : []).catch(() => []),
      ]);
      setPapers(p); setHistory(h); setStatus(s); setSurveyConfig(cfg); setRejects(rj);
      setLoading(false);
    }
    loadAll();
  }, []);

  // Poll status every 3s
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const s = await fetch("./data/system_status.json").then(r => r.ok ? r.json() : null);
        if (s) setStatus(s);
      } catch {}
    }, 3000);
    return () => clearInterval(id);
  }, []);

  const handleStar = useCallback((pid) => {
    setStarred(prev => {
      const next = new Set(prev);
      if (next.has(pid)) next.delete(pid);
      else next.add(pid);
      saveStarred(next);
      return next;
    });
  }, []);

  const handleDelete = useCallback((pid) => {
    setDeleted(prev => {
      const next = new Set(prev);
      if (next.has(pid)) next.delete(pid); // restore
      else next.add(pid);
      saveDeleted(next);
      return next;
    });
  }, []);

  return (
    <div className={`flex flex-col h-screen ${darkMode ? "dark" : ""}`}>
      {/* ─── Top Nav ─── */}
      <header className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-5 py-3 flex items-center gap-6">
        <div className="flex items-center gap-3 mr-4">
          <span className="text-lg font-bold text-gray-900 dark:text-white">PaperFeed</span>
          <span className="text-sm text-gray-500 dark:text-gray-400">{surveyConfig?.topic_overview || ""}</span>
        </div>

        {/* Tabs */}
        <nav className="flex gap-1">
          {[["papers", "Papers"], ["history", "History"]].map(([val, label]) => (
            <button
              key={val}
              onClick={() => setTab(val)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors
                ${tab === val
                  ? "bg-indigo-600 text-white"
                  : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"}`}
            >
              {label}
              {val === "history" && history.length > 0 && (
                <span className="ml-1.5 text-xs bg-white/20 dark:bg-white/10 px-1.5 py-0.5 rounded-full">
                  {history.length}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* Status + stats */}
        <div className="ml-auto flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
          {status?.status && status.status !== "idle" && (
            <span className="text-blue-500 status-pulse font-medium capitalize">{status.status}...</span>
          )}
          <span>{papers.length} papers</span>
          {starred.size > 0 && <span className="text-yellow-500">★ {starred.size}</span>}
          {deleted.size > 0 && <span className="text-red-400">✕ {deleted.size} hidden</span>}
          <button
            onClick={() => setDarkMode(!darkMode)}
            className="border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 dark:text-white"
          >
            {darkMode ? "☀️ Light" : "🌙 Dark"}
          </button>
        </div>
      </header>

      {/* ─── Body ─── */}
      <div className="flex-1 overflow-hidden bg-gray-50 dark:bg-gray-950">
        {loading ? (
          <div className="p-6"><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>
        ) : tab === "papers" ? (
          <PapersPage
            papers={papers}
            rejects={rejects}
            surveyConfig={surveyConfig}
            starred={starred}
            onStar={handleStar}
            deleted={deleted}
          />
        ) : (
          <div className="h-full overflow-y-auto">
            <HistoryPage
              history={history}
              papers={papers}
              starred={starred}
              onStar={handleStar}
              deleted={deleted}
              onDelete={handleDelete}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Mount ───────────────────────────────────────────────────────────────────

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
