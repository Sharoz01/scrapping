import React, { useState, useEffect, useRef } from "react";
import { open as tauriOpen } from "@tauri-apps/plugin-shell";

const API_BASE = import.meta.env.VITE_API_URL || "https://scrapping-phi.vercel.app";

export default function App() {
  const [activeTab, setActiveTab] = useState("scrape");
  const [leads, setLeads] = useState([]);
  const [allLeads, setAllLeads] = useState([]);
  const [stats, setStats] = useState({ scraped_today: 0, daily_limit: 25, remaining: 25 });
  const [settings, setSettings] = useState({
    daily_limit: 25,
    proposal_language: "English",
    playwright_headless: true,
    use_ai: false,
    ai_provider: "Gemini",
    gemini_api_key: "",
    openai_api_key: "",
    proposal_template: "",
    proposal_template_urdu: "",
  });

  const [theme, setTheme] = useState(() => {
    return localStorage.getItem("theme") || "dark";
  });

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("theme", nextTheme);
  };

  const [isSidebarOpen, setIsSidebarOpen] = useState(window.innerWidth > 768);

  useEffect(() => {
    let lastWidth = window.innerWidth;
    const handleResize = () => {
      const currentWidth = window.innerWidth;
      if (lastWidth > 768 && currentWidth <= 768) {
        setIsSidebarOpen(false);
      } else if (lastWidth <= 768 && currentWidth > 768) {
        setIsSidebarOpen(true);
      }
      lastWidth = currentWidth;
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Scrape states
  const [searchQuery, setSearchQuery] = useState("");
  const [scrapeSource, setScrapeSource] = useState("Google Maps (Playwright)");
  const [scrapeLimit, setScrapeLimit] = useState(10);
  const [headlessMode, setHeadlessMode] = useState(true);
  const [scrapingInProgress, setScrapingInProgress] = useState(false);
  const [logs, setLogs] = useState([]);

  // Queue states
  const [searchKW, setSearchKW] = useState("");
  const [statusFilter, setStatusFilter] = useState("unsent"); // unsent, sent

  // Database search states
  const [dbSearch, setDbSearch] = useState("");

  // Toast notifications
  const [toast, setToast] = useState(null);

  const logsEndRef = useRef(null);

  useEffect(() => {
    fetchStats();
    fetchSettings();
  }, []);

  useEffect(() => {
    fetchLeads();
  }, [statusFilter, searchKW]);

  useEffect(() => {
    if (activeTab === "database") {
      fetchAllLeads();
    }
  }, [activeTab]);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  const [timerStr, setTimerStr] = useState("");

  useEffect(() => {
    if (!stats.limit_timer_end) {
      setTimerStr("");
      return;
    }
    const interval = setInterval(() => {
      const end = new Date(stats.limit_timer_end).getTime();
      const diff = end - new Date().getTime();
      if (diff <= 0) {
        setTimerStr("Resetting...");
        clearInterval(interval);
        fetchStats();
      } else {
        const h = Math.floor(diff / (1000 * 60 * 60));
        const m = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        const s = Math.floor((diff % (1000 * 60)) / 1000);
        setTimerStr(`${h}h ${m}m ${s}s`);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [stats.limit_timer_end]);

  const showToast = (message, type = "info") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/stats`);
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.error("Error fetching stats:", e);
    }
  };

  const fetchSettings = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/settings`);
      if (res.ok) {
        const data = await res.json();
        setSettings({
          daily_limit: parseInt(data.daily_limit || 25),
          proposal_language: data.proposal_language || "English",
          playwright_headless: data.playwright_headless === "True",
          use_ai: data.use_ai === "True",
          ai_provider: data.ai_provider || "Gemini",
          gemini_api_key: data.gemini_api_key || "",
          openai_api_key: data.openai_api_key || "",
          proposal_template: data.proposal_template || "",
          proposal_template_urdu: data.proposal_template_urdu || "",
        });
        setHeadlessMode(data.playwright_headless === "True");
      }
    } catch (e) {
      console.error("Error fetching settings:", e);
    }
  };

  const fetchLeads = async () => {
    try {
      const res = await fetch(
        `${API_BASE}/api/leads?status=${statusFilter}&search=${encodeURIComponent(searchKW)}`
      );
      if (res.ok) {
        const data = await res.json();
        setLeads(data);
      }
    } catch (e) {
      console.error("Error fetching leads:", e);
    }
  };

  const fetchAllLeads = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/all-leads`);
      if (res.ok) {
        const data = await res.json();
        setAllLeads(data);
      }
    } catch (e) {
      console.error("Error fetching all leads:", e);
    }
  };

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (res.ok) {
        showToast("Settings saved successfully!", "success");
        fetchStats();
        fetchLeads();
      } else {
        showToast("Failed to save settings.", "error");
      }
    } catch (err) {
      showToast("Error saving settings: " + err.message, "error");
    }
  };

  const handleUpdateStatus = async (leadId, newStatus) => {
    try {
      const res = await fetch(`${API_BASE}/api/leads/${leadId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        showToast(`Lead marked as ${newStatus.toLowerCase()}!`, "success");
        fetchLeads();
        fetchStats();
      }
    } catch (err) {
      showToast("Error updating status: " + err.message, "error");
    }
  };

  const handleUpdateProposal = async (leadId, newProposal) => {
    try {
      const res = await fetch(`${API_BASE}/api/leads/${leadId}/proposal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposal: newProposal }),
      });
      if (res.ok) {
        // Silent update on blur, optionally show a tiny visual indicator
        // Update local state copy to avoid reloading
        setLeads((prev) =>
          prev.map((l) => (l.id === leadId ? { ...l, proposal: newProposal } : l))
        );
      }
    } catch (err) {
      console.error("Error updating proposal:", err);
    }
  };

  const handleDeleteLead = async (leadId) => {
    if (!window.confirm("Are you sure you want to delete this lead?")) return;
    try {
      const res = await fetch(`${API_BASE}/api/leads/${leadId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        showToast("Lead deleted successfully.", "success");
        fetchLeads();
        fetchStats();
      }
    } catch (err) {
      showToast("Error deleting lead: " + err.message, "error");
    }
  };

  const handleSyncSupabase = async () => {
    showToast("Starting cloud sync to Supabase...", "info");
    try {
      const res = await fetch(`${API_BASE}/api/sync-supabase`, {
        method: "POST",
      });
      const data = await res.json();
      if (res.ok) {
        showToast(`Synced successfully! ${data.synced} of ${data.total} leads pushed.`, "success");
      } else {
        showToast("Sync failed. Check API logs or Supabase credentials in .env.", "error");
      }
    } catch (err) {
      showToast("Error syncing: " + err.message, "error");
    }
  };

  const handleDeleteAll = async () => {
    if (!window.confirm("🔥 DANGER: Are you absolutely sure you want to delete ALL leads in the database? This cannot be undone!")) return;
    try {
      const res = await fetch(`${API_BASE}/api/delete-all`, {
        method: "POST",
      });
      if (res.ok) {
        showToast("All leads deleted.", "success");
        setLeads([]);
        setAllLeads([]);
        fetchStats();
      }
    } catch (err) {
      showToast("Error deleting database: " + err.message, "error");
    }
  };

  const handleStartScrape = () => {
    if (!searchQuery) {
      showToast("Please enter a search query.", "error");
      return;
    }

    setScrapingInProgress(true);
    setLogs(["[SYSTEM] Launching scraper connection..."]);

    const url = `${API_BASE}/api/scrape/stream?query=${encodeURIComponent(searchQuery)}&limit=${scrapeLimit}&headless=${headlessMode}`;
    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      const msg = event.data;
      setLogs((prev) => [...prev, msg]);

      if (msg.startsWith("SUCCESS:") || msg.startsWith("ERROR:")) {
        eventSource.close();
        setScrapingInProgress(false);
        fetchStats();
        fetchLeads();
        if (msg.startsWith("SUCCESS:")) {
          showToast("Scraping completed!", "success");
        } else {
          showToast("Scraper halted with errors.", "error");
        }
      }
    };

    eventSource.onerror = (err) => {
      console.error("SSE Error:", err);
      setLogs((prev) => [...prev, "[SYSTEM ERROR] Lost connection to scraper process."]);
      eventSource.close();
      setScrapingInProgress(false);
      fetchStats();
      fetchLeads();
    };
  };

  // Helper to trigger WhatsApp tabs
  const handleWhatsAppAction = async (lead, type, proposal) => {
    if (!lead.phone) return;

    // Clean phone number
    let cleanPhone = lead.phone.replace(/\D/g, "");
    if (cleanPhone.startsWith("0") && !cleanPhone.startsWith("00")) {
      cleanPhone = "92" + cleanPhone.substring(1);
    }

    const messageText = proposal || lead.proposal;
    const encodedMsg = encodeURIComponent(messageText);
    const webUrl = `https://web.whatsapp.com/send?phone=${cleanPhone}&text=${encodedMsg}`;
    
    // Use wa.me URL format
    const appUrl = `https://wa.me/${cleanPhone}?text=${encodedMsg}`;

    if (type === "web") {
      // Reuse Tab logic
      if (window.whatsappWindow && !window.whatsappWindow.closed) {
        window.whatsappWindow.location.href = webUrl;
        try {
          window.whatsappWindow.focus();
        } catch (e) { }
      } else {
        window.whatsappWindow = window.open(webUrl, "whatsapp_tab");
      }
    } else {
      // Open using Tauri shell open command if running in Tauri, otherwise fallback to anchor link
      const isTauri = typeof window !== "undefined" && (window.__TAURI_INTERNALS__ !== undefined || window.__TAURI__ !== undefined);
      if (isTauri) {
        try {
          await tauriOpen(appUrl);
        } catch (err) {
          console.error("Failed to open WhatsApp via Tauri shell:", err);
          const link = document.createElement("a");
          link.href = appUrl;
          link.target = "_blank";
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        }
      } else {
        const link = document.createElement("a");
        link.href = appUrl;
        link.target = "_blank";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }
    }
  };

  // Export functions
  const handleExport = (format) => {
    // Generate simple spreadsheet table representations
    if (allLeads.length === 0) {
      showToast("No data to export.", "error");
      return;
    }

    if (format === "csv") {
      const headers = ["ID", "Name", "Phone", "Website", "Address", "Category", "Query", "Scraped Date", "Outreach Status"];
      const rows = allLeads.map((l) => [
        l.id,
        `"${(l.name || "").replace(/"/g, '""')}"`,
        l.phone || "",
        l.website || "",
        `"${(l.address || "").replace(/"/g, '""')}"`,
        l.category || "",
        l.query || "",
        l.scraped_date || "",
        l.message_status || "",
      ]);
      const csvContent = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.setAttribute("download", "leads_export.csv");
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } else {
      showToast("Excel exports generated from pandas. Deploying backend Excel format.", "info");
      // Use window open to let backend handle openpyxl stream
      window.open(`${API_BASE}/api/leads`);
    }
  };

  const progressVal = stats.daily_limit > 0 ? (stats.scraped_today / stats.daily_limit) * 100 : 0;
  const isLimitReached = stats.scraped_today >= stats.daily_limit;

  // Filter DB rows
  const filteredAllLeads = allLeads.filter((l) => {
    if (!dbSearch) return true;
    const kw = dbSearch.toLowerCase();
    return (
      (l.name && l.name.toLowerCase().includes(kw)) ||
      (l.phone && l.phone.toLowerCase().includes(kw)) ||
      (l.address && l.address.toLowerCase().includes(kw)) ||
      (l.category && l.category.toLowerCase().includes(kw)) ||
      (l.query && l.query.toLowerCase().includes(kw))
    );
  });

  return (
    <div className={`app-layout ${theme}-theme`}>
      {/* Toast Alert */}
      {toast && (
        <div className={`toast-msg ${toast.type === "error" ? "error" : ""}`}>
          {toast.message}
        </div>
      )}

      {/* Top Navbar */}
      <header className="top-navbar">
        <div className="nav-brand">
          <img src="/logo.png" className="nav-logo" alt="Logo" />
          <div className="nav-title-group">
            <span className="nav-title">Accelerator Lead Gen</span>
            <span className="nav-subtitle">Web & Marketing Lead Gen</span>
          </div>
        </div>

        <div className="nav-metrics-container">
          <button
            className="theme-toggle-btn"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            {theme === "dark" ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5"></circle>
                <line x1="12" y1="1" x2="12" y2="3"></line>
                <line x1="12" y1="21" x2="12" y2="23"></line>
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                <line x1="1" y1="12" x2="3" y2="12"></line>
                <line x1="21" y1="12" x2="23" y2="12"></line>
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
              </svg>
            )}
          </button>
          <div className="nav-metric-badge">
            <span className={`nav-metric-dot ${timerStr ? "limit-reached" : isLimitReached ? "limit-reached" : ""}`}></span>
            {timerStr ? (
              <>
                <span className="nav-metric-label" style={{ color: "var(--danger-color, #ef4444)" }}>Limit Reached - Resets in: </span>
                <span className="nav-metric-value">{timerStr}</span>
              </>
            ) : (
              <>
                <span className="nav-metric-label">Current Usage: </span>
                <span className="nav-metric-value">{stats.scraped_today} / {stats.daily_limit}</span>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Main Layout Container */}
      <div className="main-layout-container">
        {/* Mobile Backdrop overlay */}
        {isSidebarOpen && (
          <div
            className="sidebar-backdrop"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}

        {/* Left Sidebar Navigation */}
        <aside className={`left-sidebar ${isSidebarOpen ? "sidebar-open" : "sidebar-closed"}`}>
          <button
            className={`sidebar-tab-btn ${activeTab === "scrape" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("scrape");
              if (window.innerWidth <= 768) setIsSidebarOpen(false);
            }}
          >
            🔍 Scrape Leads
          </button>
          <button
            className={`sidebar-tab-btn ${activeTab === "queue" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("queue");
              if (window.innerWidth <= 768) setIsSidebarOpen(false);
            }}
          >
            📋 Leads
          </button>
          <button
            className={`sidebar-tab-btn ${activeTab === "database" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("database");
              if (window.innerWidth <= 768) setIsSidebarOpen(false);
            }}
          >
            📱 Outreach
          </button>
          <button
            className={`sidebar-tab-btn ${activeTab === "settings" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("settings");
              if (window.innerWidth <= 768) setIsSidebarOpen(false);
            }}
          >
            ⚙️ Settings & Templates
          </button>
        </aside>

        {/* Floating Sidebar Toggle Arrow Button */}
        <button
          className={`sidebar-arrow-toggle ${isSidebarOpen ? "open" : "closed"}`}
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          aria-label={isSidebarOpen ? "Hide Sidebar" : "Show Sidebar"}
        >
          {isSidebarOpen ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6"></polyline>
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          )}
        </button>

        {/* Right Main Workspace */}
        <div className="main-workspace-container">
          <main className="workspace-main-content">

            {/* Tab Content Panels */}
            {activeTab === "scrape" && (
              <div className="panel-container">
                <h2 className="panel-header">Scrape New Leads</h2>

                <div className="form-grid">
                  <div className="form-group">
                    <label className="form-label">Search Query</label>
                    <input
                      type="text"
                      className="form-input"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="e.g., restaurants in Lahore, dentists in Karachi, gyms in Islamabad"
                      disabled={scrapingInProgress}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Scraping Source</label>
                    <select
                      className="form-select"
                      value={scrapeSource}
                      onChange={(e) => setScrapeSource(e.target.value)}
                      disabled={scrapingInProgress}
                    >
                      <option>Google Maps (Playwright)</option>
                      <option>OpenStreetMap (Overpass API)</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Max results for this run ({scrapeLimit})</label>
                    <input
                      type="range"
                      min="1"
                      max="30"
                      value={scrapeLimit}
                      onChange={(e) => setScrapeLimit(parseInt(e.target.value))}
                      disabled={scrapingInProgress}
                    />
                  </div>

                  <div className="form-group" style={{ display: 'none' }}>
                    <div
                      className={`toggle-wrapper ${headlessMode ? "active" : ""}`}
                      onClick={() => !scrapingInProgress && setHeadlessMode(!headlessMode)}
                    >
                      <div className="toggle-switch"></div>
                      <div>
                        <div className="form-label" style={{ marginBottom: 0 }}>Run browser in background (Headless)</div>
                        <div className="toggle-label-desc">Google Maps browser window will open if disabled.</div>
                      </div>
                    </div>
                  </div>
                </div>

                <button
                  className="btn btn-primary btn-full"
                  onClick={handleStartScrape}
                  disabled={scrapingInProgress || isLimitReached || !!timerStr}
                >
                  {scrapingInProgress ? "⏳ Scraping In Progress..." : timerStr ? `⛔ Restores in ${timerStr}` : "🚀 Run Scrape"}
                </button>

                {/* Terminal Logger Output */}
                <div className="terminal-card">
                  <div className="terminal-header">
                    <div className="terminal-buttons">
                      <span className="terminal-dot red"></span>
                      <span className="terminal-dot yellow"></span>
                      <span className="terminal-dot green"></span>
                    </div>
                    <span className="terminal-title">Scraper System Console Log</span>
                    <div></div>
                  </div>
                  <div className="terminal-body">
                    {logs.length === 0 ? (
                      <p className="terminal-empty">Logs will start displaying here once you run the scrape execution.</p>
                    ) : (
                      logs.map((log, idx) => {
                        const isSaved = log.includes("Saved:") && !log.includes("Skipped:");
                        return (
                          <div
                            key={idx}
                            style={{
                              marginBottom: "4px",
                              fontWeight: isSaved ? "bold" : "normal"
                            }}
                          >
                            {log}
                          </div>
                        );
                      })
                    )}
                    <div ref={logsEndRef} />
                  </div>
                </div>
              </div>
            )}

            {activeTab === "queue" && (
              <div className="panel-container">
                <h2 className="panel-header">Business Leads Queue</h2>

                <div className="queue-filter-bar">
                  <div className="search-input-wrapper">
                    <svg className="search-icon-svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input
                      type="text"
                      className="form-input"
                      value={searchKW}
                      onChange={(e) => setSearchKW(e.target.value)}
                      placeholder="Search by name, address, or category..."
                    />
                  </div>

                  <div className="status-toggle-btn">
                    <button
                      className={`status-toggle-option ${statusFilter === "unsent" ? "active" : ""}`}
                      onClick={() => setStatusFilter("unsent")}
                    >
                      Unsent (New)
                    </button>
                    <button
                      className={`status-toggle-option ${statusFilter === "sent" ? "active" : ""}`}
                      onClick={() => setStatusFilter("sent")}
                    >
                      Sent
                    </button>
                  </div>
                </div>

                <div className="leads-count-banner">
                  Showing <strong>{leads.length}</strong> leads with missing websites.
                </div>

                {leads.length === 0 ? (
                  <div className="info-banner" style={{ textAlign: "center" }}>
                    No leads matching your current filters. Execute a scrape query or change filters!
                  </div>
                ) : (
                  <div className="leads-list">
                    {leads.map((lead) => (
                      <LeadCard
                        key={lead.id}
                        lead={lead}
                        onUpdateStatus={handleUpdateStatus}
                        onUpdateProposal={handleUpdateProposal}
                        onDelete={handleDeleteLead}
                        onWhatsApp={handleWhatsAppAction}
                        filterType={statusFilter}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}

            {activeTab === "database" && (
              <div className="panel-container">
                <h2 className="panel-header">Database Overview</h2>

                <div className="db-actions-row">
                  <button className="btn" onClick={() => handleExport("csv")}>
                    📥 Export to CSV
                  </button>
                  <button className="btn" onClick={handleSyncSupabase}>
                    ☁️ Supabase Cloud Sync
                  </button>
                  <button className="btn btn-danger" onClick={handleDeleteAll}>
                    🗑️ Clear DB
                  </button>
                </div>

                <div className="db-table-card">
                  <div style={{ padding: "16px", borderBottom: "1px solid var(--border-color)" }}>
                    <input
                      type="text"
                      className="form-input"
                      style={{ width: "100%" }}
                      value={dbSearch}
                      onChange={(e) => setDbSearch(e.target.value)}
                      placeholder="Filter database rows below..."
                    />
                  </div>
                  <div className="db-table-wrapper">
                    <table className="db-table">
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Category</th>
                          <th>Phone</th>
                          <th>Website</th>
                          <th>Address</th>
                          <th>Scraped Date</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredAllLeads.length === 0 ? (
                          <tr>
                            <td colSpan="7" style={{ textAlign: "center", color: "var(--text-muted)" }}>
                              No database leads found.
                            </td>
                          </tr>
                        ) : (
                          filteredAllLeads.map((l) => (
                            <tr key={l.id}>
                              <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{l.name}</td>
                              <td>{l.category || "N/A"}</td>
                              <td>{l.phone || "N/A"}</td>
                              <td>{l.website || "None"}</td>
                              <td>{l.address || "N/A"}</td>
                              <td>{l.scraped_date}</td>
                              <td>
                                <span className={`lead-card-badge ${l.message_status === "Sent" ? "badge-sent" : "badge-new"}`}>
                                  {l.message_status}
                                </span>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="danger-zone">
                  <h3 className="danger-title">Danger Maintenance Actions</h3>
                  <p className="danger-desc">
                    Permanently purge the database or trigger cloud synchronization operations. Make sure you backup CSV rows if needed.
                  </p>
                  <button className="btn btn-danger" onClick={handleDeleteAll}>
                    🔥 Delete All SQLite Leads
                  </button>
                </div>
              </div>
            )}

            {activeTab === "settings" && (
              <div className="panel-container">
                <h2 className="panel-header">Configuration Settings</h2>

                <form onSubmit={handleSaveSettings}>
                  <div className="form-grid">
                    <div className="form-group">
                      <label className="form-label">Daily Scrape Limit</label>
                      <input
                        type="number"
                        className="form-input"
                        value={settings.daily_limit}
                        onChange={(e) => setSettings({ ...settings, daily_limit: parseInt(e.target.value) })}
                        min="1"
                        max="150"
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">Proposal Language</label>
                      <select
                        className="form-select"
                        value={settings.proposal_language}
                        onChange={(e) => setSettings({ ...settings, proposal_language: e.target.value })}
                      >
                        <option>English</option>
                        <option>Urdu</option>
                      </select>
                    </div>

                    <div className="form-group" style={{ justifyContent: "center", alignItems: "center" }}>
                      <div
                        className={`toggle-wrapper ${settings.playwright_headless ? "active" : ""}`}
                        onClick={() => setSettings({ ...settings, playwright_headless: !settings.playwright_headless })}
                      >
                        <div className="toggle-switch"></div>
                        <div>
                          <div className="form-label" style={{ marginBottom: 0 }}>Playwright Headless Browser</div>
                          <div className="toggle-label-desc">Run chromium background scraper browser.</div>
                        </div>
                      </div>
                    </div>

                    <div className="form-group" style={{ justifyContent: "center", alignItems: "center" }}>
                      <div
                        className={`toggle-wrapper ${settings.use_ai ? "active" : ""}`}
                        onClick={() => setSettings({ ...settings, use_ai: !settings.use_ai })}
                      >
                        <div className="toggle-switch"></div>
                        <div>
                          <div className="form-label" style={{ marginBottom: 0 }}>Enable AI-Generated Proposals</div>
                          <div className="toggle-label-desc">Use Google Gemini or OpenAI instead of fallback templates.</div>
                        </div>
                      </div>
                    </div>

                    {settings.use_ai && (
                      <>
                        <div className="form-group">
                          <label className="form-label">AI Provider</label>
                          <select
                            className="form-select"
                            value={settings.ai_provider}
                            onChange={(e) => setSettings({ ...settings, ai_provider: e.target.value })}
                          >
                            <option>Gemini</option>
                            <option>OpenAI</option>
                          </select>
                        </div>

                        <div className="form-group">
                          <label className="form-label">
                            {settings.ai_provider === "Gemini" ? "Google Gemini API Key" : "OpenAI API Key"}
                          </label>
                          <input
                            type="password"
                            className="form-input"
                            placeholder="Enter API key token..."
                            value={settings.ai_provider === "Gemini" ? settings.gemini_api_key : settings.openai_api_key}
                            onChange={(e) => {
                              if (settings.ai_provider === "Gemini") {
                                setSettings({ ...settings, gemini_api_key: e.target.value });
                              } else {
                                setSettings({ ...settings, openai_api_key: e.target.value });
                              }
                            }}
                          />
                        </div>
                      </>
                    )}

                    <div className="form-group full-width">
                      <label className="form-label">Cold Proposal English Template (Fallback)</label>
                      <textarea
                        className="lead-proposal-textarea"
                        value={settings.proposal_template}
                        onChange={(e) => setSettings({ ...settings, proposal_template: e.target.value })}
                        style={{ minHeight: "100px" }}
                      />
                      <div style={{ fontSize: "12px", color: "gray", marginTop: "4px" }}>
                        Hints: You can use variables like {"{name}"} for business name, {"{location}"} for address, and {"{category}"} for business type.
                      </div>
                    </div>
                  </div>

                  <button type="submit" className="btn btn-primary btn-full">
                    💾 Save All Settings
                  </button>
                </form>
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}

function LeadCard({ lead, onUpdateStatus, onUpdateProposal, onDelete, onWhatsApp, filterType }) {
  const [localProposal, setLocalProposal] = useState(lead.proposal || "");

  // Update local state when prop changes
  useEffect(() => {
    setLocalProposal(lead.proposal || "");
  }, [lead.proposal]);

  const handleBlur = () => {
    if (localProposal !== lead.proposal) {
      onUpdateProposal(lead.id, localProposal);
    }
  };

  return (
    <div className="lead-card">
      <div className="lead-card-header">
        <div>
          <h3 className="lead-name">{lead.name}</h3>
          <div className="lead-meta-info">
            <span className="meta-item">📂 {lead.category || "General"}</span>
            <span className="meta-item">📍 {lead.address || "No Address"}</span>
            <span className="meta-item">📞 {lead.phone || "No Phone"}</span>
            <span className="meta-item">⏱️ {lead.scraped_date}</span>
          </div>
        </div>
        <span className={`lead-card-badge ${lead.message_status === "Sent" ? "badge-sent" : "badge-new"}`}>
          {lead.message_status}
        </span>
      </div>

      <div className="lead-card-body-row">
        <div>
          <textarea
            className="lead-proposal-textarea"
            value={localProposal}
            onChange={(e) => setLocalProposal(e.target.value)}
            onBlur={handleBlur}
            placeholder="No proposal text."
          />
        </div>
        <div className="lead-actions-column">
          {lead.phone ? (
            <>
              <button
                className="btn whatsapp-btn-web"
                onClick={() => onWhatsApp(lead, "web", localProposal)}
              >
                💬 WhatsApp Web
              </button>
              <button
                className="btn whatsapp-btn-desktop"
                onClick={() => onWhatsApp(lead, "app", localProposal)}
              >
                📱 WhatsApp App
              </button>
            </>
          ) : (
            <div className="info-banner" style={{ padding: "8px 12px", fontSize: "0.75rem", textAlign: "center", marginBottom: 0 }}>
              ⚠️ Missing Phone Number
            </div>
          )}

          {filterType === "unsent" ? (
            <button
              className="btn"
              onClick={() => onUpdateStatus(lead.id, "Sent")}
            >
              ✅ Mark as Sent
            </button>
          ) : (
            <>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textAlign: "center" }}>
                Sent: {lead.sent_timestamp}
              </div>
              <button
                className="btn"
                onClick={() => onUpdateStatus(lead.id, "New")}
              >
                ↩️ Reset to New
              </button>
            </>
          )}

          <button
            className="btn btn-danger"
            onClick={() => onDelete(lead.id)}
            style={{ marginTop: "auto" }}
          >
            🗑️ Delete Lead
          </button>
        </div>
      </div>
    </div>
  );
}
