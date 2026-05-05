/**
 * app.js — Firmable company search
 *
 * Reads filter values directly from the form DOM on submission.
 * Triggers on: Enter key in the query input, or Apply Filters button click.
 * Renders result cards into #result-list and updates #result-count.
 *
 * Supports two search modes:
 *   - Standard: POST /search (hybrid BM25 + neural)
 *   - AI Search: POST /agent/search (ReAct agent, streamed via SSE)
 */

(function () {
  "use strict";

  const API_BASE        = "";
  const SEARCH_URL      = API_BASE + "/search";
  const FACETS_URL      = API_BASE + "/facets";
  const AGENT_SEARCH_URL = API_BASE + "/agent/search";

  // ── DOM refs ──────────────────────────────────────────────
  const form            = document.getElementById("search-form");
  const searchBtn       = document.getElementById("search-btn");
  const clearBtn        = document.getElementById("clear-btn");
  const queryInput      = document.getElementById("query-input");
  const resultList      = document.getElementById("result-list");
  const resultCount     = document.getElementById("result-count");
  const loading         = document.getElementById("loading-indicator");
  const errorBox        = document.getElementById("error-message");
  const pagination      = document.getElementById("pagination");
  const paginationStatus = document.getElementById("pagination-status");
  const prevBtn         = document.getElementById("pagination-prev");
  const nextBtn         = document.getElementById("pagination-next");
  const agenticToggle   = document.getElementById("agentic-toggle");
  const agenticLabel    = document.getElementById("agentic-toggle-label");
  const aiStatus        = document.getElementById("ai-status");
  const reasoningPanel  = document.getElementById("reasoning-panel");
  const reasoningContent = document.getElementById("reasoning-content");

  var currentPage = 1;

  // ── Agentic mode state (persisted in localStorage) ────────
  var agenticMode = localStorage.getItem("firmable_agentic") === "true";
  agenticToggle.checked = agenticMode;
  if (agenticMode) agenticLabel.classList.add("active");

  agenticToggle.addEventListener("change", function () {
    agenticMode = agenticToggle.checked;
    localStorage.setItem("firmable_agentic", String(agenticMode));
    if (agenticMode) {
      agenticLabel.classList.add("active");
    } else {
      agenticLabel.classList.remove("active");
      hideAIStatus();
    }
  });

  // ── Load facets on page load to populate industry checkboxes ──
  function loadIndustryFacets() {
    fetch(FACETS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (!data || !data.industry || !data.industry.length) return;
        var list = document.getElementById("industry-list");
        if (!list) return;
        list.innerHTML = data.industry.map(function (b) {
          var label = b.key.charAt(0).toUpperCase() + b.key.slice(1);
          var safeVal = JSON.stringify(b.key);
          return '<li><label><input type="checkbox" name="industry" data-key=' + safeVal + ' value=' + safeVal + ' />' + esc(label) + ' <span style="color:#9ca3af;font-size:11px">(' + b.count.toLocaleString() + ')</span></label></li>';
        }).join("");
      })
      .catch(function () { /* keep static fallback */ });
  }

  loadIndustryFacets();

  // ── Search trigger: form submit (Enter or Apply Filters) ──
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    currentPage = 1;
    if (agenticMode) {
      runAgentSearch(currentPage);
    } else {
      runSearch(currentPage);
    }
  });

  prevBtn.addEventListener("click", function () {
    if (prevBtn.disabled || currentPage <= 1) return;
    if (agenticMode) {
      runAgentSearch(currentPage - 1);
    } else {
      runSearch(currentPage - 1);
    }
  });

  nextBtn.addEventListener("click", function () {
    if (nextBtn.disabled) return;
    if (agenticMode) {
      runAgentSearch(currentPage + 1);
    } else {
      runSearch(currentPage + 1);
    }
  });

  // ── Clear All ─────────────────────────────────────────────
  clearBtn.addEventListener("click", function () {
    form.reset();
    currentPage = 1;
    resultList.innerHTML = emptyStateHTML("Enter a query or select filters, then press Enter or Apply Filters.", "Results will appear here.");
    resultCount.textContent = "";
    renderPagination(0, 1, 20);
    hideError();
    hideAIStatus();
    hideReasoningPanel();
  });

  // ── Standard search (POST /search) ────────────────────────
  function runSearch(page) {
    var body = buildRequestBody(page);
    showLoading("Searching\u2026");
    hideError();

    fetch(SEARCH_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (data) {
            throw new Error(data.detail || ("Request failed: " + res.status));
          });
        }
        return res.json();
      })
      .then(function (data) {
        currentPage = typeof data.page === "number" ? data.page : page;
        hideLoading();
        renderResults(data);
      })
      .catch(function (err) {
        hideLoading();
        showError("Search failed: " + (err.message || "unexpected error. Please try again."));
        resultList.innerHTML = "";
        resultCount.textContent = "";
      });
  }

  // ── Agent search (POST /agent/search, SSE) ─────────────────
  function runAgentSearch(page) {
    var body = buildRequestBody(page);
    showLoading("AI is thinking\u2026");
    hideError();
    hideAIStatus();
    clearReasoning();
    showReasoningPanel();

    fetch(AGENT_SEARCH_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (data) {
            throw new Error(data.detail || ("Request failed: " + res.status));
          });
        }
        consumeSSEStream(res.body, page);
      })
      .catch(function (err) {
        hideLoading();
        hideReasoningPanel();
        showError("Agent search failed: " + (err.message || "unexpected error"));
      });
  }

  function consumeSSEStream(body, page) {
    var reader = body.getReader();
    var decoder = new TextDecoder();
    var buf = "";

    function processBuffer() {
      var parts = buf.split("\n\n");
      buf = parts.pop(); // keep incomplete event in buffer
      for (var i = 0; i < parts.length; i++) {
        parseAndDispatch(parts[i]);
      }
    }

    function read() {
      reader.read().then(function (chunk) {
        if (chunk.done) {
          if (buf.trim()) parseAndDispatch(buf);
          hideLoading();
          return;
        }
        buf += decoder.decode(chunk.value, { stream: true });
        processBuffer();
        read();
      }).catch(function (err) {
        hideLoading();
        hideReasoningPanel();
        if (err.name !== "AbortError") {
          showError("Stream interrupted: " + err.message);
        }
      });
    }

    read();
  }

  function parseAndDispatch(raw) {
    var lines = raw.split("\n");
    var eventType = "";
    var dataLine = "";
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (line.indexOf("event: ") === 0) {
        eventType = line.slice(7).trim();
      } else if (line.indexOf("data: ") === 0) {
        dataLine = line.slice(6).trim();
      }
    }
    if (!eventType || !dataLine) return;
    try {
      handleSSEEvent(eventType, JSON.parse(dataLine));
    } catch (e) {
      // ignore malformed events
    }
  }

  function handleSSEEvent(eventType, payload) {
    switch (eventType) {
      case "token":
        appendReasoning(payload.text || "");
        break;

      case "tool_call":
        appendReasoning("\n[\u2192 " + esc(payload.tool || "") + "]\n");
        break;

      case "tool_result":
        appendReasoning("[\u2190 " + (payload.total || 0) + " results]\n");
        break;

      case "result":
        hideLoading();
        hideReasoningPanel();
        currentPage = typeof payload.page === "number" ? payload.page : 1;
        renderResults(payload);
        if (payload.fallback_used) {
          showAIStatus("AI unavailable \u2014 showing hybrid results");
        } else {
          hideAIStatus();
          if (payload.agent_explanation) {
            resultCount.textContent = esc(payload.agent_explanation);
          }
        }
        break;

      case "error":
        hideLoading();
        hideReasoningPanel();
        showError("Agent error: " + esc(payload.message || "unknown error"));
        break;

      case "done":
        hideLoading();
        break;
    }
  }

  // ── Reasoning panel helpers ───────────────────────────────
  function showReasoningPanel() {
    reasoningPanel.style.display = "block";
  }

  function hideReasoningPanel() {
    reasoningPanel.style.display = "none";
  }

  function clearReasoning() {
    reasoningContent.textContent = "";
  }

  function appendReasoning(text) {
    reasoningContent.textContent += text;
    reasoningContent.scrollTop = reasoningContent.scrollHeight;
  }

  function showAIStatus(msg) {
    aiStatus.textContent = msg;
    aiStatus.style.display = "inline";
  }

  function hideAIStatus() {
    aiStatus.style.display = "none";
  }

  // ── Build POST body from form ─────────────────────────────
  function buildRequestBody(page) {
    var body = { page: page || 1 };

    var query = queryInput.value.trim();
    if (query) body.query = query;

    var industries = checkedValues("industry");
    if (industries.length) body.industry = industries;

    var sizes = checkedValues("size_range");
    if (sizes.length) body.size_range = sizes;

    var country = val("country");
    if (country) body.country = country;

    var city = val("city");
    if (city) body.city = city;

    var yearFrom = intVal("year_founded_gte");
    if (yearFrom !== null) body.year_founded_gte = yearFrom;

    var yearTo = intVal("year_founded_lte");
    if (yearTo !== null) body.year_founded_lte = yearTo;

    return body;
  }

  // ── Render ────────────────────────────────────────────────
  function renderResults(data) {
    var items = data.items || [];
    var total = typeof data.total === "number" ? data.total : items.length;
    var page = typeof data.page === "number" ? data.page : currentPage;
    var pageSize = typeof data.page_size === "number" ? data.page_size : items.length || 20;

    if (!data.agent_explanation) {
      resultCount.textContent = total.toLocaleString() + " result" + (total !== 1 ? "s" : "") + " found";
    }
    renderPagination(total, page, pageSize);

    if (!items.length) {
      resultList.innerHTML = emptyStateHTML(
        "No companies matched your search.",
        "Try adjusting your filters."
      );
      return;
    }

    resultList.innerHTML = items.map(cardHTML).join("");
  }

  function cardHTML(c) {
    var lines = [];

    lines.push('<div class="company-card">');
    lines.push('  <div class="card-name">' + esc(c.name) + '</div>');

    if (c.domain) {
      lines.push('  <div class="card-domain">' + esc(c.domain) + '</div>');
    }

    lines.push('  <div class="card-meta">');

    if (c.industry) {
      lines.push('    <span><strong>Industry</strong> ' + esc(c.industry) + '</span>');
    }

    var location = buildLocation(c.city, c.region, c.country);
    if (location) {
      lines.push('    <span><strong>Location</strong> ' + esc(location) + '</span>');
    }

    if (c.year_founded) {
      lines.push('    <span><strong>Founded</strong> ' + esc(String(c.year_founded)) + '</span>');
    }

    if (c.size_range) {
      lines.push('    <span><strong>Size</strong> ' + esc(c.size_range) + '</span>');
    }

    if (typeof c.current_employee_estimate === "number") {
      lines.push('    <span><strong>Employees</strong> ' + c.current_employee_estimate.toLocaleString() + '</span>');
    }

    lines.push('  </div>');
    lines.push('</div>');

    return lines.join("\n");
  }

  function buildLocation(city, region, country) {
    return [city, region, country].filter(Boolean).join(", ");
  }

  // ── State helpers ─────────────────────────────────────────
  function showLoading(msg) {
    loading.textContent = msg || "Searching\u2026";
    loading.style.display = "inline";
    searchBtn.disabled = true;
    prevBtn.disabled = true;
    nextBtn.disabled = true;
  }

  function hideLoading() {
    loading.style.display = "none";
    loading.textContent = "Searching\u2026";
    searchBtn.disabled = false;
  }

  function renderPagination(total, page, pageSize) {
    if (!total || !pageSize) {
      pagination.style.display = "none";
      paginationStatus.textContent = "";
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      return;
    }

    var totalPages = Math.max(1, Math.ceil(total / pageSize));
    pagination.style.display = totalPages > 1 ? "flex" : "none";
    paginationStatus.textContent = "Page " + page + " of " + totalPages;
    prevBtn.disabled = page <= 1;
    nextBtn.disabled = page >= totalPages;
  }

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.style.display = "block";
  }

  function hideError() {
    errorBox.style.display = "none";
    errorBox.textContent = "";
  }

  function emptyStateHTML(heading, sub) {
    return (
      '<div class="empty-state"><strong>' +
      esc(heading) +
      "</strong><p>" +
      esc(sub) +
      "</p></div>"
    );
  }

  // ── DOM helpers ───────────────────────────────────────────
  function checkedValues(name) {
    return Array.from(form.querySelectorAll('input[name="' + name + '"]:checked')).map(function (el) {
      return el.dataset.key !== undefined ? el.dataset.key : el.value;
    });
  }

  function val(name) {
    var el = form.querySelector('[name="' + name + '"]');
    return el ? el.value.trim() : "";
  }

  function intVal(name) {
    var el = form.querySelector('[name="' + name + '"]');
    if (!el || el.value.trim() === "") return null;
    var n = parseInt(el.value, 10);
    return isNaN(n) ? null : n;
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();


  // ── DOM refs ──────────────────────────────────────────────
  const form        = document.getElementById("search-form");
  const searchBtn   = document.getElementById("search-btn");
  const clearBtn    = document.getElementById("clear-btn");
  const queryInput  = document.getElementById("query-input");
  const resultList  = document.getElementById("result-list");
  const resultCount = document.getElementById("result-count");
  const loading     = document.getElementById("loading-indicator");
  const errorBox    = document.getElementById("error-message");
  const pagination  = document.getElementById("pagination");
  const paginationStatus = document.getElementById("pagination-status");
  const prevBtn     = document.getElementById("pagination-prev");
  const nextBtn     = document.getElementById("pagination-next");

  var currentPage = 1;

  // ── Load facets on page load to populate industry checkboxes ──
  function loadIndustryFacets() {
    fetch(FACETS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (!data || !data.industry || !data.industry.length) return;
        var list = document.getElementById("industry-list");
        if (!list) return;
        list.innerHTML = data.industry.map(function (b) {
          var label = b.key.charAt(0).toUpperCase() + b.key.slice(1);
          var safeVal = JSON.stringify(b.key); // safely quoted, no HTML entity encoding
          return '<li><label><input type="checkbox" name="industry" data-key=' + safeVal + ' value=' + safeVal + ' />' + esc(label) + ' <span style="color:#9ca3af;font-size:11px">(' + b.count.toLocaleString() + ')</span></label></li>';
        }).join("");
      })
      .catch(function () { /* keep static fallback */ });
  }

  loadIndustryFacets();

  // ── Search trigger: form submit (Enter or Apply Filters) ──
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    currentPage = 1;
    runSearch(currentPage);
  });

  prevBtn.addEventListener("click", function () {
    if (prevBtn.disabled || currentPage <= 1) return;
    runSearch(currentPage - 1);
  });

  nextBtn.addEventListener("click", function () {
    if (nextBtn.disabled) return;
    runSearch(currentPage + 1);
  });

  // ── Clear All ─────────────────────────────────────────────
  clearBtn.addEventListener("click", function () {
    form.reset();
    currentPage = 1;
    resultList.innerHTML = emptyStateHTML("Enter a query or select filters, then press Enter or Apply Filters.", "Results will appear here.");
    resultCount.textContent = "";
    renderPagination(0, 1, 20);
    hideError();
  });

  // ── Core search ───────────────────────────────────────────
  function runSearch(page) {
    var body = buildRequestBody(page);
    showLoading();
    hideError();

    fetch(SEARCH_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (data) {
            throw new Error(data.detail || ("Request failed: " + res.status));
          });
        }
        return res.json();
      })
      .then(function (data) {
        currentPage = typeof data.page === "number" ? data.page : page;
        hideLoading();
        renderResults(data);
      })
      .catch(function (err) {
        hideLoading();
        showError("Search failed: " + (err.message || "unexpected error. Please try again."));
        resultList.innerHTML = "";
        resultCount.textContent = "";
      });
  }

  // ── Build POST body from form ─────────────────────────────
  function buildRequestBody(page) {
    var body = { page: page || 1 };

    var query = queryInput.value.trim();
    if (query) body.query = query;

    var industries = checkedValues("industry");
    if (industries.length) body.industry = industries;

    var sizes = checkedValues("size_range");
    if (sizes.length) body.size_range = sizes;

    var country = val("country");
    if (country) body.country = country;

    var city = val("city");
    if (city) body.city = city;

    var yearFrom = intVal("year_founded_gte");
    if (yearFrom !== null) body.year_founded_gte = yearFrom;

    var yearTo = intVal("year_founded_lte");
    if (yearTo !== null) body.year_founded_lte = yearTo;

    return body;
  }

  // ── Render ────────────────────────────────────────────────
  function renderResults(data) {
    var items = data.items || [];
    var total = typeof data.total === "number" ? data.total : items.length;
    var page = typeof data.page === "number" ? data.page : currentPage;
    var pageSize = typeof data.page_size === "number" ? data.page_size : items.length || 20;

    resultCount.textContent = total.toLocaleString() + " result" + (total !== 1 ? "s" : "") + " found";
    renderPagination(total, page, pageSize);

    if (!items.length) {
      resultList.innerHTML = emptyStateHTML(
        "No companies matched your search.",
        "Try adjusting your filters."
      );
      return;
    }

    resultList.innerHTML = items.map(cardHTML).join("");
  }

  function cardHTML(c) {
    var lines = [];

    lines.push('<div class="company-card">');
    lines.push('  <div class="card-name">' + esc(c.name) + '</div>');

    if (c.domain) {
      lines.push('  <div class="card-domain">' + esc(c.domain) + '</div>');
    }

    lines.push('  <div class="card-meta">');

    if (c.industry) {
      lines.push('    <span><strong>Industry</strong> ' + esc(c.industry) + '</span>');
    }

    var location = buildLocation(c.city, c.region, c.country);
    if (location) {
      lines.push('    <span><strong>Location</strong> ' + esc(location) + '</span>');
    }

    if (c.year_founded) {
      lines.push('    <span><strong>Founded</strong> ' + esc(String(c.year_founded)) + '</span>');
    }

    if (c.size_range) {
      lines.push('    <span><strong>Size</strong> ' + esc(c.size_range) + '</span>');
    }

    if (typeof c.current_employee_estimate === "number") {
      lines.push('    <span><strong>Employees</strong> ' + c.current_employee_estimate.toLocaleString() + '</span>');
    }

    lines.push('  </div>');
    lines.push('</div>');

    return lines.join("\n");
  }

  function buildLocation(city, region, country) {
    return [city, region, country].filter(Boolean).join(", ");
  }

  // ── State helpers ─────────────────────────────────────────
  function showLoading() {
    loading.style.display = "inline";
    searchBtn.disabled = true;
    prevBtn.disabled = true;
    nextBtn.disabled = true;
  }

  function hideLoading() {
    loading.style.display = "none";
    searchBtn.disabled = false;
  }

  function renderPagination(total, page, pageSize) {
    if (!total || !pageSize) {
      pagination.style.display = "none";
      paginationStatus.textContent = "";
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      return;
    }

    var totalPages = Math.max(1, Math.ceil(total / pageSize));
    pagination.style.display = totalPages > 1 ? "flex" : "none";
    paginationStatus.textContent = "Page " + page + " of " + totalPages;
    prevBtn.disabled = page <= 1;
    nextBtn.disabled = page >= totalPages;
  }

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.style.display = "block";
  }

  function hideError() {
    errorBox.style.display = "none";
    errorBox.textContent = "";
  }

  function emptyStateHTML(heading, sub) {
    return (
      '<div class="empty-state"><strong>' +
      esc(heading) +
      "</strong><p>" +
      esc(sub) +
      "</p></div>"
    );
  }

  // ── DOM helpers ───────────────────────────────────────────
  function checkedValues(name) {
    return Array.from(form.querySelectorAll('input[name="' + name + '"]:checked')).map(function (el) {
      // data-key holds the raw unescaped value for dynamically rendered checkboxes (e.g. industry)
      return el.dataset.key !== undefined ? el.dataset.key : el.value;
    });
  }

  function val(name) {
    var el = form.querySelector('[name="' + name + '"]');
    return el ? el.value.trim() : "";
  }

  function intVal(name) {
    var el = form.querySelector('[name="' + name + '"]');
    if (!el || el.value.trim() === "") return null;
    var n = parseInt(el.value, 10);
    return isNaN(n) ? null : n;
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
