import React, { useState, useEffect, useRef } from "react";
import { open } from "@tauri-apps/plugin-shell";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function App() {
  // Auth State
  const [token, setToken] = useState(() => localStorage.getItem("auth_token") || "");
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const saved = localStorage.getItem("current_user");
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [loginUsername, setLoginUsername] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [isSubmittingLogin, setIsSubmittingLogin] = useState(false);

  // Layout & Theme States
  const [activeTab, setActiveTab] = useState("scrape");
  const [leads, setLeads] = useState([]);
  const [allLeads, setAllLeads] = useState([]);
  const [stats, setStats] = useState({ scraped_today: 0, daily_limit: 50, remaining: 50 });
  const [settings, setSettings] = useState({
    daily_limit: 50,
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
  const [scrapeLimit, setScrapeLimit] = useState("50");
  const parsedLimit = Math.max(1, Math.min(5000, parseInt(scrapeLimit) || 1));
  const [scrapeSource, setScrapeSource] = useState("auto");
  const [scrapingInProgress, setScrapingInProgress] = useState(false);
  const [logs, setLogs] = useState([]);
  const [scrapedLeads, setScrapedLeads] = useState([]);

  // Queue states
  const [searchKW, setSearchKW] = useState("");
  const [statusFilter, setStatusFilter] = useState("unsent"); // unsent, sent
  const [filterType, setFilterType] = useState("all_target"); // all_target, no_website, unresponsive, all

  // Database search states & pagination
  const [dbSearch, setDbSearch] = useState("");
  const [dbPage, setDbPage] = useState(1);
  const dbPageSize = 25;

  const formatDisplayDate = (dateStr) => {
    if (!dateStr) return <span style={{ color: "var(--text-muted)" }}>-</span>;
    try {
      const clean = dateStr.replace(" ", "T");
      const d = new Date(clean);
      if (isNaN(d.getTime())) return <span>{dateStr.split("T")[0] || dateStr}</span>;
      return (
        <span>
          {d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
        </span>
      );
    } catch {
      return <span>{dateStr}</span>;
    }
  };

  // Admin Team & Analytics States
  const [userAnalytics, setUserAnalytics] = useState({ users: [], totals: {} });
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newFullName, setNewFullName] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [isCreatingUser, setIsCreatingUser] = useState(false);

  // Toast notifications
  const [toast, setToast] = useState(null);
  const logsEndRef = useRef(null);

  const [loadingAllLeads, setLoadingAllLeads] = useState(false);

  // Helper authenticated fetch
  const authFetch = async (url, options = {}) => {
    const headers = {
      ...(options.headers || {}),
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
      handleLogout();
    }
    return res;
  };

  // Verify auth session on load
  useEffect(() => {
    if (token) {
      authFetch(`${API_BASE}/api/auth/me`)
        .then((res) => {
          if (res.ok) return res.json();
          throw new Error("Session expired");
        })
        .then((data) => {
          if (data && data.user) {
            setCurrentUser(data.user);
            localStorage.setItem("current_user", JSON.stringify(data.user));
          }
        })
        .catch(() => {
          handleLogout();
        });
    }
  }, [token]);

  // Load data when authenticated
  useEffect(() => {
    if (currentUser) {
      fetchStats();
      fetchSettings();
      fetchLeads();
      if (currentUser.role === "admin") {
        fetchUserAnalytics();
        fetchAllLeads();
      }
    }
  }, [currentUser]);

  useEffect(() => {
    if (currentUser) {
      fetchLeads();
    }
  }, [statusFilter, searchKW, filterType, activeTab]);

  useEffect(() => {
    if (currentUser && activeTab === "database") {
      fetchAllLeads();
    } else if (currentUser && activeTab === "team" && currentUser.role === "admin") {
      fetchUserAnalytics();
    }
  }, [activeTab]);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);


  // Timer calculation
  const [timerStr, setTimerStr] = useState("");
  useEffect(() => {
    if (!stats.limit_timer_end) {
      setTimerStr("");
      return;
    }
    const updateTimer = () => {
      const end = new Date(stats.limit_timer_end).getTime();
      const diff = end - new Date().getTime();
      if (isNaN(end) || diff <= 0) {
        setTimerStr("");
        fetchStats();
      } else {
        const h = Math.floor(diff / (1000 * 60 * 60));
        const m = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        const s = Math.floor((diff % (1000 * 60)) / 1000);
        setTimerStr(`${h}h ${m}m ${s}s`);
      }
    };
    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [stats.limit_timer_end]);

  const showToast = (message, type = "info") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  // Auth Handlers
  const handleLogin = async (e) => {
    e.preventDefault();
    if (!loginUsername.trim() || !loginPassword.trim()) {
      setLoginError("Please enter both username and password");
      return;
    }
    setLoginError("");
    setIsSubmittingLogin(true);

    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: loginUsername.trim(),
          password: loginPassword.trim()
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Login failed");
      }

      setToken(data.token);
      setCurrentUser(data.user);
      localStorage.setItem("auth_token", data.token);
      localStorage.setItem("current_user", JSON.stringify(data.user));
      setActiveTab("scrape");
      showToast(`Welcome back, ${data.user.full_name || data.user.username}!`, "success");
    } catch (err) {
      setLoginError(err.message);
    } finally {
      setIsSubmittingLogin(false);
    }
  };

  const handleLogout = () => {
    setToken("");
    setCurrentUser(null);
    localStorage.removeItem("auth_token");
    localStorage.removeItem("current_user");
    setActiveTab("scrape");
    showToast("You have been logged out.", "info");
  };

  // User Management Handlers (Admin)
  const fetchUserAnalytics = async () => {
    try {
      const res = await authFetch(`${API_BASE}/api/admin/user-analytics`);
      if (res.ok) {
        const data = await res.json();
        setUserAnalytics(data.analytics || { users: [], totals: {} });
      }
    } catch (e) {
      console.error("Error fetching analytics:", e);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    if (!newUsername.trim() || !newPassword.trim()) {
      showToast("Username and password are required.", "error");
      return;
    }
    setIsCreatingUser(true);
    try {
      const res = await authFetch(`${API_BASE}/api/admin/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: newUsername.trim(),
          password: newPassword.trim(),
          full_name: newFullName.trim(),
          role: newRole
        })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(`User '${newUsername}' created successfully!`, "success");
        setNewUsername("");
        setNewPassword("");
        setNewFullName("");
        setNewRole("user");
        fetchUserAnalytics();
      } else {
        showToast(data.detail || "Failed to create user", "error");
      }
    } catch (err) {
      showToast("Error creating user: " + err.message, "error");
    } finally {
      setIsCreatingUser(false);
    }
  };

  const handleToggleUserStatus = async (userId, currentActive) => {
    try {
      const res = await authFetch(`${API_BASE}/api/admin/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !currentActive })
      });
      if (res.ok) {
        showToast(`User status updated.`, "success");
        fetchUserAnalytics();
      } else {
        const err = await res.json();
        showToast(err.detail || "Failed to update status", "error");
      }
    } catch (err) {
      showToast("Error updating user status: " + err.message, "error");
    }
  };

  const handleResetUserPassword = async (userId, username) => {
    const newPass = window.prompt(`Enter new password for user '${username}':`);
    if (!newPass) return;
    try {
      const res = await authFetch(`${API_BASE}/api/admin/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: newPass })
      });
      if (res.ok) {
        showToast(`Password for '${username}' updated successfully!`, "success");
      } else {
        const err = await res.json();
        showToast(err.detail || "Failed to reset password", "error");
      }
    } catch (err) {
      showToast("Error resetting password: " + err.message, "error");
    }
  };

  const handleDeleteUser = async (userId, username) => {
    if (!window.confirm(`Are you sure you want to delete user '${username}'?`)) return;
    try {
      const res = await authFetch(`${API_BASE}/api/admin/users/${userId}`, {
        method: "DELETE"
      });
      if (res.ok) {
        showToast(`User '${username}' deleted.`, "success");
        fetchUserAnalytics();
      } else {
        const err = await res.json();
        showToast(err.detail || "Failed to delete user", "error");
      }
    } catch (err) {
      showToast("Error deleting user: " + err.message, "error");
    }
  };

  // API Data Handlers
  const fetchStats = async () => {
    try {
      const res = await authFetch(`${API_BASE}/api/stats`);
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
      const res = await authFetch(`${API_BASE}/api/settings`);
      if (res.ok) {
        const data = await res.json();
        setSettings({
          daily_limit: parseInt(data.daily_limit || 50),
          proposal_language: data.proposal_language || "English",
          playwright_headless: data.playwright_headless === "True",
          use_ai: data.use_ai === "True",
          ai_provider: data.ai_provider || "Gemini",
          gemini_api_key: data.gemini_api_key || "",
          openai_api_key: data.openai_api_key || "",
          proposal_template: data.proposal_template || "",
          proposal_template_urdu: data.proposal_template_urdu || "",
        });
      }
    } catch (e) {
      console.error("Error fetching settings:", e);
    }
  };

  const fetchLeads = async () => {
    try {
      const res = await authFetch(
        `${API_BASE}/api/leads?status=${statusFilter}&search=${encodeURIComponent(searchKW)}&filter_type=${filterType}`
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
    setLoadingAllLeads(true);
    try {
      const res = await authFetch(`${API_BASE}/api/all-leads`);
      if (res.ok) {
        const data = await res.json();
        setAllLeads(data);
      }
    } catch (e) {
      console.error("Error fetching all leads:", e);
    } finally {
      setLoadingAllLeads(false);
    }
  };

  const handleResetLimit = async () => {
    try {
      const res = await authFetch(`${API_BASE}/api/reset-limit`, { method: "POST" });
      if (res.ok) {
        showToast("Limit timer reset successfully!", "success");
        setTimerStr("");
        fetchStats();
      } else {
        showToast("Failed to reset limit timer.", "error");
      }
    } catch (err) {
      showToast("Error resetting limit: " + err.message, "error");
    }
  };

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    try {
      const res = await authFetch(`${API_BASE}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (res.ok) {
        showToast("Settings saved successfully!", "success");
        fetchStats();
        fetchLeads();
      } else {
        showToast("Failed to save settings (Admin privileges required).", "error");
      }
    } catch (err) {
      showToast("Error saving settings: " + err.message, "error");
    }
  };

  const handleUpdateStatus = async (leadId, newStatus) => {
    try {
      const res = await authFetch(`${API_BASE}/api/leads/${leadId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        showToast(`Lead marked as ${newStatus.toLowerCase()}!`, "success");
        fetchLeads();
        fetchStats();
        if (currentUser && currentUser.role === "admin") {
          fetchUserAnalytics();
        }
      }
    } catch (err) {
      showToast("Error updating status: " + err.message, "error");
    }
  };

  const handleUpdateProposal = async (leadId, newProposal) => {
    try {
      const res = await authFetch(`${API_BASE}/api/leads/${leadId}/proposal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposal: newProposal }),
      });
      if (res.ok) {
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
      const res = await authFetch(`${API_BASE}/api/leads/${leadId}`, {
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

  const [enriching, setEnriching] = useState(false);
  const handleEnrichEmails = async () => {
    setEnriching(true);
    showToast("Scanning search engines for missing business emails...", "info");
    try {
      const res = await authFetch(`${API_BASE}/api/leads/enrich-emails?limit=25`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        if (data.enriched_count > 0) {
          showToast(`Email extraction complete! Discovered ${data.enriched_count} new emails.`, "success");
        } else {
          showToast(`Email scan complete. Checked ${data.checked} leads without new public emails found.`, "info");
        }
        fetchLeads();
        fetchAllLeads();
      } else {
        showToast("Email extraction failed.", "error");
      }
    } catch (err) {
      showToast("Error extracting emails: " + err.message, "error");
    } finally {
      setEnriching(false);
    }
  };

  const handleSyncSupabase = async () => {
    showToast("Starting cloud sync to Supabase...", "info");
    try {
      const res = await authFetch(`${API_BASE}/api/sync-supabase`, { method: "POST" });
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
      const res = await authFetch(`${API_BASE}/api/delete-all`, { method: "POST" });
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

  const handleStopScrape = async () => {
    try {
      showToast("Sending stop signal to backend scraper...", "info");
      await authFetch(`${API_BASE}/api/scrape/stop`, { method: "POST" });
      setScrapingInProgress(false);
      setLogs((prev) => [...prev, "[SYSTEM] Scrape cancelled by user."]);
      showToast("Scraper process stopped.", "info");
    } catch (err) {
      console.error("Error stopping scrape:", err);
    }
  };

  const handleStartScrape = async () => {
    if (!searchQuery) {
      showToast("Please enter a search query.", "error");
      return;
    }

    setScrapingInProgress(true);
    setLogs([
      "[SYSTEM] Launching scraper engine connection on backend...",
      `[SYSTEM] Target Query: "${searchQuery}" | Limit: ${parsedLimit} leads | Engine: ${scrapeSource}`
    ]);
    setScrapedLeads([]);

    try {
      const response = await authFetch(`${API_BASE}/api/scrape`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery, limit: parsedLimit, source: scrapeSource })
      });

      setScrapingInProgress(false);

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error: ${response.status}`);
      }

      const data = await response.json();
      setLogs(data.logs || [`[SYSTEM] Scraper completed. Saved ${data.count} new leads.`]);
      setScrapedLeads(data.leads || []);

      if (data.count > 0) {
        showToast(`Scraped & saved ${data.count} new leads!`, "success");
      } else if (data.existing_count > 0 || (data.leads && data.leads.length > 0)) {
        showToast(`Query matches ${data.leads.length} existing leads in database (0 new duplicates created).`, "info");
      } else {
        showToast(`Scraper finished. 0 new leads saved (all candidate listings evaluated).`, "info");
      }
      
      fetchStats();
      fetchLeads();
      if (currentUser && currentUser.role === "admin") {
        fetchUserAnalytics();
      }
    } catch (err) {
      console.error(err);
      setScrapingInProgress(false);
      setLogs((prev) => [...prev, `[SYSTEM ERROR] Failed to scrape: ${err.message}`]);
      showToast("Scraper halted with errors: " + err.message, "error");
    }
  };

  const handleWhatsAppAction = async (lead, type, proposal) => {
    if (!lead || !lead.phone) {
      showToast("No phone number available for this lead.", "error");
      return;
    }

    let cleanPhone = lead.phone.replace(/\D/g, "");
    if (cleanPhone.startsWith("0") && !cleanPhone.startsWith("00")) {
      cleanPhone = "92" + cleanPhone.substring(1);
    }

    if (!cleanPhone) {
      showToast("Invalid phone number format.", "error");
      return;
    }

    const messageText = proposal || lead.proposal || "";
    let targetUrl;
    if (type === "web") {
      targetUrl = `https://web.whatsapp.com/send?phone=${cleanPhone}&text=${encodeURIComponent(messageText)}`;
    } else {
      targetUrl = `https://wa.me/${cleanPhone}?text=${encodeURIComponent(messageText)}`;
    }

    // Auto mark as Sent in backend
    try {
      await authFetch(`${API_BASE}/api/whatsapp/${lead.id}`, { method: "POST" });
      handleUpdateStatus(lead.id, "Sent");
    } catch (e) {
      console.warn("Error tracking whatsapp send:", e);
    }

    let openedInTauri = false;
    if (window.__TAURI_INTERNALS__ || window.__TAURI_IPC__ || window.__TAURI__) {
      try {
        await open(targetUrl);
        openedInTauri = true;
      } catch (err) {
        console.warn("Tauri shell open failed, fallback to browser:", err);
      }
    }

    if (!openedInTauri) {
      if (type === "app") {
        const appSchemeUrl = `whatsapp://send?phone=${cleanPhone}&text=${encodeURIComponent(messageText)}`;
        window.location.href = appSchemeUrl;
        setTimeout(() => {
          window.open(targetUrl, "_blank", "noopener,noreferrer");
        }, 600);
      } else {
        window.open(targetUrl, "_blank", "noopener,noreferrer");
      }
    }
  };

  const handleExport = (format) => {
    if (allLeads.length === 0) {
      showToast("No data to export.", "error");
      return;
    }

    if (format === "csv") {
      const headers = ["ID", "Name", "Phone", "Email", "Website", "Address", "Category", "Query", "Scraped Date", "Outreach Status"];
      const rows = allLeads.map((l) => [
        l.id,
        `"${(l.name || "").replace(/"/g, '""')}"`,
        l.phone || "",
        l.email || "",
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
    }
  };

  const isLimitReached = stats.scraped_today >= stats.daily_limit;

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

  // ==========================================
  // UN-AUTHENTICATED: LOGIN VIEW
  // ==========================================
  if (!token || !currentUser) {
    return (
      <div className={`login-page-container ${theme}-theme`}>
        {toast && (
          <div className={`toast-msg ${toast.type === "error" ? "error" : ""}`}>
            {toast.message}
          </div>
        )}
        <div className="login-card">
          <div className="login-header">
            <img src="/logo.png" className="login-logo" alt="Logo" onError={(e) => { e.target.style.display = 'none'; }} />
            <h1 className="login-title">LeadGen Portal</h1>
            <p className="login-subtitle">Sign in to your scraping & outreach workspace</p>
          </div>

          <form onSubmit={handleLogin} className="login-form">
            {loginError && (
              <div className="toast-msg error" style={{ position: "static", transform: "none", marginBottom: "8px", width: "100%" }}>
                ⚠️ {loginError}
              </div>
            )}

            <div className="login-input-group">
              <label>Username</label>
              <input
                type="text"
                className="login-input"
                value={loginUsername}
                onChange={(e) => setLoginUsername(e.target.value)}
                placeholder="e.g. admin or agent"
                autoFocus
                required
              />
            </div>

            <div className="login-input-group">
              <label>Password</label>
              <input
                type="password"
                className="login-input"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>

            <button
              type="submit"
              className="login-btn"
              disabled={isSubmittingLogin}
            >
              {isSubmittingLogin ? "Authenticating..." : "🚀 Sign In"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ==========================================
  // AUTHENTICATED: MAIN APPLICATION VIEW
  // ==========================================
  const isAdmin = currentUser.role === "admin";

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
            <span className="nav-subtitle">
              {isAdmin ? "Admin Control Center" : "Agent Lead Workspace"}
            </span>
          </div>
        </div>

        <div className="nav-metrics-container">
          {/* User Profile Pill */}
          <div className="nav-user-pill">
            <div className="user-avatar-circle">
              {(currentUser.full_name || currentUser.username)[0].toUpperCase()}
            </div>
            <span className="user-name-text">{currentUser.full_name || currentUser.username}</span>
            <span className={`role-badge ${currentUser.role}`}>
              {isAdmin ? "👑 Admin" : "👤 User"}
            </span>
          </div>

          {/* Theme Toggle */}
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

          {/* Usage Badge */}
          <div className="nav-metric-badge">
            <span className={`nav-metric-dot ${timerStr ? "limit-reached" : isLimitReached ? "limit-reached" : ""}`}></span>
            {timerStr ? (
              <>
                <span className="nav-metric-label" style={{ color: "var(--danger-color, #ef4444)" }}>Limit Reached: </span>
                <span className="nav-metric-value">{timerStr}</span>
                {isAdmin && (
                  <button
                    onClick={handleResetLimit}
                    style={{
                      marginLeft: "8px",
                      padding: "2px 8px",
                      fontSize: "0.75rem",
                      borderRadius: "4px",
                      background: "var(--danger-color, #ef4444)",
                      color: "#fff",
                      border: "none",
                      cursor: "pointer"
                    }}
                    title="Reset Limit Timer"
                  >
                    Reset
                  </button>
                )}
              </>
            ) : (
              <>
                <span className="nav-metric-label">{isAdmin ? "Total Scraped: " : "My Scrapes: "}</span>
                <span className="nav-metric-value">{stats.scraped_today} / {stats.daily_limit}</span>
                {isAdmin && (isLimitReached || stats.limit_timer_end) && (
                  <button
                    onClick={handleResetLimit}
                    style={{
                      marginLeft: "8px",
                      padding: "2px 8px",
                      fontSize: "0.75rem",
                      borderRadius: "4px",
                      background: "rgba(239, 68, 68, 0.2)",
                      color: "var(--danger-color, #ef4444)",
                      border: "1px solid var(--danger-color, #ef4444)",
                      cursor: "pointer"
                    }}
                  >
                    Reset
                  </button>
                )}
              </>
            )}
          </div>

          {/* Logout Button */}
          <button
            className="logout-nav-btn"
            onClick={handleLogout}
            title="Sign out of account"
          >
            🚪 Logout
          </button>
        </div>
      </header>

      {/* Main Layout Container */}
      <div className="main-layout-container">
        {isSidebarOpen && (
          <div
            className="sidebar-backdrop"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}

        {/* Left Sidebar Navigation (Role-Based) */}
        <aside className={`left-sidebar ${isSidebarOpen ? "sidebar-open" : "sidebar-closed"}`}>
          {/* Scrape Leads (Visible to All) */}
          <button
            className={`sidebar-tab-btn ${activeTab === "scrape" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("scrape");
              if (window.innerWidth <= 768) setIsSidebarOpen(false);
            }}
          >
            🔍 Scrape Leads
          </button>

          {/* Leads (Visible to All - Scoped to User's Leads for User role) */}
          <button
            className={`sidebar-tab-btn ${activeTab === "queue" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("queue");
              if (window.innerWidth <= 768) setIsSidebarOpen(false);
            }}
          >
            📋 {isAdmin ? "All Leads" : "My Leads"}
          </button>

          {/* Outreach Database (Admin Only) */}
          {isAdmin && (
            <button
              className={`sidebar-tab-btn ${activeTab === "database" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("database");
                if (window.innerWidth <= 768) setIsSidebarOpen(false);
              }}
            >
              📱 Outreach Database
            </button>
          )}

          {/* Team & Daily Analytics (Admin Only) */}
          {isAdmin && (
            <button
              className={`sidebar-tab-btn ${activeTab === "team" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("team");
                if (window.innerWidth <= 768) setIsSidebarOpen(false);
              }}
            >
              👥 Team & Analytics
            </button>
          )}

          {/* Settings & Templates (Admin Only) */}
          {isAdmin && (
            <button
              className={`sidebar-tab-btn ${activeTab === "settings" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("settings");
                if (window.innerWidth <= 768) setIsSidebarOpen(false);
              }}
            >
              ⚙️ Settings & Templates
            </button>
          )}
        </aside>

        {/* Floating Sidebar Toggle Button */}
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

            {/* TAB 1: SCRAPE NEW LEADS */}
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
                      placeholder="e.g., truck dispatchers in Atlanta, restaurants in Lahore, dentists Karachi"
                      disabled={scrapingInProgress}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Scraper Engine</label>
                    <select
                      className="form-input"
                      value={scrapeSource}
                      onChange={(e) => setScrapeSource(e.target.value)}
                      disabled={scrapingInProgress}
                      style={{ height: '42px' }}
                    >
                      <option value="auto">✨ Smart Auto (Recommended - Bing + Google Maps Fallback)</option>
                      <option value="google_maps">🗺️ Google Maps Scraper (Playwright)</option>
                      <option value="bing">📍 Bing Maps Scraper</option>
                      <option value="osm">🌐 OpenStreetMap Scraper</option>
                    </select>
                  </div>

                  <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                    <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span>Max results for this run</span>
                      <span style={{ color: '#00e676', fontWeight: 'bold' }}>{parsedLimit} leads</span>
                    </label>
                    <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                      <input
                        type="number"
                        min="1"
                        max="5000"
                        className="form-input"
                        style={{ width: '130px', height: '42px', fontWeight: 'bold', fontSize: '1rem' }}
                        value={scrapeLimit}
                        onChange={(e) => setScrapeLimit(e.target.value)}
                        onBlur={() => {
                          if (!scrapeLimit || parseInt(scrapeLimit) < 1) setScrapeLimit("1");
                          else if (parseInt(scrapeLimit) > 5000) setScrapeLimit("5000");
                        }}
                        disabled={scrapingInProgress}
                        placeholder="e.g. 50"
                      />
                      <input
                        type="range"
                        min="1"
                        max="5000"
                        value={parsedLimit}
                        onChange={(e) => setScrapeLimit(e.target.value)}
                        disabled={scrapingInProgress}
                        style={{ flex: 1 }}
                      />
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", gap: "12px" }}>
                  <button
                    className="btn btn-primary btn-full"
                    onClick={handleStartScrape}
                    disabled={scrapingInProgress || isLimitReached || !!timerStr}
                    style={{ flex: 1 }}
                  >
                    {scrapingInProgress ? "⏳ Scraping In Progress..." : timerStr ? `⛔ Restores in ${timerStr}` : "🚀 Run Scrape"}
                  </button>
                  {scrapingInProgress && (
                    <button
                      className="btn btn-danger"
                      onClick={handleStopScrape}
                      style={{ padding: "0 24px", fontWeight: "bold" }}
                    >
                      🛑 Stop Scrape
                    </button>
                  )}
                </div>

                {/* Progress / Console Log Feed */}
                {logs.length > 0 && (
                  <div className="terminal-container">
                    <div className="terminal-header">
                      <div className="terminal-dots">
                        <span className="dot dot-red"></span>
                        <span className="dot dot-yellow"></span>
                        <span className="dot dot-green"></span>
                      </div>
                      <span className="terminal-title">Live Scraper Console</span>
                    </div>
                    <div className="terminal-body">
                      {logs.map((log, index) => (
                        <div key={index} className="terminal-line">
                          <span className="terminal-timestamp">[{new Date().toLocaleTimeString()}]</span>
                          <span className="terminal-text">{log}</span>
                        </div>
                      ))}
                      <div ref={logsEndRef} />
                    </div>
                  </div>
                )}

                {/* Live Preview of Scraped Leads */}
                {scrapedLeads.length > 0 && (
                  <div style={{ marginTop: '24px' }}>
                    <h3 style={{ fontSize: '1.1rem', marginBottom: '12px', color: 'var(--text-primary)' }}>
                      🎉 Newly Added Leads ({scrapedLeads.length})
                    </h3>
                    <div className="leads-grid">
                      {scrapedLeads.map((lead) => (
                        <LeadCard
                          key={lead.id || lead.google_maps_url}
                          lead={lead}
                          filterType="unsent"
                          onUpdateStatus={handleUpdateStatus}
                          onUpdateProposal={handleUpdateProposal}
                          onDelete={handleDeleteLead}
                          onWhatsApp={handleWhatsAppAction}
                          authFetch={authFetch}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: LEADS QUEUE */}
            {activeTab === "queue" && (
              <div className="panel-container">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
                  <h2 className="panel-header" style={{ margin: 0 }}>
                    {isAdmin ? "All Leads Workspace" : "My Leads Workspace"} ({leads.length})
                  </h2>

                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <button
                      className="btn"
                      onClick={handleEnrichEmails}
                      disabled={enriching}
                      style={{
                        background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
                        color: '#fff',
                        fontWeight: '600',
                        fontSize: '0.85rem'
                      }}
                    >
                      {enriching ? "⏳ Scanning Web for Emails..." : "🔍 Find Missing Emails"}
                    </button>
                    {isAdmin && (
                      <button
                        className="btn"
                        onClick={handleSyncSupabase}
                        style={{
                          background: 'linear-gradient(135deg, #3ecf8e 0%, #2e7d32 100%)',
                          color: '#fff',
                          fontWeight: '600',
                          fontSize: '0.85rem'
                        }}
                      >
                        ☁️ Cloud Sync
                      </button>
                    )}
                  </div>
                </div>

                {/* Filters */}
                <div className="form-grid" style={{ marginBottom: "20px" }}>
                  <div className="form-group">
                    <label className="form-label">Search Leads</label>
                    <input
                      type="text"
                      className="form-input"
                      value={searchKW}
                      onChange={(e) => setSearchKW(e.target.value)}
                      placeholder="Search by business name, city, category..."
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Outreach Status</label>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        type="button"
                        className={`btn ${statusFilter === "unsent" ? "btn-primary" : ""}`}
                        style={{ flex: 1, height: '42px' }}
                        onClick={() => setStatusFilter("unsent")}
                      >
                        ⏳ New / Unsent
                      </button>
                      <button
                        type="button"
                        className={`btn ${statusFilter === "sent" ? "btn-primary" : ""}`}
                        style={{ flex: 1, height: '42px' }}
                        onClick={() => setStatusFilter("sent")}
                      >
                        ✅ Sent
                      </button>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Website Status Filter</label>
                    <select
                      className="form-input"
                      value={filterType}
                      onChange={(e) => setFilterType(e.target.value)}
                      style={{ height: '42px' }}
                    >
                      <option value="all_target">🎯 Target Leads (No Website OR Unresponsive)</option>
                      <option value="no_website">🚫 No Website Only</option>
                      <option value="unresponsive">⚠️ Unresponsive Website Only</option>
                      <option value="all">🌐 All Filtered</option>
                    </select>
                  </div>
                </div>

                {/* Leads List */}
                {leads.length === 0 ? (
                  <div className="empty-state">
                    <span style={{ fontSize: "2.5rem" }}>📭</span>
                    <h3>No leads found in this view</h3>
                    <p style={{ color: "var(--text-muted)", marginTop: "6px" }}>
                      Try adjusting filters or scrape new leads.
                    </p>
                  </div>
                ) : (
                  <div className="leads-grid">
                    {leads.map((lead) => (
                      <LeadCard
                        key={lead.id}
                        lead={lead}
                        filterType={statusFilter}
                        onUpdateStatus={handleUpdateStatus}
                        onUpdateProposal={handleUpdateProposal}
                        onDelete={handleDeleteLead}
                        onWhatsApp={handleWhatsAppAction}
                        authFetch={authFetch}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: ADMIN OUTREACH DATABASE */}
            {isAdmin && activeTab === "database" && (() => {
              const totalDbPages = Math.max(1, Math.ceil(filteredAllLeads.length / dbPageSize));
              const currentDbRows = filteredAllLeads.slice((dbPage - 1) * dbPageSize, dbPage * dbPageSize);

              return (
                <div className="panel-container">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <h2 className="panel-header" style={{ margin: 0 }}>
                        Global Outreach Database ({filteredAllLeads.length})
                      </h2>
                      {loadingAllLeads && (
                        <span style={{ fontSize: '0.85rem', color: 'var(--secondary)' }}>
                          ⏳ Syncing data...
                        </span>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        className="btn"
                        onClick={fetchAllLeads}
                        disabled={loadingAllLeads}
                        style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
                      >
                        {loadingAllLeads ? "⏳ Loading..." : "🔄 Refresh"}
                      </button>
                      <button
                        className="btn"
                        onClick={() => handleExport("csv")}
                        style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
                      >
                        📥 Export CSV
                      </button>
                      <button
                        className="btn btn-danger"
                        onClick={handleDeleteAll}
                      >
                        🔥 Delete All
                      </button>
                    </div>
                  </div>

                  <div className="form-group" style={{ marginBottom: "16px" }}>
                    <input
                      type="text"
                      className="form-input"
                      value={dbSearch}
                      onChange={(e) => {
                        setDbSearch(e.target.value);
                        setDbPage(1);
                      }}
                      placeholder="Search database by business name, phone, address, or query..."
                    />
                  </div>

                  <div className="database-table-container">
                    <div className="table-scroll-wrapper">
                      <table className="database-table">
                        <thead>
                          <tr>
                            <th style={{ minWidth: "180px" }}>Business Name</th>
                            <th style={{ minWidth: "220px" }}>Address</th>
                            <th style={{ minWidth: "140px" }}>Phone</th>
                            <th style={{ minWidth: "150px" }}>Email</th>
                            <th style={{ minWidth: "110px" }}>Website</th>
                            <th style={{ minWidth: "110px" }}>Category</th>
                            <th style={{ minWidth: "110px" }}>Scraped Date</th>
                            <th style={{ minWidth: "110px" }}>Added By</th>
                            <th style={{ minWidth: "90px" }}>Status</th>
                            <th style={{ minWidth: "90px", textAlign: "center" }}>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {currentDbRows.length === 0 ? (
                            <tr>
                              <td colSpan={10} style={{ textAlign: "center", padding: "40px 20px", color: "var(--text-muted)" }}>
                                {loadingAllLeads ? "⏳ Loading leads..." : "No leads found matching your search."}
                              </td>
                            </tr>
                          ) : (
                            currentDbRows.map((l) => (
                              <tr key={l.id}>
                                <td>
                                  <div className="table-lead-name">
                                    <span>{l.name}</span>
                                  </div>
                                </td>
                                <td>
                                  {l.address ? (
                                    <div className="address-text-cell" title={l.address}>
                                      <span>📍</span>
                                      <span>{l.address}</span>
                                    </div>
                                  ) : (
                                    <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>-</span>
                                  )}
                                </td>
                                <td>
                                  {l.phone ? (
                                    <button
                                      className="phone-link-pill"
                                      onClick={() => handleWhatsAppAction(l, "web")}
                                      title="Open WhatsApp Chat"
                                    >
                                      📞 {l.phone}
                                    </button>
                                  ) : (
                                    <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>-</span>
                                  )}
                                </td>
                                <td>
                                  {l.email ? (
                                    <a
                                      href={`mailto:${l.email}`}
                                      className="email-link-pill"
                                      title={l.email}
                                    >
                                      ✉️ {l.email.length > 20 ? l.email.substring(0, 18) + '...' : l.email}
                                    </a>
                                  ) : (
                                    <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>-</span>
                                  )}
                                </td>
                                <td>
                                  {l.website ? (
                                    <a
                                      href={l.website}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="website-link-pill"
                                      title={l.website}
                                    >
                                      🌐 Visit
                                    </a>
                                  ) : (
                                    <span className="badge badge-danger" style={{ fontSize: "0.72rem" }}>
                                      No Website
                                    </span>
                                  )}
                                </td>
                                <td>
                                  <span className="category-tag-pill">
                                    {l.category || "Local Business"}
                                  </span>
                                </td>
                                <td>
                                  <span className="date-text-pill">
                                    {formatDisplayDate(l.scraped_date)}
                                  </span>
                                </td>
                                <td>
                                  <span className="attribution-user-badge">
                                    👤 {l.user_name || (l.user_id ? `User #${l.user_id}` : "System")}
                                  </span>
                                </td>
                                <td>
                                  <span className={`badge ${l.message_status === 'Sent' ? 'badge-success' : 'badge-warning'}`}>
                                    {l.message_status === 'Sent' ? 'Sent' : 'New'}
                                  </span>
                                </td>
                                <td style={{ textAlign: "center" }}>
                                  <div style={{ display: "flex", gap: "6px", justifyContent: "center" }}>
                                    {l.phone && (
                                      <button
                                        className="table-mini-btn"
                                        onClick={() => handleWhatsAppAction(l, "web")}
                                        title="Send WhatsApp"
                                      >
                                        💬
                                      </button>
                                    )}
                                    <button
                                      className="table-mini-btn danger"
                                      onClick={() => handleDeleteLead(l.id)}
                                      title="Delete Lead"
                                    >
                                      🗑️
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>

                    {/* Pagination Bar */}
                    <div className="table-pagination-bar">
                      <span>
                        Showing {filteredAllLeads.length > 0 ? (dbPage - 1) * dbPageSize + 1 : 0} to{" "}
                        {Math.min(dbPage * dbPageSize, filteredAllLeads.length)} of {filteredAllLeads.length} leads
                      </span>

                      <div className="pagination-btn-group">
                        <button
                          className="page-nav-btn"
                          onClick={() => setDbPage((p) => Math.max(1, p - 1))}
                          disabled={dbPage <= 1}
                        >
                          ◀ Previous
                        </button>
                        <span style={{ fontWeight: "600", fontSize: "0.85rem", padding: "0 6px" }}>
                          Page {dbPage} of {totalDbPages}
                        </span>
                        <button
                          className="page-nav-btn"
                          onClick={() => setDbPage((p) => Math.min(totalDbPages, p + 1))}
                          disabled={dbPage >= totalDbPages}
                        >
                          Next ▶
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}
            
            {/* TAB 4: ADMIN TEAM & DAILY ACTIVITY ANALYTICS */}
            {isAdmin && activeTab === "team" && (
              <div className="panel-container">
                <h2 className="panel-header">Team Management & Daily Scrapes Analytics</h2>

                {/* Top Metrics Cards */}
                <div className="analytics-stats-grid">
                  <div className="analytics-stat-card">
                    <div className="stat-icon-wrapper stat-icon-green">🔍</div>
                    <div>
                      <div className="stat-info-title">Team Scrapes Today</div>
                      <div className="stat-info-val">{userAnalytics.totals?.scrapes_today || 0}</div>
                    </div>
                  </div>

                  <div className="analytics-stat-card">
                    <div className="stat-icon-wrapper stat-icon-blue">📱</div>
                    <div>
                      <div className="stat-info-title">Team Outreach Today</div>
                      <div className="stat-info-val">{userAnalytics.totals?.outreach_today || 0}</div>
                    </div>
                  </div>

                  <div className="analytics-stat-card">
                    <div className="stat-icon-wrapper stat-icon-purple">🏢</div>
                    <div>
                      <div className="stat-info-title">Total Leads Scraped</div>
                      <div className="stat-info-val">{userAnalytics.totals?.total_leads || 0}</div>
                    </div>
                  </div>

                  <div className="analytics-stat-card">
                    <div className="stat-icon-wrapper stat-icon-amber">👥</div>
                    <div>
                      <div className="stat-info-title">Active Team Members</div>
                      <div className="stat-info-val">{userAnalytics.totals?.total_users || 0}</div>
                    </div>
                  </div>
                </div>

                {/* User Administration Layout */}
                <div className="user-admin-layout">
                  {/* Left: Add New User Form */}
                  <div className="user-form-card">
                    <h3 style={{ fontSize: "1.1rem", marginBottom: "16px", color: "var(--text-primary)" }}>
                      ➕ Add New User Account
                    </h3>
                    <form onSubmit={handleCreateUser} className="login-form">
                      <div className="login-input-group">
                        <label>Username *</label>
                        <input
                          type="text"
                          className="login-input"
                          value={newUsername}
                          onChange={(e) => setNewUsername(e.target.value)}
                          placeholder="e.g. agent_ali"
                          required
                        />
                      </div>

                      <div className="login-input-group">
                        <label>Full Name</label>
                        <input
                          type="text"
                          className="login-input"
                          value={newFullName}
                          onChange={(e) => setNewFullName(e.target.value)}
                          placeholder="e.g. Ali Khan"
                        />
                      </div>

                      <div className="login-input-group">
                        <label>Password *</label>
                        <input
                          type="password"
                          className="login-input"
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          placeholder="••••••••"
                          required
                        />
                      </div>

                      <div className="login-input-group">
                        <label>Account Role</label>
                        <select
                          className="login-input"
                          value={newRole}
                          onChange={(e) => setNewRole(e.target.value)}
                        >
                          <option value="user">👤 Standard User (Scrape Leads & Own Leads)</option>
                          <option value="admin">👑 Admin (Full Access & User Management)</option>
                        </select>
                      </div>

                      <button
                        type="submit"
                        className="login-btn"
                        disabled={isCreatingUser}
                        style={{ marginTop: "12px" }}
                      >
                        {isCreatingUser ? "Creating Account..." : "Create Account"}
                      </button>
                    </form>
                  </div>

                  {/* Right: Team Members & Daily Progress Breakdown */}
                  <div className="user-table-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <h3 style={{ fontSize: "1.1rem", color: "var(--text-primary)" }}>
                        📊 User Activity & Performance Breakdown
                      </h3>
                      <button
                        className="btn"
                        onClick={fetchUserAnalytics}
                        style={{ padding: "6px 12px", fontSize: "0.8rem" }}
                      >
                        🔄 Refresh Stats
                      </button>
                    </div>

                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th>User</th>
                          <th>Role</th>
                          <th>Scrapes (Today)</th>
                          <th>Outreach (Today)</th>
                          <th>Total Leads</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(userAnalytics.users || []).map((u) => (
                          <tr key={u.id}>
                            <td>
                              <div className="user-row-name">
                                <span className="user-full-name">{u.full_name || u.username}</span>
                                <span className="user-username-sub">@{u.username}</span>
                              </div>
                            </td>
                            <td>
                              <span className={`role-badge ${u.role}`}>
                                {u.role === 'admin' ? '👑 Admin' : '👤 User'}
                              </span>
                            </td>
                            <td>
                              <span className="stat-pill-badge active-count">
                                🔍 {u.scrapes_today} scrapes
                              </span>
                            </td>
                            <td>
                              <span className="stat-pill-badge blue-count">
                                💬 {u.outreach_today} sent
                              </span>
                            </td>
                            <td style={{ fontWeight: "600" }}>{u.total_leads}</td>
                            <td>
                              <span className={`badge ${u.is_active ? 'badge-success' : 'badge-warning'}`}>
                                {u.is_active ? 'Active' : 'Inactive'}
                              </span>
                            </td>
                            <td>
                              <div className="action-btn-group">
                                <button
                                  className="table-mini-btn"
                                  onClick={() => handleToggleUserStatus(u.id, u.is_active)}
                                  title={u.is_active ? "Deactivate User" : "Activate User"}
                                >
                                  {u.is_active ? "⏸️ Pause" : "▶️ Enable"}
                                </button>
                                <button
                                  className="table-mini-btn"
                                  onClick={() => handleResetUserPassword(u.id, u.username)}
                                  title="Reset Password"
                                >
                                  🔑 Pass
                                </button>
                                {u.id !== currentUser.id && (
                                  <button
                                    className="table-mini-btn danger"
                                    onClick={() => handleDeleteUser(u.id, u.username)}
                                    title="Delete User"
                                  >
                                    🗑️
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 5: ADMIN SETTINGS & TEMPLATES */}
            {isAdmin && activeTab === "settings" && (
              <div className="panel-container">
                <h2 className="panel-header">Settings & Proposal Templates</h2>

                <form onSubmit={handleSaveSettings}>
                  <div className="form-grid">
                    <div className="form-group">
                      <label className="form-label">Global Daily Limit (Leads per Day)</label>
                      <input
                        type="number"
                        className="form-input"
                        value={settings.daily_limit}
                        onChange={(e) => setSettings({ ...settings, daily_limit: parseInt(e.target.value) || 50 })}
                        min="1"
                        max="5000"
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">Proposal Language</label>
                      <select
                        className="form-input"
                        value={settings.proposal_language}
                        onChange={(e) => setSettings({ ...settings, proposal_language: e.target.value })}
                        style={{ height: '42px' }}
                      >
                        <option value="English">English</option>
                        <option value="Urdu">Urdu (Roman / Urdu)</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label className="form-label">AI Generation Provider</label>
                      <select
                        className="form-input"
                        value={settings.ai_provider}
                        onChange={(e) => setSettings({ ...settings, ai_provider: e.target.value })}
                        style={{ height: '42px' }}
                      >
                        <option value="Gemini">Google Gemini (Recommended)</option>
                        <option value="OpenAI">OpenAI GPT</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Gemini API Key</label>
                      <input
                        type="password"
                        className="form-input"
                        value={settings.gemini_api_key}
                        onChange={(e) => setSettings({ ...settings, gemini_api_key: e.target.value })}
                        placeholder="AIzaSy..."
                      />
                    </div>

                    <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                      <label className="form-label">Default Proposal Template (English)</label>
                      <textarea
                        className="form-input"
                        style={{ height: '110px', resize: 'vertical' }}
                        value={settings.proposal_template}
                        onChange={(e) => setSettings({ ...settings, proposal_template: e.target.value })}
                        placeholder="Hi {name}, I noticed your business doesn't have an active website..."
                      />
                    </div>

                    <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                      <label className="form-label">Default Proposal Template (Urdu)</label>
                      <textarea
                        className="form-input"
                        style={{ height: '110px', resize: 'vertical' }}
                        value={settings.proposal_template_urdu}
                        onChange={(e) => setSettings({ ...settings, proposal_template_urdu: e.target.value })}
                        placeholder="Assalam o Alaikum {name}, hum ne dekha ke aap ka business online listed hai..."
                      />
                    </div>
                  </div>

                  <button type="submit" className="btn btn-primary" style={{ marginTop: "16px", width: "100%" }}>
                    💾 Save System Configuration
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

// Individual Lead Card Component
function LeadCard({ lead, filterType, onUpdateStatus, onUpdateProposal, onDelete, onWhatsApp, authFetch }) {
  const [localProposal, setLocalProposal] = useState(lead.proposal || "");
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    setLocalProposal(lead.proposal || "");
  }, [lead.proposal]);

  const handleBlur = () => {
    if (localProposal !== lead.proposal) {
      onUpdateProposal(lead.id, localProposal);
    }
  };

  const handleGenerateAIProposal = async () => {
    setGenerating(true);
    try {
      const res = await authFetch(`${API_BASE}/api/leads/${lead.id}/proposal?force_refresh=true`);
      if (res.ok) {
        const data = await res.json();
        setLocalProposal(data.proposal);
        onUpdateProposal(lead.id, data.proposal);
      }
    } catch (e) {
      console.error("AI proposal generation failed:", e);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="lead-card">
      <div className="lead-card-header">
        <div style={{ flex: 1 }}>
          <h3 className="lead-title">
            {lead.name}
            {lead.category && <span className="badge badge-warning" style={{ marginLeft: "8px" }}>{lead.category}</span>}
          </h3>
          <div className="lead-meta-row">
            {lead.phone ? (
              <span className="lead-meta-item">📞 {lead.phone}</span>
            ) : (
              <span className="lead-meta-item" style={{ color: "var(--danger-color, #ef4444)" }}>📞 No Phone</span>
            )}
            {lead.address && <span className="lead-meta-item">📍 {lead.address}</span>}
            {lead.user_name && <span className="lead-meta-item">👤 Added by: {lead.user_name}</span>}
          </div>
        </div>

        <div style={{ textAlign: "right", display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "4px" }}>
          {lead.website ? (
            <a
              href={lead.website}
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary"
              style={{ padding: "4px 10px", fontSize: "0.75rem" }}
            >
              🌐 Visit Site
            </a>
          ) : (
            <span className="badge badge-danger">No Website</span>
          )}
          <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            {lead.website_status || "Evaluated"}
          </span>
        </div>
      </div>

      <div className="lead-card-body-row">
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
            <span style={{ fontSize: '0.8rem', color: '#90a4ae' }}>Outreach Pitch Message:</span>
            <button
              onClick={handleGenerateAIProposal}
              disabled={generating}
              style={{
                background: 'linear-gradient(135deg, #7c4dff, #651fff)',
                color: '#fff',
                border: 'none',
                borderRadius: '6px',
                padding: '4px 10px',
                fontSize: '0.78rem',
                cursor: 'pointer',
                fontWeight: '600'
              }}
            >
              {generating ? "⏳ Generating..." : "✨ Generate AI Proposal"}
            </button>
          </div>
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

          {lead.email ? (
            <a
              className="btn email-btn"
              href={`mailto:${lead.email}?subject=${encodeURIComponent("Proposal")}&body=${encodeURIComponent(localProposal || lead.proposal || "")}`}
              style={{ display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              ✉️ Send Email
            </a>
          ) : (
            <button
              className="btn email-btn disabled"
              disabled
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                opacity: 0.5,
                cursor: "not-allowed",
                background: "linear-gradient(135deg, #4b5563 0%, #374151 100%)",
                color: "#9ca3af",
                boxShadow: "none"
              }}
            >
              ✉️ Send Email
            </button>
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
